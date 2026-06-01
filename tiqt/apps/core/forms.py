from django import forms
from django_select2.forms import ModelSelect2Widget
from .models import Ticket, Cliente, Uf, Cidade, Tributacao, Comentario, TipoAcao, Departamento, Prioridade, Situacao, Tipo
from django.contrib.auth import get_user_model

User = get_user_model()

class ClienteForm(forms.ModelForm):

    cep = forms.CharField(
        max_length=9,
        required=False,
        label='Cep',
        widget=forms.TextInput(attrs={'maxlength': '9'})
    )

    cnpj = forms.CharField(
        max_length=18,
        required=False,
        label='Cnpj',
        widget=forms.TextInput(attrs={'maxlength': '18'})
    )

    def clean_cnpj(self):
        value = self.cleaned_data.get('cnpj', '')
        return ''.join(filter(str.isdigit, value))

    def clean_cep(self):
        value = self.cleaned_data.get('cep', '')
        return value.replace('-', '')

    def save(self, commit=True):
        return super().save(commit=commit)

    class Meta:
        model = Cliente
        fields = [
            'cnpj',
            'razao_social',
            'fantasia',
            'telefone',
            'email',
            'cep',
            'endereco',
            'bairro',
            'cidade',
            'uf',
            'numero',
            'complemento',
            'tributacao',
            'responsavel',
            'observacao',
            'uid',
            'plano',
        ]

        widgets = {
            'fantasia': forms.TextInput(),
            'cnpj': forms.TextInput(),
            'telefone': forms.TextInput(),
            'email': forms.EmailInput(),
            'endereco': forms.TextInput(),
            'numero': forms.TextInput(),
            'bairro': forms.TextInput(),
            'cep': forms.TextInput(),
            'complemento': forms.TextInput(),
            'responsavel': forms.TextInput(),
            'observacao': forms.Textarea(),

            'cidade': forms.Select(),

            'uf': forms.Select(),

            'tributacao': forms.Select(),

            'plano': forms.Select(),
        }

class TicketCloseForm(forms.Form):
    solucao = forms.CharField(
        label='Solução',
        widget=forms.Textarea()
    )

class TicketForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        show_responsavel = kwargs.pop('show_responsavel', False)
        super().__init__(*args, **kwargs)

        if not show_responsavel:
            self.fields.pop('responsavel', None)

    class Meta:
        model = Ticket
        fields = [
            'titulo',
            'tipo',
            'departamento', 
            'cliente',
            'protocolo',
            'situacao',
            'prioridade',
            'responsavel',
        ]

        widgets = {
            'titulo': forms.TextInput(),
            'tipo': forms.Select(),
            'departamento': forms.Select(),
            'cliente': ModelSelect2Widget(
                model=Cliente,
                search_fields=[
                    'fantasia__icontains',
                    'cnpj__icontains'
                ]
            ),
            'protocolo': forms.TextInput(),
            'situacao': forms.Select(),
            'prioridade': forms.Select(),
            'responsavel': forms.Select(),
        }

class ComentarioForm(forms.ModelForm):
    class Meta:
        model = Comentario
        fields = ['texto', 'proximo_contato', 'tipo']
        widgets = {
            'texto': forms.Textarea(attrs={'id': 'id_texto', 'class': 'form-control'}),
            'tipo': forms.Select(attrs={'id': 'id_tipo', 'class': 'form-control'}),
            'proximo_contato': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

class TicketFilterForm(forms.Form):
    q = forms.CharField(required=False)

    cliente = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Digite o cliente',
            'id': 'cliente-autocomplete'
        })
    )

    departamento = forms.ModelChoiceField(
        queryset=Departamento.objects.all(),
        required=False,
        empty_label="Todos"
    )

    tipo = forms.ModelChoiceField(
        queryset=Tipo.objects.all(),
        required=False,
        empty_label="Todos"
    )

    prioridade = forms.ModelChoiceField(
        queryset=Prioridade.objects.all(),
        required=False,
        empty_label="Todos"
    )

    situacao = forms.ModelChoiceField(
        queryset=Situacao.objects.all(),
        required=False,
        empty_label="Todos"
    )

    status = forms.ChoiceField(
        choices=[('', 'Todos')] + list(Ticket.STATUS),
        required=False,
    )

    responsavel = forms.ModelChoiceField(
        queryset=User.objects.all(),
        required=False,
        empty_label="Todos"
    )

    atendente = forms.ModelChoiceField(
        queryset=User.objects.all(),
        required=False,
        empty_label="Todos"
    )

from django import forms
from .models import Ticket, Cliente


class NewTicketForm(forms.ModelForm):

    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.all().order_by('fantasia'),
        required=True,
        label='Cliente'
    )

    class Meta:
        model = Ticket
        fields = [
            'titulo',
            'cliente',
            'departamento',
            'protocolo',
            'tipo',
            'prioridade',
            'situacao',
            'responsavel',
        ]
