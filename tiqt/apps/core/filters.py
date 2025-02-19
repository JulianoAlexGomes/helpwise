from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from .models import Cliente, Tipo, Prioridade

class TicketFilterForm(forms.Form):
    cliente = forms.ModelChoiceField(queryset=Cliente.objects.all(), required=False, label='Cliente')
    tipo = forms.ModelChoiceField(queryset=Tipo.objects.all(), required=False, label='Tipo')
    prioridade = forms.ModelChoiceField(queryset=Prioridade.objects.all(), required=False, label='Prioridade')

    def __init__(self, *args, **kwargs):
        super(TicketFilterForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'get'
        self.helper.add_input(Submit('submit', 'Filtrar'))