"""Métricas de atendimento a partir do histórico de eventos.

Tudo aqui sai de TicketEvento, não dos timestamps do Ticket: `reabrir()` zera
`encerrado_em`, então o Ticket não sabe o próprio passado. Ver [[TicketEvento]].

ATENÇÃO ao ler qualquer número daqui: eventos com estimado=True foram
reconstruídos pelo backfill a partir das Soluções e dos timestamps que
sobreviveram. Eles SUBCONTAM reaberturas antigas e portanto SUPERESTIMAM a
performance. `conformidade()` devolve `estimado_pct` justamente para o relatório
poder dizer isso na cara do leitor.
"""

from collections import defaultdict
from statistics import median

from django.utils import timezone

from ..models import Ticket, TicketEvento
from . import sla


def _marcos(ticket):
    """Primeiro CRIADO / primeiro INICIADO / ÚLTIMO ENCERRADO de um ticket.

    O último encerramento, e não o primeiro: um ticket reaberto e fechado de
    novo terminou de verdade na segunda vez.
    """
    criado = iniciado = encerrado = None
    estimado = False
    for e in ticket.eventos.all():   # já ordenado por ocorrido_em no Meta
        if e.tipo == TicketEvento.CRIADO and criado is None:
            criado = e.ocorrido_em
        elif e.tipo == TicketEvento.INICIADO and iniciado is None:
            iniciado = e.ocorrido_em
            estimado = estimado or e.estimado
        elif e.tipo == TicketEvento.ENCERRADO:
            encerrado = e.ocorrido_em
            estimado = estimado or e.estimado
    return criado, iniciado, encerrado, estimado


def _pct(parte, total):
    """None quando não há denominador — e não 0.0.

    '0%' de SLA lê-se como "todos furaram a meta"; a verdade, quando nada foi
    medido, é "não há dado". São coisas opostas e o relatório não pode confundi-las.
    """
    return round(100.0 * parte / total, 1) if total else None


def coletar(qs, cal=None):
    """Calcula os tempos úteis de cada ticket uma única vez.

    As funções de relatório consomem esta lista em vez de recalcular — o cálculo
    de minutos úteis itera dia a dia e é a parte cara.
    """
    cal = cal or sla.carregar_calendario()
    linhas = []
    qs = (qs.select_related('departamento', 'prioridade', 'responsavel', 'tipo__departamento')
            .prefetch_related('eventos'))
    for t in qs:
        criado, iniciado, encerrado, estimado = _marcos(t)
        if not criado:
            continue
        politica = sla.politica_para(t)
        linhas.append({
            'ticket': t,
            'criado': criado,
            'resposta_min': sla.minutos_uteis(criado, iniciado, cal) if iniciado and iniciado > criado else None,
            'resolucao_min': sla.minutos_uteis(criado, encerrado, cal) if encerrado and encerrado > criado else None,
            'meta_resposta': politica.minutos_resposta if politica else None,
            'meta_resolucao': politica.minutos_resolucao if politica else None,
            'estimado': estimado,
        })
    return linhas


def _agrega(linhas):
    resp = [l['resposta_min'] for l in linhas if l['resposta_min'] is not None]
    resol = [l['resolucao_min'] for l in linhas if l['resolucao_min'] is not None]

    dentro_resp = sum(1 for l in linhas
                      if l['resposta_min'] is not None and l['meta_resposta']
                      and l['resposta_min'] <= l['meta_resposta'])
    com_meta_resp = sum(1 for l in linhas if l['resposta_min'] is not None and l['meta_resposta'])

    dentro_resol = sum(1 for l in linhas
                       if l['resolucao_min'] is not None and l['meta_resolucao']
                       and l['resolucao_min'] <= l['meta_resolucao'])
    com_meta_resol = sum(1 for l in linhas if l['resolucao_min'] is not None and l['meta_resolucao'])

    return {
        'total': len(linhas),
        'respondidos': len(resp),
        'resolvidos': len(resol),
        'resposta_mediana': int(median(resp)) if resp else None,
        'resolucao_mediana': int(median(resol)) if resol else None,
        'sla_resposta_pct': _pct(dentro_resp, com_meta_resp),
        'sla_resolucao_pct': _pct(dentro_resol, com_meta_resol),
        'estimado_pct': _pct(sum(1 for l in linhas if l['estimado']), len(linhas)),
    }


