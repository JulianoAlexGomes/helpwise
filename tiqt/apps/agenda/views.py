import calendar
from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from .forms import AgendamentoForm
from .models import Agendamento

User = get_user_model()

MESES_PT = [
    '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]
# Calendário começando no domingo (padrão brasileiro)
DIAS_PT = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb']
# weekday() do Python: Seg=0 … Dom=6
DOW_SHORT = {6: 'Dom', 0: 'Seg', 1: 'Ter', 2: 'Qua', 3: 'Qui', 4: 'Sex', 5: 'Sáb'}
DOW_LONG = {
    6: 'Domingo', 0: 'Segunda-feira', 1: 'Terça-feira', 2: 'Quarta-feira',
    3: 'Quinta-feira', 4: 'Sexta-feira', 5: 'Sábado',
}
HOUR_HEIGHT = 48  # px por hora nas visões semana/dia
VIEWS = ('mes', 'semana', 'dia')


def _redirect_agenda(ag=None, view='mes', ref=None):
    """Redireciona para a agenda preservando a visão; se vier um agendamento,
    aponta para a data dele."""
    if ag is not None:
        ref = timezone.localtime(ag.inicio).date().isoformat()
    params = []
    if view:
        params.append(f'view={view}')
    if ref:
        params.append(f'ref={ref}')
    url = reverse('agenda')
    if params:
        url += '?' + '&'.join(params)
    return redirect(url)


def _posicionar(ag):
    """Calcula top/altura (px) do evento na grade de horários."""
    lt = timezone.localtime(ag.inicio)
    start_min = lt.hour * 60 + lt.minute
    if ag.fim:
        dur = (timezone.localtime(ag.fim) - lt).total_seconds() / 60
    else:
        dur = 45
    dur = max(dur, 30)
    ag._start = start_min
    ag._end = start_min + dur
    ag.top = round(start_min / 60 * HOUR_HEIGHT, 1)
    ag.height = round(dur / 60 * HOUR_HEIGHT, 1)
    ag.left = 0
    ag.width = 100
    return ag


def _layout_dia(eventos):
    """Distribui eventos que se sobrepõem no tempo em colunas lado a lado
    (estilo Google). Define ag.left e ag.width (em %) para cada evento."""
    itens = sorted(eventos, key=lambda a: (a._start, a._end))

    grupo = []
    grupo_fim = None

    def fechar(grupo):
        colunas = []  # fim do último evento de cada coluna
        for ag in grupo:
            alocado = False
            for ci, fim_col in enumerate(colunas):
                if ag._start >= fim_col:
                    colunas[ci] = ag._end
                    ag._col = ci
                    alocado = True
                    break
            if not alocado:
                ag._col = len(colunas)
                colunas.append(ag._end)
        ncols = len(colunas) or 1
        largura = 100.0 / ncols
        for ag in grupo:
            ag.width = round(largura, 2)
            ag.left = round(ag._col * largura, 2)

    for ag in itens:
        if grupo and ag._start >= grupo_fim:
            fechar(grupo)
            grupo = []
            grupo_fim = None
        grupo.append(ag)
        grupo_fim = ag._end if grupo_fim is None else max(grupo_fim, ag._end)
    if grupo:
        fechar(grupo)


class CalendarioView(LoginRequiredMixin, View):
    template_name = 'agenda/calendario.html'

    def get(self, request):
        hoje = timezone.localdate()
        view = request.GET.get('view', 'mes')
        if view not in VIEWS:
            view = 'mes'

        raw_ref = request.GET.get('ref')
        ref = hoje
        if raw_ref:
            try:
                ref = datetime.strptime(raw_ref, '%Y-%m-%d').date()
            except ValueError:
                ref = hoje

        resp_id = request.GET.get('resp') or ''
        atend_id = request.GET.get('atend') or ''

        def eventos(ini_date, fim_date):
            ini = timezone.make_aware(datetime.combine(ini_date, time.min))
            fim = timezone.make_aware(datetime.combine(fim_date, time.max))
            qs = (
                Agendamento.objects
                .filter(inicio__range=(ini, fim))
                .exclude(status=Agendamento.CANCELADO)
                .select_related('ticket', 'cliente', 'responsavel')
            )
            if resp_id:
                qs = qs.filter(responsavel_id=resp_id)
            if atend_id:
                qs = qs.filter(ticket__atendente_id=atend_id)
            return qs

        ctx = {
            'view': view,
            'ref': ref.isoformat(),
            'resp_id': str(resp_id),
            'atend_id': str(atend_id),
            # Query-strings prontas para preservar filtros nos links de navegação.
            'filtros_qs': (f'&resp={resp_id}' if resp_id else '') + (f'&atend={atend_id}' if atend_id else ''),
            'qs_resp': f'&resp={resp_id}' if resp_id else '',     # preserva só o responsável
            'qs_atend': f'&atend={atend_id}' if atend_id else '',  # preserva só o atendente
            'hoje': hoje,
            'usuarios': User.objects.filter(is_active=True).order_by('first_name', 'username'),
            'form': AgendamentoForm(initial={'responsavel': request.user}),
            'dias_semana': DIAS_PT,
            'horas': ['%02d:00' % h for h in range(24)],
            'hour_height': HOUR_HEIGHT,
        }

        if view == 'mes':
            cal = calendar.Calendar(firstweekday=6)  # domingo
            semanas_datas = cal.monthdatescalendar(ref.year, ref.month)
            qs = eventos(semanas_datas[0][0], semanas_datas[-1][-1])
            por_dia = {}
            for ag in qs:
                por_dia.setdefault(timezone.localtime(ag.inicio).date(), []).append(ag)
            semanas = [
                [{
                    'data': d, 'dia': d.day, 'no_mes': d.month == ref.month,
                    'hoje': d == hoje, 'eventos': por_dia.get(d, []),
                } for d in semana]
                for semana in semanas_datas
            ]
            primeiro = ref.replace(day=1)
            prev_ref = (primeiro - timedelta(days=1)).replace(day=1)
            next_ref = date(ref.year + (ref.month == 12), (ref.month % 12) + 1, 1)
            ctx.update({
                'titulo': f"{MESES_PT[ref.month]} {ref.year}",
                'semanas': semanas,
                'nav_ant': prev_ref.isoformat(),
                'nav_prox': next_ref.isoformat(),
                'total': qs.count(),
            })
        else:
            if view == 'semana':
                inicio_sem = ref - timedelta(days=(ref.weekday() + 1) % 7)  # domingo
                dias_datas = [inicio_sem + timedelta(days=i) for i in range(7)]
                prev_ref = inicio_sem - timedelta(days=7)
                next_ref = inicio_sem + timedelta(days=7)
                d0, d1 = dias_datas[0], dias_datas[-1]
                if d0.month == d1.month:
                    titulo = f"{d0.day} – {d1.day} de {MESES_PT[d1.month]} {d1.year}"
                else:
                    titulo = (f"{d0.day} de {MESES_PT[d0.month]} – "
                              f"{d1.day} de {MESES_PT[d1.month]} {d1.year}")
            else:  # dia
                dias_datas = [ref]
                prev_ref = ref - timedelta(days=1)
                next_ref = ref + timedelta(days=1)
                titulo = f"{DOW_LONG[ref.weekday()]}, {ref.day} de {MESES_PT[ref.month]} {ref.year}"

            qs = eventos(dias_datas[0], dias_datas[-1])
            por_dia = {}
            for ag in qs:
                _posicionar(ag)
                por_dia.setdefault(timezone.localtime(ag.inicio).date(), []).append(ag)
            for evs in por_dia.values():
                _layout_dia(evs)

            dias = [{
                'data': d, 'dia': d.day, 'dow': DOW_SHORT[d.weekday()],
                'dow_long': DOW_LONG[d.weekday()], 'hoje': d == hoje,
                'eventos': por_dia.get(d, []),
            } for d in dias_datas]

            ctx.update({
                'titulo': titulo,
                'dias': dias,
                'ncols': len(dias),
                'nav_ant': prev_ref.isoformat(),
                'nav_prox': next_ref.isoformat(),
                'total': qs.count(),
            })

        return render(request, self.template_name, ctx)


def _view_do_post(request):
    v = request.POST.get('_view')
    return v if v in VIEWS else 'mes'


class AgendamentoCreateView(LoginRequiredMixin, View):
    def post(self, request):
        view = _view_do_post(request)
        form = AgendamentoForm(request.POST)
        if form.is_valid():
            ag = form.save(commit=False)
            ag.origem = Agendamento.AVULSO
            ag.criado_por = request.user
            ag.save()
            messages.success(request, 'Agendamento criado.')
            return _redirect_agenda(ag, view=view)
        messages.error(request, 'Não foi possível criar o agendamento. Verifique os campos.')
        return _redirect_agenda(view=view, ref=request.POST.get('_ref'))


class AgendamentoUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ag = get_object_or_404(Agendamento, pk=pk)
        view = _view_do_post(request)
        form = AgendamentoForm(request.POST, instance=ag)
        if form.is_valid():
            obj = form.save(commit=False)
            # Mudou a data -> volta a notificar
            obj.notificado = False
            obj.save()
            messages.success(request, 'Agendamento atualizado.')
            return _redirect_agenda(obj, view=view)
        messages.error(request, 'Não foi possível salvar as alterações.')
        return _redirect_agenda(ag, view=view)


class AgendamentoConcluirView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ag = get_object_or_404(Agendamento, pk=pk)
        ag.concluir()
        messages.success(request, 'Agendamento concluído.')
        return _redirect_agenda(ag, view=_view_do_post(request))


class AgendamentoCancelarView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ag = get_object_or_404(Agendamento, pk=pk)
        ag.cancelar()
        messages.success(request, 'Agendamento cancelado.')
        return _redirect_agenda(ag, view=_view_do_post(request))


class AgendamentoDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ag = get_object_or_404(Agendamento, pk=pk)
        view = _view_do_post(request)
        destino = _redirect_agenda(ag, view=view)
        ag.delete()
        messages.success(request, 'Agendamento excluído.')
        return destino


def _alertas_pendentes(user):
    """Agendamentos do usuário cujo dia chegou e que ainda não foram avisados."""
    hoje = timezone.localdate()
    fim_do_dia = timezone.make_aware(datetime.combine(hoje, time.max))
    return (
        Agendamento.objects.filter(
            responsavel=user,
            status=Agendamento.PENDENTE,
            notificado=False,
            inicio__lte=fim_do_dia,
        )
        .select_related('ticket')
        .order_by('inicio')
    )


class AlertasDoDiaView(LoginRequiredMixin, View):
    """GET: lista os avisos do dia (para o modal). POST: marca como vistos
    (`notificado=True`) para não abrir o modal de novo."""

    def get(self, request):
        hoje = timezone.localdate()
        alertas = []
        for ag in _alertas_pendentes(request.user):
            quando = timezone.localtime(ag.inicio)
            alertas.append({
                'id': ag.id,
                'titulo': ag.titulo,
                'hora': quando.strftime('%H:%M'),
                'data': quando.strftime('%d/%m'),
                'hoje': quando.date() == hoje,
                'ticket': ag.ticket_id,
                'url': ag.get_url_destino(),
            })
        return JsonResponse({'alertas': alertas})

    def post(self, request):
        qs = _alertas_pendentes(request.user)
        ids = request.POST.getlist('ids') or request.POST.getlist('ids[]')
        if ids:
            qs = qs.filter(id__in=ids)
        qs.update(notificado=True)
        return JsonResponse({'ok': True})
