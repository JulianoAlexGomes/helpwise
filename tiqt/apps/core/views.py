from django.http import JsonResponse
from .models import Cliente
from django.views import View
from django.views.generic import TemplateView, DetailView, ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LogoutView as BaseLogoutView
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache
from django.shortcuts import reverse, render, resolve_url, get_object_or_404, redirect
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.urls import reverse_lazy
from django_tables2 import SingleTableMixin
from tiqt.apps.core.models import Ticket, Comentario
from tiqt.apps.core.tables import TicketTable
from .forms import TicketForm, ClienteForm, TicketCloseForm, ComentarioForm
from .models import Cliente, Ticket, Solucao, ComentarioArquivo, ComentarioImagem, CertificadoCliente, User, Departamento, Prioridade, Cidade, Uf, Tributacao
from datetime import datetime, timedelta, time
import tiqt.settings as settings
from django.db.models import Q
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from rest_framework import viewsets
from .serializers import ClienteSerializer
from django.utils import timezone
from .models import Ticket
import os
from django.contrib.auth import get_user_model
from openpyxl import Workbook
from django.http import HttpResponse
from datetime import datetime, timedelta
from django.shortcuts import render
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Count, Case, When, IntegerField, DateField
from .models import Ticket
from django.db.models.functions import TruncMonth, Cast
from django.template.loader import render_to_string
from django.db.models.functions import TruncDate
from .forms import TicketFilterForm
from .filters import apply_filters

User = get_user_model()

def HomeView(request):
    hoje = timezone.localdate()
    primeiro_dia_mes = hoje.replace(day=1)

    # =========================
    # FILTROS DE DATA (SEM HORA)
    # =========================
    data_inicio_str = request.GET.get("data_inicio")
    data_fim_str = request.GET.get("data_fim")

    data_inicio = (
        datetime.strptime(data_inicio_str, "%Y-%m-%d").date()
        if data_inicio_str else primeiro_dia_mes
    )

    data_fim = (
        datetime.strptime(data_fim_str, "%Y-%m-%d").date()
        if data_fim_str else hoje
    )

    # 🔥 CONVERSÃO CORRETA PARA DATETIME
    data_inicio_dt = timezone.make_aware(
        datetime.combine(data_inicio, time.min)
    )

    data_fim_dt = timezone.make_aware(
        datetime.combine(data_fim, time.max)
    )

    usuarios_ids = request.GET.getlist("usuarios")
    departamento_id = request.GET.get("departamento")
    prioridade_id = request.GET.get("prioridade")

    # =========================
    # QUERY BASE (DATETIME)
    # =========================
    tickets = Ticket.objects.filter(
        criado_em__gte=data_inicio_dt,
        criado_em__lte=data_fim_dt
    )

    if usuarios_ids:
        tickets = tickets.filter(responsavel_id__in=usuarios_ids)

    if departamento_id:
        tickets = tickets.filter(departamento_id=departamento_id)

    if prioridade_id:
        tickets = tickets.filter(prioridade_id=prioridade_id)

    # =========================
    # TOTAIS
    # =========================
    totais = tickets.aggregate(
        abertos=Count(Case(When(status=Ticket.ABERTO, then=1))),
        andamento=Count(Case(When(status=Ticket.EM_ATENDIMENTO, then=1))),
        encerrados=Count(Case(When(status=Ticket.ENCERRADO, then=1))),
        cancelados=Count(Case(When(status=Ticket.CANCELADO, then=1))),
    )

    # =========================
    # EVOLUÇÃO DIÁRIA
    # =========================
    evolucao = (
    tickets
    .filter(criado_em__isnull=False) 
    .annotate(dia=TruncDate("criado_em"))
    .values("dia")
    .annotate(total=Count("id"))
    .order_by("dia")
)

    labels_dias = []
    dados_dias = []

    for e in evolucao:
        if e["dia"] is None:
            continue
        labels_dias.append(e["dia"].strftime("%d/%m"))
        dados_dias.append(e["total"])
    # =========================
    # EMPILHADO POR USUÁRIO
    # =========================
    dados_por_usuario = (
        tickets
        .values(
            "responsavel__first_name",
            "responsavel__last_name",
            "responsavel__username"
        )
        .annotate(
            abertos=Count(Case(When(status=Ticket.ABERTO, then=1))),
            andamento=Count(Case(When(status=Ticket.EM_ATENDIMENTO, then=1))),
            encerrados=Count(Case(When(status=Ticket.ENCERRADO, then=1))),
            cancelados=Count(Case(When(status=Ticket.CANCELADO, then=1))),
        )
        .order_by("responsavel__first_name")
    )

    labels_usuarios = []
    dados_abertos = []
    dados_andamento = []
    dados_encerrados = []
    dados_cancelados = []

    for item in dados_por_usuario:
        nome = (
            f"{item['responsavel__first_name']} {item['responsavel__last_name']}".strip()
            or item["responsavel__username"]
        )

        labels_usuarios.append(nome)
        dados_abertos.append(item["abertos"])
        dados_andamento.append(item["andamento"])
        dados_encerrados.append(item["encerrados"])
        dados_cancelados.append(item["cancelados"])

    context = {
        "atendimentos_aberto": totais["abertos"],
        "atendimentos_andamento": totais["andamento"],
        "atendimentos_encerrados": totais["encerrados"],
        "atendimentos_cancelados": totais["cancelados"],

        "labels_usuarios": labels_usuarios,
        "dados_abertos": dados_abertos,
        "dados_andamento": dados_andamento,
        "dados_encerrados": dados_encerrados,
        "dados_cancelados": dados_cancelados,

        "labels_dias": labels_dias,
        "dados_dias": dados_dias,

        "usuarios": User.objects.all(),
        "usuarios_selecionados": usuarios_ids,
        "departamentos": Departamento.objects.all(),
        "prioridades": Prioridade.objects.all(),
        "departamento_selecionado": departamento_id,
        "prioridade_selecionada": prioridade_id,
        "data_inicio": data_inicio.strftime("%Y-%m-%d"),
        "data_fim": data_fim.strftime("%Y-%m-%d"),
    }

    return render(request, "core/home.html", context)



