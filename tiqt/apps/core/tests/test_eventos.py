"""Testes do histórico append-only de tickets.

Sem model_mommy de propósito: a lib não é instalada nem suporta Django moderno,
e os testes existentes que dependem dela não coletam. Aqui montamos os objetos
pelo ORM direto.
"""

import pytest

from tiqt.apps.core.models import (
    Cliente, Departamento, Prioridade, Situacao, Ticket, TicketEvento, Tipo, User,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(db):
    return User.objects.create_user(username='fulano', password='x')


@pytest.fixture
def outro_user(db):
    return User.objects.create_user(username='sicrano', password='x')


@pytest.fixture
def ticket(db):
    dep = Departamento.objects.create(descricao='Suporte')
    return Ticket.objects.create(
        departamento=dep,
        # plano=None explícito: o campo tem default=1, que não existe no banco de teste.
        cliente=Cliente.objects.create(fantasia='ACME', plano=None),
        tipo=Tipo.objects.create(descricao='Dúvida', departamento=dep),
        prioridade=Prioridade.objects.create(descricao='Normal'),
        situacao=Situacao.objects.create(descricao='Nova'),
        titulo='Teste',
    )


def eventos(ticket, tipo=None):
    qs = ticket.eventos.all()
    return qs.filter(tipo=tipo) if tipo is not None else qs


class TestEventosNaCriacao:
    def test_ticket_novo_grava_evento_criado(self, ticket):
        assert eventos(ticket, TicketEvento.CRIADO).count() == 1
        ev = eventos(ticket, TicketEvento.CRIADO).get()
        assert ev.ocorrido_em == ticket.criado_em
        assert ev.status_para == Ticket.ABERTO
        assert ev.estimado is False

    def test_save_seguinte_nao_duplica_criado(self, ticket):
        ticket.titulo = 'Outro'
        ticket.save()
        assert eventos(ticket, TicketEvento.CRIADO).count() == 1


class TestEventosDeTransicao:
    def test_iniciar_grava_evento(self, ticket, user):
        ticket.iniciar_atendimento(user, origem='detalhe')
        ev = eventos(ticket, TicketEvento.INICIADO).get()
        assert ev.usuario == user
        assert ev.status_de == Ticket.ABERTO
        assert ev.status_para == Ticket.EM_ATENDIMENTO
        assert ev.origem == 'detalhe'

    def test_encerrar_grava_evento(self, ticket, user):
        ticket.iniciar_atendimento(user)
        ticket.encerrar_atendimento(user, origem='kanban')
        ev = eventos(ticket, TicketEvento.ENCERRADO).get()
        assert ev.usuario == user
        assert ev.status_de == Ticket.EM_ATENDIMENTO
        assert ev.status_para == Ticket.ENCERRADO

    def test_encerrar_sem_user_nao_estoura(self, ticket):
        """A assinatura antiga (sem user) tem que continuar funcionando."""
        ticket.encerrar_atendimento()
        ev = eventos(ticket, TicketEvento.ENCERRADO).get()
        assert ev.usuario is None
        assert ticket.status == Ticket.ENCERRADO

    def test_cancelar_grava_evento(self, ticket, user):
        ticket.cancelar_atendimento(user)
        ev = eventos(ticket, TicketEvento.CANCELADO).get()
        assert ev.usuario == user
        assert ev.status_para == Ticket.CANCELADO


class TestReaberturaPreservaHistorico:
    """O bug que motiva a tabela inteira.

    reabrir() zera encerrado_em/cancelado_em no Ticket. Antes, isso apagava o
    fechamento para sempre. Agora o evento sobrevive numa linha própria.
    """

    def test_reabrir_preserva_o_encerrado_anterior(self, ticket, user):
        ticket.iniciar_atendimento(user)
        ticket.encerrar_atendimento(user)
        encerrado_em_original = ticket.encerrado_em

        ticket.reabrir(user)

        # o Ticket esqueceu...
        assert ticket.encerrado_em is None
        # ...mas o histórico não.
        ev = eventos(ticket, TicketEvento.ENCERRADO).get()
        assert ev.ocorrido_em == encerrado_em_original

    def test_reabrir_grava_evento_com_status_anterior(self, ticket, user):
        ticket.encerrar_atendimento(user)
        ticket.reabrir(user)
        ev = eventos(ticket, TicketEvento.REABERTO).get()
        assert ev.status_de == Ticket.ENCERRADO
        assert ev.status_para == Ticket.EM_ATENDIMENTO
        assert ev.usuario == user

    def test_ciclo_encerra_reabre_encerra_mantem_os_dois_fechamentos(self, ticket, user, outro_user):
        ticket.iniciar_atendimento(user)
        ticket.encerrar_atendimento(user)
        ticket.reabrir(outro_user)
        ticket.encerrar_atendimento(outro_user)

        assert eventos(ticket, TicketEvento.ENCERRADO).count() == 2
        assert eventos(ticket, TicketEvento.REABERTO).count() == 1
        # a timeline fica em ordem e com os autores certos
        tipos = list(ticket.eventos.values_list('tipo', flat=True))
        assert tipos == [TicketEvento.CRIADO, TicketEvento.INICIADO, TicketEvento.ENCERRADO,
                         TicketEvento.REABERTO, TicketEvento.ENCERRADO]

    def test_reabrir_cancelado_preserva_o_cancelamento(self, ticket, user):
        ticket.cancelar_atendimento(user)
        cancelado_em_original = ticket.cancelado_em
        ticket.reabrir(user)

        assert ticket.cancelado_em is None
        ev = eventos(ticket, TicketEvento.CANCELADO).get()
        assert ev.ocorrido_em == cancelado_em_original


class TestPoliticaSla:
    def test_sem_politica_devolve_none(self, ticket):
        from tiqt.apps.core.services.sla import politica_para
        assert politica_para(ticket) is None

    def test_escolhe_a_mais_especifica(self, ticket):
        from tiqt.apps.core.models import SlaPolitica
        from tiqt.apps.core.services.sla import politica_para

        SlaPolitica.objects.create(minutos_resposta=999, minutos_resolucao=999)  # curinga total
        SlaPolitica.objects.create(prioridade=ticket.prioridade, minutos_resposta=60, minutos_resolucao=480)
        especifica = SlaPolitica.objects.create(
            departamento=ticket.departamento, prioridade=ticket.prioridade,
            minutos_resposta=15, minutos_resolucao=120)

        assert politica_para(ticket) == especifica

    def test_curinga_vale_quando_nao_ha_especifica(self, ticket):
        from tiqt.apps.core.models import SlaPolitica
        from tiqt.apps.core.services.sla import politica_para

        global_ = SlaPolitica.objects.create(minutos_resposta=60, minutos_resolucao=480)
        assert politica_para(ticket) == global_

    def test_politica_inativa_e_ignorada(self, ticket):
        from tiqt.apps.core.models import SlaPolitica
        from tiqt.apps.core.services.sla import politica_para

        SlaPolitica.objects.create(departamento=ticket.departamento, prioridade=ticket.prioridade,
                                   minutos_resposta=15, minutos_resolucao=120, ativo=False)
        assert politica_para(ticket) is None
