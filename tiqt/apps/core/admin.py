from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import (User, Ticket, Comentario, Departamento, Cliente, Etiqueta,
                     CaixaEntradaRecusa, Expediente, Feriado, Prioridade,
                     SlaPolitica, TicketEvento)
from .services.sla import carregar_calendario, invalidar_calendario, minutos_por_dia_util

# Quando não há Expediente cadastrado, `minutos_por_dia_util` é 0 e não dá para
# converter dias em minutos. 8h é só para o admin não quebrar antes de alguém
# cadastrar o expediente — o SLA de verdade usa o calendário real.
MINUTOS_DIA_FALLBACK = 480


def _minutos_dia():
    return minutos_por_dia_util(carregar_calendario()) or MINUTOS_DIA_FALLBACK


def _legivel(minutos):
    """588 -> '1d'; 3494 -> '5d 9h'; 90 -> '1h30'. O 'dia' é o expediente."""
    if minutos is None:
        return '—'
    por_dia = _minutos_dia()
    if minutos < 60:
        return '%dmin' % minutos
    if minutos < por_dia:
        h, m = divmod(minutos, 60)
        return '%dh%s' % (h, '%02d' % m if m else '')
    dias, resto = divmod(minutos, por_dia)
    horas = resto // 60
    return '%dd%s' % (dias, ' %dh' % horas if horas else '')


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


class SlaPoliticaForm(forms.ModelForm):
    """Cadastro em dias e horas — ninguém precisa saber que 2352min são 4 dias.

    O modelo continua guardando MINUTOS ÚTEIS (é o que o cálculo de SLA usa);
    estes campos são só a tradução na entrada e na saída. E "dia" aqui é o
    expediente cadastrado, não 24h — por isso a conversão passa pelo calendário.
    """

    resposta_dias = forms.IntegerField(label='Dias', min_value=0, initial=0, required=False)
    resposta_horas = forms.IntegerField(label='Horas', min_value=0, max_value=23, initial=0, required=False)
    resposta_minutos = forms.IntegerField(label='Minutos', min_value=0, max_value=59, initial=0, required=False)
    resolucao_dias = forms.IntegerField(label='Dias', min_value=0, initial=0, required=False)
    resolucao_horas = forms.IntegerField(label='Horas', min_value=0, max_value=23, initial=0, required=False)
    resolucao_minutos = forms.IntegerField(label='Minutos', min_value=0, max_value=59, initial=0, required=False)

    class Meta:
        model = SlaPolitica
        fields = ['departamento', 'prioridade', 'ativo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        por_dia = _minutos_dia()
        h = por_dia // 60, por_dia % 60
        aviso = 'Um dia útil = %dh%s (o expediente cadastrado), não 24h.' % (
            h[0], '%02d' % h[1] if h[1] else '')
        self.fields['resposta_dias'].help_text = aviso
        self.fields['resolucao_dias'].help_text = aviso

        # Editando: decompõe os minutos gravados de volta em dias + horas + min.
        # Sem o resto em minutos, abrir e salvar uma meta de 2h27 a truncaria
        # para 2h — o form comeria 27 minutos em silêncio.
        if self.instance and self.instance.pk:
            for campo in ('resposta', 'resolucao'):
                total = getattr(self.instance, 'minutos_%s' % campo) or 0
                dias, resto = divmod(total, por_dia)
                horas, minutos = divmod(resto, 60)
                self.fields['%s_dias' % campo].initial = dias
                self.fields['%s_horas' % campo].initial = horas
                self.fields['%s_minutos' % campo].initial = minutos

    def _compor(self, campo):
        por_dia = _minutos_dia()
        dias = self.cleaned_data.get('%s_dias' % campo) or 0
        horas = self.cleaned_data.get('%s_horas' % campo) or 0
        minutos = self.cleaned_data.get('%s_minutos' % campo) or 0
        return dias * por_dia + horas * 60 + minutos

    def clean(self):
        dados = super().clean()
        self.instance.minutos_resposta = self._compor('resposta')
        self.instance.minutos_resolucao = self._compor('resolucao')

        if not self.instance.minutos_resposta:
            raise forms.ValidationError('Informe a meta de resposta (dias, horas e/ou minutos).')
        if not self.instance.minutos_resolucao:
            raise forms.ValidationError('Informe a meta de resolução (dias, horas e/ou minutos).')
        # Resolver mais rápido do que responder é contradição: o relógio da
        # resolução conta desde a abertura, então ele inclui o de resposta.
        if self.instance.minutos_resolucao < self.instance.minutos_resposta:
            raise forms.ValidationError(
                'A meta de resolução não pode ser menor que a de resposta — as duas '
                'contam desde a abertura do ticket.')
        return dados


@admin.register(SlaPolitica)
class SlaPoliticaAdmin(admin.ModelAdmin):
    form = SlaPoliticaForm
    list_display = ['departamento_ou_todos', 'prioridade_ou_todas',
                    'meta_resposta', 'meta_resolucao', 'ativo']
    list_filter = ['ativo', 'departamento', 'prioridade']
    fieldsets = (
        (None, {
            'fields': ('departamento', 'prioridade', 'ativo'),
            'description': 'Deixe Departamento ou Prioridade em branco para valer como curinga. '
                           'A política mais específica sempre vence.',
        }),
        ('Meta de RESPOSTA — tempo até alguém iniciar o atendimento', {
            'fields': (('resposta_dias', 'resposta_horas', 'resposta_minutos'),),
        }),
        ('Meta de RESOLUÇÃO — tempo até encerrar, contado desde a abertura', {
            'fields': (('resolucao_dias', 'resolucao_horas', 'resolucao_minutos'),),
        }),
    )

    @admin.display(description='Departamento', ordering='departamento')
    def departamento_ou_todos(self, obj):
        # format_html exige ao menos um argumento — sem placeholder ele levanta
        # TypeError e derruba a listagem inteira.
        return obj.departamento or format_html('<i style="opacity:.6">{}</i>', 'todos')

    @admin.display(description='Prioridade', ordering='prioridade')
    def prioridade_ou_todas(self, obj):
        return obj.prioridade or format_html('<i style="opacity:.6">{}</i>', 'todas')

    @admin.display(description='Resposta', ordering='minutos_resposta')
    def meta_resposta(self, obj):
        return format_html('<b>{}</b> <span style="opacity:.5">({} min)</span>',
                           _legivel(obj.minutos_resposta), obj.minutos_resposta)

    @admin.display(description='Resolução', ordering='minutos_resolucao')
    def meta_resolucao(self, obj):
        return format_html('<b>{}</b> <span style="opacity:.5">({} min)</span>',
                           _legivel(obj.minutos_resolucao), obj.minutos_resolucao)


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