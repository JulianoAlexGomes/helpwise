"""Reconstrói o histórico de tickets anterior ao TicketEvento.

Não é data migration de propósito: pytest.ini roda com --nomigrations, então uma
data migration nunca seria exercitada por teste algum e estrearia direto em
produção. Aqui você tem --dry-run, --limit, e escolhe a hora de rodar.

Idempotente: tudo que ele grava tem origem='backfill', e ele apaga o que gravou
antes de gravar de novo. Eventos reais (origem != 'backfill') nunca são tocados.

LIMITAÇÕES — leia antes de confiar nos números:
  * Reaberturas antigas (anteriores ao comentário automático "Ticket reaberto")
    não deixaram rastro nenhum. São invisíveis.
  * Cancelamentos que foram reabertos: cancelado_em foi zerado e cancelar não
    cria Solucao. Perdidos por completo.
  * Encerramentos recuperam o INSTANTE (via Solucao), mas a ordem exata
    intercalada com reaberturas é inferida por timestamp, não observada.
  * Troca de responsável/prioridade/departamento nunca foi registrada.
Consequência: o passado reconstruído SUBCONTA reaberturas, e portanto
SUPERESTIMA a performance. Filtre estimado=False para o número duro.
"""

from django.core.management.base import BaseCommand
from django.db.models import Count

from tiqt.apps.core.models import Comentario, Solucao, Ticket, TicketEvento

TOLERANCIA_DEDUP_SEG = 120


