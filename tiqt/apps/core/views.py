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
from django.db.models.deletion import ProtectedError
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
from .forms import TicketFilterForm, NewTicketForm, MeusTicketsFilterForm
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

        "usuarios": User.objects.filter(is_active=True),
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
        user = self.request.user
        queryset = Ticket.objects.filter(
            Q(status=Ticket.ABERTO) | Q(status=Ticket.EM_ATENDIMENTO)
        ).select_related('cliente', 'responsavel', 'atendente', 'tipo', 'prioridade', 'situacao')

        form = MeusTicketsFilterForm(self.request.GET)
        papel = form.cleaned_data.get('papel') if form.is_valid() else ''
        if papel == MeusTicketsFilterForm.RESPONSAVEL:
            queryset = queryset.filter(responsavel=user)
        elif papel == MeusTicketsFilterForm.ATENDENTE:
            queryset = queryset.filter(atendente=user)
        else:
            queryset = queryset.filter(Q(responsavel=user) | Q(atendente=user))

        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(Q(titulo__icontains=query) | Q(id__icontains=query))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = MeusTicketsFilterForm(self.request.GET)
        context['is_meus_tickets'] = True
        context['query'] = self.request.GET.get('q', '')
        context['request'] = self.request
        context['filtered_count'] = self.get_table_data().count()
        return context


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
        'per_page': 10
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
            notificar_atribuicao(ticket, ator=request.user, notificar_ator=False)
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


class PerfilView(LoginRequiredMixin, View):
    """Permite ao usuário editar seus próprios dados e trocar a senha."""

    def get(self, request):
        from .forms import PerfilForm
        form = PerfilForm(instance=request.user)
        return render(request, 'core/perfil.html', {'form': form})

    def post(self, request):
        from .forms import PerfilForm
        from django.contrib.auth import update_session_auth_hash
        form = PerfilForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            user = form.save()
            nova_senha = form.cleaned_data.get('nova_senha')
            if nova_senha:
                user.set_password(nova_senha)
                user.save()
                update_session_auth_hash(request, user)  # mantém o login ativo
            messages.success(request, 'Perfil atualizado com sucesso!')
            return redirect('perfil')
        return render(request, 'core/perfil.html', {'form': form})


