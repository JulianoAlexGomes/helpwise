from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from .forms import AssistenteForm
from .models import ConsultaIA
from .services import IAError, analisar_erro


class AssistenteView(LoginRequiredMixin, View):
    template_name = "ia/assistente.html"

    def get(self, request):
        return render(request, self.template_name, {"form": AssistenteForm()})

    def post(self, request):
        form = AssistenteForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        consulta = form.save(commit=False)
        consulta.usuario = request.user

        imagem = form.cleaned_data.get("imagem")
        departamento = form.cleaned_data.get("departamento")

        # Imagem é opcional: lê os bytes só se houver
        imagem_bytes = None
        mime_type = None
        if imagem:
            imagem.seek(0)
            imagem_bytes = imagem.read()
            mime_type = getattr(imagem, "content_type", "") or "image/png"

        try:
            resultado = analisar_erro(
                imagem_bytes=imagem_bytes,
                mime_type=mime_type,
                descricao=consulta.descricao,
                departamento=departamento,
            )
        except IAError as exc:
            messages.error(request, str(exc))
            return render(request, self.template_name, {"form": form})

        from django.conf import settings

        consulta.resposta_ia = resultado["raw"]
        consulta.modelo = settings.IA_MODELO
        consulta.save()

        return render(
            request,
            self.template_name,
            {
                "form": AssistenteForm(),
                "consulta": consulta,
                "solucao_empresa": resultado["empresa"],
                "solucao_externa": resultado["externa"],
            },
        )


class FeedbackView(LoginRequiredMixin, View):
    def post(self, request, pk):
        consulta = get_object_or_404(ConsultaIA, pk=pk)
        valor = request.POST.get("resolveu")
        if valor in ("sim", "nao"):
            consulta.resolveu = valor == "sim"
            consulta.save(update_fields=["resolveu"])
            messages.success(request, "Obrigado pelo retorno!")
        return redirect(reverse("ia_assistente"))
