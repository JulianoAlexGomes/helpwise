"""Testes do painel de TV: autorização e comportamento do payload."""

from datetime import time, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from tiqt.apps.core.models import (
    Cliente, Departamento, Expediente, Prioridade, Situacao, SlaPolitica, Ticket, Tipo, User,
)

pytestmark = pytest.mark.django_db

TOKEN = 'token-de-teste-123'


@pytest.fixture
def expediente(db):
    for dia in range(5):
        Expediente.objects.create(dia_semana=dia, hora_inicio=time(8, 0), hora_fim=time(18, 0))


@pytest.fixture(autouse=True)
def limpa_cache():
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def user_atendente(db):
    return User.objects.create_user(username='atendente', password='x')


@pytest.fixture
def ticket(db):
    dep = Departamento.objects.create(descricao='Suporte')
    return Ticket.objects.create(
        departamento=dep,
        cliente=Cliente.objects.create(fantasia='ACME', plano=None),
        tipo=Tipo.objects.create(descricao='Dúvida', departamento=dep),
        prioridade=Prioridade.objects.create(descricao='Normal', peso=1),
        situacao=Situacao.objects.create(descricao='Nova'),
        titulo='Impressora não imprime',
    )


class TestAutorizacao:
    def test_deslogado_sem_token_e_barrado(self, client, settings, expediente):
        settings.PAINEL_TV_TOKEN = TOKEN
        r = client.get(reverse('painel_tv_dados'))
        assert r.status_code == 403

    def test_token_errado_e_barrado(self, client, settings, expediente):
        settings.PAINEL_TV_TOKEN = TOKEN
        r = client.get(reverse('painel_tv_dados'), {'k': 'chute'})
        assert r.status_code == 403

    def test_token_certo_entra(self, client, settings, expediente):
        settings.PAINEL_TV_TOKEN = TOKEN
        r = client.get(reverse('painel_tv_dados'), {'k': TOKEN})
        assert r.status_code == 200

    def test_usuario_logado_entra_sem_token(self, client, settings, expediente):
        settings.PAINEL_TV_TOKEN = TOKEN
        client.force_login(User.objects.create_user(username='z', password='x'))
        assert client.get(reverse('painel_tv_dados')).status_code == 200

    def test_token_vazio_falha_fechado(self, client, settings, expediente):
        """Sem token configurado, ninguém entra por ?k= — cai para exigir login."""
        settings.PAINEL_TV_TOKEN = ''
        assert client.get(reverse('painel_tv_dados'), {'k': ''}).status_code == 403


