"""Painel de TV: fila e atendimento em tempo real, com SLA em horário comercial.

Módulo separado porque views.py já passa de 2100 linhas.

Divisão de trabalho com o front: o servidor manda o tempo útil JÁ CONSUMIDO e
quando o expediente fecha; o JS só incrementa o contador entre um refresh e
outro. O JS não sabe o que é feriado nem hora de almoço — se soubesse, seriam
duas implementações da mesma regra, divergindo no primeiro feriado cadastrado.
"""

from datetime import datetime, time

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.http import require_GET

from .models import Ticket
from .services import sla

# Faixas de cor por % da meta consumida. Constante única: o JS recebe estes
# mesmos cortes no payload em vez de ter a régua dele.
PCT_ATENCAO = 70
PCT_ESTOURO = 100

CACHE_KEY_PAYLOAD = 'painel_tv:payload'
CACHE_TTL_PAYLOAD = 20   # 5 TVs na parede = 1 cálculo, não 5

# Acima disso não vale iterar dia a dia em minutos_uteis: já estourou faz tempo.
MAX_DIAS_CALCULO = 45

# A partir daqui o ticket sai da fila do dia e vira "dívida antiga": continua
# contado e visível num contador próprio, mas não disputa espaço na tela com o
# que chegou hoje. Sem isso a TV abre com 33 cards de +90 dias e a operação do
# dia some no meio.
#
# 7 dias foi medido, não chutado: com 30 dias a tela ficava 87% vermelha (a fila
# tem cauda de meses); com 7, a fila do dia fica legível e a dívida antiga
# continua gritando no contador. Se a fila encolher, dá para apertar.
DIAS_FILA_DO_DIA = 7

# Quem entra como coluna fixa na TV. Os membros deste grupo aparecem SEMPRE,
# mesmo sem ticket nenhum — coluna que some quando a pessoa zera é coluna que faz
# a tela inteira reflowar na frente de quem está lendo.
#
# Grupo ausente ou vazio => fallback: só quem tem ticket em atendimento. A TV não
# pode depender de configuração para funcionar.
GRUPO_ATENDENTES = 'Atendentes'

# Quantas colunas existem é decidido pelo grupo, no admin — não há teto aqui.
CHAVE_SEM_RESPONSAVEL = 'sem-responsavel'
CHAVE_OUTROS = 'outros'


def _autorizado(request):
    """A TV entra por token; gente entra por sessão.

    Sessão não serve para a TV: SESSION_COOKIE_AGE não está configurado (2
    semanas) e não renova, então a tela apagaria sozinha num sábado qualquer.
    Token vazio => cai para 'só logado' (falha fechado).
    """
    token = getattr(settings, 'PAINEL_TV_TOKEN', '')
    chave = request.GET.get('k', '')
    if token and constant_time_compare(chave, token):
        return True
    return request.user.is_authenticated


def _rotulo(filtros):
    """Ex.: 'Suporte + Notas · Correção'. Vai no cabeçalho da TV.

    Quem olha a tela da parede precisa saber que está vendo um recorte — senão lê
    'fila: 3' e conclui que a empresa inteira tem 3 tickets."""
    from .models import Departamento, Prioridade, Tipo

    partes = []
    for campo, model in (('departamento', Departamento), ('tipo', Tipo), ('prioridade', Prioridade)):
        if campo not in filtros:
            continue
        nomes = list(model.objects.filter(pk__in=filtros[campo]).values_list('descricao', flat=True))
        if nomes:
            partes.append(' + '.join(sorted(nomes)))
    return ' · '.join(partes)


def _iniciais(nome):
    """'Maria Silva' -> 'MS'; 'Juliano' -> 'JU'. O avatar da coluna pede 2 letras.

    Iniciais e não `User.foto`: a TV fica meses ligada e buscaria uma imagem por
    coluna a cada render — e em dev os arquivos de mídia nem existem no disco.
    """
    partes = [p for p in (nome or '').split() if p]
    if not partes:
        return '?'
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


