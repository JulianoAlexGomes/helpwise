from django_tables2 import Table, LinkColumn, A, tables, CheckBoxColumn
from django.utils.html import format_html
from .models import Ticket, User
from django.urls import reverse

# (cor do texto, cor de fundo suave) por status
STATUS_STYLES = {
    Ticket.ABERTO:         ('#00897b', 'rgba(0,150,136,.14)'),
    Ticket.EM_ATENDIMENTO: ('#ef6c00', 'rgba(245,124,0,.16)'),
    Ticket.ENCERRADO:      ('#2e7d32', 'rgba(76,175,80,.18)'),
    Ticket.CANCELADO:      ('#e53935', 'rgba(229,57,53,.13)'),
}

class StatusColumn(tables.Column):
    def render(self, value, record):  # noqa: ARG002
        color, bg = STATUS_STYLES.get(record.status, ('#6b7280', 'rgba(120,124,130,.16)'))
        label = record.get_status_display()
        return format_html(
            '<span style="background:{};color:{};padding:4px 11px;'
            'border-radius:20px;font-size:11.5px;font-weight:700;'
            'white-space:nowrap">{}</span>',
            bg, color, label
        )


class GrupoColumn(tables.Column):
    """Indicador discreto de agrupamento + botão de agrupar.

    Sem grupo: um ícone 'Agrupar'. Com grupo: um chip 'link N' que mostra os #ids
    irmãos no tooltip. Os data-* alimentam o modal de agrupar no template."""

    def render(self, record):
        cliente_nome = ''
        if record.cliente_id:
            cliente_nome = record.cliente.fantasia or str(record.cliente)
        attrs = format_html(
            'data-ticket-id="{}" data-cliente-id="{}" data-cliente-nome="{}"',
            record.pk, record.cliente_id or '', cliente_nome)
        grupo = record.grupo
        if grupo:
            membros = [t.pk for t in grupo.tickets.all()]
            irmaos = ', '.join('#%s' % p for p in membros if p != record.pk) or '—'
            return format_html(
                '<button type="button" class="tkl-grp-chip js-agrupar" {attrs} '
                'data-grupo-id="{gid}" title="Agrupado com {irmaos}">'
                '<i class="material-icons" translate="no">link</i>{n}</button>',
                attrs=attrs, gid=grupo.pk, irmaos=irmaos, n=len(membros))
        return format_html(
            '<button type="button" class="tkl-grp-add js-agrupar" {attrs} '
            'title="Agrupar com outro ticket deste cliente">'
            '<i class="material-icons" translate="no">add_link</i></button>',
            attrs=attrs)

class TicketTable(Table):
    id = LinkColumn('ticket_detail', args=[A('pk')])
    atendente = tables.Column(accessor='atendente.get_full_name', verbose_name='Atendente')
    cliente = tables.Column(accessor='cliente.fantasia', verbose_name='Cliente')
    status = StatusColumn(verbose_name='Status')

    class Meta:
        model = Ticket
        template_name = 'django_tables2/table.html'
        fields = ('id', 'atendente', 'titulo', 'tipo', 'prioridade', 'cliente', 'responsavel', 'status')
        attrs = {'class': 'hw-table'}
        paginate_by = None


class MeusTicketsTable(TicketTable):
    """Tabela de 'Meus tickets': igual à padrão, mais a coluna de seleção em lote.

    É uma subclasse justamente para os checkboxes NÃO vazarem para as outras 6
    listagens (Encerrados, Cancelados, Todos...), que compartilham a TicketTable.
    """

    selecao = CheckBoxColumn(
        accessor='pk',
        verbose_name='',
        orderable=False,
        attrs={
            'th__input': {'class': 'js-sel-todos', 'title': 'Selecionar todos'},
            'td__input': {'class': 'js-sel-ticket'},
        },
    )
    # Agrupamento de tickets do mesmo cliente (indicador + botão Agrupar)
    grupo = GrupoColumn(accessor='pk', verbose_name='Grupo', orderable=False)

    class Meta(TicketTable.Meta):
        fields = ('selecao',) + TicketTable.Meta.fields + ('grupo',)
        sequence = ('selecao', '...', 'grupo')
        # O <tr> carrega id/status/título: o JS monta o modal de encerramento a
        # partir da linha, e precisa saber quem está Aberto (0) — esses serão
        # iniciados em seu nome antes de encerrar.
        row_attrs = {
            'data-ticket-id': lambda record: record.pk,
            'data-status': lambda record: record.status,
            'data-titulo': lambda record: record.titulo or '(sem título)',
            # data-dev: ticket que JÁ É CARD num quadro de Desenvolvimento não pode
            # ser encerrado por aqui (quem encerra é o time de dev). Vem da anotação
            # `no_quadro_dev` (Exists) na MyTicketsView. O backend também barra.
            'data-dev': lambda record: '1' if getattr(record, 'no_quadro_dev', False) else '0',
            # Agrupamento: o JS colapsa os membros de um mesmo grupo num único campo
            # de solução no modal de encerrar.
            'data-grupo-id': lambda record: record.grupo_id or '',
            'data-grupo-membros': lambda record: (
                ','.join(str(t.pk) for t in record.grupo.tickets.all()) if record.grupo_id else ''
            ),
        }