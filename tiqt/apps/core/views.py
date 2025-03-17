from django.views import View
from django.views.generic import TemplateView, DetailView, ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LogoutView as BaseLogoutView
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache
from django.shortcuts import reverse, render, resolve_url, get_object_or_404, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django_tables2 import SingleTableMixin
from tiqt.apps.core.models import Ticket, Comentario
from tiqt.apps.core.tables import TicketTable
from .forms import TicketForm, ClienteForm, TicketCloseForm, ComentarioForm
from .models import Cliente, Ticket, Solucao, ComentarioArquivo, ComentarioImagem
from .filters import TicketFilterForm
from datetime import datetime
import tiqt.settings as settings
import os
from django.http import JsonResponse


def HomeView(request):
    atendimentos_aberto = Ticket.objects.filter(status=Ticket.ABERTO).count()
    atendimentos_andamento = Ticket.objects.filter(status=Ticket.EM_ATENDIMENTO).count()
    atendimentos_encerrados = Ticket.objects.filter(status=Ticket.ENCERRADO).count()
    atendimentos_cancelados = Ticket.objects.filter(status=Ticket.CANCELADO).count()

    context = {
        'atendimentos_aberto': atendimentos_aberto,
        'atendimentos_andamento': atendimentos_andamento,
        'atendimentos_encerrados': atendimentos_encerrados,
        'atendimentos_cancelados': atendimentos_cancelados,
    }

    return render(request, 'core/home.html', context)

def excluir_arquivo(request, comentario_id, tipo):
    comentario = get_object_or_404(Comentario, id=comentario_id)

    if tipo == 'imagem' and comentario.imagem:
        caminho_arquivo = os.path.join(settings.MEDIA_ROOT, str(comentario.imagem))
        if os.path.exists(caminho_arquivo):
            os.remove(caminho_arquivo)
        comentario.imagem = None

    elif tipo == 'arquivo' and comentario.arquivo:
        caminho_arquivo = os.path.join(settings.MEDIA_ROOT, str(comentario.arquivo))
        if os.path.exists(caminho_arquivo):
            os.remove(caminho_arquivo)
        comentario.arquivo = None

    comentario.save()
    return JsonResponse({'status': 'Arquivo excluído com sucesso'})


def apply_filters(queryset, form):
    if form.is_valid():
        # Cliente, Departamento, Tipo, Prioridade e Situação
        if form.cleaned_data['cliente']:
            queryset = queryset.filter(cliente=form.cleaned_data['cliente'])
        if form.cleaned_data['departamento']:
            queryset = queryset.filter(departamento=form.cleaned_data['departamento'])
        if form.cleaned_data['tipo']:
            queryset = queryset.filter(tipo=form.cleaned_data['tipo'])
        if form.cleaned_data['prioridade']:
            queryset = queryset.filter(prioridade=form.cleaned_data['prioridade'])
        if form.cleaned_data['situacao']:
            queryset = queryset.filter(situacao=form.cleaned_data['situacao'])

        # Filtros de Criado em
        if form.cleaned_data['criado_em_inicio']:
            criado_em_inicio = datetime.combine(form.cleaned_data['criado_em_inicio'], datetime.min.time())
            queryset = queryset.filter(criado_em__gte=criado_em_inicio)
        if form.cleaned_data['criado_em_fim']:
            criado_em_fim = datetime.combine(form.cleaned_data['criado_em_fim'], datetime.max.time())
            queryset = queryset.filter(criado_em__lte=criado_em_fim)

        # Filtros de Encerrado em
        if form.cleaned_data['encerrado_em_inicio']:
            encerrado_em_inicio = datetime.combine(form.cleaned_data['encerrado_em_inicio'], datetime.min.time())
            queryset = queryset.filter(encerrado_em__gte=encerrado_em_inicio)
        if form.cleaned_data['encerrado_em_fim']:
            encerrado_em_fim = datetime.combine(form.cleaned_data['encerrado_em_fim'], datetime.max.time())
            queryset = queryset.filter(encerrado_em__lte=encerrado_em_fim)

        # Filtros de Cancelado em
        if form.cleaned_data['cancelado_em_inicio']:
            cancelado_em_inicio = datetime.combine(form.cleaned_data['cancelado_em_inicio'], datetime.min.time())
            queryset = queryset.filter(cancelado_em__gte=cancelado_em_inicio)
        if form.cleaned_data['cancelado_em_fim']:
            cancelado_em_fim = datetime.combine(form.cleaned_data['cancelado_em_fim'], datetime.max.time())
            queryset = queryset.filter(cancelado_em__lte=cancelado_em_fim)

        # Filtros de Solução Criado em
        if form.cleaned_data['solucao_criado_em_inicio']:
            solucao_criado_em_inicio = datetime.combine(form.cleaned_data['solucao_criado_em_inicio'], datetime.min.time())
            queryset = queryset.filter(solucao__criado_em__gte=solucao_criado_em_inicio)
        if form.cleaned_data['solucao_criado_em_fim']:
            solucao_criado_em_fim = datetime.combine(form.cleaned_data['solucao_criado_em_fim'], datetime.max.time())
            queryset = queryset.filter(solucao__criado_em__lte=solucao_criado_em_fim)

    return queryset


