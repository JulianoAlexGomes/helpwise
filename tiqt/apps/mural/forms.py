from django import forms
from django.contrib.auth import get_user_model

from .models import CategoriaNota, Nota

User = get_user_model()

# 'browser-default' faz o Materialize ignorar o campo (não converte selects nem
# aplica o estilo underline antigo). Ver memória frontend-gotchas.
_DT_FORMATS = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S']


class NotaForm(forms.ModelForm):
    # Campo extra (não-model): se preenchido, gera/atualiza um Agendamento na agenda.
    agendar_em = forms.DateTimeField(
        required=False,
        input_formats=_DT_FORMATS,
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'class': 'mr-input browser-default'},
            format='%Y-%m-%dT%H:%M',
        ),
    )
    # Campo extra: número do ticket a vincular (opcional).
    ticket_num = forms.IntegerField(
        required=False, min_value=1,
        widget=forms.NumberInput(attrs={'class': 'mr-input browser-default', 'placeholder': 'Nº do ticket'}),
    )

    class Meta:
        model = Nota
        fields = ['titulo', 'conteudo', 'categoria', 'status', 'prioridade',
                  'responsavel', 'vencimento']
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'mr-input browser-default', 'maxlength': 120}),
            'conteudo': forms.Textarea(attrs={'class': 'mr-input browser-default', 'rows': 4}),
            'categoria': forms.Select(attrs={'class': 'mr-input browser-default'}),
            'status': forms.Select(attrs={'class': 'mr-input browser-default'}),
            'prioridade': forms.Select(attrs={'class': 'mr-input browser-default'}),
            'responsavel': forms.Select(attrs={'class': 'mr-input browser-default'}),
            'vencimento': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'mr-input browser-default'},
                format='%Y-%m-%dT%H:%M',
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vencimento'].input_formats = _DT_FORMATS
        self.fields['conteudo'].required = False
        self.fields['categoria'].required = False
        self.fields['responsavel'].required = False
        self.fields['vencimento'].required = False

        self.fields['categoria'].queryset = CategoriaNota.objects.filter(ativo=True)
        self.fields['categoria'].empty_label = 'Sem categoria'

        self.fields['responsavel'].queryset = (
            User.objects.filter(is_active=True).order_by('first_name', 'username')
        )
        self.fields['responsavel'].label_from_instance = (
            lambda u: u.get_full_name() or u.username
        )
        self.fields['responsavel'].empty_label = 'Sem responsável'

        # Pré-preenche agendar_em ao editar uma nota já agendada.
        if self.instance and self.instance.pk and self.instance.agendamento_id:
            self.fields['agendar_em'].initial = self.instance.agendamento.inicio
        # Pré-preenche o nº do ticket ao editar.
        if self.instance and self.instance.pk and self.instance.ticket_id:
            self.fields['ticket_num'].initial = self.instance.ticket_id

    def clean_ticket_num(self):
        num = self.cleaned_data.get('ticket_num')
        if num:
            from tiqt.apps.core.models import Ticket
            if not Ticket.objects.filter(pk=num).exists():
                raise forms.ValidationError('Ticket #%d não encontrado.' % num)
        return num

    def save(self, commit=True):
        nota = super().save(commit=False)
        num = self.cleaned_data.get('ticket_num')
        if num:
            from tiqt.apps.core.models import Ticket
            nota.ticket = Ticket.objects.filter(pk=num).first()
        else:
            nota.ticket = None
        if commit:
            nota.save()
        return nota


class CategoriaNotaForm(forms.ModelForm):
    class Meta:
        model = CategoriaNota
        fields = ['nome', 'cor', 'icone', 'ordem']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'mr-input browser-default', 'maxlength': 60}),
            'cor': forms.TextInput(attrs={'type': 'color', 'class': 'mr-color browser-default'}),
            'icone': forms.TextInput(attrs={'class': 'mr-input browser-default', 'maxlength': 40}),
            'ordem': forms.NumberInput(attrs={'class': 'mr-input browser-default', 'min': 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['icone'].required = False
        self.fields['ordem'].required = False
