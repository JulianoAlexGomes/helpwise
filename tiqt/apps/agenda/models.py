from django.conf import settings
from django.db import models
from django.utils import timezone

from tiqt.apps.core.models import Cliente, Comentario, Ticket


class Agendamento(models.Model):
    """Um compromisso na agenda.

    Pode ser *avulso* (criado direto na agenda) ou ter *origem em ticket*
    (gerado automaticamente a partir do `proximo_contato` de um comentário).
    """

    PENDENTE = 0
    CONCLUIDO = 1
    CANCELADO = 2
    STATUS = (
        (PENDENTE, 'Pendente'),
        (CONCLUIDO, 'Concluído'),
        (CANCELADO, 'Cancelado'),
    )

    AVULSO = 'avulso'
    TICKET = 'ticket'
    ORIGEM = (
        (AVULSO, 'Avulso'),
        (TICKET, 'Ticket'),
    )

    titulo = models.CharField(max_length=120)
    descricao = models.TextField(null=True, blank=True)
    inicio = models.DateTimeField()
    fim = models.DateTimeField(null=True, blank=True)
    dia_inteiro = models.BooleanField(default=False)

    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agendamentos',
    )

    origem = models.CharField(max_length=10, choices=ORIGEM, default=AVULSO)
    status = models.SmallIntegerField(choices=STATUS, default=PENDENTE)

    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, null=True, blank=True,
        related_name='agendamentos',
    )
    cliente = models.ForeignKey(
        Cliente, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='agendamentos',
    )
    # Comentário que originou este agendamento (quando vem de um ticket).
    # OneToOne garante 1 agendamento por "próximo contato".
    comentario = models.OneToOneField(
        Comentario, on_delete=models.CASCADE, null=True, blank=True,
        related_name='agendamento',
    )

    # Controle da notificação "no dia" (evita notificar mais de uma vez).
    notificado = models.BooleanField(default=False)

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='agendamentos_criados',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['inicio']
        indexes = [
            models.Index(fields=['inicio']),
            models.Index(fields=['responsavel', 'status']),
        ]

    def __str__(self):
        return f"{self.titulo} ({self.inicio:%d/%m/%Y %H:%M})"

    @property
    def cor(self):
        """Cor usada no calendário conforme status/origem."""
        if self.status == self.CONCLUIDO:
            return '#9aa0a6'
        if self.status == self.CANCELADO:
            return '#bdbdbd'
        if self.origem == self.TICKET:
            return '#00897b'
        return '#5c6bc0'

    @property
    def atrasado(self):
        return self.status == self.PENDENTE and self.inicio < timezone.now()

    def get_url_destino(self):
        """Para onde a notificação/click deve levar."""
        if self.ticket_id:
            return f"/ticket/{self.ticket_id}/"
        return "/agenda/"

    def pode_gerenciar(self, user):
        """Só o criador pode cancelar/excluir o agendamento.
        Registros antigos sem criador (`criado_por` nulo) ficam liberados."""
        if not user or not user.is_authenticated:
            return False
        return self.criado_por_id is None or self.criado_por_id == user.id

    def concluir(self):
        self.status = self.CONCLUIDO
        self.save(update_fields=['status', 'atualizado_em'])

    def cancelar(self):
        self.status = self.CANCELADO
        self.save(update_fields=['status', 'atualizado_em'])
