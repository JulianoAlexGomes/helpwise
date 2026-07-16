"""Relatórios de atendimento: tela + exportação PDF/Excel.

Módulo separado (views.py já passa de 2100 linhas).

As seções são montadas UMA vez em `_secoes()` e servem tela, Excel e PDF. Se um
número aparece na tela, é o mesmo do Excel e do PDF — nunca três verdades.
"""

from datetime import datetime, time

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone

from .models import Departamento, Prioridade, Ticket, Tipo
from .services import export, relatorios
from .views import e_diretoria, tickets_visiveis_para

# Um ticket parado há mais que isso entra no relatório de dívida.
DIAS_DIVIDA = 7


def _periodo(request):
    hoje = timezone.localdate()
    ini_str = request.GET.get('data_inicio')
    fim_str = request.GET.get('data_fim')
    try:
        ini = datetime.strptime(ini_str, '%Y-%m-%d').date() if ini_str else hoje.replace(day=1)
        fim = datetime.strptime(fim_str, '%Y-%m-%d').date() if fim_str else hoje
    except ValueError:
        raise Http404('Data inválida.')
    return ini, fim


def _base(request):
    """Permissão + filtros de dimensão (departamento/prioridade). SEM recorte de data.

    Separado do período de propósito: o relatório de dívida é uma foto do estado
    ATUAL — um ticket parado há 300 dias não pode sumir da lista só porque o
    filtro de data é "este mês". Mas ele tem que respeitar departamento e
    prioridade como todo o resto.
    """
    qs = tickets_visiveis_para(request.user, Ticket.objects.all())

    dep = request.GET.get('departamento')
    pri = request.GET.get('prioridade')
    tip = request.GET.get('tipo')
    if dep:
        qs = qs.filter(departamento_id=dep)
    if pri:
        qs = qs.filter(prioridade_id=pri)
    if tip:
        qs = qs.filter(tipo_id=tip)
    return qs


def _queryset(request, ini, fim):
    """`_base` + o recorte do período. É o que alimenta conformidade e volume."""
    return _base(request).filter(
        criado_em__gte=timezone.make_aware(datetime.combine(ini, time.min)),
        criado_em__lte=timezone.make_aware(datetime.combine(fim, time.max)),
    )


def _min(v):
    return export.minutos_legivel(v)


def _pct(v):
    """None (sem denominador) vira travessão, não '0%'."""
    return f'{v}%' if v is not None else '—'


def _secoes(request, ini, fim):
    """Monta tudo. Devolve (secoes, contexto_extra, avisos)."""
    qs = _queryset(request, ini, fim)
    linhas = relatorios.coletar(qs)
    diretoria = e_diretoria(request.user)

    geral = relatorios.geral(linhas)
    por_dep = relatorios.conformidade(linhas, por='departamento')
    por_pri = relatorios.conformidade(linhas, por='prioridade')
    por_tipo = relatorios.conformidade(linhas, por='tipo')
    volume = relatorios.volume_semanal(qs)
    # `_base` e não `_queryset`: a dívida respeita departamento/prioridade, mas
    # ignora o período — é estado atual, não histórico do recorte.
    divida = relatorios.divida(DIAS_DIVIDA, qs=_base(request))

    secoes = [
        {
            'titulo': 'Conformidade de SLA por departamento',
            'colunas': ['Departamento', 'Tickets', 'Resp. no prazo', 'Resol. no prazo',
                        'Resposta (mediana)', 'Resolução (mediana)'],
            'linhas': [[d['grupo'], d['total'], _pct(d['sla_resposta_pct']), _pct(d['sla_resolucao_pct']),
                        _min(d['resposta_mediana']), _min(d['resolucao_mediana'])] for d in por_dep],
        },
        {
            'titulo': 'Conformidade de SLA por prioridade',
            'colunas': ['Prioridade', 'Tickets', 'Resp. no prazo', 'Resol. no prazo',
                        'Resposta (mediana)', 'Resolução (mediana)'],
            'linhas': [[d['grupo'], d['total'], _pct(d['sla_resposta_pct']), _pct(d['sla_resolucao_pct']),
                        _min(d['resposta_mediana']), _min(d['resolucao_mediana'])] for d in por_pri],
        },
        {
            'titulo': 'Conformidade de SLA por tipo',
            'colunas': ['Tipo', 'Tickets', 'Resp. no prazo', 'Resol. no prazo',
                        'Resposta (mediana)', 'Resolução (mediana)'],
            'linhas': [[d['grupo'], d['total'], _pct(d['sla_resposta_pct']), _pct(d['sla_resolucao_pct']),
                        _min(d['resposta_mediana']), _min(d['resolucao_mediana'])] for d in por_tipo],
        },
        {
            'titulo': 'Volume por semana (entradas x saídas)',
            'colunas': ['Semana', 'Abertos', 'Encerrados', 'Saldo'],
            'linhas': [[v['semana'].strftime('%d/%m/%Y'), v['entradas'], v['saidas'],
                        f"{v['saldo']:+d}"] for v in volume],
        },
        {
            'titulo': f'Tickets parados há mais de {DIAS_DIVIDA} dias (situação atual, independe do período)',
            'colunas': ['#', 'Dias', 'Status', 'Departamento', 'Prioridade', 'Responsável', 'Cliente', 'Título'],
            'linhas': [[d['id'], d['idade_dias'], d['status'], d['departamento'], d['prioridade'],
                        d['responsavel'], d['cliente'], d['titulo']] for d in divida],
        },
    ]

    # Produtividade individual é só para a Diretoria — não vaza comparativo de
    # atendente para quem não deveria ver.
    if diretoria:
        prod = relatorios.produtividade(linhas)
        secoes.insert(2, {
            'titulo': 'Produtividade por atendente',
            'colunas': ['Atendente', 'Tickets', 'Respondidos', 'Resolvidos',
                        'Resposta (mediana)', 'Resolução (mediana)'],
            'linhas': [[p['atendente'], p['total'], p['respondidos'], p['resolvidos'],
                        _min(p['resposta_mediana']), _min(p['resolucao_mediana'])] for p in prod],
        })

    avisos = []
    # `estimado_pct` é None quando não há ticket nenhum no período — `None > 0`
    # estouraria.
    if geral['estimado_pct']:
        avisos.append(
            f"{geral['estimado_pct']}% dos tickets deste período têm histórico RECONSTRUÍDO "
            f"a partir das Soluções e dos timestamps antigos, porque o registro de eventos "
            f"passou a existir em 16/07/2026. Reaberturas anteriores a essa data são "
            f"invisíveis, então estes números SUBCONTAM retrabalho e, portanto, "
            f"SUPERESTIMAM a performance. Números totalmente medidos só a partir de 16/07/2026."
        )
    if diretoria:
        avisos.append(
            'Produtividade por atendente: no histórico reconstruído o ticket é atribuído ao '
            'responsável ATUAL, não necessariamente a quem o atendeu — a troca de responsável '
            'nunca foi registrada. Use como ordem de grandeza, não como avaliação individual.'
        )

    return secoes, {'geral': geral, 'por_dep': por_dep, 'divida': divida}, avisos


