from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


class User(AbstractUser):
    pass

class Departamento(models.Model):
    descricao = models.CharField(max_length=100)

    def __str__(self):
        return self.descricao


class Tipo(models.Model):

    descricao = models.CharField(max_length=100)
    departamento = models.ForeignKey(Departamento, on_delete=models.CASCADE)

    def __str__(self):
        return self.descricao


class Prioridade(models.Model):
    id = models.AutoField(primary_key=True)
    descricao = models.CharField(max_length=20, null=True, blank=True)
    observacoes = models.TextField(max_length= 100, null=True, blank=True, default=1)

    def __str__(self):
        return self.descricao


class Uf(models.Model):
    descricao = models.CharField(max_length=50, null=True, blank=True)
    sigla = models.CharField(max_length=2, null=True, blank=True)

    def __str__(self):
        return self.sigla


class Cidade(models.Model):
    codigo = models.CharField(max_length=7, null=True, blank=True)
    descricao = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return self.descricao


class Tributacao(models.Model):
    descricao = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return self.descricao
    

class Cliente(models.Model):
    razao_social = models.CharField(max_length=120, null=True, blank=True)
    fantasia = models.CharField(max_length=120, null=True, blank=True)
    cnpj = models.CharField(max_length=14, null=True, blank=True)
    telefone = models.CharField(max_length=11, null=True, blank=True)
    email = models.EmailField(max_length=120, null=True, blank=True)
    endereco = models.CharField(max_length=120, null=True, blank=True)
    numero = models.CharField(max_length=10, null=True, blank=True)
    bairro = models.CharField(max_length=120, null=True, blank=True)
    cep = models.CharField(max_length=8, null=True, blank=True)
    complemento = models.CharField(max_length=120, null=True, blank=True)
    cidade = models.ForeignKey(Cidade, on_delete=models.PROTECT, null=True, blank=True)
    uf = models.ForeignKey(Uf, on_delete=models.PROTECT, null=True, blank=True)
    tributacao = models.ForeignKey(Tributacao, on_delete=models.PROTECT, null=True, blank=True)
    responsavel = models.CharField(max_length=120, null=True, blank=True)
    observacao = models.TextField(null=True, blank=True)
    data_cadastro = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    data_alteracao = models.DateTimeField(auto_now=True, null=True, blank=True)
    ativo = models.BooleanField(default=True, null=True, blank=True)
    motivo_inativacao = models.TextField(null=True, blank=True)
    data_inativacao = models.DateTimeField(null=True, blank=True)
    uid = models.CharField(max_length=120, null=True, blank=True)

    def __str__(self):
        return f"{self.fantasia or ''} - {self.cidade or ''}/{self.uf or ''}"
    


class Ticket(models.Model):
    ABERTO = 0
    EM_ATENDIMENTO = 1
    ENCERRADO = 2
    CANCELADO = 3

    STATUS = (
        (ABERTO, 'Aberto'),
        (EM_ATENDIMENTO, 'Em atendimento'),
        (ENCERRADO, 'Encerrado'),
        (CANCELADO, 'Cancelado')
    )

    departamento = models.ForeignKey(Departamento, on_delete=models.PROTECT, default=1)
    responsavel = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='responsavel_por', editable=False)
    criado_em = models.DateTimeField(auto_now_add=True, editable=False)
    iniciado_em = models.DateTimeField(null=True, blank=True, editable=False)
    encerrado_em = models.DateTimeField(null=True, blank=True, editable=False)
    status = models.SmallIntegerField(choices=STATUS, default=ABERTO, editable=False)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT)
    tipo = models.ForeignKey(Tipo, on_delete=models.PROTECT, default=3)
    prioridade = models.ForeignKey(Prioridade, on_delete=models.PROTECT, default=2)
    # atendente = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='atendido_por', editable=False)
    
    class Meta:
        ordering = ["criado_em"]

    def iniciar_atendimento(self, user):
        self.responsavel = user
        self.status = self.EM_ATENDIMENTO
        self.iniciado_em = timezone.localtime()
        self.save()

    def encerrar_atendimento(self):
        self.status = self.ENCERRADO
        self.encerrado_em = timezone.localtime()
        self.save()

    def get_absolute_url(self):
        from django.shortcuts import reverse
        return reverse("ticket_detail", kwargs={"pk": self.pk})

    def ultimo_comentario(self):
            ultimo_comentario = self.comentario_set.order_by('-id').first()
            return ultimo_comentario.texto if ultimo_comentario else ''
    
    def get_solucao(self):
        solucao = self.solucao_set.order_by('-criado_em').first()
        return solucao.texto if solucao else ''


class Comentario(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE)
    criado_em = models.DateTimeField(auto_now_add=True)
    texto = models.TextField()
    autor = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return self.texto

class Solucao(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE)
    criado_em = models.DateTimeField(auto_now_add=True)
    texto = models.TextField()
    autor = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return self.texto
    