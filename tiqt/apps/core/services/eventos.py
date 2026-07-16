"""Registro do histórico de tickets (TicketEvento).

Chamado de dentro dos métodos de transição do Ticket, que são o único caminho
por onde status muda. Signal não serve aqui: post_save não sabe qual transição
ocorreu nem quem é o usuário, e dispararia à toa nos saves de reordenação do
Kanban.
"""

from django.utils import timezone


def registrar(ticket, tipo, *, usuario=None, status_de=None, origem='',
              ocorrido_em=None, estimado=False):
    from tiqt.apps.core.models import TicketEvento

    return TicketEvento.objects.create(
        ticket=ticket,
        tipo=tipo,
        usuario=usuario,
        status_de=status_de,
        status_para=ticket.status,
        origem=origem,
        estimado=estimado,
        ocorrido_em=ocorrido_em or timezone.now(),
    )