class TicketDetailView(View):
    def _contexto(self, ticket, form):
        from .models import KanbanQuadro
        from tiqt.apps.mural.models import CategoriaNota

        comments = (
            Comentario.objects.filter(ticket=ticket)
            .select_related('autor', 'tipo')
            .prefetch_related('arquivos', 'imagens')
            .order_by('-criado_em')
        )
        # O quadro padrão é preenchido pelo status do ticket, então não entra no seletor.
        quadros = KanbanQuadro.objects.filter(is_padrao=False).prefetch_related('colunas')
        return {
            'object': ticket,
            'comments': comments,
            'solucoes': ticket.get_solucoes().select_related('autor'),
            'form': form,
            'client': ticket.cliente,
            'notas': ticket.notas_mural.select_related('categoria', 'responsavel'),
            'agendamentos': ticket.agendamentos.select_related('responsavel'),
            'kanban_cards': ticket.kanban_cards.select_related('coluna__quadro'),
            'quadros_kanban': quadros,
            'categorias_mural': CategoriaNota.objects.filter(ativo=True),
        }

    def get(self, request, pk):
        ticket = get_object_or_404(
            Ticket.objects.select_related(
                'cliente', 'tipo', 'prioridade', 'situacao',
                'responsavel', 'atendente', 'cancelado',
            ),
            pk=pk,
        )
        return render(request, 'core/ticket_detail.html', self._contexto(ticket, ComentarioForm()))

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

        return render(request, 'core/ticket_detail.html', self._contexto(ticket, form))



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
        from .models import Tipo, KanbanColuna, KanbanQuadro, KanbanCard
        from .models import Prioridade
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

        # Quadro selecionado (default = o padrão, que vem primeiro na ordenação)
        quadros = list(KanbanQuadro.objects.all())
        quadro_id = self.request.GET.get('quadro', '')
        quadro_atual = None
        if quadro_id:
            quadro_atual = next((q for q in quadros if str(q.id) == str(quadro_id)), None)
        if quadro_atual is None:
            quadro_atual = next((q for q in quadros if q.is_padrao), quadros[0] if quadros else None)

        colunas = list(quadro_atual.colunas.all()) if quadro_atual else []

        if quadro_atual and quadro_atual.is_padrao:
            # Quadro padrão: tickets vêm do status (+ override em Ticket.kanban_coluna)
            for coluna in colunas:
                filtro = Q(kanban_coluna_id=coluna.id)
                if coluna.status_associado is not None:
                    filtro |= Q(kanban_coluna__isnull=True, status=coluna.status_associado)
                tickets = qs.filter(filtro).order_by('kanban_ordem', '-id')
                if coluna.status_associado == Ticket.ENCERRADO:
                    tickets = tickets[:30]
                coluna.lista = list(tickets)
                coluna.qtd = len(coluna.lista)
                coluna.arrastavel = coluna.status_associado != Ticket.ENCERRADO
                coluna.encerrada = coluna.status_associado == Ticket.ENCERRADO
        else:
            # Quadro personalizado: cards explicitamente adicionados (tickets, notas ou avulsos)
            tem_filtro = bool(responsavel_id or atendente_id or tipo_id)
            ids_permitidos = set(qs.values_list('id', flat=True)) if tem_filtro else None

            def card_visivel(card):
                """Aplica os filtros a um card de quadro personalizado.

                Cards de ticket seguem o filtro completo. Notas e cards avulsos não têm
                atendente nem tipo, então usam uma única "pessoa" — o responsável da nota
                ou quem criou o card — comparada tanto ao filtro de responsável quanto ao
                de atendente. O filtro de tipo, que eles não têm como satisfazer, os esconde.
                """
                if not tem_filtro:
                    return True
                if card.ticket_id:
                    return card.ticket_id in ids_permitidos
                if tipo_id:
                    return False
                pessoa_id = card.nota.responsavel_id if card.nota_id else card.autor_id
                if pessoa_id is None:
                    return False
                # Cada filtro de pessoa ativo precisa bater, igual ao AND dos cards de ticket.
                return all(str(pessoa_id) == f for f in (responsavel_id, atendente_id) if f)

            for coluna in colunas:
                cards = (KanbanCard.objects
                         .filter(coluna=coluna)
                         .select_related('ticket', 'ticket__cliente', 'ticket__prioridade',
                                         'ticket__responsavel', 'ticket__tipo',
                                         'nota', 'nota__categoria', 'nota__responsavel',
                                         'cliente', 'autor')
                         .prefetch_related('etiquetas', 'membros', 'comentarios')
                         .order_by('ordem', '-id'))
                coluna.lista = [card for card in cards if card_visivel(card)]
                coluna.qtd = len(coluna.lista)
                coluna.arrastavel = True
                coluna.encerrada = coluna.status_associado == Ticket.ENCERRADO

        context['quadros']                = quadros
        context['quadro_atual']           = quadro_atual
        context['colunas']                = colunas
        context['usuarios']               = User.objects.filter(is_active=True).order_by('first_name')
        context['tipos']                  = Tipo.objects.all().order_by('descricao')
        context['prioridades']            = Prioridade.objects.all().order_by('descricao')
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


# ─────────────────────────────────────────────────────────────
#  Kanban personalizável: quadros, colunas, cards + comentários
# ─────────────────────────────────────────────────────────────

def _parse_status_associado(val):
    """Normaliza o status vindo do form ('' → None; 0..3 → int)."""
    val = (val or '').strip()
    if val == '':
        return None
    try:
        iv = int(val)
    except (TypeError, ValueError):
        return None
    return iv if iv in (Ticket.ABERTO, Ticket.EM_ATENDIMENTO, Ticket.ENCERRADO, Ticket.CANCELADO) else None


# ── Quadros (boards) ─────────────────────────────────────────

class KanbanQuadroCriarView(LoginRequiredMixin, View):
    def post(self, request):
        from .models import KanbanQuadro, KanbanColuna
        nome = (request.POST.get('nome') or '').strip()
        if not nome:
            return JsonResponse({'error': 'Informe o nome do quadro'}, status=400)
        ultimo = KanbanQuadro.objects.order_by('-ordem').first()
        ordem = (ultimo.ordem + 1) if ultimo else 0
        quadro = KanbanQuadro.objects.create(nome=nome, is_padrao=False, ordem=ordem)
        # Coluna inicial para o quadro já ser utilizável
        KanbanColuna.objects.create(quadro=quadro, nome='A fazer', cor='#607d8b', ordem=0)
        return JsonResponse({'ok': True, 'id': quadro.id, 'nome': quadro.nome})


class KanbanQuadroEditarView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from .models import KanbanQuadro
        quadro = get_object_or_404(KanbanQuadro, pk=pk)
        if quadro.is_padrao:
            return JsonResponse({'error': 'O quadro padrão não pode ser renomeado'}, status=400)
        nome = (request.POST.get('nome') or '').strip()
        if nome:
            quadro.nome = nome
            quadro.save(update_fields=['nome'])
        return JsonResponse({'ok': True, 'nome': quadro.nome})


