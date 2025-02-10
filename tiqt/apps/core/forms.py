from django import forms
from django_select2.forms import ModelSelect2Widget
from .models import Ticket, Cliente


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
                    'razao_social',
                    'fantasia',
                    'cnpj',
                    'telefone',
                    'email',
                    'endereco',
                    'numero',
                    'bairro',
                    'cep',
                    'complemento',
                    'cidade',
                    'uf',
                    'tributacao',
                    'responsavel',
                    'observacao',
                    'ativo',
                    'inativo',
                ]


    
class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['departamento', 'cliente']
        widgets = {
            'cliente': ModelSelect2Widget(model=Cliente, search_fields=['fantasia__icontains', 'razao_social__icontains']),
        }