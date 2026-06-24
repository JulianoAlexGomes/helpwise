"""Mantém a agenda em sincronia com o `proximo_contato` dos comentários.

Sempre que um comentário de ticket é salvo com um "próximo contato",
criamos/atualizamos um Agendamento de origem TICKET ligado a ele. Se o
próximo contato é removido, o agendamento correspondente é apagado.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from tiqt.apps.core.models import Comentario

from .models import Agendamento


@receiver(post_save, sender=Comentario, dispatch_uid='agenda_sync_proximo_contato')
def sincronizar_agendamento(sender, instance, **kwargs):
    comentario = instance

    # Sem próximo contato -> não deve existir agendamento ligado a este comentário.
    if not comentario.proximo_contato:
        Agendamento.objects.filter(comentario=comentario).delete()
        return

    ticket = comentario.ticket
    # Quem deve fazer o contato: o responsável do ticket, senão o autor do comentário.
    responsavel = ticket.responsavel or comentario.autor

    titulo = (ticket.titulo or '').strip() or f"Contato ticket #{ticket.pk}"

    defaults = {
        'titulo': titulo,
        'descricao': comentario.texto,
        'inicio': comentario.proximo_contato,
        'responsavel': responsavel,
        'origem': Agendamento.TICKET,
        'ticket': ticket,
        'cliente': ticket.cliente,
        'criado_por': comentario.autor,
    }

    agendamento = Agendamento.objects.filter(comentario=comentario).first()
    if agendamento is None:
        Agendamento.objects.create(comentario=comentario, **defaults)
        return

    # Atualiza dados; se a data mudou, reabilita a notificação.
    data_mudou = agendamento.inicio != comentario.proximo_contato
    for campo, valor in defaults.items():
        setattr(agendamento, campo, valor)
    if data_mudou and agendamento.status == Agendamento.PENDENTE:
        agendamento.notificado = False
    agendamento.save()
