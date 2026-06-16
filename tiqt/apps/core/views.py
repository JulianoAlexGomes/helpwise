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
from django.http import HttpResponseRedirect, HttpResponse, Http404, FileResponse
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
import requests as http_requests
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
from .forms import TicketFilterForm, NewTicketForm
from .filters import apply_filters
from tiqt.apps.notifications.services import notificar_atribuicao
import json
from collections import Counter

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
    ticket_dts = tickets.filter(criado_em__isnull=False).values_list("criado_em", flat=True)
    date_counts = Counter(timezone.localtime(dt).date() for dt in ticket_dts)

    labels_dias = []
    dados_dias = []
    current_date = data_inicio
    while current_date <= data_fim:
        labels_dias.append(current_date.strftime("%d/%m"))
        dados_dias.append(date_counts.get(current_date, 0))
        current_date += timedelta(days=1)
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

        "labels_dias": json.dumps(labels_dias),
        "dados_dias": json.dumps(dados_dias),

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
    if not cliente.certificado_digital:
        messages.error(request, 'Este cliente não possui certificado digital.')
        return redirect('cliente_list')
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

# class NewTicketView(LoginRequiredMixin, View):

#     def get(self, request):
#         cliente_id = request.GET.get('cliente')

#         if cliente_id:
#             form = TicketForm(initial={'cliente': cliente_id})
#         else:
#             form = TicketForm()

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

        form = NewTicketForm(
            initial={'cliente': cliente_id} if cliente_id else None
        )

        return render(request, 'core/ticket_form.html', {'form': form})

    def post(self, request):
        form = NewTicketForm(request.POST)

        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.atendente = request.user
            ticket.save()
            notificar_atribuicao(ticket, ator=request.user)
            return redirect(reverse('ticket_detail', args=[ticket.pk]))

        return render(request, 'core/ticket_form.html', {'form': form})


class TicketUpdateView(LoginRequiredMixin, View):
    def get(self, request, pk):
        ticket = Ticket.objects.get(pk=pk)
        # show_responsavel = ticket.status == 'ABERTO' 
        form = TicketForm(instance=ticket, show_responsavel=True)
        return render(request, 'core/ticket_form.html', {'form': form, 'ticket': ticket})

    def post(self, request, pk):
        ticket = Ticket.objects.get(pk=pk)
        # show_responsavel = ticket.status == 'ABERTO' 
        form = TicketForm(request.POST, instance=ticket, show_responsavel=True)
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


class KanbanView(LoginRequiredMixin, TemplateView):
    template_name = 'core/kanban.html'

    def get_context_data(self, **kwargs):
        from .models import Tipo
        context = super().get_context_data(**kwargs)
        responsavel_id = self.request.GET.get('responsavel', '')
        atendente_id   = self.request.GET.get('atendente', '')
        tipo_id        = self.request.GET.get('tipo', '')

        qs = Ticket.objects.select_related('cliente', 'prioridade', 'responsavel', 'atendente', 'tipo')
        if responsavel_id:
            qs = qs.filter(responsavel_id=responsavel_id)
        if atendente_id:
            qs = qs.filter(atendente_id=atendente_id)
        if tipo_id:
            qs = qs.filter(tipo_id=tipo_id)

        context['tickets_aberto']         = qs.filter(status=Ticket.ABERTO).order_by('-id')
        context['tickets_em_atendimento'] = qs.filter(status=Ticket.EM_ATENDIMENTO).order_by('-id')
        context['tickets_encerrado']      = qs.filter(status=Ticket.ENCERRADO).order_by('-encerrado_em')[:30]
        context['usuarios']               = User.objects.filter(is_active=True).order_by('first_name')
        context['tipos']                  = Tipo.objects.all().order_by('descricao')
        context['responsavel_selecionado'] = responsavel_id
        context['atendente_selecionado']   = atendente_id
        context['tipo_selecionado']        = tipo_id
        return context


