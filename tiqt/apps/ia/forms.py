from django import forms

from tiqt.apps.core.models import Departamento
from .models import ConsultaIA


class AssistenteForm(forms.ModelForm):
    departamento = forms.ModelChoiceField(
        queryset=Departamento.objects.all(),
        required=False,
        empty_label="— Geral / não sei —",
        label="Departamento",
        widget=forms.Select(attrs={"class": "browser-default ia-select"}),
    )

    class Meta:
        model = ConsultaIA
        fields = ["imagem", "descricao"]
        widgets = {
            "imagem": forms.FileInput(
                attrs={"accept": "image/*", "id": "id_imagem"}
            ),
            "descricao": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": "ia-textarea",
                    "placeholder": "Ex.: Erro ao emitir nota fiscal depois de atualizar o sistema.",
                }
            ),
        }
        labels = {
            "imagem": "Print do erro",
            "descricao": "O que aconteceu",
        }

    def clean(self):
        cleaned = super().clean()
        imagem = cleaned.get("imagem")
        descricao = (cleaned.get("descricao") or "").strip()
        if not imagem and not descricao:
            raise forms.ValidationError(
                "Envie o print do erro ou descreva o problema para analisar."
            )
        return cleaned
