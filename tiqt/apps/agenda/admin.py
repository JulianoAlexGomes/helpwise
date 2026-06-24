from django.contrib import admin

from .models import Agendamento


@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'inicio', 'responsavel', 'origem', 'status', 'ticket')
    list_filter = ('status', 'origem', 'responsavel')
    search_fields = ('titulo', 'descricao')
    date_hierarchy = 'inicio'
    autocomplete_fields = ()
    raw_id_fields = ('ticket', 'cliente', 'comentario')
