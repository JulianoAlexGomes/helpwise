from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from .models import Cliente, Tipo, Prioridade, Departamento, Situacao, User

def apply_filters(queryset, form):

    if not form.is_valid():
        return queryset

    if form.cleaned_data.get('cliente'):
        queryset = queryset.filter(
            cliente__fantasia__icontains=form.cleaned_data['cliente']
        )

    if form.cleaned_data.get('responsavel'):
        queryset = queryset.filter(responsavel=form.cleaned_data['responsavel'])

    if form.cleaned_data.get('atendente'):
        queryset = queryset.filter(atendente=form.cleaned_data['atendente'])

    if form.cleaned_data.get('tipo'):
        queryset = queryset.filter(tipo=form.cleaned_data['tipo'])

    if form.cleaned_data.get('departamento'):
        queryset = queryset.filter(departamento=form.cleaned_data['departamento'])

    if form.cleaned_data.get('prioridade'):
        queryset = queryset.filter(prioridade=form.cleaned_data['prioridade'])

    if form.cleaned_data.get('situacao'):
        queryset = queryset.filter(situacao=form.cleaned_data['situacao'])

    return queryset
