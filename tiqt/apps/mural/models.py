from django.conf import settings
from django.db import models
from django.utils import timezone


class CategoriaNota(models.Model):
    """Categoria personalizável das notas (ex.: Boletos, Treinamentos, RH)."""

    nome = models.CharField(max_length=60)
    cor = models.CharField(max_length=7, default='#00796b')
    # Nome de um material icon (opcional), ex.: 'receipt', 'school'.
    icone = models.CharField(max_length=40, null=True, blank=True)
    ordem = models.PositiveIntegerField(default=0)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['ordem', 'nome']
        verbose_name = 'Categoria de nota'
        verbose_name_plural = 'Categorias de notas'

    def __str__(self):
        return self.nome


class Nota(models.Model):
    """Uma nota no mural compartilhado da empresa."""

    A_FAZER = 0
    EM_ANDAMENTO = 1
    CONCLUIDA = 2
    ARQUIVADA = 3
    STATUS = (
        (A_FAZER, 'A fazer'),
        (EM_ANDAMENTO, 'Em andamento'),
        (CONCLUIDA, 'Concluída'),
        (ARQUIVADA, 'Arquivada'),
    )
    # Cor usada no rótulo de status.
    COR_STATUS = {
        A_FAZER: '#5c6bc0',
        EM_ANDAMENTO: '#f5a623',
        CONCLUIDA: '#43a047',
        ARQUIVADA: '#9aa0a6',
    }

    NORMAL = 0
    URGENTE = 1
    PRIORIDADE = (
        (NORMAL, 'Normal'),
        (URGENTE, 'Urgente'),
    )

    titulo = models.CharField(max_length=120)
    conteudo = models.TextField(null=True, blank=True)
    categoria = models.ForeignKey(
        CategoriaNota, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notas',
    )
    status = models.SmallIntegerField(choices=STATUS, default=A_FAZER)
    prioridade = models.SmallIntegerField(choices=PRIORIDADE, default=NORMAL)

    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notas',
    )
    fixado = models.BooleanField(default=False)
    vencimento = models.DateTimeField(null=True, blank=True)

    # Posição livre no quadro (px). Nulo = ainda não posicionada (entra na
    # grade automática). `z` controla o empilhamento ao arrastar (maior = frente).
    pos_x = models.IntegerField(null=True, blank=True)
    pos_y = models.IntegerField(null=True, blank=True)
    z = models.PositiveIntegerField(default=0)

    # Evento gerado na agenda a partir desta nota (quando agendada).
    agendamento = models.OneToOneField(
        'agenda.Agendamento', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='nota',
    )

    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notas_criadas',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fixado', '-criado_em']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['categoria']),
        ]

    def __str__(self):
        return self.titulo

    @property
    def cor_status(self):
        return self.COR_STATUS.get(self.status, '#5c6bc0')

    @property
    def arquivada(self):
        return self.status == self.ARQUIVADA

    @property
    def concluida(self):
        return self.status == self.CONCLUIDA

    @property
    def atrasado(self):
        return (
            self.status in (self.A_FAZER, self.EM_ANDAMENTO)
            and self.vencimento is not None
            and self.vencimento < timezone.now()
        )


class NotaArquivo(models.Model):
    """Anexo (PDF/arquivo) de uma nota."""

    nota = models.ForeignKey(Nota, on_delete=models.CASCADE, related_name='arquivos')
    arquivo = models.FileField(upload_to='mural_arquivos/')
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Arquivo ({self.arquivo.name})"

    def delete(self, *args, **kwargs):
        # Remove o arquivo físico ao excluir o registro.
        self.arquivo.delete(save=False)
        super().delete(*args, **kwargs)