def excluir_comentario(request, comentario_id):
    comentario = get_object_or_404(Comentario, id=comentario_id)
    ticket_id = comentario.ticket.id
    comentario.delete()
    return redirect('ticket_detail', ticket_id)


def excluir_arquivo(request, comentario_id, tipo):
    comentario = get_object_or_404(Comentario, id=comentario_id)
    arquivo_removido = False

    if tipo == 'imagem':
        imagens = comentario.imagens.all()  # Obtém todas as imagens relacionadas
        for imagem in imagens:
            caminho_arquivo = os.path.join(settings.MEDIA_ROOT, str(imagem.imagem))
            if os.path.exists(caminho_arquivo):
                os.remove(caminho_arquivo)
            imagem.delete()
            arquivo_removido = True

    elif tipo == 'arquivo':
        arquivos = comentario.arquivos.all()  # Obtém todos os arquivos relacionados
        for arquivo in arquivos:
            caminho_arquivo = os.path.join(settings.MEDIA_ROOT, str(arquivo.arquivo))
            if os.path.exists(caminho_arquivo):
                os.remove(caminho_arquivo)
            arquivo.delete()
            arquivo_removido = True

    if arquivo_removido:
        messages.success(request, 'Arquivo excluído com sucesso.')
    else:
        messages.error(request, 'Erro ao excluir o arquivo.')

    return redirect('ticket_detail', pk=comentario.ticket.pk)

from datetime import datetime

