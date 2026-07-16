"""Testes do painel de TV.

MODELO: a coluna é de quem ABRIU o ticket (`Ticket.atendente`, gravado na
criação em views.py:595). Quem está RESOLVENDO (`Ticket.responsavel`) aparece
dentro do card. As colunas são os membros do grupo `Atendentes`.
"""

from datetime import time, timedelta

import pytest
from django.contrib.auth.models import Group
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
def base(db):
    """As FKs obrigatórias do Ticket, montadas uma vez."""
    dep = Departamento.objects.create(descricao='Suporte')
    return {
        'dep': dep,
        # plano=None explícito: o campo tem default=1 e o Plano 1 não existe no
        # banco de teste — estoura de IntegrityError só no teardown.
        'cliente': Cliente.objects.create(fantasia='ACME', plano=None),
        'tipo': Tipo.objects.create(descricao='Dúvida', departamento=dep),
        'prio': Prioridade.objects.create(descricao='Normal', peso=1),
        'sit': Situacao.objects.create(descricao='Nova'),
    }


@pytest.fixture
def grupo(db):
    return Group.objects.create(name='Atendentes')


@pytest.fixture
def atendente(db, grupo):
    """Um atendente de verdade: no grupo, e é ele quem abre os tickets."""
    u = User.objects.create_user(username='henrique', first_name='Henrique', password='x')
    u.groups.add(grupo)
    return u


@pytest.fixture
def user_atendente(db):
    """Usuário sem grupo — para os casos de fallback."""
    return User.objects.create_user(username='avulso', first_name='Avulso', password='x')


def novo_ticket(base, titulo='Impressora não imprime', atendente=None, **kw):
    """Cria como a NewTicketView cria: `atendente` = quem abriu."""
    return Ticket.objects.create(
        departamento=base['dep'], cliente=base['cliente'], tipo=base['tipo'],
        prioridade=base['prio'], situacao=base['sit'], titulo=titulo,
        atendente=atendente, **kw
    )


@pytest.fixture
def ticket(base, atendente):
    return novo_ticket(base, atendente=atendente)


def dados(client, settings, **params):
    settings.PAINEL_TV_TOKEN = TOKEN
    return client.get(reverse('painel_tv_dados'), {'k': TOKEN, **params}).json()


def colunas(d):
    return {c['chave']: c for c in d['por_atendente']}


class TestAutorizacao:
    def test_deslogado_sem_token_e_barrado(self, client, settings, expediente):
        settings.PAINEL_TV_TOKEN = TOKEN
        assert client.get(reverse('painel_tv_dados')).status_code == 403

    def test_token_errado_e_barrado(self, client, settings, expediente):
        settings.PAINEL_TV_TOKEN = TOKEN
        assert client.get(reverse('painel_tv_dados'), {'k': 'chute'}).status_code == 403

    def test_token_certo_entra(self, client, settings, expediente):
        settings.PAINEL_TV_TOKEN = TOKEN
        assert client.get(reverse('painel_tv_dados'), {'k': TOKEN}).status_code == 200

    def test_usuario_logado_entra_sem_token(self, client, settings, expediente):
        settings.PAINEL_TV_TOKEN = TOKEN
        client.force_login(User.objects.create_user(username='z', password='x'))
        assert client.get(reverse('painel_tv_dados')).status_code == 200

    def test_token_vazio_falha_fechado(self, client, settings, expediente):
        """Sem token configurado, ninguém entra por ?k= — cai para exigir login."""
        settings.PAINEL_TV_TOKEN = ''
        assert client.get(reverse('painel_tv_dados'), {'k': ''}).status_code == 403