def _subtitulo(request, ini, fim):
    partes = [f'Período: {ini:%d/%m/%Y} a {fim:%d/%m/%Y}']
    dep = request.GET.get('departamento')
    pri = request.GET.get('prioridade')
    if dep:
        d = Departamento.objects.filter(pk=dep).first()
        if d:
            partes.append(f'Departamento: {d.descricao}')
    if pri:
        p = Prioridade.objects.filter(pk=pri).first()
        if p:
            partes.append(f'Prioridade: {p.descricao}')
    tip = request.GET.get('tipo')
    if tip:
        t = Tipo.objects.filter(pk=tip).first()
        if t:
            partes.append(f'Tipo: {t.descricao}')
    if not e_diretoria(request.user):
        partes.append(f'Apenas os tickets de {request.user.get_full_name() or request.user.username}')
    return ' · '.join(partes)


@login_required
def relatorios_view(request):
    ini, fim = _periodo(request)
    secoes, extra, avisos = _secoes(request, ini, fim)
    return render(request, 'core/relatorios.html', {
        'secoes': secoes,
        'avisos': avisos,
        'subtitulo': _subtitulo(request, ini, fim),
        'data_inicio': ini.strftime('%Y-%m-%d'),
        'data_fim': fim.strftime('%Y-%m-%d'),
        'departamentos': Departamento.objects.all(),
        'prioridades': Prioridade.objects.all(),
        'tipos': Tipo.objects.select_related('departamento').order_by('departamento__descricao', 'descricao'),
        'departamento_selecionado': request.GET.get('departamento', ''),
        'prioridade_selecionada': request.GET.get('prioridade', ''),
        'tipo_selecionado': request.GET.get('tipo', ''),
        'e_diretoria': e_diretoria(request.user),
        **extra,
    })


@login_required
def relatorios_excel(request):
    ini, fim = _periodo(request)
    secoes, _, avisos = _secoes(request, ini, fim)
    # O aviso sobre dado reconstruído vai junto: uma planilha viaja por e-mail
    # sem o contexto da tela onde foi gerada.
    secoes = [{'titulo': 'Leia antes', 'colunas': ['Avisos'],
               'linhas': [[a] for a in avisos] or [['Sem ressalvas.']]}] + secoes
    return export.to_excel(secoes, nome='relatorio_atendimento')


@login_required
def relatorios_pdf(request):
    ini, fim = _periodo(request)
    secoes, _, avisos = _secoes(request, ini, fim)
    return export.to_pdf(secoes, titulo='Relatório de Atendimento',
                         subtitulo=_subtitulo(request, ini, fim),
                         avisos=avisos, nome='relatorio_atendimento')
