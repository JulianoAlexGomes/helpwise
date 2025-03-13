from django_tables2 import Table, LinkColumn, A, tables
from .models import Ticket, User
from django.urls import reverse

class TicketTable(Table):
    id = LinkColumn('ticket_detail', args=[A('pk')])
    cliente = tables.Column(accessor='cliente.fantasia', verbose_name='Cliente')
    ultimo_comentario = tables.Column(accessor='ultimo_comentario', verbose_name='Último Comentário')
    solucao = tables.Column(accessor='get_solucao', verbose_name='Solução')
    # atendente = tables.Column(accessor='atendente.username', verbose_name='Atendente')

    class Meta:
        model = Ticket
        template_name = 'django_tables2/bootstrap.html'
        fields = ('id', 'tipo', 'prioridade', 'cliente', 'ultimo_comentario', 'solucao', 'responsavel')
        attrs = {'class': 'striped responsive-table'}