class TestPayload:
    def _dados(self, client, settings):
        settings.PAINEL_TV_TOKEN = TOKEN
        return client.get(reverse('painel_tv_dados'), {'k': TOKEN}).json()

    def test_ticket_sem_politica_fica_cinza_e_nunca_vermelho(self, client, settings, expediente, ticket):
        d = self._dados(client, settings)
        item = d['fila'][0]
        assert item['sem_sla'] is True
        assert item['cor'] == 'cinza'
        assert item['meta_min'] is None

    def test_ticket_na_fila_aparece_na_faixa_certa(self, client, settings, expediente, ticket):
        d = self._dados(client, settings)
        assert len(d['fila']) == 1
        assert len(d['atendimento']) == 0
        assert d['fila'][0]['id'] == ticket.id
        assert d['resumo']['fila_total'] == 1

    def test_ticket_pego_migra_para_atendimento(self, client, settings, expediente, ticket):
        user = User.objects.create_user(username='atendente', password='x')
        ticket.iniciar_atendimento(user)

        d = self._dados(client, settings)
        assert len(d['fila']) == 0
        assert len(d['atendimento']) == 1
        assert d['atendimento'][0]['id'] == ticket.id

    def test_meta_vem_da_politica(self, client, settings, expediente, ticket):
        SlaPolitica.objects.create(prioridade=ticket.prioridade,
                                   minutos_resposta=60, minutos_resolucao=480)
        d = self._dados(client, settings)
        item = d['fila'][0]
        assert item['meta_min'] == 60
        assert item['sem_sla'] is False

    def test_encerrado_nao_aparece(self, client, settings, expediente, ticket):
        user = User.objects.create_user(username='a', password='x')
        ticket.iniciar_atendimento(user)
        ticket.encerrar_atendimento(user)

        d = self._dados(client, settings)
        assert len(d['fila']) == 0
        assert len(d['atendimento']) == 0
        assert d['resumo']['encerrados_hoje'] == 1

    def test_payload_traz_os_cortes_de_cor(self, client, settings, expediente, ticket):
        """O JS não tem régua própria: os cortes vêm do servidor."""
        d = self._dados(client, settings)
        assert d['cortes'] == {'atencao': 70, 'estouro': 100}

    def test_ticket_muito_antigo_nao_mente_o_cronometro(self, client, settings, expediente, ticket):
        """Em atendimento há 300 dias: não pode virar '0min' nem um número inventado.

        A faixa de atendimento não tem corte por idade (um ticket sendo
        trabalhado há meses precisa aparecer), então é aqui que o clamp importa.
        """
        user = User.objects.create_user(username='a', password='x')
        ticket.iniciar_atendimento(user)
        Ticket.objects.filter(pk=ticket.pk).update(criado_em=timezone.now() - timedelta(days=300))

        d = self._dados(client, settings)
        item = d['atendimento'][0]
        assert item['antigo'] is True
        assert item['consumido_min'] is None   # sem cronômetro falso
        assert item['idade_dias'] >= 299

    def test_ticket_antigo_com_meta_conta_como_estourado(self, client, settings, expediente, ticket):
        SlaPolitica.objects.create(prioridade=ticket.prioridade,
                                   minutos_resposta=60, minutos_resolucao=480)
        user = User.objects.create_user(username='a', password='x')
        ticket.iniciar_atendimento(user)
        Ticket.objects.filter(pk=ticket.pk).update(criado_em=timezone.now() - timedelta(days=300))

        d = self._dados(client, settings)
        assert d['atendimento'][0]['cor'] == 'vermelho'
        assert d['resumo']['estourados'] == 1

    def test_sem_expediente_cadastrado_avisa_em_vez_de_estourar(self, client, settings, ticket):
        """Sem Expediente, a TV tem que dizer o que falta, não dar 500."""
        d = self._dados(client, settings)   # repare: sem a fixture `expediente`
        assert d['expediente_configurado'] is False
        assert len(d['fila']) == 1          # a fila continua visível

    def test_antigo_sai_da_fila_do_dia_mas_vira_contador(self, client, settings, expediente, ticket):
        """A dívida antiga não some da TV: sai da lista e vira número."""
        Ticket.objects.filter(pk=ticket.pk).update(criado_em=timezone.now() - timedelta(days=120))

        d = self._dados(client, settings)
        assert d['fila'] == []                          # não polui a fila do dia
        assert d['resumo']['parados_total'] == 1        # mas continua contado
        assert d['resumo']['parados_mais_antigo_dias'] >= 119
        assert d['resumo']['fila_total'] == 0

    def test_fila_do_dia_e_divida_convivem(self, client, settings, expediente, ticket):
        velho = Ticket.objects.create(
            departamento=ticket.departamento, cliente=ticket.cliente, tipo=ticket.tipo,
            prioridade=ticket.prioridade, situacao=ticket.situacao, titulo='Esquecido')
        Ticket.objects.filter(pk=velho.pk).update(criado_em=timezone.now() - timedelta(days=300))

        d = self._dados(client, settings)
        assert [i['id'] for i in d['fila']] == [ticket.id]   # só o de hoje na lista
        assert d['resumo']['parados_total'] == 1
        assert d['resumo']['parados_mais_antigo_dias'] >= 299

    def test_sem_divida_o_contador_zera(self, client, settings, expediente, ticket):
        d = self._dados(client, settings)
        assert d['resumo']['parados_total'] == 0
        assert d['resumo']['parados_mais_antigo_dias'] == 0

    def test_fila_ordena_por_peso(self, client, settings, expediente, ticket):
        alta = Prioridade.objects.create(descricao='Alta', peso=9)
        urgente = Ticket.objects.create(
            departamento=ticket.departamento, cliente=ticket.cliente, tipo=ticket.tipo,
            prioridade=alta, situacao=ticket.situacao, titulo='Servidor fora')

        d = self._dados(client, settings)
        assert [i['id'] for i in d['fila']] == [urgente.id, ticket.id]


