from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from .models import Cliente, Tipo, Prioridade, Departamento, Situacao, User

class TicketFilterForm(forms.Form):
    cliente = forms.ModelChoiceField(queryset=Cliente.objects.all(), required=False, label='Cliente')
    tipo = forms.ModelChoiceField(queryset=Tipo.objects.all(), required=False, label='Tipo')
    prioridade = forms.ModelChoiceField(queryset=Prioridade.objects.all(), required=False, label='Prioridade')
    departamento = forms.ModelChoiceField(queryset=Departamento.objects.all(), required=False, label='Departamento')
    situacao = forms.ModelChoiceField(queryset=Situacao.objects.all(), required=False, label='Situação')

    def __init__(self, *args, **kwargs):
        super(TicketFilterForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'get'
        self.helper.add_input(Submit('submit', 'Filtrar'))

class TicketFilterForm(forms.Form):
    cliente = forms.ModelChoiceField(queryset=Cliente.objects.all(), required=False, label='Cliente')
    tipo = forms.ModelChoiceField(queryset=Tipo.objects.all(), required=False, label='Tipo')
    prioridade = forms.ModelChoiceField(queryset=Prioridade.objects.all(), required=False, label='Prioridade')
    departamento = forms.ModelChoiceField(queryset=Departamento.objects.all(), required=False, label='Departamento')
    situacao = forms.ModelChoiceField(queryset=Situacao.objects.all(), required=False, label='Situação')
    responsavel = forms.ModelChoiceField(queryset=User.objects.all(), required=False, label='Responsável')
    atendente = forms.ModelChoiceField(queryset=User.objects.all(), required=False, label='Atendente')
    criado_em_inicio = forms.DateField(required=False, label='Criado em (início)', widget=forms.DateInput(attrs={'type': 'date'}))
    criado_em_fim = forms.DateField(required=False, label='Criado em (fim)', widget=forms.DateInput(attrs={'type': 'date'}))
    encerrado_em_inicio = forms.DateField(required=False, label='Encerrado em (início)', widget=forms.DateInput(attrs={'type': 'date'}))
    encerrado_em_fim = forms.DateField(required=False, label='Encerrado em (fim)', widget=forms.DateInput(attrs={'type': 'date'}))
    cancelado_em_inicio = forms.DateField(required=False, label='Cancelado em (início)', widget=forms.DateInput(attrs={'type': 'date'}))
    cancelado_em_fim = forms.DateField(required=False, label='Cancelado em (fim)', widget=forms.DateInput(attrs={'type': 'date'}))
    solucao_criado_em_inicio = forms.DateField(required=False, label='Solução Criado em (início)', widget=forms.DateInput(attrs={'type': 'date'}))
    solucao_criado_em_fim = forms.DateField(required=False, label='Solução Criado em (fim)', widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        super(TicketFilterForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'get'
        self.helper.add_input(Submit('submit', 'Filtrar'))