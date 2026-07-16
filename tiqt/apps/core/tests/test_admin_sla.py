"""Testes do cadastro de SLA no admin.

O modelo guarda MINUTOS ÚTEIS (é o que o cálculo usa), mas ninguém deveria
precisar saber que 2352min são 4 dias. O form traduz na entrada e na saída.
"""

from datetime import time

import pytest

from tiqt.apps.core.admin import SlaPoliticaForm, _legivel
from tiqt.apps.core.models import Departamento, Expediente, Prioridade, SlaPolitica

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def limpa_cache():
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def expediente(db):
    """Seg-sex 08:00-18:00 = 600 min/dia útil."""
    for dia in range(5):
        Expediente.objects.create(dia_semana=dia, hora_inicio=time(8, 0), hora_fim=time(18, 0))


def preenche(**kw):
    dados = {'resposta_dias': 0, 'resposta_horas': 0, 'resposta_minutos': 0,
             'resolucao_dias': 0, 'resolucao_horas': 0, 'resolucao_minutos': 0,
             'ativo': True}
    dados.update(kw)
    return dados


class TestCadastroEmDiasEHoras:
    def test_dias_viram_minutos_do_expediente(self, expediente):
        """1 dia = 600 min (o expediente), não 1440."""
        f = SlaPoliticaForm(preenche(resposta_dias=1, resolucao_dias=5))
        assert f.is_valid(), f.errors
        obj = f.save()
        assert obj.minutos_resposta == 600
        assert obj.minutos_resolucao == 3000

    def test_dias_e_horas_somam(self, expediente):
        f = SlaPoliticaForm(preenche(resposta_dias=2, resposta_horas=3, resolucao_dias=5))
        assert f.is_valid(), f.errors
        assert f.save().minutos_resposta == 2 * 600 + 180

    def test_so_horas(self, expediente):
        f = SlaPoliticaForm(preenche(resposta_horas=4, resolucao_horas=8))
        assert f.is_valid(), f.errors
        obj = f.save()
        assert obj.minutos_resposta == 240
        assert obj.minutos_resolucao == 480

    def test_so_minutos(self, expediente):
        """Meta de 30min: sem o campo de minutos isso era impossível de cadastrar."""
        f = SlaPoliticaForm(preenche(resposta_minutos=30, resolucao_horas=2))
        assert f.is_valid(), f.errors
        assert f.save().minutos_resposta == 30

    def test_dias_horas_e_minutos_somam(self, expediente):
        f = SlaPoliticaForm(preenche(resposta_dias=1, resposta_horas=2, resposta_minutos=27,
                                     resolucao_dias=5))
        assert f.is_valid(), f.errors
        assert f.save().minutos_resposta == 600 + 120 + 27

    def test_editar_decompoe_os_minutos_de_volta(self, expediente):
        """Reabrir a política tem que mostrar 2d 3h, não 1380."""
        pol = SlaPolitica.objects.create(minutos_resposta=1380, minutos_resolucao=3000)
        f = SlaPoliticaForm(instance=pol)
        assert f.fields['resposta_dias'].initial == 2
        assert f.fields['resposta_horas'].initial == 3
        assert f.fields['resposta_minutos'].initial == 0
        assert f.fields['resolucao_dias'].initial == 5

    def test_editar_preserva_os_minutos_quebrados(self, expediente):
        """147min (o Urgente real) = 2h27. Sem o campo de minutos, viraria 2h."""
        pol = SlaPolitica.objects.create(minutos_resposta=147, minutos_resolucao=882)
        f = SlaPoliticaForm(instance=pol)
        assert f.fields['resposta_dias'].initial == 0
        assert f.fields['resposta_horas'].initial == 2
        assert f.fields['resposta_minutos'].initial == 27

    @pytest.mark.parametrize('resp,resol', [
        (1380, 3000),      # redondo
        (147, 882),        # o Urgente real, quebrado
        (30, 120),         # minutos puros
        (588, 3528),       # exatamente 1 dia
    ])
    def test_ida_e_volta_nao_perde_valor(self, expediente, resp, resol):
        """Abrir e salvar sem mexer não pode alterar a meta — em nenhum valor."""
        pol = SlaPolitica.objects.create(minutos_resposta=resp, minutos_resolucao=resol)
        f = SlaPoliticaForm(instance=pol)
        dados = preenche(**{
            '%s_%s' % (campo, unidade): f.fields['%s_%s' % (campo, unidade)].initial
            for campo in ('resposta', 'resolucao')
            for unidade in ('dias', 'horas', 'minutos')
        })
        f2 = SlaPoliticaForm(dados, instance=pol)
        assert f2.is_valid(), f2.errors
        obj = f2.save()
        assert obj.minutos_resposta == resp
        assert obj.minutos_resolucao == resol

    def test_meta_vazia_e_barrada(self, expediente):
        """Meta zerada faria todo ticket nascer estourado."""
        f = SlaPoliticaForm(preenche(resolucao_dias=5))
        assert not f.is_valid()
        assert 'resposta' in str(f.errors).lower()

    def test_resolucao_menor_que_resposta_e_barrada(self, expediente):
        """As duas contam desde a abertura: resolver antes de responder é contradição."""
        f = SlaPoliticaForm(preenche(resposta_dias=5, resolucao_dias=1))
        assert not f.is_valid()
        assert 'resolução não pode ser menor' in str(f.errors)

    def test_sem_expediente_nao_estoura(self, db):
        """Cadastrar SLA antes do expediente não pode dar divisão por zero."""
        f = SlaPoliticaForm(preenche(resposta_dias=1, resolucao_dias=2))
        assert f.is_valid(), f.errors
        assert f.save().minutos_resposta == 480    # fallback de 8h

    def test_curinga_continua_possivel(self, expediente):
        f = SlaPoliticaForm(preenche(resposta_dias=1, resolucao_dias=5))
        assert f.is_valid(), f.errors
        obj = f.save()
        assert obj.departamento is None and obj.prioridade is None

    def test_especifica_por_departamento_e_prioridade(self, expediente):
        dep = Departamento.objects.create(descricao='Suporte')
        pri = Prioridade.objects.create(descricao='Urgente', peso=4)
        f = SlaPoliticaForm(preenche(departamento=dep.id, prioridade=pri.id,
                                     resposta_horas=2, resolucao_dias=1))
        assert f.is_valid(), f.errors
        obj = f.save()
        assert obj.departamento == dep and obj.prioridade == pri
        assert obj.minutos_resposta == 120