class TestAgrupamentoPorDepartamento:
    def _dados(self, client, settings):
        settings.PAINEL_TV_TOKEN = TOKEN
        return client.get(reverse('painel_tv_dados'), {'k': TOKEN}).json()

    @pytest.fixture
    def dois_deptos(self, ticket):
        """ticket já é do 'Suporte'; cria um segundo em 'Desenvolvimento'."""
        dev = Departamento.objects.create(descricao='Desenvolvimento')
        outro = Ticket.objects.create(
            departamento=dev, cliente=ticket.cliente,
            tipo=Tipo.objects.create(descricao='Bug', departamento=dev),
            prioridade=ticket.prioridade, situacao=ticket.situacao, titulo='Bug no XML')
        return ticket, outro

    def test_fila_vem_ordenada_por_departamento(self, client, settings, expediente, dois_deptos):
        """O JS quebra o grupo quando o departamento muda: a ordem tem que vir pronta."""
        d = self._dados(client, settings)
        deptos = [i['departamento'] for i in d['fila']]
        assert deptos == sorted(deptos)

    def test_payload_traz_resumo_por_departamento(self, client, settings, expediente, dois_deptos):
        d = self._dados(client, settings)
        resumo = {r['departamento']: r for r in d['por_departamento']}
        assert resumo['Suporte']['fila'] == 1
        assert resumo['Desenvolvimento']['fila'] == 1

    def test_resumo_por_departamento_conta_a_divida_antiga(self, client, settings, expediente, dois_deptos):
        """Os parados não aparecem na lista, mas têm que aparecer no contador do grupo."""
        _, dev_ticket = dois_deptos
        Ticket.objects.filter(pk=dev_ticket.pk).update(criado_em=timezone.now() - timedelta(days=120))

        d = self._dados(client, settings)
        resumo = {r['departamento']: r for r in d['por_departamento']}
        assert resumo['Desenvolvimento']['fila'] == 0      # saiu da lista
        assert resumo['Desenvolvimento']['parados'] == 1   # mas continua contado

    def test_meta_do_departamento_vence_a_de_prioridade(self, client, settings, expediente, dois_deptos):
        """Política (depto, prio) é mais específica que (—, prio)."""
        ticket, _ = dois_deptos
        SlaPolitica.objects.create(prioridade=ticket.prioridade,
                                   minutos_resposta=999, minutos_resolucao=999)
        SlaPolitica.objects.create(departamento=ticket.departamento, prioridade=ticket.prioridade,
                                   minutos_resposta=42, minutos_resolucao=99)

        d = self._dados(client, settings)
        item = next(i for i in d['fila'] if i['departamento'] == 'Suporte')
        assert item['meta_min'] == 42

    def test_departamentos_diferentes_tem_metas_diferentes(self, client, settings, expediente, dois_deptos):
        sup, dev = dois_deptos
        SlaPolitica.objects.create(departamento=sup.departamento, minutos_resposta=60, minutos_resolucao=480)
        SlaPolitica.objects.create(departamento=dev.departamento, minutos_resposta=600, minutos_resolucao=6000)

        d = self._dados(client, settings)
        metas = {i['departamento']: i['meta_min'] for i in d['fila']}
        assert metas['Suporte'] == 60
        assert metas['Desenvolvimento'] == 600


