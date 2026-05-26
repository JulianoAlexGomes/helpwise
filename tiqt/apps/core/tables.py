from django_tables2 import Table, LinkColumn, A, tables
from django.utils.html import format_html
from .models import Ticket, User
from django.urls import reverse

STATUS_COLORS = {
    Ticket.ABERTO:         '#009688',
    Ticket.EM_ATENDIMENTO: '#ff9800',
    Ticket.ENCERRADO:      '#4caf50',
    Ticket.CANCELADO:      '#e53935',
}

class StatusColumn(tables.Column):
    def render(self, value, record):  # noqa: ARG002
        color = STATUS_COLORS.get(record.status, '#9e9e9e')
        label = record.get_status_display()
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;'
            'border-radius:12px;font-size:11px;font-weight:600;'
            'white-space:nowrap">{}</span>',
            color, label
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
        attrs = {'class': 'striped responsive-table'}
        paginate_by = None