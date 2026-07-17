"""Filtro do Kanban por membro e 'Meus tickets' incluindo membro de card.

Chama KanbanView.get_context_data direto (via RequestFactory) para inspecionar
quais cards ficam visíveis, sem renderizar o template.
"""

import pytest
from django.test import RequestFactory

from tiqt.apps.core.models import (
    Cliente, Departamento, KanbanCard, KanbanColuna, KanbanQuadro, Prioridade,
    Situacao, Ticket, Tipo, User,
)
from tiqt.apps.core.views import KanbanView

pytestmark = pytest.mark.django_db


@pytest.fixture
def dep(db):
    return Departamento.objects.create(descricao='Suporte')


@pytest.fixture
def cliente(db):
    return Cliente.objects.create(fantasia='ACME', plano=None)


def make_ticket(dep, cliente, **kw):
    return Ticket.objects.create(
        departamento=dep, cliente=cliente,
        tipo=Tipo.objects.create(descricao='D', departamento=dep),
        prioridade=Prioridade.objects.create(descricao='N'),
        situacao=Situacao.objects.create(descricao='Nova'),
        titulo='t', **kw,
    )


def contexto(user, params):
    req = RequestFactory().get('/ticket/kanban/', params)
    req.user = user
    view = KanbanView()
    view.request = req
    view.kwargs = {}
    return view.get_context_data()


def cards_visiveis(ctx):
    ids = set()
    for col in ctx['colunas']:
        for card in getattr(col, 'lista', []):
            ids.add(card.id)
    return ids


@pytest.fixture
def board(db, dep):
    quadro = KanbanQuadro.objects.create(nome='Board')
    coluna = KanbanColuna.objects.create(quadro=quadro, nome='A fazer')
    return quadro, coluna


def test_filtro_por_membro_mostra_so_cards_daquele_membro(board, dep, cliente):
    quadro, coluna = board
    u1 = User.objects.create_user('a', password='x')
    c1 = KanbanCard.objects.create(coluna=coluna, ticket=make_ticket(dep, cliente))
    c2 = KanbanCard.objects.create(coluna=coluna, ticket=make_ticket(dep, cliente))
    c1.membros.add(u1)

    ctx = contexto(u1, {'quadro': quadro.id, 'membro': u1.id})
    vis = cards_visiveis(ctx)
    assert c1.id in vis
    assert c2.id not in vis


def test_meus_inclui_card_onde_sou_membro(board, dep, cliente):
    quadro, coluna = board
    u1 = User.objects.create_user('a', password='x')
    # ticket onde u1 NÃO é responsável nem atendente, mas é membro do card
    c1 = KanbanCard.objects.create(coluna=coluna, ticket=make_ticket(dep, cliente))
    c1.membros.add(u1)

    ctx = contexto(u1, {'quadro': quadro.id, 'meus': '1'})
    assert c1.id in cards_visiveis(ctx)


def test_meus_esconde_card_sem_vinculo(board, dep, cliente):
    quadro, coluna = board
    u1 = User.objects.create_user('a', password='x')
    u2 = User.objects.create_user('b', password='x')
    # ticket do u2, sem u1 como membro
    c1 = KanbanCard.objects.create(coluna=coluna, ticket=make_ticket(dep, cliente, responsavel=u2))

    ctx = contexto(u1, {'quadro': quadro.id, 'meus': '1'})
    assert c1.id not in cards_visiveis(ctx)


def test_meus_inclui_como_responsavel(board, dep, cliente):
    quadro, coluna = board
    u1 = User.objects.create_user('a', password='x')
    c1 = KanbanCard.objects.create(coluna=coluna, ticket=make_ticket(dep, cliente, responsavel=u1))

    ctx = contexto(u1, {'quadro': quadro.id, 'meus': '1'})
    assert c1.id in cards_visiveis(ctx)


def test_sem_filtro_mostra_tudo(board, dep, cliente):
    quadro, coluna = board
    u1 = User.objects.create_user('a', password='x')
    c1 = KanbanCard.objects.create(coluna=coluna, ticket=make_ticket(dep, cliente))
    c2 = KanbanCard.objects.create(coluna=coluna, ticket=make_ticket(dep, cliente))

    ctx = contexto(u1, {'quadro': quadro.id})
    vis = cards_visiveis(ctx)
    assert c1.id in vis and c2.id in vis
