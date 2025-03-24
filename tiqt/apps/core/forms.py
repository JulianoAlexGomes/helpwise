from django import forms
# from django_select2.forms import ModelSelect2Widget
from .models import Ticket, Cliente, Uf, Cidade, Tributacao, Comentario, TipoAcao

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
                    'plano',
                ]
        widgets = {
            'fantasia': forms.TextInput(attrs={'id': 'id_fantasia'}),
            'cnpj': forms.TextInput(attrs={'id': 'id_cnpj'}),
            'cidade': forms.TextInput(attrs={'id': 'id_cidade'}),
            'uf': forms.TextInput(attrs={'id': 'id_uf'}),
            'tributacao': forms.TextInput(attrs={'id': 'id_tributacao'}),
            'uid': forms.TextInput(attrs={'id': 'id_uid'}),
            'plano': forms.Select(attrs={'id': 'id_plano'}),
        }
        
class TicketForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        show_responsavel = kwargs.pop('show_responsavel', False)
        super(TicketForm, self).__init__(*args, **kwargs)
        if show_responsavel:
            self.fields.pop('responsavel')

    class Meta:
        model = Ticket
        fields = ['titulo', 'tipo', 'departamento', 'cliente', 'protocolo', 'situacao', 'prioridade', 'responsavel']
        widgets = {
            'titulo': forms.TextInput(attrs={'id': 'id_titulo', 'class': 'form-control'}),
            'tipo': forms.Select(attrs={'id': 'id_tipo', 'class': 'form-control'}),
            'departamento': forms.Select(attrs={'id': 'id_departamento', 'class': 'form-control'}),
            'cliente': forms.Select(attrs={'id': 'id_cliente', 'class': 'form-control'}),
            'protocolo': forms.TextInput(attrs={'id': 'id_protocolo', 'class': 'form-control'}),
            'situacao': forms.Select(attrs={'id': 'id_situacao', 'class': 'form-control'}),
            'prioridade': forms.Select(attrs={'id': 'id_prioridade', 'class': 'form-control'}),
            'responsavel': forms.Select(attrs={'id': 'id_responsavel', 'class': 'form-control'}),
        }

class TicketCloseForm(forms.Form):
    solucao = forms.CharField(widget=forms.Textarea, label='Solução')

class ComentarioForm(forms.ModelForm):
    class Meta:
        model = Comentario
        fields = ['texto', 'proximo_contato', 'tipo']
        widgets = {
            'texto': forms.Textarea(attrs={'id': 'id_texto', 'class': 'form-control'}),
            'tipo': forms.Select(attrs={'id': 'id_tipo', 'class': 'form-control'}),
            'proximo_contato': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }
