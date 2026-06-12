"""
Alimenta a base de conhecimento automaticamente: toda vez que uma solução de
ticket é registrada (core.Solucao), cria a entrada correspondente na base.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from tiqt.apps.core.models import Solucao
from .sync import sincronizar_solucao

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Solucao, dispatch_uid="ia_alimentar_base")
def alimentar_base(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        sincronizar_solucao(instance)
    except Exception:
        # Nunca quebra o fechamento do ticket por causa da base da IA
        logger.exception("Falha ao alimentar a base de conhecimento da IA")
