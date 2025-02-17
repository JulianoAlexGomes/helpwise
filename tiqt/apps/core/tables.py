from django_tables2 import Table, LinkColumn, A, tables
from .models import Ticket
from django.urls import reverse

class TicketTable(Table):
    id = LinkColumn('ticket_detail', args=[A('pk')])
    cliente = tables.Column(accessor='cliente.fantasia', verbose_name='Cliente')
    ultimo_comentario = tables.Column(accessor='comentario_set.last.texto', verbose_name='Último Comentário')

    class Meta:
        model = Ticket
        template_name = 'django_tables2/bootstrap.html'
        fields = ('id','tipo','prioridade','status','cliente','ultimo_comentario','responsavel')
        attrs = {'class': 'striped responsive-table'}

    # def render(self):
    #     return '<a href="{}">{}</a>'.format(
    #         reverse('ticket_detail', args=[self.record.pk]),
    #         super().render()
    #     )