class KanbanQuadroExcluirView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from .models import KanbanQuadro
        quadro = get_object_or_404(KanbanQuadro, pk=pk)
        if quadro.is_padrao:
            return JsonResponse({'error': 'O quadro padrão não pode ser excluído'}, status=400)
        quadro.delete()  # colunas e cards em cascata
        return JsonResponse({'ok': True})


# ── Colunas ──────────────────────────────────────────────────

class KanbanColunaCriarView(LoginRequiredMixin, View):
    def post(self, request):
        from .models import KanbanColuna, KanbanQuadro
        quadro = get_object_or_404(KanbanQuadro, pk=request.POST.get('quadro_id'))
        nome = (request.POST.get('nome') or '').strip()
        cor = (request.POST.get('cor') or '#607d8b').strip()
        if not nome:
            return JsonResponse({'error': 'Informe o nome da coluna'}, status=400)
        status = _parse_status_associado(request.POST.get('status_associado'))
        ultima = quadro.colunas.order_by('-ordem').first()
        ordem = (ultima.ordem + 1) if ultima else 0
        coluna = KanbanColuna.objects.create(
            quadro=quadro, nome=nome, cor=cor, ordem=ordem, status_associado=status)
        return JsonResponse({'ok': True, 'id': coluna.id, 'nome': coluna.nome, 'cor': coluna.cor})


class KanbanColunaEditarView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from .models import KanbanColuna
        coluna = get_object_or_404(KanbanColuna.objects.select_related('quadro'), pk=pk)
        nome = (request.POST.get('nome') or '').strip()
        cor = (request.POST.get('cor') or '').strip()
        campos = []
        if nome:
            coluna.nome = nome
            campos.append('nome')
        if cor:
            coluna.cor = cor
            campos.append('cor')
        # Só permite (re)mapear status em colunas de quadros personalizados
        if not coluna.quadro.is_padrao and 'status_associado' in request.POST:
            coluna.status_associado = _parse_status_associado(request.POST.get('status_associado'))
            campos.append('status_associado')
        if campos:
            coluna.save(update_fields=campos)
        return JsonResponse({'ok': True, 'nome': coluna.nome, 'cor': coluna.cor})


class KanbanColunaExcluirView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from .models import KanbanColuna
        coluna = get_object_or_404(KanbanColuna.objects.select_related('quadro'), pk=pk)
        if coluna.quadro.is_padrao:
            return JsonResponse({'error': 'Colunas do quadro padrão não podem ser excluídas'}, status=400)
        coluna.delete()  # cards em cascata
        return JsonResponse({'ok': True})


class KanbanColunasReordenarView(LoginRequiredMixin, View):
    def post(self, request):
        from .models import KanbanColuna
        ids = [i for i in (request.POST.get('ordem') or '').split(',') if i]
        for pos, coluna_id in enumerate(ids):
            KanbanColuna.objects.filter(pk=coluna_id).update(ordem=pos)
        return JsonResponse({'ok': True})


# ── Cards e movimentação ─────────────────────────────────────

class TicketMoverColunaView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from .models import KanbanColuna, KanbanCard
        ticket = get_object_or_404(Ticket, pk=pk)
        coluna = get_object_or_404(KanbanColuna.objects.select_related('quadro'), pk=request.POST.get('coluna_id'))
        status_destino = coluna.status_associado

        if status_destino is not None and status_destino != ticket.status:
            if status_destino == Ticket.EM_ATENDIMENTO and ticket.status == Ticket.ABERTO:
                ticket.iniciar_atendimento(request.user)
            elif status_destino == Ticket.ENCERRADO:
                # Encerrar exige solução — tratado pelo modal (close-ajax) antes de mover
                return JsonResponse({'error': 'needs_solution'}, status=400)
            # Demais casos: apenas reposiciona (sem transição de negócio)

        # Este endpoint é usado apenas pelo quadro padrão (move por ticket)
        ticket.kanban_coluna = coluna
        ticket.kanban_ordem = 0
        ticket.save(update_fields=['kanban_coluna', 'kanban_ordem'])

        return JsonResponse({
            'ok': True,
            'status': ticket.status,
            'responsavel': ticket.responsavel.get_full_name() if ticket.responsavel else '',
        })


