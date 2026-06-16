"""Helpers para criar notificações in-app."""
from .models import Notification


def notificar(recipient, message, url=''):
    """Cria uma notificação para um usuário. Retorna None se não houver destinatário."""
    if recipient is None:
        return None
    return Notification.objects.create(
        recipient=recipient,
        message=message,
        url=url or '',
    )


def notificar_atribuicao(ticket, ator=None, notificar_ator=True):
    """
    Notifica o responsável e o atendente de um ticket de que ele foi atribuído a eles.
    Por padrão o próprio `ator` (quem cria/atribui) também é notificado quando se
    atribui — passe `notificar_ator=False` para silenciar a auto-notificação.
    Retorna a lista de notificações criadas.
    """
    destinatarios = {}
    if ticket.responsavel_id:
        destinatarios[ticket.responsavel_id] = ticket.responsavel
    if ticket.atendente_id:
        destinatarios[ticket.atendente_id] = ticket.atendente

    titulo = (ticket.titulo or '').strip()
    message = f"Novo ticket #{ticket.pk} atribuído a você"
    if titulo:
        message += f": {titulo}"
    url = f"/ticket/{ticket.pk}/"

    criadas = []
    for user_id, user in destinatarios.items():
        if not notificar_ator and ator is not None and user_id == ator.pk:
            continue
        criadas.append(notificar(user, message, url))
    return criadas
