from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from tiqt.apps.agenda.models import Agendamento

from .forms import CategoriaNotaForm, NotaForm
from .models import CategoriaNota, Nota, NotaArquivo

User = get_user_model()


def _redirect_mural(request):
    """Volta ao mural preservando os filtros ativos (categoria/status/resp/arquivadas)."""
    params = {}
    for chave in ('categoria', 'status', 'resp', 'arquivadas', 'catmodal'):
        valor = request.POST.get(chave) or request.GET.get(chave)
        if valor:
            params[chave] = valor
    url = reverse('mural')
    if params:
        url += '?' + urlencode(params)
    return redirect(url)


class MuralView(LoginRequiredMixin, TemplateView):
    template_name = 'mural/mural.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        req = self.request

        cat_id = req.GET.get('categoria') or ''
        status = req.GET.get('status') or ''
        resp_id = req.GET.get('resp') or ''
        ver_arquivadas = req.GET.get('arquivadas') == '1'

        notas = (
            Nota.objects
            .select_related('categoria', 'responsavel', 'agendamento')
            .prefetch_related('arquivos')
        )
        if not ver_arquivadas:
            notas = notas.exclude(status=Nota.ARQUIVADA)
        if cat_id:
            notas = notas.filter(categoria_id=cat_id)
        if status != '':
            notas = notas.filter(status=status)
        if resp_id:
            notas = notas.filter(responsavel_id=resp_id)

        categorias = CategoriaNota.objects.filter(ativo=True)

        # Contagem por categoria (respeitando o filtro de arquivadas).
        base_count = Nota.objects.all()
        if not ver_arquivadas:
            base_count = base_count.exclude(status=Nota.ARQUIVADA)
        contagens = dict(
            base_count.values_list('categoria_id').annotate(n=Count('id'))
        )
        for c in categorias:
            c.n_notas = contagens.get(c.id, 0)

        notas = list(notas)
        n_urgentes = sum(1 for n in notas if n.prioridade == Nota.URGENTE and not n.arquivada)

        ctx.update({
            'notas': notas,
            'categorias': categorias,
            'total': len(notas),
            'n_urgentes': n_urgentes,
            'total_geral': base_count.count(),
            'sem_categoria': contagens.get(None, 0),
            'usuarios': User.objects.filter(is_active=True).order_by('first_name', 'username'),
            'status_choices': Nota.STATUS,
            'prioridade_choices': Nota.PRIORIDADE,
            'form': NotaForm(),
            'categoria_form': CategoriaNotaForm(),
            # filtros ativos
            'f_categoria': str(cat_id),
            'f_status': str(status),
            'f_resp': str(resp_id),
            'ver_arquivadas': ver_arquivadas,
            # constantes p/ o template
            'STATUS_ARQUIVADA': Nota.ARQUIVADA,
            'STATUS_CONCLUIDA': Nota.CONCLUIDA,
        })
        return ctx


def _sync_agendamento(nota, agendar_em, user):
    """Cria/atualiza/remove o Agendamento vinculado conforme `agendar_em`."""
    if agendar_em:
        responsavel = nota.responsavel or user
        ag = nota.agendamento
        if ag is None:
            ag = Agendamento(origem=Agendamento.AVULSO, criado_por=user)
        ag.titulo = nota.titulo[:120]
        ag.descricao = nota.conteudo
        ag.inicio = agendar_em
        ag.responsavel = responsavel
        ag.notificado = False
        ag.save()
        if nota.agendamento_id != ag.id:
            nota.agendamento = ag
            nota.save(update_fields=['agendamento'])
    elif nota.agendamento_id:
        # Removeu a data -> apaga o evento vinculado.
        ag = nota.agendamento
        nota.agendamento = None
        nota.save(update_fields=['agendamento'])
        ag.delete()


def _salvar_arquivos(request, nota):
    for arquivo in request.FILES.getlist('arquivos'):
        NotaArquivo.objects.create(nota=nota, arquivo=arquivo)


class NotaCreateView(LoginRequiredMixin, View):
    def post(self, request):
        form = NotaForm(request.POST)
        if form.is_valid():
            nota = form.save(commit=False)
            nota.autor = request.user
            nota.save()
            _salvar_arquivos(request, nota)
            _sync_agendamento(nota, form.cleaned_data.get('agendar_em'), request.user)
            messages.success(request, 'Nota criada.')
        else:
            messages.error(request, 'Não foi possível criar a nota. Verifique os campos.')
        return _redirect_mural(request)


class NotaUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        nota = get_object_or_404(Nota, pk=pk)
        form = NotaForm(request.POST, instance=nota)
        if form.is_valid():
            nota = form.save()
            _salvar_arquivos(request, nota)
            _sync_agendamento(nota, form.cleaned_data.get('agendar_em'), request.user)
            messages.success(request, 'Nota atualizada.')
        else:
            messages.error(request, 'Não foi possível salvar a nota.')
        return _redirect_mural(request)


class NotaStatusView(LoginRequiredMixin, View):
    """Muda o status da nota (concluir/arquivar/reabrir) via param `status`."""

    def post(self, request, pk):
        nota = get_object_or_404(Nota, pk=pk)
        try:
            novo = int(request.POST.get('status'))
        except (TypeError, ValueError):
            novo = None
        if novo in dict(Nota.STATUS):
            nota.status = novo
            nota.save(update_fields=['status', 'atualizado_em'])
            messages.success(request, 'Status atualizado.')
        return _redirect_mural(request)


class NotaFixarView(LoginRequiredMixin, View):
    def post(self, request, pk):
        nota = get_object_or_404(Nota, pk=pk)
        nota.fixado = not nota.fixado
        nota.save(update_fields=['fixado', 'atualizado_em'])
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'ok': True, 'fixado': nota.fixado})
        return _redirect_mural(request)


class NotaDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        nota = get_object_or_404(Nota, pk=pk)
        for arq in nota.arquivos.all():
            arq.delete()
        if nota.agendamento_id:
            ag = nota.agendamento
            nota.agendamento = None
            nota.save(update_fields=['agendamento'])
            ag.delete()
        nota.delete()
        messages.success(request, 'Nota excluída.')
        return _redirect_mural(request)


class NotaArquivoDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        arq = get_object_or_404(NotaArquivo, pk=pk)
        arq.delete()
        messages.success(request, 'Anexo removido.')
        return _redirect_mural(request)


class NotaPosicaoView(LoginRequiredMixin, View):
    """Salva a posição (x, y) da nota no quadro e traz para a frente (z)."""

    def post(self, request, pk):
        nota = get_object_or_404(Nota, pk=pk)
        try:
            x = int(float(request.POST.get('x')))
            y = int(float(request.POST.get('y')))
        except (TypeError, ValueError):
            return JsonResponse({'ok': False}, status=400)
        x = max(0, min(x, 20000))
        y = max(0, min(y, 20000))
        topo = (Nota.objects.aggregate(m=Max('z'))['m'] or 0) + 1
        nota.pos_x = x
        nota.pos_y = y
        nota.z = topo
        nota.save(update_fields=['pos_x', 'pos_y', 'z', 'atualizado_em'])
        return JsonResponse({'ok': True, 'z': nota.z})


class NotaOrganizarView(LoginRequiredMixin, View):
    """Limpa as posições -> as notas voltam para a grade automática."""

    def post(self, request):
        Nota.objects.exclude(pos_x__isnull=True).update(pos_x=None, pos_y=None, z=0)
        messages.success(request, 'Quadro reorganizado.')
        return _redirect_mural(request)


class CategoriaCreateView(LoginRequiredMixin, View):
    def post(self, request):
        form = CategoriaNotaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Categoria criada.')
        else:
            messages.error(request, 'Não foi possível criar a categoria.')
        return _redirect_mural(request)


class CategoriaUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        cat = get_object_or_404(CategoriaNota, pk=pk)
        form = CategoriaNotaForm(request.POST, instance=cat)
        if form.is_valid():
            form.save()
            messages.success(request, 'Categoria atualizada.')
        else:
            messages.error(request, 'Não foi possível salvar a categoria.')
        return _redirect_mural(request)


class CategoriaDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        cat = get_object_or_404(CategoriaNota, pk=pk)
        # SET_NULL: as notas ficam sem categoria, não são apagadas.
        cat.delete()
        messages.success(request, 'Categoria excluída.')
        return _redirect_mural(request)
