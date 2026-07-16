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
    """Ex.: 'Desenvolvimento · Correção'. Vai no cabeçalho da TV.

    Quem olha a tela da parede precisa saber que está vendo um recorte — senão lê
    'fila: 3' e conclui que a empresa inteira tem 3 tickets."""
    from .models import Departamento, Prioridade, Tipo
    partes = []
    if 'departamento' in filtros:
        d = Departamento.objects.filter(pk=filtros['departamento']).first()
        if d:
            partes.append(d.descricao)
    if 'tipo' in filtros:
        t = Tipo.objects.filter(pk=filtros['tipo']).first()
        if t:
            partes.append(t.descricao)
    if 'prioridade' in filtros:
        p = Prioridade.objects.filter(pk=filtros['prioridade']).first()
        if p:
            partes.append(p.descricao)
    return ' · '.join(partes)


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

    return {
        'id': ticket.id,
        'titulo': ticket.titulo or f'Ticket #{ticket.id}',
        'cliente': ticket.cliente.fantasia if ticket.cliente_id else '',
        'departamento': ticket.departamento.descricao if ticket.departamento_id else 'Sem departamento',
        'departamento_id': ticket.departamento_id or 0,
        'prioridade': ticket.prioridade.descricao if ticket.prioridade_id else '',
        'peso': ticket.prioridade.peso if ticket.prioridade_id else 0,
        'consumido_min': consumido,
        'meta_min': meta,
        'pct': pct,
        'idade_dias': idade_dias,
        'antigo': antigo,
        'cor': _cor(pct, sem_sla),
        'sem_sla': sem_sla,
    }


def _filtros(request):
    """Filtros da TV, vindos da URL.

    A TV é uma tela em quiosque: não tem quem clique nela. Então o que ela mostra
    é decidido no link — /tv/?k=TOKEN&departamento=2 é a TV do Dev, outro link é a
    do Suporte. Ver o montador de link no template.
    """
    out = {}
    for campo in ('departamento', 'tipo', 'prioridade'):
        v = request.GET.get(campo)
        if v and v.isdigit():
            out[campo] = int(v)
    return out


def _aplicar_filtros(qs, filtros):
    if 'departamento' in filtros:
        qs = qs.filter(departamento_id=filtros['departamento'])
    if 'tipo' in filtros:
        qs = qs.filter(tipo_id=filtros['tipo'])
    if 'prioridade' in filtros:
        qs = qs.filter(prioridade_id=filtros['prioridade'])
    return qs


def _montar_payload(filtros=None):
    filtros = filtros or {}
    agora = timezone.now()
    cal = sla.carregar_calendario()

    base = Ticket.objects.select_related('cliente', 'prioridade', 'departamento')
    base = _aplicar_filtros(base, filtros)

    # Fila: ninguém pegou ainda. O relógio corre contra a meta de RESPOSTA.
    fila_qs = base.filter(status=Ticket.ABERTO, responsavel__isnull=True)
    # Em atendimento: alguém pegou. O relógio corre contra a meta de RESOLUÇÃO,
    # contada desde criado_em — o cliente não tem culpa se ficou 3h na fila.
    atend_qs = base.filter(status=Ticket.EM_ATENDIMENTO)

    fila_toda = [_item(t, agora, cal, 'minutos_resposta') for t in fila_qs]
    atendimento = [_item(t, agora, cal, 'minutos_resolucao') for t in atend_qs]

    # Fila do dia x dívida antiga. Os antigos não somem: viram um contador, para
    # a tela ser legível sem varrer o problema para debaixo do tapete.
    fila = [i for i in fila_toda if i['idade_dias'] <= DIAS_FILA_DO_DIA]
    parados = [i for i in fila_toda if i['idade_dias'] > DIAS_FILA_DO_DIA]

    # Agrupado por departamento (o JS quebra a lista onde o departamento muda),
    # e dentro dele: mais urgente primeiro, depois quem espera há mais tempo.
    # Ordem alfabética de departamento de propósito — numa TV que fica ligada o
    # dia todo, grupo que troca de lugar sozinho é grupo que ninguém acompanha.
    # Ordenamos por idade_dias e não por consumido_min: este último é None nos antigos.
    fila.sort(key=lambda i: (i['departamento'], -i['peso'], -i['idade_dias']))
    atendimento.sort(key=lambda i: (i['departamento'], -i['pct'], -i['idade_dias']))
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

    # Contagem por departamento, incluindo a dívida antiga — para o cabeçalho de
    # cada grupo dizer o tamanho do problema, não só o que coube na tela.
    por_depto = {}

    def _conta(itens, chave):
        for i in itens:
            d = por_depto.setdefault(i['departamento'], {
                'departamento': i['departamento'], 'fila': 0, 'atendimento': 0,
                'parados': 0, 'estourados': 0})
            d[chave] += 1
            if i['cor'] == 'vermelho':
                d['estourados'] += 1

    _conta(fila, 'fila')
    _conta(atendimento, 'atendimento')
    _conta(parados, 'parados')

    return {
        'gerado_em': agora.isoformat(),
        'expediente_aberto': aberto,
        'expediente_fecha_em': fechamento.isoformat() if fechamento else None,
        'expediente_abre_em': abre_em,
        'expediente_configurado': configurado,
        'cortes': {'atencao': PCT_ATENCAO, 'estouro': PCT_ESTOURO},
        'dias_fila_do_dia': DIAS_FILA_DO_DIA,
        'fila': fila,
        'atendimento': atendimento,
        'por_departamento': sorted(por_depto.values(), key=lambda d: d['departamento']),
        'resumo': {
            'fila_total': len(fila),
            'atendimento_total': len(atendimento),
            'estourados': sum(1 for i in fila + atendimento if i['cor'] == 'vermelho'),
            'encerrados_hoje': encerrados_hoje,
            # A dívida antiga fica visível como número, mesmo fora das listas.
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
        'filtros': filtros,
        'rotulo_filtros': _rotulo(filtros),
        'pode_configurar': pode_configurar,
        'pode_ver_token': pode_ver_token,
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
    # do Dev por até 20s.
    chave = CACHE_KEY_PAYLOAD + ':' + ','.join(f'{k}={v}' for k, v in sorted(filtros.items()))
    payload = cache.get(chave)
    if payload is None:
        payload = _montar_payload(filtros)
        cache.set(chave, payload, CACHE_TTL_PAYLOAD)
    return JsonResponse(payload)


def _negado(request):
    from django.contrib.auth.views import redirect_to_login
    return redirect_to_login(request.get_full_path())
