from django import forms
from django_select2.forms import ModelSelect2Widget
from .models import Ticket, Cliente

class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['departamento', 'cliente']
        widgets = {
            'cliente': ModelSelect2Widget(model=Cliente, search_fields=['fantasia__icontains', 'razao_social__icontains']),
        }

class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['fantasia', 'razao_social', 'cnpj', 'endereco', 'telefone', 'email']