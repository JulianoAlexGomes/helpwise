from django_tables2 import Table, LinkColumn, A, tables
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