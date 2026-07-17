"""Testes do agrupamento de tickets (mesmo cliente, solução compartilhada).

Objetos montados pelo ORM direto (sem model_mommy), como nos demais testes.
"""

import pytest

from tiqt.apps.core.models import (
    Cliente, Departamento, KanbanCard, KanbanColuna, KanbanQuadro, Prioridade,
    Situacao, Ticket, TicketGrupo, Tipo, User,
)
from tiqt.apps.core.views import _encerrar_grupo

pytestmark = pytest.mark.django_db


@pytest.fixture
def dep(db):
    return Departamento.objects.create(descricao='Suporte')


@pytest.fixture
def user(db):
    return User.objects.create_user(username='fulano', password='x')


@pytest.fixture
def cliente(db):
    return Cliente.objects.create(fantasia='ACME', plano=None)


@pytest.fixture
def outro_cliente(db):
    return Cliente.objects.create(fantasia='Globex', plano=None)


def make_ticket(dep, cliente, user=None, titulo='T', status=Ticket.EM_ATENDIMENTO):
    t = Ticket.objects.create(
        departamento=dep,
        cliente=cliente,
        tipo=Tipo.objects.create(descricao='Dúvida', departamento=dep),
        prioridade=Prioridade.objects.create(descricao='Normal'),
        situacao=Situacao.objects.create(descricao='Nova'),
        titulo=titulo,
        responsavel=user,
    )
    if status != Ticket.ABERTO:
        t.status = status
        t.iniciado_em = t.criado_em
        t.save()
    return t


def em_grupo(cliente, *tickets):
    grupo = TicketGrupo.objects.create(cliente=cliente)
    Ticket.objects.filter(pk__in=[t.pk for t in tickets]).update(grupo=grupo)
    for t in tickets:
        t.refresh_from_db()
    return grupo


class TestAgrupar:
    def test_agrupa_tickets_do_mesmo_cliente(self, client, user, dep, cliente):
        a = make_ticket(dep, cliente, user)
        b = make_ticket(dep, cliente, user)
        client.force_login(user)
        resp = client.post('/ticket/grupo/agrupar/', {'ticket_id': a.pk, 'ids': [b.pk]})
        assert resp.status_code == 200
        a.refresh_from_db(); b.refresh_from_db()
        assert a.grupo_id is not None
        assert a.grupo_id == b.grupo_id
        assert a.grupo.cliente_id == cliente.pk

    def test_rejeita_clientes_diferentes(self, client, user, dep, cliente, outro_cliente):
        a = make_ticket(dep, cliente, user)
        b = make_ticket(dep, outro_cliente, user)
        client.force_login(user)
        resp = client.post('/ticket/grupo/agrupar/', {'ticket_id': a.pk, 'ids': [b.pk]})
        assert resp.status_code == 400
        b.refresh_from_db()
        assert b.grupo_id is None

    def test_junta_no_grupo_existente_do_ancora(self, client, user, dep, cliente):
        a = make_ticket(dep, cliente, user)
        b = make_ticket(dep, cliente, user)
        c = make_ticket(dep, cliente, user)
        grupo = em_grupo(cliente, a, b)
        client.force_login(user)
        resp = client.post('/ticket/grupo/agrupar/', {'ticket_id': a.pk, 'ids': [c.pk]})
        assert resp.status_code == 200
        c.refresh_from_db()
        assert c.grupo_id == grupo.pk


class TestDesagrupar:
    def test_desagrupar_dissolve_grupo_pequeno(self, client, user, dep, cliente):
        a = make_ticket(dep, cliente, user)
        b = make_ticket(dep, cliente, user)
        grupo = em_grupo(cliente, a, b)
        client.force_login(user)
        resp = client.post('/ticket/grupo/desagrupar/', {'ticket_id': a.pk})
        assert resp.status_code == 200
        a.refresh_from_db(); b.refresh_from_db()
        # a sai; b ficaria sozinho, então o grupo é desfeito e b também fica solto
        assert a.grupo_id is None
        assert b.grupo_id is None
        assert not TicketGrupo.objects.filter(pk=grupo.pk).exists()

    def test_desagrupar_mantem_grupo_com_2_ou_mais(self, client, user, dep, cliente):
        a = make_ticket(dep, cliente, user)
        b = make_ticket(dep, cliente, user)
        c = make_ticket(dep, cliente, user)
        grupo = em_grupo(cliente, a, b, c)
        client.force_login(user)
        client.post('/ticket/grupo/desagrupar/', {'ticket_id': a.pk})
        a.refresh_from_db(); b.refresh_from_db(); c.refresh_from_db()
        assert a.grupo_id is None
        assert b.grupo_id == grupo.pk and c.grupo_id == grupo.pk
        assert TicketGrupo.objects.filter(pk=grupo.pk).exists()


class TestEncerrarGrupo:
    def test_mesma_solucao_encerra_todos_e_dissolve(self, user, dep, cliente):
        a = make_ticket(dep, cliente, user)
        b = make_ticket(dep, cliente, user)
        c = make_ticket(dep, cliente, user)
        grupo = em_grupo(cliente, a, b, c)

        encerrados, ignorados = _encerrar_grupo(a, 'resolvido', user, 'teste')

        assert set(encerrados) == {a.pk, b.pk, c.pk}
        assert ignorados == []
        for t in (a, b, c):
            t.refresh_from_db()
            assert t.status == Ticket.ENCERRADO
            assert t.solucao_set.count() == 1
            assert t.solucao_set.first().texto == 'resolvido'
        # todos encerrados → grupo perde o sentido e é desfeito
        assert not TicketGrupo.objects.filter(pk=grupo.pk).exists()

    def test_ticket_solto_encerra_so_ele(self, user, dep, cliente):
        a = make_ticket(dep, cliente, user)
        encerrados, ignorados = _encerrar_grupo(a, 'ok', user, 'teste')
        assert encerrados == [a.pk]
        a.refresh_from_db()
        assert a.status == Ticket.ENCERRADO

    def test_membro_no_quadro_dev_e_pulado(self, user, dep, cliente):
        a = make_ticket(dep, cliente, user)
        b = make_ticket(dep, cliente, user)
        em_grupo(cliente, a, b)

        # b vira card num quadro de Desenvolvimento — quem encerra é o time de dev
        depdev = Departamento.objects.create(descricao='Desenvolvimento')
        quadro = KanbanQuadro.objects.create(nome='Dev', departamento_entrada=depdev)
        coluna = KanbanColuna.objects.create(quadro=quadro, nome='A fazer')
        KanbanCard.objects.create(coluna=coluna, ticket=b)

        a.refresh_from_db()
        encerrados, ignorados = _encerrar_grupo(a, 'ok', user, 'teste')

        assert a.pk in encerrados
        assert b.pk not in encerrados
        b.refresh_from_db()
        assert b.status != Ticket.ENCERRADO
        assert any(i['id'] == b.pk for i in ignorados)


class TestDissolverSePequeno:
    def test_dissolve_quando_menos_de_dois(self, dep, cliente):
        a = make_ticket(dep, cliente)
        grupo = em_grupo(cliente, a)   # só 1 membro
        assert grupo.dissolver_se_pequeno() is True
        assert not TicketGrupo.objects.filter(pk=grupo.pk).exists()

    def test_mantem_com_dois(self, dep, cliente):
        a = make_ticket(dep, cliente)
        b = make_ticket(dep, cliente)
        grupo = em_grupo(cliente, a, b)
        assert grupo.dissolver_se_pequeno() is False
        assert TicketGrupo.objects.filter(pk=grupo.pk).exists()