class KanbanCardMoverView(LoginRequiredMixin, View):
    """Move um card (ticket ou avulso) entre colunas de um quadro personalizado."""
    def post(self, request):
        from .models import KanbanColuna, KanbanCard
        card = get_object_or_404(
            KanbanCard.objects.select_related('ticket', 'coluna__quadro'),
            pk=request.POST.get('card_id'),
        )
        coluna = get_object_or_404(KanbanColuna.objects.select_related('quadro'), pk=request.POST.get('coluna_id'))
        if coluna.quadro_id != card.coluna.quadro_id:
            return JsonResponse({'error': 'Coluna de outro quadro'}, status=400)

        ticket = card.ticket
        nota = card.nota
        status_destino = coluna.status_associado

        if ticket and status_destino is not None and status_destino != ticket.status:
            if status_destino == Ticket.EM_ATENDIMENTO and ticket.status == Ticket.ABERTO:
                ticket.iniciar_atendimento(request.user)
            elif status_destino == Ticket.ENCERRADO:
                return JsonResponse({'error': 'needs_solution'}, status=400)

        # Nota do mural: status usa os mesmos inteiros (0..3), aplica direto
        if nota and status_destino is not None and status_destino != nota.status:
            nota.status = status_destino
            nota.save(update_fields=['status'])

        card.coluna = coluna
        card.ordem = 0
        card.save(update_fields=['coluna', 'ordem'])
        return JsonResponse({
            'ok': True,
            'status': ticket.status if ticket else None,
            'responsavel': ticket.responsavel.get_full_name() if ticket and ticket.responsavel else '',
            'nota_status': nota.get_status_display() if nota else None,
            'nota_cor': nota.cor_status if nota else None,
        })


class KanbanCardAdicionarView(LoginRequiredMixin, View):
    """Adiciona um ticket a uma coluna de um quadro personalizado."""
    def post(self, request):
        from .models import KanbanColuna, KanbanCard
        coluna = get_object_or_404(KanbanColuna.objects.select_related('quadro'), pk=request.POST.get('coluna_id'))
        if coluna.quadro.is_padrao:
            return JsonResponse({'error': 'O quadro padrão é preenchido automaticamente'}, status=400)
        ticket = get_object_or_404(
            Ticket.objects.select_related('cliente', 'prioridade', 'responsavel', 'tipo'),
            pk=request.POST.get('ticket_id'),
        )
        if KanbanCard.objects.filter(ticket=ticket, coluna__quadro=coluna.quadro).exists():
            return JsonResponse({'error': 'Este ticket já está neste quadro'}, status=400)
        card = KanbanCard.objects.create(ticket=ticket, coluna=coluna, ordem=0)
        html = render_to_string('core/_kanban_card.html', {
            'ticket': ticket, 'draggable': True, 'card_id': card.id, 'card': card,
            'done': coluna.status_associado == Ticket.ENCERRADO,
        })
        return JsonResponse({'ok': True, 'html': html})


class NotaBuscaAjaxView(LoginRequiredMixin, View):
    """Busca notas do mural por título/conteúdo (para adicionar cards a um quadro)."""
    def get(self, request):
        from tiqt.apps.mural.models import Nota
        q = (request.GET.get('q') or '').strip()
        base = Nota.objects.select_related('categoria')
        if q:
            base = base.filter(Q(titulo__icontains=q) | Q(conteudo__icontains=q))
        else:
            base = base.none()
        resultados = [{
            'id': n.pk,
            'titulo': n.titulo,
            'categoria': n.categoria.nome if n.categoria_id else '',
            'status': n.get_status_display(),
        } for n in base.order_by('-criado_em')[:20]]
        return JsonResponse({'resultados': resultados})


class KanbanCardAdicionarNotaView(LoginRequiredMixin, View):
    """Vincula uma nota do mural a uma coluna de um quadro personalizado."""
    def post(self, request):
        from .models import KanbanColuna, KanbanCard
        from tiqt.apps.mural.models import Nota
        coluna = get_object_or_404(KanbanColuna.objects.select_related('quadro'), pk=request.POST.get('coluna_id'))
        if coluna.quadro.is_padrao:
            return JsonResponse({'error': 'O quadro padrão é preenchido automaticamente'}, status=400)
        nota = get_object_or_404(
            Nota.objects.select_related('categoria', 'responsavel'), pk=request.POST.get('nota_id'))
        if KanbanCard.objects.filter(nota=nota, coluna__quadro=coluna.quadro).exists():
            return JsonResponse({'error': 'Esta nota já está neste quadro'}, status=400)

        # Ao entrar numa coluna com status, a nota já assume esse status
        if coluna.status_associado is not None and nota.status != coluna.status_associado:
            nota.status = coluna.status_associado
            nota.save(update_fields=['status'])

        card = KanbanCard.objects.create(nota=nota, coluna=coluna, ordem=0)
        html = render_to_string('core/_kanban_nota_card.html', {
            'card': card, 'done': coluna.status_associado == Ticket.ENCERRADO,
        })
        return JsonResponse({'ok': True, 'html': html})


