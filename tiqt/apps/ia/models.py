from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError

from tiqt.apps.core.models import Departamento


def validar_tamanho_imagem(value):
    """Limita o print do erro a 5 MB (screenshots costumam passar de 300 KB)."""
    limite_mb = 5
    if value.size > limite_mb * 1024 * 1024:
        raise ValidationError(f"A imagem não pode ser maior que {limite_mb} MB.")


class BaseConhecimento(models.Model):
    """Base de conhecimento dedicada que a IA usa para sugerir soluções."""

    titulo = models.CharField(max_length=150)
    descricao_problema = models.TextField(
        help_text="Como o erro aparece / sintomas observados."
    )
    solucao = models.TextField(help_text="Passo a passo da solução.")
    palavras_chave = models.CharField(
        max_length=255,
        blank=True,
        help_text="Termos separados por vírgula para ajudar a busca (ex: sefaz, certificado, conexão).",
    )
    departamento = models.ForeignKey(
        Departamento,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conhecimentos",
    )
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Base de conhecimento"
        verbose_name_plural = "Base de conhecimento"
        ordering = ["titulo"]

    def __str__(self):
        return self.titulo


class ConsultaIA(models.Model):
    """Histórico de cada consulta feita ao assistente (auditoria + métrica de acerto)."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consultas_ia",
    )
    imagem = models.ImageField(
        upload_to="ia_consultas/",
        validators=[validar_tamanho_imagem],
        blank=True,
        null=True,
    )
    descricao = models.TextField(
        blank=True,
        help_text="Descrição do funcionário sobre o que aconteceu.",
    )
    resposta_ia = models.TextField(blank=True)
    resolveu = models.BooleanField(null=True, blank=True)
    modelo = models.CharField(max_length=80, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Consulta à IA"
        verbose_name_plural = "Consultas à IA"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Consulta #{self.pk} de {self.usuario}"
