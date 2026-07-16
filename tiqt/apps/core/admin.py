from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (User, Ticket, Comentario, Departamento, Cliente, Etiqueta,
                     CaixaEntradaRecusa, Expediente, Feriado, Prioridade,
                     SlaPolitica, TicketEvento)
from .services.sla import invalidar_calendario


class CalendarioCacheMixin:
    """O calendário fica em cache por 5 min; mexer nele pelo admin limpa na hora.

    Sem isso, cadastrar um feriado e não ver efeito nenhum vira sessão de debug."""

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        invalidar_calendario()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        invalidar_calendario()


@admin.register(Expediente)
class ExpedienteAdmin(CalendarioCacheMixin, admin.ModelAdmin):
    list_display = ['dia_semana', 'hora_inicio', 'hora_fim', 'ativo']
    list_filter = ['dia_semana', 'ativo']


@admin.register(Feriado)
class FeriadoAdmin(CalendarioCacheMixin, admin.ModelAdmin):
    list_display = ['data', 'descricao', 'recorrente_anual']
    list_filter = ['recorrente_anual']
    search_fields = ['descricao']


@admin.register(SlaPolitica)
class SlaPoliticaAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'departamento', 'prioridade', 'minutos_resposta',
                    'minutos_resolucao', 'ativo']
    list_filter = ['ativo', 'departamento', 'prioridade']


@admin.register(Prioridade)
class PrioridadeAdmin(admin.ModelAdmin):
    list_display = ['id', 'descricao', 'peso']
    list_editable = ['peso']


@admin.register(TicketEvento)
class TicketEventoAdmin(admin.ModelAdmin):
    """Só leitura: histórico não se edita — é o ponto da tabela existir."""

    list_display = ['id', 'ticket', 'tipo', 'ocorrido_em', 'usuario', 'origem', 'estimado']
    list_filter = ['tipo', 'estimado', 'origem']
    search_fields = ['ticket__id']
    date_hierarchy = 'ocorrido_em'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Etiqueta)
class EtiquetaAdmin(admin.ModelAdmin):
    list_display = ['id', 'nome', 'cor', 'criado_em']


@admin.register(CaixaEntradaRecusa)
class CaixaEntradaRecusaAdmin(admin.ModelAdmin):
    list_display = ['id', 'quadro', 'ticket', 'usuario', 'criado_em']
    list_filter = ['quadro', 'usuario']
    search_fields = ['ticket__id', 'motivo']

class ComentarioInline(admin.TabularInline):
    model = Comentario
    extra = 1

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ['id', 'titulo', 'criado_em']
    inlines = [ComentarioInline]

@admin.register(Comentario)
class ComentarioAdmin(admin.ModelAdmin):
    list_display = ['id', 'ticket', 'autor', 'criado_em']
    list_filter = ['ticket', 'autor']

# aqui preciso registrar o user para poder cadastrar novos usuarios
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active']
    list_filter = UserAdmin.list_filter + ('is_active',)
    actions = ['inativar_atendentes', 'ativar_atendentes']

    @admin.action(description='Inativar atendente(s) selecionado(s)')
    def inativar_atendentes(self, request, queryset):
        atualizados = queryset.update(is_active=False)
        self.message_user(
            request,
            f'{atualizados} atendente(s) inativado(s). Não aparecem mais nos filtros nem conseguem acessar.'
        )

    @admin.action(description='Reativar atendente(s) selecionado(s)')
    def ativar_atendentes(self, request, queryset):
        atualizados = queryset.update(is_active=True)
        self.message_user(request, f'{atualizados} atendente(s) reativado(s).')