def _cliente_id_valido(valor):
    """Retorna um id de cliente válido (ou None se vazio/inexistente)."""
    valor = (valor or '').strip()
    if not valor:
        return None
    from .models import Cliente
    return valor if Cliente.objects.filter(pk=valor).exists() else None


def _render_card_comentario(coment):
    """HTML de um comentário de card avulso, estilo Trello (avatar + autor + tempo)."""
    from django.utils.html import escape
    autor = escape(coment.autor.get_full_name() or coment.autor.username)
    data = timezone.localtime(coment.criado_em).strftime('%d/%m/%Y %H:%M')
    texto_html = escape(coment.texto).replace('\n', '<br>')
    if getattr(coment.autor, 'foto', None):
        avatar = f'<span class="fc-c-avatar"><img src="{coment.autor.foto.url}" alt=""></span>'
    else:
        inicial = escape((autor[:1] or '?').upper())
        avatar = f'<span class="fc-c-avatar">{inicial}</span>'
    return (
        '<div class="fc-comment">'
        f'{avatar}'
        '<div class="fc-comment-body">'
        f'<div class="fc-comment-head"><b>{autor}</b> <span>{data}</span></div>'
        f'<div class="fc-comment-text">{texto_html}</div>'
        '</div>'
        '</div>'
    )


def _id_valido(modelo, valor):
    """Retorna o id se existir no modelo, senão None (aceita vazio)."""
    valor = (valor or '').strip()
    if not valor:
        return None
    return valor if modelo.objects.filter(pk=valor).exists() else None


class KanbanCardAvulsoSalvarView(LoginRequiredMixin, View):
    """Cria ou edita um card avulso (nota livre, sem ticket) num quadro personalizado."""
    def post(self, request):
        from .models import KanbanColuna, KanbanCard
        titulo = (request.POST.get('titulo') or '').strip()
        if not titulo:
            return JsonResponse({'error': 'Informe um título para o card'}, status=400)
        texto = (request.POST.get('texto') or '').strip()
        cliente_id = _cliente_id_valido(request.POST.get('cliente_id'))
        responsavel_id = _id_valido(User, request.POST.get('responsavel_id'))
        prioridade_id = _id_valido(Prioridade, request.POST.get('prioridade_id'))
        membros_ids = [m for m in request.POST.getlist('membros')
                       if User.objects.filter(pk=m).exists()]
        card_id = request.POST.get('card_id')

        if card_id:  # edição
            card = get_object_or_404(KanbanCard, pk=card_id)
            card.titulo = titulo
            card.texto = texto
            card.cliente_id = cliente_id
            card.responsavel_id = responsavel_id
            card.prioridade_id = prioridade_id
            card.save(update_fields=['titulo', 'texto', 'cliente', 'responsavel', 'prioridade'])
        else:        # criação
            coluna = get_object_or_404(KanbanColuna.objects.select_related('quadro'), pk=request.POST.get('coluna_id'))
            if coluna.quadro.is_padrao:
                return JsonResponse({'error': 'Cards avulsos só em quadros personalizados'}, status=400)
            card = KanbanCard.objects.create(
                coluna=coluna, ticket=None, titulo=titulo, texto=texto, cliente_id=cliente_id,
                responsavel_id=responsavel_id, prioridade_id=prioridade_id,
                autor=request.user, ordem=0)

        card.membros.set(membros_ids)

        card = (KanbanCard.objects
                .select_related('cliente', 'coluna', 'responsavel', 'prioridade')
                .prefetch_related('membros', 'etiquetas')
                .get(pk=card.id))
        html = render_to_string('core/_kanban_free_card.html', {
            'card': card, 'done': card.coluna.status_associado == Ticket.ENCERRADO,
        })
        return JsonResponse({'ok': True, 'id': card.id, 'html': html})


class KanbanCardDetalheView(LoginRequiredMixin, View):
    """Retorna os dados de um card avulso (para o modal de edição), incluindo comentários."""
    def get(self, request):
        from .models import KanbanCard
        card = get_object_or_404(
            KanbanCard.objects.select_related('cliente', 'responsavel', 'prioridade')
            .prefetch_related('comentarios__autor', 'membros', 'etiquetas'),
            pk=request.GET.get('card_id'),
        )
        comentarios_html = ''.join(_render_card_comentario(c) for c in card.comentarios.all())
        membros = [{'id': u.id, 'nome': u.get_full_name() or u.username} for u in card.membros.all()]
        return JsonResponse({
            'ok': True,
            'titulo': card.titulo,
            'texto': card.texto,
            'cliente_id': card.cliente_id or '',
            'cliente_text': str(card.cliente) if card.cliente_id else '',
            'responsavel_id': card.responsavel_id or '',
            'prioridade_id': card.prioridade_id or '',
            'membros': membros,
            'etiquetas_html': _card_etiquetas_html(card),
            'comentarios_html': comentarios_html,
        })


