from django import forms
# from django_select2.forms import ModelSelect2Widget
from .models import Ticket, Cliente, Uf, Cidade, Tributacao, Comentario

class ClienteForm(forms.ModelForm):
    uf = forms.ModelChoiceField(queryset=Uf.objects.all(), required=False, label='UF')
    cidade = forms.ModelChoiceField(queryset=Cidade.objects.all(), required=False, label='Cidade')
    tributacao = forms.ModelChoiceField(queryset=Tributacao.objects.all(), required=False, label='Tributação')
    
    class Meta:
        model = Cliente
        fields = [                    
                    'fantasia',
                    'cnpj',
                    'cidade',
                    'uf',
                    'tributacao',
                    'uid',
                ]
        widgets = {
            'fantasia': forms.TextInput(attrs={'id': 'id_fantasia'}),
            'cnpj': forms.TextInput(attrs={'id': 'id_cnpj'}),
            'cidade': forms.TextInput(attrs={'id': 'id_cidade'}),
            'uf': forms.TextInput(attrs={'id': 'id_uf'}),
            'tributacao': forms.TextInput(attrs={'id': 'id_tributacao'}),
            'uid': forms.TextInput(attrs={'id': 'id_uid'}),
        }
        
class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['tipo', 'departamento', 'cliente', 'prioridade']
        widgets = {
            'tipo': forms.Select(attrs={'id': 'id_tipo', 'class': 'form-control'}),
            'departamento': forms.Select(attrs={'id': 'id_departamento', 'class': 'form-control'}),
            'cliente': forms.Select(attrs={'id': 'id_cliente', 'class': 'form-control'}),
            'prioridade': forms.Select(attrs={'id': 'id_prioridade', 'class': 'form-control'}),
        }


class TicketCloseForm(forms.Form):
    solucao = forms.CharField(widget=forms.Textarea, label='Solução')

class ComentarioForm(forms.ModelForm):
    class Meta:
        model = Comentario
        fields = ['texto']