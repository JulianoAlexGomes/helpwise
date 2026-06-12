from django.contrib import admin

from .models import BaseConhecimento, ConsultaIA


@admin.register(BaseConhecimento)
class BaseConhecimentoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "departamento", "ativo", "atualizado_em")
    list_filter = ("ativo", "departamento")
    search_fields = ("titulo", "palavras_chave", "descricao_problema", "solucao")
    list_editable = ("ativo",)


@admin.register(ConsultaIA)
class ConsultaIAAdmin(admin.ModelAdmin):
    list_display = ("id", "usuario", "resolveu", "modelo", "criado_em")
    list_filter = ("resolveu", "modelo", "criado_em")
    search_fields = ("descricao", "resposta_ia")
    readonly_fields = ("usuario", "imagem", "descricao", "resposta_ia", "modelo", "criado_em")
