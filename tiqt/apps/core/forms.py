from django import forms
from django_select2.forms import ModelSelect2Widget
from .models import Ticket, Cliente

class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
                    
                    'fantasia',
                    'cnpj',
                    'cidade',
                    'uf',
                    'tributacao',
                ]
        widgets = {
            'fantasia': forms.TextInput(attrs={'id': 'id_fantasia'}),
            'cnpj': forms.TextInput(attrs={'id': 'id_cnpj'}),
            'cidade': forms.TextInput(attrs={'id': 'id_cidade'}),
            'uf': forms.TextInput(attrs={'id': 'id_uf'}),
            'tributacao': forms.TextInput(attrs={'id': 'id_tributacao'}),
        }

class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['tipo', 'departamento', 'cliente', 'prioridade']
        widgets = {'cliente': ModelSelect2Widget(model=Cliente, search_fields=['fantasia__icontains', 'razao_social__icontains']),}