class KanbanCardComentarView(LoginRequiredMixin, View):
    """Adiciona um comentário a um card avulso."""
    def post(self, request):
        from .models import KanbanCard, KanbanCardComentario
        card = get_object_or_404(KanbanCard, pk=request.POST.get('card_id'))
        texto = (request.POST.get('texto') or '').strip()
        if not texto:
            return JsonResponse({'error': 'Escreva um comentário'}, status=400)
        coment = KanbanCardComentario.objects.create(card=card, texto=texto, autor=request.user)
        return JsonResponse({'ok': True, 'html': _render_card_comentario(coment)})


# ── Etiquetas do Kanban (estilo Trello) ────────────────────────────────────

def _etiquetas_payload(card=None):
    """Lista todas as etiquetas; marca quais estão aplicadas ao card (se dado)."""
    from .models import Etiqueta
    aplicadas = set(card.etiquetas.values_list('id', flat=True)) if card else set()
    return [{
        'id': e.id, 'nome': e.nome, 'cor': e.cor, 'aplicada': e.id in aplicadas,
    } for e in Etiqueta.objects.all()]


def _card_etiquetas_html(card):
    """Chips das etiquetas do card, para atualizar o card na tela após um toggle."""
    return render_to_string('core/_kanban_etiquetas.html', {'etiquetas': card.etiquetas.all()})


class EtiquetaListView(LoginRequiredMixin, View):
    """Todas as etiquetas; com ?card_id=, indica quais estão no card."""
    def get(self, request):
        from .models import KanbanCard
        card = None
        card_id = request.GET.get('card_id')
        if card_id:
            card = get_object_or_404(KanbanCard, pk=card_id)
        return JsonResponse({'etiquetas': _etiquetas_payload(card)})


class EtiquetaCriarView(LoginRequiredMixin, View):
    """Cria uma etiqueta nova (nome opcional + cor)."""
    def post(self, request):
        from .models import Etiqueta
        cor = (request.POST.get('cor') or '').strip()
        if not cor:
            return JsonResponse({'error': 'Escolha uma cor'}, status=400)
        etiqueta = Etiqueta.objects.create(
            nome=(request.POST.get('nome') or '').strip()[:40], cor=cor[:7])
        return JsonResponse({'ok': True, 'id': etiqueta.id, 'nome': etiqueta.nome, 'cor': etiqueta.cor})


class EtiquetaEditarView(LoginRequiredMixin, View):
    """Renomeia/recolore uma etiqueta (afeta todos os cards que a usam)."""
    def post(self, request):
        from .models import Etiqueta
        etiqueta = get_object_or_404(Etiqueta, pk=request.POST.get('etiqueta_id'))
        cor = (request.POST.get('cor') or '').strip()
        if cor:
            etiqueta.cor = cor[:7]
        etiqueta.nome = (request.POST.get('nome') or '').strip()[:40]
        etiqueta.save(update_fields=['nome', 'cor'])
        return JsonResponse({'ok': True, 'id': etiqueta.id, 'nome': etiqueta.nome, 'cor': etiqueta.cor})


class EtiquetaExcluirView(LoginRequiredMixin, View):
    """Exclui uma etiqueta do sistema (remove de todos os cards)."""
    def post(self, request):
        from .models import Etiqueta
        Etiqueta.objects.filter(pk=request.POST.get('etiqueta_id')).delete()
        return JsonResponse({'ok': True})


class CardMembrosSalvarView(LoginRequiredMixin, View):
    """Define os membros de um card do Kanban (serve para card de ticket, nota ou avulso).

    É informação interna do Kanban: não altera o ticket nem a nota vinculados."""
    def post(self, request):
        from .models import KanbanCard
        card = get_object_or_404(KanbanCard, pk=request.POST.get('card_id'))
        ids = [m for m in request.POST.getlist('membros') if User.objects.filter(pk=m).exists()]
        card.membros.set(ids)
        html = render_to_string('core/_kanban_membros.html', {'membros': card.membros.all()})
        return JsonResponse({'ok': True, 'html': html})