class TestTelasDoAdminAbrem:
    """Renderiza de verdade — testar só o form deixou passar um format_html sem
    argumento, que derrubava a listagem inteira com TypeError."""

    @pytest.fixture
    def admin_logado(self, client, db):
        from tiqt.apps.core.models import User
        u = User.objects.create_superuser(username='root', email='a@b.c', password='x')
        client.force_login(u)
        return client

    def test_listagem_abre_com_curinga(self, admin_logado, expediente):
        """A política curinga (departamento e prioridade nulos) é o caso do bug."""
        SlaPolitica.objects.create(minutos_resposta=600, minutos_resolucao=3000)
        r = admin_logado.get('/admin/core/slapolitica/')
        assert r.status_code == 200
        assert b'todos' in r.content and b'todas' in r.content
        assert b'<b>1d</b>' in r.content        # a coluna legível

    def test_listagem_abre_com_politica_especifica(self, admin_logado, expediente):
        dep = Departamento.objects.create(descricao='Suporte')
        pri = Prioridade.objects.create(descricao='Urgente', peso=4)
        SlaPolitica.objects.create(departamento=dep, prioridade=pri,
                                   minutos_resposta=120, minutos_resolucao=600)
        r = admin_logado.get('/admin/core/slapolitica/')
        assert r.status_code == 200
        assert b'Suporte' in r.content

    def test_form_de_criacao_abre(self, admin_logado, expediente):
        r = admin_logado.get('/admin/core/slapolitica/add/')
        assert r.status_code == 200
        for campo in [b'resposta_dias', b'resposta_horas', b'resolucao_dias', b'resolucao_horas']:
            assert campo in r.content
        assert b'name="minutos_resposta"' not in r.content   # escondido: é derivado

    def test_form_de_edicao_abre_com_os_valores_traduzidos(self, admin_logado, expediente):
        pol = SlaPolitica.objects.create(minutos_resposta=1380, minutos_resolucao=3000)
        r = admin_logado.get('/admin/core/slapolitica/%s/change/' % pol.pk)
        assert r.status_code == 200
        assert b'Um dia' in r.content     # o aviso do tamanho do dia útil

    def test_salvar_pelo_admin_grava_os_minutos(self, admin_logado, expediente):
        r = admin_logado.post('/admin/core/slapolitica/add/', {
            'departamento': '', 'prioridade': '', 'ativo': 'on',
            'resposta_dias': '2', 'resposta_horas': '3',
            'resolucao_dias': '5', 'resolucao_horas': '0',
        })
        assert r.status_code == 302, r.content[:400]   # redirect = salvou
        pol = SlaPolitica.objects.get()
        assert pol.minutos_resposta == 2 * 600 + 180
        assert pol.minutos_resolucao == 3000


class TestLegivel:
    """A coluna da lista: 588 -> '1d'. Ninguém deve precisar dividir de cabeça."""

    def test_minutos(self, expediente):
        assert _legivel(45) == '45min'

    def test_horas(self, expediente):
        assert _legivel(90) == '1h30'
        assert _legivel(120) == '2h'

    def test_dias(self, expediente):
        assert _legivel(600) == '1d'          # 1 dia útil exato
        assert _legivel(3000) == '5d'
        assert _legivel(660) == '1d 1h'

    def test_none(self, expediente):
        assert _legivel(None) == '—'

    def test_sem_expediente_usa_o_fallback_e_nao_divide_por_zero(self, db):
        assert _legivel(480) == '1d'          # fallback: 8h = 1 dia