class TestOQueApareceNaTV:
    def test_ticket_aberto_aparece(self, client, settings, expediente, ticket):
        d = dados(client, settings)
        assert [i['id'] for i in d['itens']] == [ticket.id]
        assert d['resumo']['fila_total'] == 1
        assert d['resumo']['atendimento_total'] == 0

    def test_ticket_em_atendimento_continua_na_tela(self, client, settings, expediente, ticket, user_atendente):
        """Pegar para resolver NÃO tira o ticket da coluna de quem abriu."""
        ticket.iniciar_atendimento(user_atendente)

        d = dados(client, settings)
        assert [i['id'] for i in d['itens']] == [ticket.id]
        assert d['resumo']['atendimento_total'] == 1
        assert d['resumo']['fila_total'] == 0
        # e continua na coluna de QUEM ABRIU
        assert colunas(d)[str(ticket.atendente_id)]['ids'] == [ticket.id]

    def test_encerrado_sai_da_tv(self, client, settings, expediente, ticket, user_atendente):
        ticket.iniciar_atendimento(user_atendente)
        ticket.encerrar_atendimento(user_atendente)

        d = dados(client, settings)
        assert d['itens'] == []
        assert d['resumo']['encerrados_hoje'] == 1

    def test_cancelado_sai_da_tv(self, client, settings, expediente, ticket, user_atendente):
        ticket.cancelar_atendimento(user_atendente)
        assert dados(client, settings)['itens'] == []

    def test_ticket_sem_politica_fica_cinza_e_nunca_vermelho(self, client, settings, expediente, ticket):
        i = dados(client, settings)['itens'][0]
        assert i['sem_sla'] is True
        assert i['cor'] == 'cinza'
        assert i['meta_min'] is None

    def test_meta_de_resposta_enquanto_ninguem_assume(self, client, settings, expediente, ticket):
        SlaPolitica.objects.create(prioridade=ticket.prioridade,
                                   minutos_resposta=60, minutos_resolucao=480)
        assert dados(client, settings)['itens'][0]['meta_min'] == 60

    def test_meta_vira_a_de_resolucao_quando_alguem_assume(self, client, settings, expediente, ticket, user_atendente):
        SlaPolitica.objects.create(prioridade=ticket.prioridade,
                                   minutos_resposta=60, minutos_resolucao=480)
        ticket.iniciar_atendimento(user_atendente)
        assert dados(client, settings)['itens'][0]['meta_min'] == 480

    def test_antigo_sai_das_colunas_mas_vira_contador(self, client, settings, expediente, ticket):
        Ticket.objects.filter(pk=ticket.pk).update(criado_em=timezone.now() - timedelta(days=120))

        d = dados(client, settings)
        assert d['itens'] == []
        assert d['resumo']['parados_total'] == 1
        assert d['resumo']['parados_mais_antigo_dias'] >= 119

    def test_ticket_muito_antigo_nao_mente_o_cronometro(self, client, settings, expediente, base, atendente):
        """Em atendimento há 300 dias: não pode virar '0min' nem número inventado."""
        t = novo_ticket(base, atendente=atendente)
        t.iniciar_atendimento(atendente)
        Ticket.objects.filter(pk=t.pk).update(criado_em=timezone.now() - timedelta(days=300))

        # com 300 dias ele sai das colunas (>7d) — o cronômetro é conferido no payload
        from tiqt.apps.core.views_painel import _item
        from tiqt.apps.core.services import sla
        t.refresh_from_db()
        i = _item(t, timezone.now(), sla.carregar_calendario(), 'minutos_resolucao')
        assert i['antigo'] is True
        assert i['consumido_min'] is None
        assert i['idade_dias'] >= 299

    def test_sem_expediente_cadastrado_avisa_em_vez_de_estourar(self, client, settings, ticket):
        d = dados(client, settings)   # repare: sem a fixture `expediente`
        assert d['expediente_configurado'] is False
        assert len(d['itens']) == 1   # os cards continuam visíveis

    def test_payload_traz_os_cortes_de_cor(self, client, settings, expediente, ticket):
        """O JS não tem régua própria: os cortes vêm do servidor."""
        assert dados(client, settings)['cortes'] == {'atencao': 70, 'estouro': 100}

    def test_payload_traz_o_tamanho_do_dia_util(self, client, settings, expediente, ticket):
        """Sem isso o JS mostraria "58h14" em vez de "5d 6h" — ou dividiria por 24."""
        assert dados(client, settings)['minutos_por_dia_util'] == 600   # 08:00-18:00

    def test_sem_expediente_o_dia_util_e_zero(self, client, settings, ticket):
        """O JS cai para horas em vez de dividir por zero."""
        assert dados(client, settings)['minutos_por_dia_util'] == 0