class KanbanQuadroFundoView(LoginRequiredMixin, View):
    """Salva o fundo (wallpaper) do Modo Kanban de um quadro."""
    def post(self, request):
        from .models import KanbanQuadro
        quadro = get_object_or_404(KanbanQuadro, pk=request.POST.get('quadro_id'))
        quadro.fundo = (request.POST.get('fundo') or '').strip()[:255]
        quadro.save(update_fields=['fundo'])
        return JsonResponse({'ok': True, 'fundo': quadro.fundo})


class CardEtiquetaToggleView(LoginRequiredMixin, View):
    """Aplica/remove uma etiqueta de um card. Retorna os chips atualizados do card."""
    def post(self, request):
        from .models import KanbanCard, Etiqueta
        card = get_object_or_404(KanbanCard, pk=request.POST.get('card_id'))
        etiqueta = get_object_or_404(Etiqueta, pk=request.POST.get('etiqueta_id'))
        if card.etiquetas.filter(pk=etiqueta.pk).exists():
            card.etiquetas.remove(etiqueta)
            aplicada = False
        else:
            card.etiquetas.add(etiqueta)
            aplicada = True
        return JsonResponse({'ok': True, 'aplicada': aplicada, 'html': _card_etiquetas_html(card)})


class TicketEnviarMuralView(LoginRequiredMixin, View):
    """Cria uma nota no mural já vinculada a este ticket."""
    def post(self, request, pk):
        from tiqt.apps.mural.models import CategoriaNota, Nota
        ticket = get_object_or_404(Ticket, pk=pk)

        titulo = (request.POST.get('titulo') or '').strip()
        if not titulo:
            return JsonResponse({'error': 'Informe um título para a nota'}, status=400)

        categoria = None
        cat_id = (request.POST.get('categoria') or '').strip()
        if cat_id:
            categoria = CategoriaNota.objects.filter(pk=cat_id, ativo=True).first()

        nota = Nota.objects.create(
            titulo=titulo[:120],
            conteudo=(request.POST.get('conteudo') or '').strip(),
            categoria=categoria,
            ticket=ticket,
            autor=request.user,
        )
        return JsonResponse({'ok': True, 'nota_id': nota.pk})


class KanbanCardRemoverView(LoginRequiredMixin, View):
    """Remove um card de um quadro personalizado (não apaga o ticket vinculado)."""
    def post(self, request):
        from .models import KanbanCard
        KanbanCard.objects.filter(pk=request.POST.get('card_id')).delete()
        return JsonResponse({'ok': True})


class TicketBuscaAjaxView(LoginRequiredMixin, View):
    """Busca tickets por #id, título ou cliente (para adicionar cards a um quadro)."""
    def get(self, request):
        q = (request.GET.get('q') or '').strip()
        base = Ticket.objects.select_related('cliente')
        # Aceita "#332", "332" ou texto (título/cliente), combinando número + texto
        num = q.lstrip('#').strip()
        filtros = Q()
        if num.isdigit():
            filtros |= Q(pk=int(num))
        if q:
            filtros |= (
                Q(titulo__icontains=q)
                | Q(cliente__fantasia__icontains=q)
                | Q(cliente__razao_social__icontains=q)
            )
        base = base.filter(filtros) if filtros else base.none()
        resultados = [{
            'id': t.pk,
            'titulo': t.titulo or '(sem título)',
            'cliente': str(t.cliente),
            'status': t.get_status_display(),
        } for t in base.order_by('-id')[:20]]
        return JsonResponse({'resultados': resultados})


class TicketComentarAjaxView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from django.utils.html import escape
        ticket = get_object_or_404(Ticket, pk=pk)
        texto = (request.POST.get('texto') or '').strip()
        if not texto:
            return JsonResponse({'error': 'Escreva um comentário'}, status=400)
        comentario = Comentario.objects.create(
            ticket=ticket, texto=texto, autor=request.user, tipo_id=1,
        )
        autor = escape(request.user.get_full_name() or request.user.username)
        data = timezone.localtime(comentario.criado_em).strftime('%d/%m/%Y %H:%M')
        tipo = escape(comentario.tipo.descricao) if comentario.tipo else ''
        texto_html = escape(texto).replace('\n', '<br>')
        html = (
            '<div class="tp-block">'
            f'<div class="tp-block-meta">{autor} • {data}'
            f'{" • " + tipo if tipo else ""}</div>'
            f'<div class="tp-block-text">{texto_html}</div>'
            '</div>'
        )
        return JsonResponse({'ok': True, 'html': html})


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
    paginate_by = 15

    def get_queryset(self):
        queryset = Cliente.objects.all().order_by('fantasia')

        q = self.request.GET.get('q')
        cidade = self.request.GET.get('cidade')
        uf = self.request.GET.get('uf')
        tributacao = self.request.GET.get('tributacao')
        situacao = self.request.GET.get('situacao') or 'ativos'

        # Por padrão, mostra apenas clientes ativos (esconde os inativados).
        # Trata `ativo=NULL` (registros antigos) como ativo.
        if situacao == 'inativos':
            queryset = queryset.filter(ativo=False)
        elif situacao == 'todos':
            pass
        else:  # ativos (padrão)
            queryset = queryset.filter(Q(ativo=True) | Q(ativo__isnull=True))

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
        context['situacao'] = self.request.GET.get('situacao') or 'ativos'
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
        context['tickets_count'] = self.object.ticket_set.count()
        return context

    def form_valid(self, form):
        # Cliente com tickets é protegido (Ticket.cliente = PROTECT). Em vez de
        # estourar ProtectedError (500), bloqueia e avisa o usuário.
        self.object = self.get_object()
        try:
            return super().form_valid(form)
        except ProtectedError:
            n = self.object.ticket_set.count()
            messages.error(
                self.request,
                f'Não é possível excluir "{self.object}" porque há {n} '
                f'ticket(s) vinculado(s) a este cliente.'
            )
            return redirect('cliente_update', pk=self.object.pk)


