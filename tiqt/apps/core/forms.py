from django import forms
from django_select2.forms import ModelSelect2Widget
from .models import Ticket, Cliente

# Atualize a classe ClienteForm crie um id para os campos de modo a facilitar a identificação dos campos no template
class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
                    
                    'fantasia',
                    'cnpj',
                    'cidade',
                    'uf',
                ]
        widgets = {
            'razao_social': forms.TextInput(attrs={'id': 'id_razao_social'}),
            'fantasia': forms.TextInput(attrs={'id': 'id_fantasia'}),
            'cnpj': forms.TextInput(attrs={'id': 'id_cnpj'}),
            'telefone': forms.TextInput(attrs={'id': 'id_telefone'}),
            'email': forms.EmailInput(attrs={'id': 'id_email'}),
            'endereco': forms.TextInput(attrs={'id': 'id_endereco'}),
            'numero': forms.TextInput(attrs={'id': 'id_numero'}),
            'bairro': forms.TextInput(attrs={'id': 'id_bairro'}),
            'cep': forms.TextInput(attrs={'id': 'id_cep'}),
            'complemento': forms.TextInput(attrs={'id': 'id_complemento'}),
            'cidade': forms.TextInput(attrs={'id': 'id_cidade'}),
            'uf': forms.TextInput(attrs={'id': 'id_uf'}),
            'tributacao': forms.TextInput(attrs={'id': 'id_tributacao'}),
            'responsavel': forms.TextInput(attrs={'id': 'id_responsavel'}),
            'observacao': forms.Textarea(attrs={'id': 'id_observacao'}),
            'ativo': forms.CheckboxInput(attrs={'id': 'id_ativo'}),
            'inativo': forms.CheckboxInput(attrs={'id': 'id_inativo'}),
        }


    
class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['departamento', 'cliente']
        widgets = {
            'cliente': ModelSelect2Widget(model=Cliente, search_fields=['fantasia__icontains', 'razao_social__icontains']),
        }