class TestResponsavelNoCard:
    """O card mostra quem está RESOLVENDO — a informação que mais muda na tela."""

    def test_sem_responsavel_vem_vazio(self, client, settings, expediente, ticket):
        i = dados(client, settings)['itens'][0]
        assert i['responsavel_nome'] == ''
        assert i['em_atendimento'] is False

    def test_designado_na_criacao_nao_e_o_mesmo_que_assumido(self, client, settings, expediente, base, atendente, user_atendente):
        """O form de criação permite indicar quem vai resolver — mas designar não
        é começar. Enquanto o status for Aberto, o relógio corre contra a meta de
        RESPOSTA e o card não pode dar a entender que o ticket está andando."""
        SlaPolitica.objects.create(minutos_resposta=60, minutos_resolucao=480)
        t = novo_ticket(base, atendente=atendente, responsavel=user_atendente)

        i = dados(client, settings)['itens'][0]
        assert i['responsavel_nome'] == 'Avulso'
        assert i['em_atendimento'] is False    # designado, não assumido
        assert i['meta_min'] == 60             # meta de RESPOSTA: ninguém começou

    def test_ao_assumir_a_meta_vira_a_de_resolucao(self, client, settings, expediente, base, atendente, user_atendente):
        SlaPolitica.objects.create(minutos_resposta=60, minutos_resolucao=480)
        t = novo_ticket(base, atendente=atendente, responsavel=user_atendente)
        t.iniciar_atendimento(user_atendente)

        i = dados(client, settings)['itens'][0]
        assert i['em_atendimento'] is True
        assert i['meta_min'] == 480

    def test_quem_inicia_o_atendimento_vira_o_responsavel(self, client, settings, expediente, ticket, user_atendente):
        ticket.iniciar_atendimento(user_atendente)

        i = dados(client, settings)['itens'][0]
        assert i['responsavel_nome'] == 'Avulso'
        assert i['em_atendimento'] is True

    def test_card_traz_as_iniciais_do_responsavel(self, client, settings, expediente, base, atendente):
        dev = User.objects.create_user(username='jg', first_name='Juliano', last_name='Gomes', password='x')
        t = novo_ticket(base, atendente=atendente)
        t.iniciar_atendimento(dev)

        i = dados(client, settings)['itens'][0]
        assert i['responsavel_nome'] == 'Juliano Gomes'
        assert i['responsavel_iniciais'] == 'JG'


class TestColunasPorQuemAbriu:
    def test_a_coluna_e_de_quem_abriu_nao_de_quem_resolve(self, client, settings, expediente, base, atendente):
        """O caso real: Lucas abre, Juliano resolve — o card é do Lucas."""
        dev = User.objects.create_user(username='dev', first_name='Dev', password='x')
        t = novo_ticket(base, atendente=atendente)
        t.iniciar_atendimento(dev)

        c = colunas(dados(client, settings))
        assert str(atendente.id) in c            # quem abriu tem a coluna
        assert str(dev.id) not in c              # quem resolve não ganha coluna
        assert c[str(atendente.id)]['ids'] == [t.id]

    def test_membro_do_grupo_sem_ticket_tem_coluna_vazia(self, client, settings, expediente, grupo):
        ocioso = User.objects.create_user(username='ocioso', first_name='Ocioso', password='x')
        ocioso.groups.add(grupo)

        c = colunas(dados(client, settings))
        assert c[str(ocioso.id)]['total'] == 0
        assert c[str(ocioso.id)]['ids'] == []

    def test_ticket_aberto_por_quem_nao_e_atendente_nao_aparece(self, client, settings, expediente, base, atendente):
        """Decisão de negócio: a TV é a operação dos atendentes.

        E o corte tem que ser total: o ticket não pode nem viajar no payload nem
        contar no KPI, senão a tela diz "2 na fila" e mostra 1 card.
        """
        de_fora = User.objects.create_user(username='defora', first_name='Fora', password='x')
        meu = novo_ticket(base, 'Meu', atendente=atendente)
        novo_ticket(base, 'Do estranho', atendente=de_fora)

        d = dados(client, settings)
        assert [i['id'] for i in d['itens']] == [meu.id]     # nem no payload
        assert d['resumo']['fila_total'] == 1                # nem no KPI
        assert str(de_fora.id) not in colunas(d)             # nem coluna

    def test_kpi_bate_com_o_que_esta_na_tela(self, client, settings, expediente, base, atendente):
        """Invariante: a soma das colunas == o que os KPIs anunciam."""
        de_fora = User.objects.create_user(username='defora', first_name='Fora', password='x')
        for i in range(3):
            novo_ticket(base, f'meu{i}', atendente=atendente)
        for i in range(2):
            novo_ticket(base, f'alheio{i}', atendente=de_fora)

        d = dados(client, settings)
        r = d['resumo']
        das_colunas = [i for c in d['por_atendente'] for i in c['ids']]
        assert len(das_colunas) == r['fila_total'] + r['atendimento_total'] == 3

    def test_colunas_em_ordem_alfabetica_e_nao_por_volume(self, client, settings, expediente, base, grupo):
        """Regressão: coluna que pula de lugar numa TV é coluna que ninguém acompanha."""
        zulmira = User.objects.create_user(username='zulmira', first_name='Zulmira', password='x')
        ana = User.objects.create_user(username='ana', first_name='Ana', password='x')
        zulmira.groups.add(grupo)
        ana.groups.add(grupo)
        for i in range(3):
            novo_ticket(base, f'Z{i}', atendente=zulmira)   # Zulmira tem MAIS
        novo_ticket(base, 'A0', atendente=ana)

        d = dados(client, settings)
        assert [c['nome'] for c in d['por_atendente']] == ['Ana', 'Zulmira']

    def test_coluna_conta_estourados_e_em_atendimento(self, client, settings, expediente, base, atendente, user_atendente):
        SlaPolitica.objects.create(minutos_resposta=1, minutos_resolucao=1)
        t1 = novo_ticket(base, 'A', atendente=atendente)
        t1.iniciar_atendimento(user_atendente)
        Ticket.objects.filter(pk=t1.pk).update(criado_em=timezone.now() - timedelta(days=1))
        novo_ticket(base, 'B', atendente=atendente)

        c = colunas(dados(client, settings))[str(atendente.id)]
        assert c['total'] == 2
        assert c['em_atendimento'] == 1
        assert c['estourados'] >= 1

    def test_ids_das_colunas_sao_particao_exata(self, client, settings, expediente, base, atendente):
        for i in range(3):
            novo_ticket(base, f't{i}', atendente=atendente)

        d = dados(client, settings)
        das_colunas = [i for c in d['por_atendente'] for i in c['ids']]
        assert sorted(das_colunas) == sorted(i['id'] for i in d['itens'])
        assert len(das_colunas) == len(set(das_colunas))

    def test_colunas_carregam_ids_e_nao_copias(self, client, settings, expediente, ticket):
        """Duas cópias do mesmo ticket = tick atualiza uma, render lê a outra."""
        c = dados(client, settings)['por_atendente'][0]
        assert 'cards' not in c
        assert all(isinstance(i, int) for i in c['ids'])

    def test_sem_grupo_cai_no_comportamento_simples(self, client, settings, expediente, base, user_atendente):
        """A TV não pode depender de alguém lembrar de criar o grupo."""
        t = novo_ticket(base, atendente=user_atendente)   # sem grupo nenhum criado
        c = colunas(dados(client, settings))
        assert c[str(user_atendente.id)]['ids'] == [t.id]

    def test_membro_inativo_nao_vira_coluna(self, client, settings, expediente, grupo):
        morto = User.objects.create_user(username='ex', password='x', is_active=False)
        morto.groups.add(grupo)
        assert dados(client, settings)['por_atendente'] == []

    def test_nome_do_grupo_e_case_insensitive(self, client, settings, expediente, db):
        """Ele pode cadastrar 'atendentes' minúsculo no admin."""
        g = Group.objects.create(name='atendentes')
        User.objects.create_user(username='x1', first_name='Alguem', password='x').groups.add(g)
        assert len(dados(client, settings)['por_atendente']) == 1

    def test_iniciais(self):
        from tiqt.apps.core.views_painel import _iniciais
        assert _iniciais('Maria Silva') == 'MS'
        assert _iniciais('Juliano') == 'JU'
        assert _iniciais('Ana Paula de Souza') == 'AS'
        assert _iniciais('') == '?'
        assert _iniciais(None) == '?'


class TestAvatarDaColuna:
    """Foto do atendente, com a inicial atrás como rede de segurança."""

    def test_coluna_traz_a_url_da_foto(self, client, settings, expediente, grupo):
        u = User.objects.create_user(username='comfoto', first_name='Com Foto', password='x')
        u.foto = 'avatares/teste.jpg'
        u.save()
        u.groups.add(grupo)

        c = dados(client, settings)['por_atendente'][0]
        assert c['foto'].endswith('avatares/teste.jpg')
        assert c['iniciais'] == 'CF'      # a inicial vai junto: é o fallback

    def test_sem_foto_manda_string_vazia(self, client, settings, expediente, atendente):
        """O João do grupo real não tem foto — o template cai na inicial."""
        c = dados(client, settings)['por_atendente'][0]
        assert c['foto'] == ''
        assert c['iniciais'] == 'HE'

    def test_foto_no_fallback_sem_grupo(self, client, settings, expediente, base):
        """Sem grupo configurado a coluna nasce do ticket — e ainda assim tem foto."""
        u = User.objects.create_user(username='semgrupo', first_name='Sem Grupo', password='x')
        u.foto = 'avatares/x.png'
        u.save()
        novo_ticket(base, atendente=u)

        c = dados(client, settings)['por_atendente'][0]
        assert c['foto'].endswith('avatares/x.png')


class TestCorDaPrioridade:
    """O nível sai do PESO, não do nome: o nome muda no admin, o peso é o que
    já ordena a fila."""

    @pytest.mark.parametrize('peso,nivel', [(1, 1), (2, 2), (3, 3), (4, 4)])
    def test_peso_vira_nivel(self, client, settings, expediente, base, atendente, peso, nivel):
        p = Prioridade.objects.create(descricao='X', peso=peso)
        Ticket.objects.create(departamento=base['dep'], cliente=base['cliente'], tipo=base['tipo'],
                              prioridade=p, situacao=base['sit'], titulo='t', atendente=atendente)
        assert dados(client, settings)['itens'][0]['prioridade_nivel'] == nivel

    def test_peso_alto_e_clampado(self, client, settings, expediente, base, atendente):
        """Peso 9 no admin não pode virar classe CSS .p9, que não existe."""
        p = Prioridade.objects.create(descricao='Absurda', peso=9)
        Ticket.objects.create(departamento=base['dep'], cliente=base['cliente'], tipo=base['tipo'],
                              prioridade=p, situacao=base['sit'], titulo='t', atendente=atendente)
        assert dados(client, settings)['itens'][0]['prioridade_nivel'] == 4

    def test_peso_zero_cai_em_neutro(self, client, settings, expediente, base, atendente):
        """Prioridade sem peso configurado (o default) não pode virar .p0."""
        p = Prioridade.objects.create(descricao='Sem peso')   # peso=0
        Ticket.objects.create(departamento=base['dep'], cliente=base['cliente'], tipo=base['tipo'],
                              prioridade=p, situacao=base['sit'], titulo='t', atendente=atendente)
        assert dados(client, settings)['itens'][0]['prioridade_nivel'] == 1


class TestOrdenacaoEstavel:
    """Quem espera há mais tempo primeiro — e a ordem não pode mudar sozinha."""

    def test_mais_antigo_primeiro(self, client, settings, expediente, base, atendente):
        novo = novo_ticket(base, 'Novo', atendente=atendente)
        velho = novo_ticket(base, 'Velho', atendente=atendente)
        Ticket.objects.filter(pk=velho.pk).update(criado_em=timezone.now() - timedelta(days=3))

        d = dados(client, settings)
        assert [i['id'] for i in d['itens']] == [velho.id, novo.id]

    def test_nao_ordena_por_pct(self, client, settings, expediente, base, atendente):
        """pct corre em velocidades diferentes por meta: os cards se cruzariam."""
        alta = Prioridade.objects.create(descricao='Alta', peso=9)
        SlaPolitica.objects.create(prioridade=alta, minutos_resposta=1, minutos_resolucao=1)
        SlaPolitica.objects.create(prioridade=base['prio'], minutos_resposta=99999, minutos_resolucao=99999)

        # o mais NOVO tem pct altíssimo (meta de 1min); o mais VELHO tem pct baixo
        velho = novo_ticket(base, 'Velho', atendente=atendente)
        Ticket.objects.filter(pk=velho.pk).update(criado_em=timezone.now() - timedelta(days=2))
        novo = Ticket.objects.create(
            departamento=base['dep'], cliente=base['cliente'], tipo=base['tipo'],
            prioridade=alta, situacao=base['sit'], titulo='Novo urgente', atendente=atendente)

        d = dados(client, settings)
        # idade manda, não pct
        assert [i['id'] for i in d['itens']] == [velho.id, novo.id]


class TestFiltrosDaTV:
    """A TV é quiosque: o que ela mostra vem do link, não de clique."""

    @pytest.fixture
    def dois(self, base, atendente):
        sup = novo_ticket(base, 'Do suporte', atendente=atendente)
        dev = Departamento.objects.create(descricao='Desenvolvimento')
        tipo_dev = Tipo.objects.create(descricao='Correção', departamento=dev)
        d = Ticket.objects.create(
            departamento=dev, cliente=base['cliente'], tipo=tipo_dev,
            prioridade=base['prio'], situacao=base['sit'], titulo='Bug XML', atendente=atendente)
        return sup, d, dev, tipo_dev

    def test_sem_filtro_mostra_tudo(self, client, settings, expediente, dois):
        assert len(dados(client, settings)['itens']) == 2

    def test_filtra_por_departamento(self, client, settings, expediente, dois):
        _, d_ticket, dev, _ = dois
        assert [i['id'] for i in dados(client, settings, departamento=dev.id)['itens']] == [d_ticket.id]

    def test_filtra_por_tipo(self, client, settings, expediente, dois):
        _, d_ticket, _, tipo_dev = dois
        assert [i['id'] for i in dados(client, settings, tipo=tipo_dev.id)['itens']] == [d_ticket.id]

    def test_filtra_por_prioridade(self, client, settings, expediente, dois, base):
        sup, _, _, _ = dois
        urgente = Prioridade.objects.create(descricao='Urgente', peso=9)
        Ticket.objects.filter(pk=sup.pk).update(prioridade=urgente)
        assert [i['id'] for i in dados(client, settings, prioridade=urgente.id)['itens']] == [sup.id]

    def test_filtro_invalido_e_ignorado(self, client, settings, expediente, dois):
        """?departamento=abc não pode derrubar a TV da parede."""
        assert len(dados(client, settings, departamento='abc')['itens']) == 2

    def test_departamento_aceita_varios(self, client, settings, expediente, base, atendente, dois):
        """Uma TV que junta Suporte + Notas, por exemplo."""
        sup, d_ticket, dev, _ = dois
        notas = Departamento.objects.create(descricao='Notas')
        t_notas = Ticket.objects.create(
            departamento=notas, cliente=base['cliente'],
            tipo=Tipo.objects.create(descricao='NF', departamento=notas),
            prioridade=base['prio'], situacao=base['sit'], titulo='NFe', atendente=atendente)

        settings.PAINEL_TV_TOKEN = TOKEN
        r = client.get(reverse('painel_tv_dados'),
                       {'k': TOKEN, 'departamento': [sup.departamento_id, notas.id]}).json()
        ids = sorted(i['id'] for i in r['itens'])
        assert ids == sorted([sup.id, t_notas.id])
        assert d_ticket.id not in ids               # Desenvolvimento ficou de fora

    def test_um_valido_e_um_invalido_usa_so_o_valido(self, client, settings, expediente, dois):
        sup, _, dev, _ = dois
        settings.PAINEL_TV_TOKEN = TOKEN
        r = client.get(reverse('painel_tv_dados'),
                       {'k': TOKEN, 'departamento': [str(dev.id), 'abc']}).json()
        assert len(r['itens']) == 1

    def test_valores_repetidos_nao_duplicam(self, client, settings, expediente, dois):
        _, d_ticket, dev, _ = dois
        settings.PAINEL_TV_TOKEN = TOKEN
        r = client.get(reverse('painel_tv_dados'),
                       {'k': TOKEN, 'departamento': [dev.id, dev.id]}).json()
        assert [i['id'] for i in r['itens']] == [d_ticket.id]

    def test_cache_separa_um_departamento_de_dois(self, client, settings, expediente, base, atendente, dois):
        """A chave de cache tem que distinguir ?dep=1 de ?dep=1&dep=2."""
        sup, _, dev, _ = dois
        settings.PAINEL_TV_TOKEN = TOKEN
        so_dev = client.get(reverse('painel_tv_dados'), {'k': TOKEN, 'departamento': dev.id}).json()
        dois_deps = client.get(reverse('painel_tv_dados'),
                               {'k': TOKEN, 'departamento': [dev.id, sup.departamento_id]}).json()
        assert len(so_dev['itens']) == 1
        assert len(dois_deps['itens']) == 2

    def test_rotulo_junta_os_departamentos(self, client, settings, expediente, base, atendente, dois):
        sup, _, dev, _ = dois
        settings.PAINEL_TV_TOKEN = TOKEN
        r = client.get(reverse('painel_tv'), {'k': TOKEN, 'departamento': [dev.id, sup.departamento_id]})
        assert 'Desenvolvimento + Suporte'.encode() in r.content

    def test_cache_nao_vaza_entre_filtros(self, client, settings, expediente, dois):
        _, _, dev, _ = dois
        assert len(dados(client, settings)['itens']) == 2
        assert len(dados(client, settings, departamento=dev.id)['itens']) == 1

    def test_filtro_vale_nas_colunas(self, client, settings, expediente, dois, atendente):
        _, d_ticket, dev, _ = dois
        c = colunas(dados(client, settings, departamento=dev.id))
        assert c[str(atendente.id)]['ids'] == [d_ticket.id]

    def test_encerrados_hoje_respeita_o_filtro(self, client, settings, expediente, dois, user_atendente):
        _, d_ticket, dev, _ = dois
        d_ticket.iniciar_atendimento(user_atendente)
        d_ticket.encerrar_atendimento(user_atendente)

        assert dados(client, settings, departamento=dev.id)['resumo']['encerrados_hoje'] == 1
        assert dados(client, settings, departamento=999)['resumo']['encerrados_hoje'] == 0

    def test_encerrados_hoje_conta_de_verdade(self, client, settings, expediente, ticket, user_atendente):
        """Regressão: com __date no MySQL sem tz tables, isso ficava 0 para sempre."""
        ticket.iniciar_atendimento(user_atendente)
        ticket.encerrar_atendimento(user_atendente)
        assert dados(client, settings)['resumo']['encerrados_hoje'] == 1

    def test_rotulo_do_escopo_aparece_no_cabecalho(self, client, settings, expediente, dois):
        _, _, dev, _ = dois
        settings.PAINEL_TV_TOKEN = TOKEN
        r = client.get(reverse('painel_tv'), {'k': TOKEN, 'departamento': dev.id})
        assert 'Desenvolvimento'.encode() in r.content


class TestMetasPorDepartamento:
    """Testa sla.politica_para pelo payload — não é sobre agrupamento."""

    def test_meta_do_departamento_vence_a_de_prioridade(self, client, settings, expediente, ticket):
        SlaPolitica.objects.create(prioridade=ticket.prioridade,
                                   minutos_resposta=999, minutos_resolucao=999)
        SlaPolitica.objects.create(departamento=ticket.departamento, prioridade=ticket.prioridade,
                                   minutos_resposta=42, minutos_resolucao=99)
        assert dados(client, settings)['itens'][0]['meta_min'] == 42

    def test_departamentos_diferentes_tem_metas_diferentes(self, client, settings, expediente, base, atendente):
        sup = novo_ticket(base, atendente=atendente)
        dev = Departamento.objects.create(descricao='Desenvolvimento')
        Ticket.objects.create(
            departamento=dev, cliente=base['cliente'],
            tipo=Tipo.objects.create(descricao='Bug', departamento=dev),
            prioridade=base['prio'], situacao=base['sit'], titulo='Bug', atendente=atendente)
        SlaPolitica.objects.create(departamento=sup.departamento, minutos_resposta=60, minutos_resolucao=480)
        SlaPolitica.objects.create(departamento=dev, minutos_resposta=600, minutos_resolucao=6000)

        metas = {i['departamento']: i['meta_min'] for i in dados(client, settings)['itens']}
        assert metas['Suporte'] == 60
        assert metas['Desenvolvimento'] == 600


class TestMontadorDeLink:
    """O link tem que ABRIR a TV, não cair no login."""

    @pytest.fixture
    def diretor(self, db):
        u = User.objects.create_user(username='chefe', password='x')
        u.groups.add(Group.objects.create(name='Diretoria'))
        return u

    def test_diretoria_recebe_o_token_para_montar_o_link(self, client, settings, expediente, diretor):
        settings.PAINEL_TV_TOKEN = TOKEN
        client.force_login(diretor)
        assert f'data-token="{TOKEN}"'.encode() in client.get(reverse('painel_tv')).content

    def test_atendente_comum_nao_ve_o_token(self, client, settings, expediente):
        """O token abre o painel sem senha: não vaza para todo usuário logado."""
        settings.PAINEL_TV_TOKEN = TOKEN
        client.force_login(User.objects.create_user(username='z', password='x'))
        r = client.get(reverse('painel_tv'))
        assert TOKEN.encode() not in r.content
        assert b'Copiar link da TV' not in r.content
        assert b'id="form-config"' in r.content      # mas ainda pode filtrar a tela

    def test_sem_token_configurado_avisa_em_vez_de_dar_link_quebrado(self, client, settings, expediente, diretor):
        settings.PAINEL_TV_TOKEN = ''
        client.force_login(diretor)
        r = client.get(reverse('painel_tv'))
        assert b'Copiar link da TV' not in r.content
        assert b'PAINEL_TV_TOKEN' in r.content

    def test_link_montado_abre_a_tv_sem_sessao(self, client, settings, expediente, ticket):
        settings.PAINEL_TV_TOKEN = TOKEN
        client.logout()
        r = client.get(reverse('painel_tv'), {'k': TOKEN, 'departamento': ticket.departamento_id})
        assert r.status_code == 200
        assert b'id="form-config"' not in r.content   # modo quiosque


class TestReducedMotion:
    """A TV de parede ignora prefers-reduced-motion; o navegador de gente, não.

    Regressão: o Windows da TV estava com "Efeitos de animação" desligado, o
    Chrome reportava `reduce`, e a rolagem simplesmente não existia — em
    silêncio, sem erro nenhum. Como a rolagem é o que torna visível o card que
    não coube, na TV ela não é decoração.
    """

    def test_quiosque_ignora_a_preferencia(self, client, settings, expediente):
        settings.PAINEL_TV_TOKEN = TOKEN
        r = client.get(reverse('painel_tv'), {'k': TOKEN})   # sem sessão = TV
        assert b'var MODO_QUIOSQUE = true' in r.content

    def test_logado_respeita_a_preferencia(self, client, settings, expediente):
        settings.PAINEL_TV_TOKEN = TOKEN
        client.force_login(User.objects.create_user(username='z', password='x'))
        r = client.get(reverse('painel_tv'))
        assert b'var MODO_QUIOSQUE = false' in r.content

    def test_a_guarda_depende_do_modo(self, client, settings, expediente):
        """O `return` que matava a animação só pode valer fora do quiosque."""
        settings.PAINEL_TV_TOKEN = TOKEN
        h = client.get(reverse('painel_tv'), {'k': TOKEN}).content.decode()
        assert "!MODO_QUIOSQUE && window.matchMedia('(prefers-reduced-motion: reduce)')" in h


class TestVelocidadeDoAutoScroll:
    """A conta do scroll é pura — dá para travá-la sem browser.

    Regressão: um piso de DURAÇÃO (max(12s, ...)) fazia a coluna que sobra 65px
    rolar a 6px/s — indistinguível de parada, que foi o defeito relatado na TV.
    O piso tem que ser da velocidade máxima, não do tempo.
    """

    VEL = 18       # VELOCIDADE_PX_S no template
    DUR_MIN = 4    # DUR_MIN_S no template
    DWELL = 0.84   # fração do ciclo em movimento (8% de pausa em cada ponta)

    def _velocidade(self, desloc):
        subida = max(self.DUR_MIN, desloc / self.VEL / self.DWELL)
        return desloc / (subida * self.DWELL)

    def test_constantes_batem_com_o_template(self):
        """Se alguém mexer no template, este teste vira mentira — então confere."""
        from pathlib import Path
        import re
        tpl = (Path(__file__).resolve().parents[1] / 'templates' / 'core' / 'painel_tv.html').read_text(encoding='utf-8')
        assert re.search(r'VELOCIDADE_PX_S = %d\b' % self.VEL, tpl)
        assert re.search(r'DUR_MIN_S = %d\b' % self.DUR_MIN, tpl)
        assert 'desloc / VELOCIDADE_PX_S / 0.84' in tpl

    # Abaixo deste deslocamento o piso de duração entra e freia de propósito —
    # senão uma sobra de 12px viraria um tremor de meio segundo.
    LIMIAR_PISO = 61   # VEL * DWELL * DUR_MIN

    @pytest.mark.parametrize('desloc', [65, 100, 300, 700, 1200])
    def test_velocidade_e_constante_acima_do_piso(self, desloc):
        assert abs(self._velocidade(desloc) - self.VEL) < 0.5

    def test_sobra_pequena_nao_fica_parecendo_parada(self):
        """O defeito relatado: a coluna com 9 cards, sobrando ~65px.

        Antes: 6.4 px/s — 1 pixel a cada 6 segundos, parece parada."""
        assert self._velocidade(65) >= 8

    @pytest.mark.parametrize('desloc', [12, 30, 60])
    def test_abaixo_do_piso_freia_mas_continua_visivel(self, desloc):
        """O piso protege contra tremida, mas não pode voltar a parecer parado."""
        v = self._velocidade(desloc)
        assert v <= self.VEL          # freado
        assert v >= 3.5               # ainda perceptível


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
