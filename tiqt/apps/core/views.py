from django.views import View
from django.views.generic import TemplateView, DetailView, ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LogoutView as BaseLogoutView
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache
from django.forms import modelform_factory
from django.shortcuts import reverse, render, resolve_url
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django_tables2 import SingleTableMixin
from tiqt.apps.core.models import Ticket
from tiqt.apps.core.models import Comentario
from tiqt.apps.core.tables import TicketTable
from .forms import TicketForm, ClienteForm, TicketCloseForm
from .models import Cliente, Ticket, Solucao
from .filters import TicketFilterForm
import tiqt.settings as settings


def HomeView(request):
    atendimentos_aberto = Ticket.objects.filter(status=Ticket.ABERTO).count()
    atendimentos_andamento = Ticket.objects.filter(status=Ticket.EM_ATENDIMENTO).count()
    atendimentos_finalizados = Ticket.objects.filter(status=Ticket.ENCERRADO).count()

    context = {
        'atendimentos_aberto': atendimentos_aberto,
        'atendimentos_andamento': atendimentos_andamento,
        'atendimentos_finalizados': atendimentos_finalizados,
    }

    return render(request, 'core/home.html', context)


class MyTicketsView(LoginRequiredMixin, SingleTableMixin, TemplateView):
    template_name = 'core/tickets_list.html'
    table_class = TicketTable
    # table_pagination = {
    #     'per_page': 10
    # }

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

    # table_pagination = {
    #     'per_page': 10
    # }   

class InProgressTicketsView(LoginRequiredMixin, SingleTableMixin, TemplateView):
    template_name = 'core/tickets_list.html'
    table_class = TicketTable
    table_data = Ticket.objects.filter(status=Ticket.EM_ATENDIMENTO)
    # table_pagination = {
    #     'per_page': 10
    # }


class ClosedTicketsView(LoginRequiredMixin, SingleTableMixin, TemplateView):
    template_name = 'core/tickets_list.html'
    table_class = TicketTable
    table_data = Ticket.objects.filter(status=Ticket.ENCERRADO)
    # table_pagination = {
    #     'per_page': 10
    # }


class NewTicketView(LoginRequiredMixin, CreateView):
    template_name = 'core/ticket_form.html'
    form_class = TicketForm


class TicketUpdateView(LoginRequiredMixin, UpdateView):
    model = Ticket
    form_class = TicketForm
    template_name = 'core/ticket_form.html'


class TicketDetailView(LoginRequiredMixin, DetailView):
    template_name = 'core/ticket_detail.html'
    model = Ticket

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["comment_form"] = modelform_factory(
            Comentario, exclude=('criado_em', 'ticket', ))
        context["comments"] = self.object.comentario_set.all()
        return context


class TicketAcceptView(LoginRequiredMixin, View):

    def get(self, request, pk):
        ticket = Ticket.objects.get(pk=pk)
        ticket.iniciar_atendimento(request.user)
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
            ticket=ticket, texto=request.POST['texto'], autor=request.user)
        comment.save()
        return HttpResponseRedirect(
            reverse("ticket_detail", kwargs={"pk": ticket_pk}))

class ClienteListView(ListView):
    model = Cliente
    template_name = 'core/cliente_list.html'
    context_object_name = 'clientes'

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
        """Logout may be done via POST."""
        auth_logout(request)
        redirect_to = self.get_success_url()
        if redirect_to != request.get_full_path():
            # Redirect to target page once the session has been cleared.
            return HttpResponseRedirect(redirect_to)
        return super().get(request, *args, **kwargs)

    def get_default_redirect_url(self):
        """Return the default redirect URL."""
        if self.next_page:
            return resolve_url(self.next_page)
        elif settings.LOGOUT_REDIRECT_URL:
            return resolve_url(settings.LOGOUT_REDIRECT_URL)
        else:
            return self.request.path