class TicketPreviewAjaxView(LoginRequiredMixin, View):
    """Retorna um resumo (pré-visualização) do ticket para exibir em modal no Kanban
    e permite editar campos básicos (responsável, atendente, situação, prioridade, tipo)."""

    def get(self, request, pk):
        from .models import Tipo, Situacao
        ticket = get_object_or_404(
            Ticket.objects.select_related(
                'cliente', 'prioridade', 'responsavel', 'atendente', 'tipo', 'situacao'
            ),
            pk=pk,
        )
        context = {
            'ticket': ticket,
            'comentarios': ticket.comentarios.select_related('autor', 'tipo').order_by('-criado_em')[:5],
            'solucoes': ticket.solucao_set.select_related('autor').order_by('-criado_em'),
            'usuarios': User.objects.filter(is_active=True).order_by('first_name'),
            'tipos': Tipo.objects.all().order_by('descricao'),
            'prioridades': Prioridade.objects.all().order_by('descricao'),
            'situacoes': Situacao.objects.all().order_by('descricao'),
        }
        return render(request, 'core/_ticket_preview.html', context)

    def post(self, request, pk):
        ticket = get_object_or_404(Ticket, pk=pk)

        def set_fk(field, value, allow_empty=False):
            value = (value or '').strip()
            if not value:
                if allow_empty:
                    setattr(ticket, field + '_id', None)
                return
            setattr(ticket, field + '_id', value)

        set_fk('responsavel', request.POST.get('responsavel'), allow_empty=True)
        set_fk('atendente', request.POST.get('atendente'), allow_empty=True)
        set_fk('situacao', request.POST.get('situacao'))
        set_fk('prioridade', request.POST.get('prioridade'))
        set_fk('tipo', request.POST.get('tipo'))

        try:
            ticket.save(update_fields=['responsavel', 'atendente', 'situacao', 'prioridade', 'tipo'])
        except Exception as exc:
            return JsonResponse({'error': f'Não foi possível salvar: {exc}'}, status=400)

        return JsonResponse({
            'ok': True,
            'responsavel': ticket.responsavel.get_full_name() if ticket.responsavel else '—',
            'atendente': ticket.atendente.get_full_name() if ticket.atendente else '—',
            'prioridade': ticket.prioridade.descricao if ticket.prioridade else '—',
            'tipo': ticket.tipo.descricao if ticket.tipo else '—',
            'situacao': ticket.situacao.descricao if ticket.situacao else '—',
        })




class TicketAcceptAjaxView(LoginRequiredMixin, View):

    def post(self, request, pk):
        ticket = get_object_or_404(Ticket, pk=pk)
        if ticket.status != Ticket.ABERTO:
            return JsonResponse({'error': 'Ticket não está aberto'}, status=400)
        ticket.iniciar_atendimento(request.user)
        return JsonResponse({'ok': True, 'responsavel': request.user.get_full_name()})


class TicketCloseAjaxView(LoginRequiredMixin, View):

    def post(self, request, pk):
        ticket = get_object_or_404(Ticket, pk=pk)
        if ticket.status == Ticket.ENCERRADO:
            return JsonResponse({'error': 'Ticket já está encerrado'}, status=400)
        solucao_texto = request.POST.get('solucao', '').strip()
        if not solucao_texto:
            return JsonResponse({'error': 'Informe a solução antes de encerrar'}, status=400)
        Solucao.objects.create(ticket=ticket, texto=solucao_texto, autor=request.user)
        ticket.encerrar_atendimento()
        return JsonResponse({'ok': True})


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


# ─── API: busca de clientes retornando id + nome (para o modal rápido) ────────
def clientes_busca_api(request):
    q = request.GET.get('q', '').strip()
    results = []
    if q:
        clientes = (
            Cliente.objects
            .filter(
                Q(fantasia__icontains=q) |
                Q(razao_social__icontains=q) |
                Q(cnpj__icontains=q)
            )
            .order_by('fantasia')[:15]
        )
        for c in clientes:
            results.append({
                'id': c.id,
                'text': " - ".join(filter(None, [c.fantasia, c.razao_social, c.cnpj]))
            })
    return JsonResponse({'results': results})


def buscar_cep(request, cep):
    cep = cep.replace('-', '').replace('.', '').strip()
    if len(cep) != 8 or not cep.isdigit():
        return JsonResponse({'erro': 'CEP inválido'}, status=400)

    apis = [
        f"https://viacep.com.br/ws/{cep}/json/",
        f"https://brasilapi.com.br/api/cep/v1/{cep}",
        f"https://ws.apicep.com/cep/{cep}.json",
    ]

    endereco = None
    for url in apis:
        try:
            resp = http_requests.get(url, timeout=3)
            if resp.status_code != 200:
                continue
            data = resp.json()
            if 'erro' in data:
                continue
            if 'street' in data:  # BrasilAPI
                endereco = {
                    'logradouro': data.get('street', ''),
                    'bairro': data.get('neighborhood', ''),
                    'cidade': data.get('city', ''),
                    'uf': data.get('state', ''),
                }
            elif 'address' in data:  # APICEP
                endereco = {
                    'logradouro': data.get('address', ''),
                    'bairro': data.get('district', ''),
                    'cidade': data.get('city', ''),
                    'uf': data.get('state', ''),
                }
            else:  # ViaCEP
                endereco = {
                    'logradouro': data.get('logradouro', ''),
                    'bairro': data.get('bairro', ''),
                    'cidade': data.get('localidade', ''),
                    'uf': data.get('uf', ''),
                }
            break
        except Exception:
            continue

    if not endereco:
        return JsonResponse({'erro': 'CEP não encontrado'}, status=404)

    uf_id = None
    cidade_id = None
    try:
        uf_obj = Uf.objects.get(sigla__iexact=endereco['uf'])
        uf_id = uf_obj.id
    except Uf.DoesNotExist:
        pass

    try:
        cidade_obj = Cidade.objects.filter(descricao__iexact=endereco['cidade']).first()
        if cidade_obj:
            cidade_id = cidade_obj.id
    except Exception:
        pass

    return JsonResponse({
        'logradouro': endereco['logradouro'],
        'bairro': endereco['bairro'],
        'cidade': endereco['cidade'],
        'uf': endereco['uf'],
        'cidade_id': cidade_id,
        'uf_id': uf_id,
    })


