from django import forms
from django.contrib.auth import get_user_model

from .models import Agendamento

User = get_user_model()


class AgendamentoForm(forms.ModelForm):
    class Meta:
        model = Agendamento
        fields = ['titulo', 'descricao', 'inicio', 'fim', 'dia_inteiro',
                  'responsavel', 'cliente']
        widgets = {
            # 'browser-default' faz o Materialize ignorar o campo (não converte
            # selects nem aplica o estilo underline antigo via AutoInit).
            'titulo': forms.TextInput(attrs={'class': 'ag-input browser-default', 'maxlength': 120}),
            'descricao': forms.Textarea(attrs={'class': 'ag-input browser-default', 'rows': 3}),
            'inicio': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'ag-input browser-default'},
                format='%Y-%m-%dT%H:%M',
            ),
            'fim': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'ag-input browser-default'},
                format='%Y-%m-%dT%H:%M',
            ),
            'dia_inteiro': forms.CheckboxInput(attrs={'class': 'ag-check browser-default'}),
            'responsavel': forms.Select(attrs={'class': 'ag-input browser-default'}),
            'cliente': forms.Select(attrs={'class': 'ag-input browser-default'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['inicio'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S']
        self.fields['fim'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S']
        self.fields['fim'].required = False
        self.fields['cliente'].required = False
        self.fields['descricao'].required = False
        # Só usuários ativos como responsável
        self.fields['responsavel'].queryset = (
            User.objects.filter(is_active=True).order_by('first_name', 'username')
        )
        self.fields['responsavel'].label_from_instance = (
            lambda u: u.get_full_name() or u.username
        )

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get('inicio')
        fim = cleaned.get('fim')
        if inicio and fim and fim < inicio:
            self.add_error('fim', 'O término não pode ser antes do início.')
        return cleaned