def _atendentes_fixos():
    """Os membros do grupo `Atendentes` — colunas que existem mesmo sem ticket.

    Devolve [] quando o grupo não existe ou está vazio: aí o painel cai no
    comportamento antigo (coluna só para quem tem ticket). A TV precisa
    funcionar antes de alguém lembrar de configurar o grupo.
    """
    from django.contrib.auth.models import Group

    grupo = Group.objects.filter(name__iexact=GRUPO_ATENDENTES).first()
    if not grupo:
        return []
    return list(grupo.user_set.filter(is_active=True))


def _foto_url(user):
    """URL da foto, ou '' se não tiver.

    O template desenha a inicial no fundo e sobrepõe a <img> com
    onerror="this.remove()" — mesmo padrão do Kanban. É o que salva quando o
    arquivo está no banco mas não no disco (o caso de dev, e de qualquer upload
    que se perca).
    """
    try:
        return user.foto.url if user and user.foto else ''
    except ValueError:
        return ''


def _agrupar_por_atendente(itens, fixos):
    """Uma coluna por atendente do grupo. O ticket cai na coluna de QUEM O ABRIU.

    As colunas são EXATAMENTE os membros do grupo `Atendentes`, mesmo os que
    estão sem ticket — coluna que aparece e some conforme a pessoa abre ou
    encerra faria a grade inteira reflowar na frente de quem lê.

    Ticket aberto por quem não está no grupo NÃO aparece: é decisão de negócio
    (a TV é a operação dos atendentes). Note que isso não esconde o trabalho de
    quem resolve — um chamado que o Lucas abriu e o Juliano está resolvendo
    aparece na coluna do Lucas, com o Juliano no card.

    Sem grupo configurado, cai no comportamento simples: coluna para cada
    atendente que tenha ticket. A TV precisa funcionar antes de alguém lembrar
    de criar o grupo.

    Os grupos carregam IDs, não cópias dos cards. É deliberado: o `tick()` do JS
    muta consumido_min/pct/cor nos objetos de `itens[]` a cada segundo. Se os
    grupos trouxessem os cards inteiros, o payload teria DUAS cópias de cada
    ticket, o tick atualizaria uma e o render leria a outra — cronômetro
    congelado na parede. Com ids, há um objeto por ticket e uma fonte só.
    """
    fixos = list(fixos or [])
    colunas = {}

    def _nova(chave, nome, iniciais, do_grupo):
        return colunas.setdefault(chave, {
            'chave': chave, 'nome': nome, 'iniciais': iniciais, 'foto': '',
            'do_grupo': do_grupo, 'total': 0, 'estourados': 0,
            'em_atendimento': 0, 'ids': [],
        })

    for u in fixos:
        nome = u.get_full_name() or u.username
        col = _nova(str(u.id), nome, _iniciais(nome), True)
        col['foto'] = _foto_url(u)

    for item in itens:
        chave = str(item['atendente_id']) if item['atendente_id'] else CHAVE_SEM_RESPONSAVEL
        col = colunas.get(chave)
        if col is None:
            if fixos:
                continue      # abriu quem não é atendente: fora da TV
            col = _nova(chave, item['atendente_nome'] or 'Sem atendente',
                        item['atendente_iniciais'] or '—', False)
            col['foto'] = item['atendente_foto']
        col['total'] += 1
        col['ids'].append(item['id'])
        if item['cor'] == 'vermelho':
            col['estourados'] += 1
        if item['em_atendimento']:
            col['em_atendimento'] += 1

    # Alfabética e NUNCA por contagem: numa TV, coluna que pula de lugar a cada
    # ticket é coluna que ninguém consegue acompanhar.
    return sorted(colunas.values(), key=lambda c: c['nome'].lower())


def _cor(pct, sem_sla):
    if sem_sla:
        return 'cinza'
    if pct >= PCT_ESTOURO:
        return 'vermelho'
    if pct >= PCT_ATENCAO:
        return 'amarelo'
    return 'verde'


def _item(ticket, agora, cal, meta_attr):
    politica = sla.politica_para(ticket)
    meta = getattr(politica, meta_attr) if politica else None
    sem_sla = meta is None

    idade_dias = (agora - ticket.criado_em).days
    # Acima do limite não vale iterar dia a dia — e um cronômetro em minutos
    # perde o sentido de qualquer forma. Estes viram "há N dias": mostrar
    # "0min" (ou um múltiplo inventado da meta) para um ticket de 300 dias
    # seria mentira na parede.
    antigo = idade_dias > MAX_DIAS_CALCULO

    if antigo:
        consumido = None
        pct = 100.0 if meta else 0.0
    else:
        consumido = sla.minutos_uteis(ticket.criado_em, agora, cal)
        pct = round(consumido / meta * 100, 1) if meta else 0.0

    resp = ticket.responsavel
    resp_nome = (resp.get_full_name() or resp.username) if resp else ''
    aten = ticket.atendente
    aten_nome = (aten.get_full_name() or aten.username) if aten else ''
    peso = ticket.prioridade.peso if ticket.prioridade_id else 0

    return {
        'id': ticket.id,
        'titulo': ticket.titulo or f'Ticket #{ticket.id}',
        'cliente': ticket.cliente.fantasia if ticket.cliente_id else '',
        'departamento': ticket.departamento.descricao if ticket.departamento_id else 'Sem departamento',
        'departamento_id': ticket.departamento_id or 0,
        # `atendente` é QUEM ABRIU o chamado (views.py:595 grava request.user na
        # criação) — é ele quem dá a coluna. `responsavel` é quem está
        # RESOLVENDO: vem do form de criação ou de quem clicou em iniciar
        # atendimento, e aparece dentro do card.
        'atendente_id': ticket.atendente_id or 0,
        'atendente_nome': aten_nome,
        'atendente_iniciais': _iniciais(aten_nome) if aten_nome else '',
        'atendente_foto': _foto_url(aten),
        'responsavel_id': ticket.responsavel_id or 0,
        'responsavel_nome': resp_nome,
        'responsavel_iniciais': _iniciais(resp_nome) if resp_nome else '',
        'em_atendimento': ticket.status == Ticket.EM_ATENDIMENTO,
        'prioridade': ticket.prioridade.descricao if ticket.prioridade_id else '',
        'peso': peso,
        # Nível 1..4 para a cor do chip. Sai do PESO e não do nome: o nome muda no
        # admin, o peso é o que já ordena a fila. Peso 0 (não configurado) cai em
        # 1 = neutro.
        'prioridade_nivel': min(4, max(1, peso)) if peso else 1,
        'consumido_min': consumido,
        'meta_min': meta,
        'pct': pct,
        'idade_dias': idade_dias,
        'antigo': antigo,
        'cor': _cor(pct, sem_sla),
        'sem_sla': sem_sla,
    }


def _filtros(request):
    """Filtros da TV, vindos da URL. Cada um aceita VÁRIOS valores.

    A TV é uma tela em quiosque: não tem quem clique nela. Então o que ela mostra
    é decidido no link — /tv/?k=TOKEN&departamento=2&departamento=5 é a TV que
    junta dois departamentos. Ver o montador de link no template.

    Valor não numérico é ignorado em silêncio: ?departamento=abc não pode
    derrubar a tela da parede.
    """
    out = {}
    for campo in ('departamento', 'tipo', 'prioridade'):
        vals = [int(v) for v in request.GET.getlist(campo) if v.isdigit()]
        if vals:
            out[campo] = sorted(set(vals))
    return out


def _aplicar_filtros(qs, filtros):
    if 'departamento' in filtros:
        qs = qs.filter(departamento_id__in=filtros['departamento'])
    if 'tipo' in filtros:
        qs = qs.filter(tipo_id__in=filtros['tipo'])
    if 'prioridade' in filtros:
        qs = qs.filter(prioridade_id__in=filtros['prioridade'])
    return qs


def _montar_payload(filtros=None):
    filtros = filtros or {}
    agora = timezone.now()
    cal = sla.carregar_calendario()

    # `atendente` (quem abriu) dá a coluna; `responsavel` (quem resolve) vai no
    # card. Ambos no select_related: sem isso é uma query por ticket.
    base = Ticket.objects.select_related(
        'cliente', 'prioridade', 'departamento', 'responsavel', 'atendente')
    base = _aplicar_filtros(base, filtros)

    # A TV mostra o que está VIVO: aberto ou em atendimento. Encerrado/cancelado
    # sai da tela. Não existe "fila sem dono" — todo ticket tem quem o abriu; o
    # que pode faltar é quem o resolva.
    vivos_qs = base.filter(status__in=[Ticket.ABERTO, Ticket.EM_ATENDIMENTO])

    # Com o grupo configurado, o corte é aqui e não no agrupamento: um ticket que
    # não vai virar coluna também não pode contar no KPI nem viajar no JSON —
    # senão a tela diz "17 na fila" e mostra 12 cards.
    fixos = _atendentes_fixos()
    if fixos:
        vivos_qs = vivos_qs.filter(atendente__in=fixos)

    # Sem responsável, o relógio corre contra a meta de RESPOSTA; com alguém
    # resolvendo, contra a de RESOLUÇÃO — sempre desde criado_em, porque o
    # cliente não tem culpa do tempo que o chamado ficou parado.
    todos = [
        _item(t, agora, cal,
              'minutos_resolucao' if t.status == Ticket.EM_ATENDIMENTO else 'minutos_resposta')
        for t in vivos_qs
    ]

    # O que chegou na semana fica nas colunas; o resto vira contador. Sem isso a
    # coluna do Henrique abriria com 45 cards, quase todos de meses atrás.
    itens = [i for i in todos if i['idade_dias'] <= DIAS_FILA_DO_DIA]
    parados = [i for i in todos if i['idade_dias'] > DIAS_FILA_DO_DIA]

    # Quem espera há mais tempo primeiro — é a regra pedida, e por sorte é
    # ESTÁVEL: todo ticket envelhece na mesma taxa, então dois cards nunca se
    # ultrapassam. (Ordenar por `pct` seria instável: metas diferentes fazem o
    # percentual correr em velocidades diferentes, os cards se cruzam e trocam de
    # lugar debaixo do olho de quem lê a parede.)
    itens.sort(key=lambda i: -i['idade_dias'])
    parados.sort(key=lambda i: -i['idade_dias'])

    fechamento = sla.proximo_fechamento(agora, cal)
    aberto = fechamento is not None

    # Sem nenhum Expediente cadastrado não há "próxima abertura" — a tela avisa o
    # que falta em vez de estourar 500 numa TV que ninguém está olhando de perto.
    try:
        abre_em = None if aberto else sla.proxima_abertura(agora, cal).isoformat()
        configurado = True
    except ImproperlyConfigured:
        abre_em = None
        configurado = False

    # Range explícito, e NÃO `encerrado_em__date=hoje`: o MySQL daqui não tem as
    # tabelas de timezone instaladas, então __date não estoura — devolve VAZIO em
    # silêncio. O KPI ficaria zerado para sempre e pareceria só um dia fraco.
    hoje = timezone.localdate()
    inicio_hoje = timezone.make_aware(datetime.combine(hoje, time.min))
    fim_hoje = timezone.make_aware(datetime.combine(hoje, time.max))
    encerrados_hoje = _aplicar_filtros(
        Ticket.objects.filter(encerrado_em__gte=inicio_hoje, encerrado_em__lte=fim_hoje,
                              status=Ticket.ENCERRADO),
        filtros).count()

    return {
        'gerado_em': agora.isoformat(),
        'expediente_aberto': aberto,
        'expediente_fecha_em': fechamento.isoformat() if fechamento else None,
        'expediente_abre_em': abre_em,
        'expediente_configurado': configurado,
        'cortes': {'atencao': PCT_ATENCAO, 'estouro': PCT_ESTOURO},
        'dias_fila_do_dia': DIAS_FILA_DO_DIA,
        # Quanto vale um "dia" para o JS formatar o cronômetro. Não é 1440: o
        # relógio conta minutos ÚTEIS, então o dia é o expediente cadastrado.
        # Quem sabe disso é o servidor — o JS não tem calendário.
        'minutos_por_dia_util': sla.minutos_por_dia_util(cal),
        # Lista única e plana: é a fonte de cada card. As colunas só carregam ids.
        'itens': itens,
        'por_atendente': _agrupar_por_atendente(itens, fixos),
        'resumo': {
            'fila_total': sum(1 for i in itens if not i['em_atendimento']),
            'atendimento_total': sum(1 for i in itens if i['em_atendimento']),
            'estourados': sum(1 for i in itens if i['cor'] == 'vermelho'),
            'encerrados_hoje': encerrados_hoje,
            # A dívida antiga fica visível como número, mesmo fora das colunas.
            'parados_total': len(parados),
            'parados_mais_antigo_dias': parados[0]['idade_dias'] if parados else 0,
        },
    }


@require_GET
def painel_tv(request):
    if not _autorizado(request):
        return _negado(request)

    from .models import Departamento, Prioridade, Tipo
    from .views import e_diretoria

    filtros = _filtros(request)
    # O montador de link só aparece para quem está logado — na TV em modo
    # quiosque (token) não há ninguém para clicar.
    pode_configurar = request.user.is_authenticated
    # O token é o que abre o painel sem senha: só quem monta TV precisa vê-lo.
    pode_ver_token = pode_configurar and e_diretoria(request.user)
    token_tv = getattr(settings, 'PAINEL_TV_TOKEN', '')

    return render(request, 'core/painel_tv.html', {
        'token': request.GET.get('k', ''),
        # Sempre as 3 chaves como lista: no template, `{% if x in filtros.tipo %}`
        # com a chave ausente viraria `x in ''` e estouraria TypeError.
        'filtros': {c: filtros.get(c, []) for c in ('departamento', 'tipo', 'prioridade')},
        'rotulo_filtros': _rotulo(filtros),
        'pode_configurar': pode_configurar,
        'pode_ver_token': pode_ver_token,
        # Sem sessão só se entra por token: é a TV na parede, não o navegador de
        # alguém. Lá a rolagem é funcional (sem ela o card fica invisível), então
        # o painel ignora prefers-reduced-motion — que continua valendo para
        # quem abre /tv/ logado.
        'modo_quiosque': not request.user.is_authenticated,
        # Sem token configurado não existe modo quiosque — a tela diz isso em vez
        # de entregar um link que vai cair no login da TV.
        'token_tv': token_tv if pode_ver_token else '',
        'token_configurado': bool(token_tv),
        'departamentos': Departamento.objects.all(),
        'tipos': Tipo.objects.select_related('departamento').order_by('departamento__descricao', 'descricao'),
        'prioridades': Prioridade.objects.all(),
    })


@require_GET
def painel_tv_dados(request):
    if not _autorizado(request):
        return JsonResponse({'error': 'não autorizado'}, status=403)

    filtros = _filtros(request)
    # A chave inclui os filtros: sem isso a TV do Suporte serviria o cache da TV
    # do Dev por até 20s. Os ids viram "1-2" e não "[1, 2]": chave de cache com
    # espaço é inválida em memcached, e hoje só funciona porque o backend é local.
    chave = CACHE_KEY_PAYLOAD + ':' + ','.join(
        '%s=%s' % (k, '-'.join(str(i) for i in v)) for k, v in sorted(filtros.items()))
    payload = cache.get(chave)
    if payload is None:
        payload = _montar_payload(filtros)
        cache.set(chave, payload, CACHE_TTL_PAYLOAD)
    return JsonResponse(payload)


def _negado(request):
    from django.contrib.auth.views import redirect_to_login
    return redirect_to_login(request.get_full_path())