def buscar_cnpj(request, cnpj):
    cnpj = ''.join(filter(str.isdigit, cnpj))
    if len(cnpj) != 14:
        return JsonResponse({'erro': 'CNPJ inválido'}, status=400)

    dados = None

    # BrasilAPI
    try:
        resp = http_requests.get(f'https://brasilapi.com.br/api/cnpj/v1/{cnpj}', timeout=5)
        if resp.status_code == 200:
            d = resp.json()
            telefone = (d.get('ddd_telefone_1') or '').replace(' ', '').replace('-', '')
            cep_raw = (d.get('cep') or '').replace('-', '').replace('.', '')
            dados = {
                'razao_social': d.get('razao_social', ''),
                'fantasia': d.get('nome_fantasia', ''),
                'email': d.get('email', ''),
                'telefone': telefone,
                'logradouro': d.get('logradouro', ''),
                'numero': d.get('numero', ''),
                'complemento': d.get('complemento', ''),
                'bairro': d.get('bairro', ''),
                'cidade': d.get('municipio', ''),
                'uf': d.get('uf', ''),
                'cep': cep_raw,
            }
    except Exception:
        pass

    # CNPJ.ws fallback
    if not dados:
        try:
            resp = http_requests.get(f'https://publica.cnpj.ws/cnpj/{cnpj}', timeout=5)
            if resp.status_code == 200:
                d = resp.json()
                est = d.get('estabelecimento', {})
                telefone = (est.get('telefone1') or '').replace(' ', '').replace('-', '')
                cep_raw = (est.get('cep') or '').replace('-', '').replace('.', '')
                dados = {
                    'razao_social': d.get('razao_social', ''),
                    'fantasia': est.get('nome_fantasia', '') or '',
                    'email': est.get('email', '') or '',
                    'telefone': telefone,
                    'logradouro': f"{est.get('tipo_logradouro', '')} {est.get('logradouro', '')}".strip(),
                    'numero': est.get('numero', '') or '',
                    'complemento': est.get('complemento', '') or '',
                    'bairro': est.get('bairro', '') or '',
                    'cidade': (est.get('cidade') or {}).get('nome', ''),
                    'uf': (est.get('estado') or {}).get('sigla', ''),
                    'cep': cep_raw,
                }
        except Exception:
            pass

    if not dados:
        return JsonResponse({'erro': 'CNPJ não encontrado'}, status=404)

    uf_id = None
    cidade_id = None
    try:
        uf_obj = Uf.objects.get(sigla__iexact=dados['uf'])
        uf_id = uf_obj.id
    except Uf.DoesNotExist:
        pass
    try:
        cidade_obj = Cidade.objects.filter(descricao__iexact=dados['cidade']).first()
        if cidade_obj:
            cidade_id = cidade_obj.id
    except Exception:
        pass

    dados['uf_id'] = uf_id
    dados['cidade_id'] = cidade_id
    return JsonResponse(dados)


# ─── View: criação rápida de ticket via AJAX (modal) ──────────────────────────
class QuickTicketCreateView(LoginRequiredMixin, View):

    def post(self, request):
        cliente_id      = request.POST.get('cliente_id')
        titulo          = request.POST.get('titulo', '').strip()
        departamento_id = request.POST.get('departamento')
        tipo_id         = request.POST.get('tipo') or 3
        prioridade_id   = request.POST.get('prioridade') or 2
        atendente_id    = request.POST.get('atendente') or None
        responsavel_id  = request.POST.get('responsavel') or None

        if not cliente_id or not titulo or not departamento_id:
            return JsonResponse({'error': 'Preencha cliente, título e departamento.'}, status=400)

        ticket = Ticket.objects.create(
            cliente_id=cliente_id,
            titulo=titulo,
            departamento_id=departamento_id,
            tipo_id=tipo_id,
            prioridade_id=prioridade_id,
            situacao_id=1,
            atendente_id=atendente_id if atendente_id else request.user.pk,
            responsavel_id=responsavel_id if responsavel_id else None,
        )

        notificar_atribuicao(ticket, ator=request.user)

        return JsonResponse({'redirect': reverse('ticket_detail', kwargs={'pk': ticket.pk})})