def download_certificado(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    file_path = cliente.certificado_digital.path
    if os.path.exists(file_path):
        with open(file_path, 'rb') as fh:
            response = HttpResponse(fh.read(), content_type="application/octet-stream")
            response['Content-Disposition'] = 'inline; filename=' + os.path.basename(file_path)
            return response
    raise Http404


class MyTicketsView(LoginRequiredMixin, SingleTableMixin, TemplateView):
    template_name = 'core/tickets_list.html'
    table_class = TicketTable
    # table_pagination = {
    #     'per_page': 10
    # }

    def get_table_data(self, **kwargs):
        return Ticket.objects.filter(Q(status=Ticket.ABERTO) | Q(status=Ticket.EM_ATENDIMENTO),responsavel=self.request.user)

class OpenTicketsView(LoginRequiredMixin, SingleTableMixin, TemplateView):
    template_name = 'core/tickets_list.html'
    table_class = TicketTable

    def get_table_data(self):
        queryset = Ticket.objects.filter(status=Ticket.ABERTO)
        form = TicketFilterForm(self.request.GET)
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(
                Q(titulo__icontains=query) | 
                Q(id__icontains=query) | 
                Q(atendente__first_name__icontains=query) |
                Q(atendente__last_name__icontains=query)
            )
        if form.is_valid():
            queryset = apply_filters(queryset, form)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_table_data()
        context['filter_form'] = TicketFilterForm(self.request.GET)
        context['query'] = self.request.GET.get('q', '')
        context['request'] = self.request
        context['filtered_count'] = queryset.count()
        return context

    table_pagination = {
        'per_page': 10000
    }

class InProgressTicketsView(LoginRequiredMixin, SingleTableMixin, TemplateView):
    template_name = 'core/tickets_list.html'
    table_class = TicketTable

    def get_table_data(self):
        queryset = Ticket.objects.filter(status=Ticket.EM_ATENDIMENTO)
        form = TicketFilterForm(self.request.GET)
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(Q(titulo__icontains=query) | Q(id__icontains=query))
        if form.is_valid():
            queryset = apply_filters(queryset, form)
        return queryset
    

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_table_data()
        context['filter_form'] = TicketFilterForm(self.request.GET)
        context['query'] = self.request.GET.get('q', '')
        context['request'] = self.request
        context['filtered_count'] = queryset.count()
        return context

    table_pagination = {
        'per_page': 10
    }

class ClosedTicketsView(LoginRequiredMixin, SingleTableMixin, TemplateView):
    template_name = 'core/tickets_list.html'
    table_class = TicketTable

    def get_table_data(self):
        queryset = Ticket.objects.filter(status=Ticket.ENCERRADO)
        form = TicketFilterForm(self.request.GET)
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(Q(titulo__icontains=query) | Q(id__icontains=query))
        if form.is_valid():
            queryset = apply_filters(queryset, form)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_table_data()
        context['filter_form'] = TicketFilterForm(self.request.GET)
        context['query'] = self.request.GET.get('q', '')
        context['request'] = self.request
        context['filtered_count'] = queryset.count()
        return context

    table_pagination = {
        'per_page': 10
    }

class EveryoneTicketsView(LoginRequiredMixin, SingleTableMixin, TemplateView):
    template_name = 'core/tickets_list.html'
    table_class = TicketTable

    def get_table_data(self):
        queryset = Ticket.objects.all()
        form = TicketFilterForm(self.request.GET)
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(Q(titulo__icontains=query) | Q(id__icontains=query))
        if form.is_valid():
            queryset = apply_filters(queryset, form)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_table_data()
        context['filter_form'] = TicketFilterForm(self.request.GET)
        context['query'] = self.request.GET.get('q', '')
        context['request'] = self.request
        context['filtered_count'] = queryset.count()
        return context

    table_pagination = {
        'per_page': 10
    }

class CanceledTicketsView(LoginRequiredMixin, SingleTableMixin, TemplateView):
    template_name = 'core/tickets_list.html'
    table_class = TicketTable

    def get_table_data(self):
        queryset = Ticket.objects.filter(status=Ticket.CANCELADO)
        form = TicketFilterForm(self.request.GET)
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(Q(titulo__icontains=query) | Q(id__icontains=query))
        if form.is_valid():
            queryset = apply_filters(queryset, form)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_table_data()
        context['filter_form'] = TicketFilterForm(self.request.GET)
        context['query'] = self.request.GET.get('q', '')
        context['request'] = self.request
        context['filtered_count'] = queryset.count()
        return context

    table_pagination = {
        'per_page': 10
    }

class DesenvTicketsView(LoginRequiredMixin, SingleTableMixin, TemplateView):
    template_name = 'core/tickets_list.html'
    table_class = TicketTable

    def get_table_data(self):
        queryset = Ticket.objects.filter(Q(status=Ticket.ABERTO) | Q(status=Ticket.EM_ATENDIMENTO), departamento=2)
        form = TicketFilterForm(self.request.GET)
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(Q(titulo__icontains=query) | Q(id__icontains=query))
        if form.is_valid():
            queryset = apply_filters(queryset, form)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_table_data()
        context['filter_form'] = TicketFilterForm(self.request.GET)
        context['query'] = self.request.GET.get('q', '')
        context['request'] = self.request
        context['filtered_count'] = queryset.count()
        return context

    table_pagination = {
        'per_page': 10
    }

# class NewTicketView(LoginRequiredMixin, View):
#     def get(self, request):
#         form = TicketForm()
#         return render(request, 'core/ticket_form.html', {'form': form})

#     def post(self, request):
#         form = TicketForm(request.POST)
#         if form.is_valid():
#             ticket = form.save(commit=False)
#             ticket.atendente = request.user
#             ticket.save()
#             return redirect(reverse('ticket_detail', args=[ticket.pk]))
#         return render(request, 'core/ticket_form.html', {'form': form})

class NewTicketView(LoginRequiredMixin, View):

    def get(self, request):
        cliente_id = request.GET.get('cliente')

        if cliente_id:
            form = TicketForm(initial={'cliente': cliente_id})
        else:
            form = TicketForm()

        return render(request, 'core/ticket_form.html', {'form': form})

    def post(self, request):
        form = TicketForm(request.POST)

        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.atendente = request.user
            ticket.save()
            return redirect(reverse('ticket_detail', args=[ticket.pk]))

        return render(request, 'core/ticket_form.html', {'form': form})

class TicketUpdateView(LoginRequiredMixin, View):
    def get(self, request, pk):
        ticket = Ticket.objects.get(pk=pk)
        show_responsavel = ticket.status == 'EM_ATENDIMENTO' 
        form = TicketForm(instance=ticket, show_responsavel=show_responsavel)
        return render(request, 'core/ticket_form.html', {'form': form, 'ticket': ticket})

    def post(self, request, pk):
        ticket = Ticket.objects.get(pk=pk)
        show_responsavel = ticket.status == 'EM_ATENDIMENTO' 
        form = TicketForm(request.POST, instance=ticket, show_responsavel=show_responsavel)
        if form.is_valid():
            form.save()
            return redirect(reverse('ticket_detail', args=[ticket.pk]))
        return render(request, 'core/ticket_form.html', {'form': form, 'ticket': ticket})

class TicketDetailView(View):
    def get(self, request, pk):
        ticket = get_object_or_404(Ticket, pk=pk)
        comments = Comentario.objects.filter(ticket=ticket).order_by('-criado_em')
        solucoes = ticket.get_solucoes()
        form = ComentarioForm()
        client = Cliente.objects.get(pk=ticket.cliente.pk)  
        return render(request, 'core/ticket_detail.html', {'object': ticket, 'comments': comments, 'solucoes': solucoes, 'form': form, 'client': client})

    def post(self, request, pk):
        ticket = get_object_or_404(Ticket, pk=pk)
        form = ComentarioForm(request.POST)

        if form.is_valid():
            comment = form.save(commit=False)
            comment.ticket = ticket
            comment.autor = request.user
            comment.save()

            # Salvar arquivos
            arquivos = request.FILES.getlist('arquivos')
            for arquivo in arquivos:
                ComentarioArquivo.objects.create(comentario=comment, arquivo=arquivo)

            # Salvar imagens
            imagens = request.FILES.getlist('imagens')
            for imagem in imagens:
                ComentarioImagem.objects.create(comentario=comment, imagem=imagem)

            return redirect(reverse('ticket_detail', kwargs={'pk': pk}))

        comments = Comentario.objects.filter(ticket=ticket).order_by('criado_em')
        return render(request, 'core/ticket_detail.html', {'object': ticket, 'comments': comments, 'form': form})



class TicketAcceptView(LoginRequiredMixin, View):

    def get(self, request, pk):
        ticket = Ticket.objects.get(pk=pk)
        ticket.iniciar_atendimento(request.user)
        return HttpResponseRedirect(reverse("ticket_detail", kwargs={"pk": pk}))

class TicketCancelView(LoginRequiredMixin, View):

    def get(self, request, pk):
        ticket = Ticket.objects.get(pk=pk)
        ticket.cancelar_atendimento(request.user)
        return HttpResponseRedirect(reverse("ticket_detail", kwargs={"pk": pk}))


class CloseTicketView(LoginRequiredMixin, View):

    def get(self, request, pk):
        ticket = Ticket.objects.get(pk=pk)
        form = TicketCloseForm()
        return render(request, 'core/ticket_close_form.html', {'form': form, 'ticket': ticket})

    def post(self, request, pk):
        ticket = Ticket.objects.get(pk=pk)
        form = TicketCloseForm(request.POST)
        if form.is_valid():
            solucao_texto = form.cleaned_data['solucao']
            solucao = Solucao.objects.create(ticket=ticket, texto=solucao_texto, autor=request.user)
            ticket.encerrar_atendimento()
            return HttpResponseRedirect(reverse("ticket_detail", kwargs={"pk": pk}))
        return render(request, 'core/ticket_close_form.html', {'form': form, 'ticket': ticket})


class CommentView(LoginRequiredMixin, View):

    # def post(self, request, ticket_pk):
    #     ticket = Ticket.objects.get(pk=ticket_pk)
    #     comment = Comentario(
    #         ticket=ticket, 
    #         texto=request.POST['texto'], 
    #         autor=request.user,
    #         proximo_contato=request.POST.get('proximo_contato'),
    #         tipo_id=request.POST.get('tipo')
    #     )
    #     comment.save()
    #     return HttpResponseRedirect(
    #         reverse("ticket_detail", kwargs={"pk": ticket_pk}))

    def post(self, request, ticket_pk):
        ticket = Ticket.objects.get(pk=ticket_pk)
        comment = Comentario(
            ticket=ticket, 
            texto=request.POST['texto'], 
            autor=request.user,
            proximo_contato=request.POST.get('proximo_contato'),
            tipo_id=request.POST.get('tipo')
        )
        comment.save()

        if comment.tipo.id == '5':
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                'notifications',
                {
                    'type': 'send_notification',
                    'message': f'Novo comentário liberado no ticket #{ticket_pk}'
                }
            )

        return HttpResponseRedirect(
            reverse("ticket_detail", kwargs={"pk": ticket_pk}))
    
    def get(self, request, ticket_pk):
        return HttpResponseRedirect(
            reverse("ticket_detail", kwargs={"pk": ticket_pk}))

