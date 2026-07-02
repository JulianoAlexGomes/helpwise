from django.contrib import admin

from .models import CategoriaNota, Nota, NotaArquivo


@admin.register(CategoriaNota)
class CategoriaNotaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cor', 'icone', 'ordem', 'ativo')
    list_editable = ('ordem', 'ativo')
    search_fields = ('nome',)


class NotaArquivoInline(admin.TabularInline):
    model = NotaArquivo
    extra = 0


@admin.register(Nota)
class NotaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'categoria', 'status', 'prioridade', 'responsavel', 'fixado', 'criado_em')
    list_filter = ('status', 'prioridade', 'categoria', 'fixado', 'responsavel')
    search_fields = ('titulo', 'conteudo')
    date_hierarchy = 'criado_em'
    raw_id_fields = ('agendamento',)
    inlines = [NotaArquivoInline]