class ClienteInativarView(LoginRequiredMixin, View):
    """Inativa um cliente (não exclui): ele deixa de aparecer nas listagens e
    buscas, mas os tickets vinculados são preservados."""

    def post(self, request, pk):
        cliente = get_object_or_404(Cliente, pk=pk)
        cliente.ativo = False
        cliente.motivo_inativacao = (request.POST.get('motivo') or '').strip()
        cliente.data_inativacao = timezone.now()
        cliente.save(update_fields=['ativo', 'motivo_inativacao', 'data_inativacao'])
        messages.success(request, f'Cliente "{cliente}" inativado com sucesso.')
        return redirect('cliente_list')


class ClienteReativarView(LoginRequiredMixin, View):
    """Reativa um cliente previamente inativado."""

    def post(self, request, pk):
        cliente = get_object_or_404(Cliente, pk=pk)
        cliente.ativo = True
        cliente.motivo_inativacao = None
        cliente.data_inativacao = None
        cliente.save(update_fields=['ativo', 'motivo_inativacao', 'data_inativacao'])
        messages.success(request, f'Cliente "{cliente}" reativado com sucesso.')
        return redirect(f"{reverse('cliente_list')}?situacao=inativos")


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
            .filter(Q(ativo=True) | Q(ativo__isnull=True))
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


def _cliente_label(cliente):
    """Mesmo formato usado por clientes_busca_api, para o front reaproveitar."""
    return " - ".join(filter(None, [cliente.fantasia, cliente.razao_social, cliente.cnpj]))


class ClienteQuickCreateView(LoginRequiredMixin, View):
    """Cadastro rápido de empresa (modal). Retorna {id, text} pronto para
    ser selecionado nos autocompletes de cliente das telas de novo ticket."""

    def post(self, request):
        cnpj = ''.join(filter(str.isdigit, request.POST.get('cnpj') or ''))
        if cnpj:
            existente = Cliente.objects.filter(cnpj=cnpj).first()
            if existente:
                return JsonResponse({
                    'error': 'Já existe uma empresa cadastrada com este CNPJ.',
                    'id': existente.id,
                    'text': _cliente_label(existente),
                }, status=400)

        form = ClienteForm(request.POST)
        if not form.is_valid():
            primeiro = next(iter(form.errors.values()))[0]
            return JsonResponse({'error': primeiro, 'errors': form.errors}, status=400)

        if not (form.cleaned_data.get('fantasia') or form.cleaned_data.get('razao_social')):
            return JsonResponse({'error': 'Informe ao menos a razão social ou o nome fantasia.'}, status=400)

        cliente = form.save()
        return JsonResponse({'ok': True, 'id': cliente.id, 'text': _cliente_label(cliente)})


# ─── API: busca de clientes retornando id + nome (para o modal rápido) ────────
def clientes_busca_api(request):
    q = request.GET.get('q', '').strip()
    results = []
    if q:
        clientes = (
            Cliente.objects
            .filter(Q(ativo=True) | Q(ativo__isnull=True))
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
        resp = http_requests.get(f'https://brasilapi.com.br/api/cnpj/v1/{cnpj}', timeout=10)
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
            resp = http_requests.get(f'https://publica.cnpj.ws/cnpj/{cnpj}', timeout=10)
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

        notificar_atribuicao(ticket, ator=request.user, notificar_ator=False)

        return JsonResponse({'redirect': reverse('ticket_detail', kwargs={'pk': ticket.pk})})