class ClienteViewSet(viewsets.ModelViewSet):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer

# class ClienteListView(ListView):
#     model = Cliente
#     template_name = 'core/cliente_list.html'
#     context_object_name = 'clientes'

#     def get_queryset(self):
#         return Cliente.objects.all().order_by('fantasia')

class ClienteListView(ListView):
    model = Cliente
    template_name = 'core/cliente_list.html'
    context_object_name = 'clientes'

    def get_queryset(self):
        queryset = Cliente.objects.all().order_by('fantasia')

        q = self.request.GET.get('q')
        cidade = self.request.GET.get('cidade')
        uf = self.request.GET.get('uf')
        tributacao = self.request.GET.get('tributacao')

        if q:
            queryset = queryset.filter(
                Q(fantasia__icontains=q) |
                Q(razao_social__icontains=q) |
                Q(cnpj__icontains=q)
            )

        if cidade:
            queryset = queryset.filter(cidade_id=cidade)

        if uf:
            queryset = queryset.filter(uf_id=uf)

        if tributacao:
            queryset = queryset.filter(tributacao_id=tributacao)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cidades'] = Cidade.objects.all().order_by('descricao')
        context['ufs'] = Uf.objects.all().order_by('sigla')
        context['tributacoes'] = Tributacao.objects.all().order_by('descricao')
        return context