class MyTicketsView(LoginRequiredMixin, SingleTableMixin, TemplateView):
    template_name = 'core/tickets_list.html'
    table_class = TicketTable
    table_pagination = {
        'per_page': 10
    }

    def get_table_data(self, **kwargs):
        return Ticket.objects.filter(status=Ticket.EM_ATENDIMENTO, responsavel=self.request.user)

class OpenTicketsView(LoginRequiredMixin, SingleTableMixin, TemplateView):
    template_name = 'core/tickets_list.html'
    table_class = TicketTable

    def get_table_data(self):
        queryset = Ticket.objects.filter(status=Ticket.ABERTO)
        form = TicketFilterForm(self.request.GET)
        if form.is_valid():
            if form.cleaned_data['cliente']:
                queryset = queryset.filter(cliente=form.cleaned_data['cliente'])
            if form.cleaned_data['departamento']:
                queryset = queryset.filter(departamento=form.cleaned_data['departamento'])
            if form.cleaned_data['tipo']:
                queryset = queryset.filter(tipo=form.cleaned_data['tipo'])
            if form.cleaned_data['prioridade']:
                queryset = queryset.filter(prioridade=form.cleaned_data['prioridade'])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = TicketFilterForm(self.request.GET)
        context['request'] = self.request
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
        return apply_filters(queryset, form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = TicketFilterForm(self.request.GET)
        context['request'] = self.request
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
        return apply_filters(queryset, form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = TicketFilterForm(self.request.GET)
        context['request'] = self.request
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
        return apply_filters(queryset, form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = TicketFilterForm(self.request.GET)
        context['request'] = self.request
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
        return apply_filters(queryset, form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = TicketFilterForm(self.request.GET)
        context['request'] = self.request
        return context

    table_pagination = {
        'per_page': 10
    }

class NewTicketView(LoginRequiredMixin, View):
    def get(self, request):
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

# class TicketDetailView(LoginRequiredMixin, View):
#     def get(self, request, pk):
#         ticket = get_object_or_404(Ticket, pk=pk)
#         form = ComentarioForm()
#         comments = ticket.comentario.all()
#         return render(request, 'core/ticket_detail.html', {'object': ticket, 'form': form, 'comments': comments})

#     def post(self, request, pk):
#         ticket = get_object_or_404(Ticket, pk=pk)
#         form = ComentarioForm(request.POST)
#         if form.is_valid():
#             comentario = form.save(commit=False)
#             comentario.ticket = ticket
#             comentario.autor = request.user
#             comentario.save()
#             return redirect('ticket_detail', pk=ticket.pk)
#         comments = ticket.comentario.all()
#         return render(request, 'core/ticket_detail.html', {'object': ticket, 'form': form, 'comments': comments})

class TicketDetailView(View):
    def get(self, request, pk):
        ticket = get_object_or_404(Ticket, pk=pk)
        comments = Comentario.objects.filter(ticket=ticket).order_by('-criado_em')
        solucoes = ticket.get_solucoes()
        form = ComentarioForm()
        return render(request, 'core/ticket_detail.html', {'object': ticket, 'comments': comments, 'solucoes': solucoes, 'form': form})

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

        comments = Comentario.objects.filter(ticket=ticket).order_by('-criado_em')
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
        return HttpResponseRedirect(
            reverse("ticket_detail", kwargs={"pk": ticket_pk}))
    
    def get(self, request, ticket_pk):
        return HttpResponseRedirect(
            reverse("ticket_detail", kwargs={"pk": ticket_pk}))

class ClienteListView(ListView):
    model = Cliente
    template_name = 'core/cliente_list.html'
    context_object_name = 'clientes'

    def get_queryset(self):
        return Cliente.objects.all().order_by('fantasia')

class ClienteCreateView(CreateView):
    model = Cliente
    form_class = ClienteForm
    template_name = 'core/cliente_form.html'
    success_url = reverse_lazy('cliente_list')

class ClienteUpdateView(UpdateView):
    model = Cliente
    form_class = ClienteForm
    template_name = 'core/cliente_form.html'
    success_url = reverse_lazy('cliente_list')

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