class TestFiltrosDaTV:
    """A TV é quiosque: o que ela mostra vem do link, não de clique."""

    def _dados(self, client, settings, **params):
        settings.PAINEL_TV_TOKEN = TOKEN
        return client.get(reverse('painel_tv_dados'), {'k': TOKEN, **params}).json()

    @pytest.fixture
    def dois(self, ticket):
        dev = Departamento.objects.create(descricao='Desenvolvimento')
        tipo_dev = Tipo.objects.create(descricao='Correção', departamento=dev)
        outro = Ticket.objects.create(
            departamento=dev, cliente=ticket.cliente, tipo=tipo_dev,
            prioridade=ticket.prioridade, situacao=ticket.situacao, titulo='Bug XML')
        return ticket, outro, dev, tipo_dev

    def test_sem_filtro_mostra_tudo(self, client, settings, expediente, dois):
        d = self._dados(client, settings)
        assert len(d['fila']) == 2

    def test_filtra_por_departamento(self, client, settings, expediente, dois):
        _, outro, dev, _ = dois
        d = self._dados(client, settings, departamento=dev.id)
        assert [i['id'] for i in d['fila']] == [outro.id]
        assert d['resumo']['fila_total'] == 1

    def test_filtra_por_tipo(self, client, settings, expediente, dois):
        _, outro, _, tipo_dev = dois
        d = self._dados(client, settings, tipo=tipo_dev.id)
        assert [i['id'] for i in d['fila']] == [outro.id]

    def test_filtra_por_prioridade(self, client, settings, expediente, dois):
        ticket, _, _, _ = dois
        urgente = Prioridade.objects.create(descricao='Urgente', peso=9)
        Ticket.objects.filter(pk=ticket.pk).update(prioridade=urgente)

        d = self._dados(client, settings, prioridade=urgente.id)
        assert [i['id'] for i in d['fila']] == [ticket.id]

    def test_filtro_invalido_e_ignorado(self, client, settings, expediente, dois):
        """?departamento=abc não pode derrubar a TV da parede."""
        d = self._dados(client, settings, departamento='abc')
        assert len(d['fila']) == 2

    def test_cache_nao_vaza_entre_filtros(self, client, settings, expediente, dois):
        """A TV do Dev não pode servir o cache da TV do Suporte."""
        _, outro, dev, _ = dois
        todos = self._dados(client, settings)
        so_dev = self._dados(client, settings, departamento=dev.id)
        assert len(todos['fila']) == 2
        assert len(so_dev['fila']) == 1

    def test_encerrados_hoje_respeita_o_filtro(self, client, settings, expediente, dois, user_atendente):
        ticket, outro, dev, _ = dois
        outro.iniciar_atendimento(user_atendente)
        outro.encerrar_atendimento(user_atendente)

        assert self._dados(client, settings, departamento=dev.id)['resumo']['encerrados_hoje'] == 1
        assert self._dados(client, settings, departamento=ticket.departamento_id)['resumo']['encerrados_hoje'] == 0

    def test_encerrados_hoje_conta_de_verdade(self, client, settings, expediente, ticket, user_atendente):
        """Regressão: com __date no MySQL sem tz tables, isso ficava 0 para sempre."""
        ticket.iniciar_atendimento(user_atendente)
        ticket.encerrar_atendimento(user_atendente)
        assert self._dados(client, settings)['resumo']['encerrados_hoje'] == 1

    def test_rotulo_do_escopo_aparece_no_cabecalho(self, client, settings, expediente, dois):
        """Quem lê 'fila: 1' na parede precisa saber que é só do Dev."""
        _, _, dev, _ = dois
        settings.PAINEL_TV_TOKEN = TOKEN
        r = client.get(reverse('painel_tv'), {'k': TOKEN, 'departamento': dev.id})
        assert 'Desenvolvimento'.encode() in r.content

    def test_montador_de_link_some_no_modo_quiosque(self, client, settings, expediente):
        """Logado configura; a TV com token não tem quem clique.

        Procura o atributo do form, não a string 'form-config' solta: ela também
        aparece no JS, que é renderizado nos dois casos.
        """
        settings.PAINEL_TV_TOKEN = TOKEN
        r = client.get(reverse('painel_tv'), {'k': TOKEN})
        assert b'id="form-config"' not in r.content
        assert b'Copiar link da TV' not in r.content

        client.force_login(User.objects.create_user(username='z', password='x'))
        r = client.get(reverse('painel_tv'))
        assert b'id="form-config"' in r.content


