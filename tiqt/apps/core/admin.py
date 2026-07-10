from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Ticket, Comentario, Departamento, Cliente, Etiqueta


@admin.register(Etiqueta)
class EtiquetaAdmin(admin.ModelAdmin):
    list_display = ['id', 'nome', 'cor', 'criado_em']

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