def conformidade(linhas, por='departamento'):
    """% dentro da meta e tempos medianos, agrupado por departamento, prioridade ou tipo."""
    def chave_de(t):
        if por == 'departamento':
            return t.departamento.descricao if t.departamento_id else 'Sem departamento'
        if por == 'prioridade':
            return t.prioridade.descricao if t.prioridade_id else 'Sem prioridade'
        if por == 'tipo':
            # O tipo pertence a um departamento e os nomes se repetem entre eles
            # ("Implantação" existe no Suporte e é um departamento também), então
            # o rótulo carrega o departamento para não fundir grupos distintos.
            if not t.tipo_id:
                return 'Sem tipo'
            dep = t.tipo.departamento.descricao if t.tipo.departamento_id else '?'
            return f'{dep} › {t.tipo.descricao}'
        raise ValueError(f'agrupamento desconhecido: {por}')

    grupos = defaultdict(list)
    for l in linhas:
        grupos[chave_de(l['ticket'])].append(l)

    out = [dict(grupo=k, **_agrega(v)) for k, v in grupos.items()]
    out.sort(key=lambda d: -d['total'])
    return out


def geral(linhas):
    return _agrega(linhas)


def produtividade(linhas):
    """Por atendente. Só faz sentido para a Diretoria.

    RESSALVA que precisa acompanhar o número: para o histórico reconstruído, o
    ticket é atribuído ao responsável ATUAL, não a quem de fato atendeu — a troca
    de responsável nunca foi registrada. Ver `estimado_pct`.
    """
    grupos = defaultdict(list)
    for l in linhas:
        r = l['ticket'].responsavel
        nome = (r.get_full_name() or r.username) if r else 'Sem responsável'
        grupos[nome].append(l)

    out = []
    for nome, v in grupos.items():
        a = _agrega(v)
        out.append({'atendente': nome, **a})
    out.sort(key=lambda d: -d['resolvidos'])
    return out


def volume_semanal(qs, semanas=12):
    """Entradas x saídas por semana. Mostra se a fila cresce ou encolhe.

    Agrupa em Python, e não com TruncWeek/__date no banco: o MySQL daqui não tem
    as tabelas de timezone instaladas, então as funções de data do banco estouram
    ("Are time zone definitions for your database installed?"). É o mesmo motivo
    pelo qual a HomeView usa Counter. Ver [[frontend-gotchas]].
    """
    from collections import Counter
    from datetime import timedelta

    corte = timezone.now() - timedelta(weeks=semanas)
    ids = list(qs.values_list('id', flat=True))
    if not ids:
        return []

    def serie(tipo):
        dts = (TicketEvento.objects
               .filter(ticket_id__in=ids, tipo=tipo, ocorrido_em__gte=corte)
               .values_list('ocorrido_em', flat=True))
        # Segunda-feira da semana de cada evento, no fuso local.
        return Counter(
            (lambda d: d - timedelta(days=d.weekday()))(timezone.localtime(dt).date())
            for dt in dts
        )

    entradas = serie(TicketEvento.CRIADO)
    saidas = serie(TicketEvento.ENCERRADO)

    out = []
    for semana in sorted(set(entradas) | set(saidas)):
        e, s = entradas.get(semana, 0), saidas.get(semana, 0)
        out.append({'semana': semana, 'entradas': e, 'saidas': s, 'saldo': e - s})
    return out


def divida(dias=7, qs=None):
    """Tickets parados: abertos/em atendimento há mais de `dias`.

    Lista de ação, não de gestão — é o que precisa de faxina.
    """
    corte = timezone.now() - timezone.timedelta(days=dias)
    base = qs if qs is not None else Ticket.objects.all()
    parados = (base.filter(status__in=[Ticket.ABERTO, Ticket.EM_ATENDIMENTO],
                           criado_em__lt=corte)
               .select_related('departamento', 'cliente', 'responsavel', 'prioridade')
               .order_by('criado_em'))

    agora = timezone.now()
    return [{
        'id': t.id,
        'titulo': t.titulo or f'Ticket #{t.id}',
        'cliente': t.cliente.fantasia if t.cliente_id else '',
        'departamento': t.departamento.descricao if t.departamento_id else '',
        'prioridade': t.prioridade.descricao if t.prioridade_id else '',
        'responsavel': (t.responsavel.get_full_name() or t.responsavel.username) if t.responsavel_id else '— ninguém pegou',
        'status': t.get_status_display(),
        'idade_dias': (agora - t.criado_em).days,
    } for t in parados]