class TestMontadorDeLink:
    """O link tem que ABRIR a TV, não cair no login.

    Quem monta o link está logado e sem ?k= — copiar a URL da barra daria um
    link sem chave nenhuma, que na TV vira tela de login.
    """

    @pytest.fixture
    def diretor(self, db):
        from django.contrib.auth.models import Group
        u = User.objects.create_user(username='chefe', password='x')
        u.groups.add(Group.objects.create(name='Diretoria'))
        return u

    def test_diretoria_recebe_o_token_para_montar_o_link(self, client, settings, expediente, diretor):
        settings.PAINEL_TV_TOKEN = TOKEN
        client.force_login(diretor)
        r = client.get(reverse('painel_tv'))
        assert f'data-token="{TOKEN}"'.encode() in r.content

    def test_atendente_comum_nao_ve_o_token(self, client, settings, expediente):
        """O token abre o painel sem senha: não vaza para todo usuário logado."""
        settings.PAINEL_TV_TOKEN = TOKEN
        client.force_login(User.objects.create_user(username='z', password='x'))
        r = client.get(reverse('painel_tv'))

        assert TOKEN.encode() not in r.content       # nem no data-attr, nem solto
        assert b'Copiar link da TV' not in r.content
        assert b'id="form-config"' in r.content      # mas ainda pode filtrar a tela

    def test_sem_token_configurado_avisa_em_vez_de_dar_link_quebrado(self, client, settings, expediente, diretor):
        settings.PAINEL_TV_TOKEN = ''
        client.force_login(diretor)
        r = client.get(reverse('painel_tv'))

        assert b'Copiar link da TV' not in r.content   # link que cairia no login
        assert b'PAINEL_TV_TOKEN' in r.content         # diz o que fazer

    def test_link_montado_abre_a_tv_sem_sessao(self, client, settings, expediente, ticket):
        """O fim da linha: a URL que o botão monta funciona deslogado."""
        settings.PAINEL_TV_TOKEN = TOKEN
        dep_id = ticket.departamento_id

        client.logout()
        r = client.get(reverse('painel_tv'), {'k': TOKEN, 'departamento': dep_id})
        assert r.status_code == 200                    # não redireciona para login
        assert b'id="form-config"' not in r.content     # e é modo quiosque


def test_nenhum_template_tem_comentario_multilinha():
    """`{# ... #}` do Django é de UMA linha: quebrado em duas, o resto vaza na tela.

    Sem banco e sem render — é lint de template. Já vazou uma vez no painel_tv;
    este teste existe para não vazar de novo. Multi-linha se faz com
    {% comment %}...{% endcomment %}.
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[3]   # tiqt/
    problemas = []
    for tpl in raiz.rglob('templates/**/*.html'):
        for n, linha in enumerate(tpl.read_text(encoding='utf-8').splitlines(), 1):
            if '{#' in linha and '#}' not in linha:
                problemas.append(f'{tpl.relative_to(raiz)}:{n}')
    assert not problemas, 'Comentário {# #} aberto em várias linhas (vaza na tela): ' + ', '.join(problemas)


class TestPainelRender:
    def test_pagina_abre_com_token(self, client, settings, expediente):
        settings.PAINEL_TV_TOKEN = TOKEN
        r = client.get(reverse('painel_tv'), {'k': TOKEN})
        assert r.status_code == 200
        assert b'Painel de Atendimento' in r.content

    def test_pagina_deslogada_redireciona_para_login(self, client, settings, expediente):
        settings.PAINEL_TV_TOKEN = TOKEN
        r = client.get(reverse('painel_tv'))
        assert r.status_code == 302
        assert '/login/' in r['Location']
