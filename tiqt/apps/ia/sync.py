"""
Lógica compartilhada para alimentar a base de conhecimento a partir das
soluções de tickets (modelo core.Solucao).

Usada tanto pelo comando `importar_solucoes` (backfill do histórico) quanto
pelo signal que alimenta a base automaticamente a cada solução nova.
"""
from .models import BaseConhecimento


def sincronizar_solucao(solucao, min_chars=20):
    """
    Cria uma entrada na base de conhecimento a partir de uma Solucao.
    Retorna True se criou, False se ignorou (curta demais ou duplicada).
    """
    texto = (getattr(solucao, "texto", "") or "").strip()
    if len(texto) < min_chars:
        return False

    ticket = getattr(solucao, "ticket", None)
    if ticket is None:
        return False

    titulo = (ticket.titulo or f"Solução do ticket #{ticket.id}").strip()[:150]
    departamento = getattr(ticket, "departamento", None)

    # Evita duplicar a mesma solução
    if BaseConhecimento.objects.filter(titulo=titulo, solucao=texto).exists():
        return False

    BaseConhecimento.objects.create(
        titulo=titulo,
        descricao_problema=titulo,
        solucao=texto,
        departamento=departamento,
        ativo=True,
    )
    return True