class Command(BaseCommand):
    help = 'Reconstrói TicketEvento a partir dos timestamps e das Soluções existentes.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Só conta o que faria, sem gravar nada.')
        parser.add_argument('--limit', type=int, default=None,
                            help='Processa só os N tickets mais recentes (para conferir antes de valer).')
        parser.add_argument('--batch', type=int, default=1000,
                            help='Tamanho do lote de insert (default 1000).')

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        limit = opts['limit']
        batch = opts['batch']

        tickets = Ticket.objects.all().order_by('-id')
        if limit:
            tickets = tickets[:limit]
        ids = list(tickets.values_list('id', flat=True))

        self.stdout.write(f'Tickets a processar: {len(ids)}')

        if not dry:
            # Reexecutável: limpa só o que este command gravou antes.
            apagados, _ = TicketEvento.objects.filter(
                origem='backfill', ticket_id__in=ids).delete()
            if apagados:
                self.stdout.write(f'Removidos {apagados} eventos de backfill anteriores.')

        eventos = []
        eventos += self._criados(ids)
        eventos += self._iniciados(ids)
        encerrados = self._encerrados_por_solucao(ids)
        eventos += encerrados
        eventos += self._encerrados_orfaos(ids, encerrados)
        eventos += self._cancelados(ids)
        eventos += self._reaberturas(ids)

        self._resumo(eventos)

        if dry:
            self.stdout.write(self.style.WARNING('\n--dry-run: nada foi gravado.'))
            return

        TicketEvento.objects.bulk_create(eventos, batch_size=batch)
        self.stdout.write(self.style.SUCCESS(f'\n{len(eventos)} eventos gravados.'))
        self.stdout.write(
            'Lembre: estes eventos são estimado=True. Os números confiáveis '
            'começam a partir de agora, com os eventos gravados em tempo real.'
        )

    def _ev(self, ticket_id, tipo, ocorrido_em, usuario_id=None, status_para=None, estimado=True):
        return TicketEvento(
            ticket_id=ticket_id, tipo=tipo, ocorrido_em=ocorrido_em,
            usuario_id=usuario_id, status_para=status_para,
            origem='backfill', estimado=estimado,
        )

    def _criados(self, ids):
        """Exato: criado_em nunca é sobrescrito por nada."""
        vals = Ticket.objects.filter(id__in=ids, criado_em__isnull=False).values('id', 'criado_em')
        return [self._ev(v['id'], TicketEvento.CRIADO, v['criado_em'],
                         status_para=Ticket.ABERTO, estimado=False) for v in vals]

    def _iniciados(self, ids):
        """iniciado_em é exato; o autor é aproximado (responsavel pode ter mudado)."""
        vals = (Ticket.objects.filter(id__in=ids, iniciado_em__isnull=False)
                .values('id', 'iniciado_em', 'responsavel_id'))
        return [self._ev(v['id'], TicketEvento.INICIADO, v['iniciado_em'],
                         usuario_id=v['responsavel_id'], status_para=Ticket.EM_ATENDIMENTO)
                for v in vals]

    def _encerrados_por_solucao(self, ids):
        """A Solucao é a fonte canônica dos encerramentos.

        Ela é criada no mesmo request, logo antes de encerrar_atendimento(), e
        SOBREVIVE ao reabrir() — que zera encerrado_em. É o que permite recuperar
        fechamentos que o Ticket já esqueceu.
        """
        vals = (Solucao.objects.filter(ticket_id__in=ids)
                .values('ticket_id', 'criado_em', 'autor_id').order_by('criado_em'))
        return [self._ev(v['ticket_id'], TicketEvento.ENCERRADO, v['criado_em'],
                         usuario_id=v['autor_id'], status_para=Ticket.ENCERRADO)
                for v in vals]

    def _encerrados_orfaos(self, ids, ja_gerados):
        """Ticket encerrado sem Solucao nenhuma — encerrado por fora do fluxo normal."""
        por_ticket = {}
        for ev in ja_gerados:
            por_ticket.setdefault(ev.ticket_id, []).append(ev.ocorrido_em)

        vals = Ticket.objects.filter(id__in=ids, encerrado_em__isnull=False).values('id', 'encerrado_em')
        out = []
        for v in vals:
            perto = any(abs((v['encerrado_em'] - dt).total_seconds()) < TOLERANCIA_DEDUP_SEG
                        for dt in por_ticket.get(v['id'], []))
            if not perto:
                out.append(self._ev(v['id'], TicketEvento.ENCERRADO, v['encerrado_em'],
                                    status_para=Ticket.ENCERRADO))
        return out

    def _cancelados(self, ids):
        vals = (Ticket.objects.filter(id__in=ids, cancelado_em__isnull=False)
                .values('id', 'cancelado_em', 'cancelado_id'))
        return [self._ev(v['id'], TicketEvento.CANCELADO, v['cancelado_em'],
                         usuario_id=v['cancelado_id'], status_para=Ticket.CANCELADO)
                for v in vals]

    def _reaberturas(self, ids):
        """Best-effort: o único rastro é o comentário automático de reabertura.

        Reaberturas anteriores a esse comentário existir são irrecuperáveis.
        """
        vals = (Comentario.objects
                .filter(ticket_id__in=ids, texto__startswith='Ticket reaberto (estava')
                .values('ticket_id', 'criado_em', 'autor_id'))
        return [self._ev(v['ticket_id'], TicketEvento.REABERTO, v['criado_em'],
                         usuario_id=v['autor_id'])
                for v in vals]

    def _resumo(self, eventos):
        nomes = dict(TicketEvento.TIPOS)
        contagem = {}
        for ev in eventos:
            contagem[ev.tipo] = contagem.get(ev.tipo, 0) + 1

        self.stdout.write('\nEventos por tipo:')
        for tipo, n in sorted(contagem.items()):
            self.stdout.write(f'  {nomes[tipo]:<22} {n}')

        exatos = sum(1 for e in eventos if not e.estimado)
        self.stdout.write(f'\n  exatos (estimado=False):  {exatos}')
        self.stdout.write(f'  estimados:                {len(eventos) - exatos}')
        self.stdout.write(f'  TOTAL:                    {len(eventos)}')

        orfaos = Ticket.objects.filter(encerrado_em__isnull=False).annotate(
            n=Count('solucao')).filter(n=0).count()
        if orfaos:
            self.stdout.write(self.style.WARNING(
                f'\n  {orfaos} ticket(s) encerrado(s) sem Solucao — autor do encerramento desconhecido.'))