class ClienteCreateView(CreateView):
    model = Cliente
    form_class = ClienteForm
    template_name = 'core/cliente_form.html'
    success_url = reverse_lazy('cliente_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        cliente = form.instance
        certificados = self.request.FILES.getlist('certificados')
        for certificado in certificados:
            CertificadoCliente.objects.create(cliente=cliente, arquivo=certificado)
        return response

class ClienteUpdateView(UpdateView):
    model = Cliente
    form_class = ClienteForm
    template_name = 'core/cliente_form.html'
    success_url = reverse_lazy('cliente_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        cliente = form.instance
        certificados = self.request.FILES.getlist('certificados')
        for certificado in certificados:
            CertificadoCliente.objects.create(cliente=cliente, arquivo=certificado)
        return response

class CertificadoDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        certificado = get_object_or_404(CertificadoCliente, pk=pk)
        cliente_id = certificado.cliente.id
        certificado.delete()
        return redirect('cliente_update', pk=cliente_id)

class ClienteDeleteView(LoginRequiredMixin, DeleteView):
    model = Cliente
    template_name = 'core/cliente_confirm_delete.html'
    success_url = reverse_lazy('cliente_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cliente'] = self.object
        return context


class LogoutView(BaseLogoutView):
    http_method_names = ["post", "options"]
    template_name = "registration/logged_out.html"
    extra_context = None

    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        auth_logout(request)
        redirect_to = self.get_success_url()
        if redirect_to != request.get_full_path():
            return HttpResponseRedirect(redirect_to)
        return super().get(request, *args, **kwargs)

    def get_default_redirect_url(self):
        if self.next_page:
            return resolve_url(self.next_page)
        elif settings.LOGOUT_REDIRECT_URL:
            return resolve_url(settings.LOGOUT_REDIRECT_URL)
        else:
            return self.request.path

def clientes_autocomplete(request):
    term = request.GET.get('term', '').strip()

    data = {}

    if term:
        clientes = (
            Cliente.objects
            .filter(
                Q(fantasia__icontains=term) |
                Q(razao_social__icontains=term) |
                Q(cnpj__icontains=term)
            )
            .order_by('fantasia')[:15]
        )

        for cliente in clientes:
            label = " - ".join(filter(None, [
                cliente.fantasia,
                cliente.razao_social,
                cliente.cnpj
            ]))
            data[label] = None  # Materialize exige esse formato

    return JsonResponse(data)