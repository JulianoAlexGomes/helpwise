from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from PIL import Image
import os
import uuid
from django.conf import settings

class User(AbstractUser):
    foto = models.ImageField(upload_to='avatares/', null=True, blank=True)

class Departamento(models.Model):
    descricao = models.CharField(max_length=100)

    def __str__(self):
        return self.descricao


class Tipo(models.Model):

    descricao = models.CharField(max_length=100)
    departamento = models.ForeignKey(Departamento, on_delete=models.CASCADE)

    def __str__(self):
        return self.descricao

class TipoAcao(models.Model):

    descricao = models.CharField(max_length=100)

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
    
class Situacao(models.Model):
    descricao = models.CharField(max_length=50, null=True, blank=True)
    
    def __str__(self):
        return self.descricao

class Status(models.Model):
    descricao = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return self.descricao
    
class Plano(models.Model):
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
    certificado_digital = models.FileField(upload_to='certificados/', null=True, blank=True, default=None)
    plano = models.ForeignKey(Plano, on_delete=models.PROTECT, null=True, blank=True, default=1)

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
    responsavel = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='responsavel_por', editable=True)
    criado_em = models.DateTimeField(auto_now_add=True, editable=False)
    iniciado_em = models.DateTimeField(null=True, blank=True, editable=False)
    encerrado_em = models.DateTimeField(null=True, blank=True, editable=False)
    cancelado_em = models.DateTimeField(null=True, blank=True, editable=False)
    status = models.SmallIntegerField(choices=STATUS, default=ABERTO, editable=False)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT)
    tipo = models.ForeignKey(Tipo, on_delete=models.PROTECT, default=3)
    prioridade = models.ForeignKey(Prioridade, on_delete=models.PROTECT, default=2)
    atendente = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='atendido_por', editable=False)
    protocolo = models.CharField(max_length=20, null=True, blank=True)
    titulo = models.CharField(max_length=60, null=True, blank=True)
    situacao = models.ForeignKey(Situacao, on_delete=models.PROTECT, default=1)
    cancelado = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='cancelado_por', editable=True)
    kanban_coluna = models.ForeignKey('KanbanColuna', on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')
    kanban_ordem = models.PositiveIntegerField(default=0)


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

    def cancelar_atendimento(self, user):
        self.cancelado = user
        self.status = self.CANCELADO
        self.cancelado_em = timezone.localtime()
        self.save()

    def get_absolute_url(self):
        from django.shortcuts import reverse
        return reverse("ticket_detail", kwargs={"pk": self.pk})

    def ultimo_comentario(self):
        ultimo_comentario = self.comentario_set.order_by('-criado_em').first()
        return ultimo_comentario.texto if ultimo_comentario else ''
    
    def get_solucao(self):
        solucao = self.solucao_set.order_by('-criado_em').first()
        return solucao.texto if solucao else ''

    def get_solucoes(self):
        return self.solucao_set.all()


class KanbanQuadro(models.Model):
    """Quadro Kanban (board). Compartilhado por todos os usuários.

    O quadro `is_padrao=True` é o fluxo por status de hoje (Aberto/Em
    atendimento/Encerrado): mostra todos os tickets automaticamente via status.
    Quadros personalizados começam vazios — os tickets são adicionados
    explicitamente (ver KanbanCard) e organizados em colunas livres, que podem
    opcionalmente ser mapeadas a um status."""

    nome = models.CharField(max_length=60)
    is_padrao = models.BooleanField(default=False)
    ordem = models.PositiveIntegerField(default=0)
    # Fundo do Modo Kanban (estilo wallpaper do Trello). Guarda um valor CSS de
    # background: cor (#0079bf), gradiente (linear-gradient(...)) ou url('...').
    fundo = models.CharField(max_length=255, blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_padrao', 'ordem', 'id']  # padrão sempre primeiro

    def __str__(self):
        return self.nome


class KanbanColuna(models.Model):
    """Coluna de um quadro Kanban.

    Quando `status_associado` está preenchido, a coluna representa um estágio do
    fluxo de negócio (Aberto/Em atendimento/Encerrado) e mover cards para ela
    dispara a transição correspondente. Quando é None, é uma coluna livre,
    puramente organizacional (estilo Trello)."""

    quadro = models.ForeignKey(KanbanQuadro, on_delete=models.CASCADE, related_name='colunas')
    nome = models.CharField(max_length=40)
    cor = models.CharField(max_length=20, default='#607d8b')  # hex usado no header
    ordem = models.PositiveIntegerField(default=0)
    status_associado = models.SmallIntegerField(choices=Ticket.STATUS, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['ordem', 'id']

    def __str__(self):
        return self.nome


class KanbanCard(models.Model):
    """Card numa coluna de um quadro personalizado.

    Pode ser vinculado a um ticket (`ticket`), a uma nota do mural (`nota`), ou
    ser um card avulso — nota livre com `titulo`/`texto`. Usado apenas em quadros
    NÃO padrão; no quadro padrão a colocação vem do status do ticket.

    Os status de Ticket e de Nota compartilham os mesmos inteiros 0..3, então
    `KanbanColuna.status_associado` serve para ambos."""

    coluna = models.ForeignKey(KanbanColuna, on_delete=models.CASCADE, related_name='cards')
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='kanban_cards', null=True, blank=True)
    nota = models.ForeignKey('mural.Nota', on_delete=models.CASCADE, related_name='kanban_cards', null=True, blank=True)
    titulo = models.CharField(max_length=120, blank=True, default='')   # card avulso
    texto = models.TextField(blank=True, default='')                    # card avulso
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')  # card avulso
    # Quem criou o card avulso. É a "pessoa" do card nos filtros do Kanban, já que
    # ele não tem responsável nem atendente. Nulo nos cards criados antes deste campo.
    autor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    # Etiquetas coloridas do card (estilo Trello). Vivem no card, não no ticket.
    etiquetas = models.ManyToManyField('Etiqueta', blank=True, related_name='cards')
    # Pessoas e prioridade do card avulso (estilo Trello). Só usados em cards avulsos.
    responsavel = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    membros = models.ManyToManyField(User, blank=True, related_name='+')
    prioridade = models.ForeignKey(Prioridade, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    ordem = models.PositiveIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['ordem', '-id']

    def __str__(self):
        if self.ticket_id:
            return f"Ticket #{self.ticket_id} em {self.coluna}"
        if self.nota_id:
            return f"Nota #{self.nota_id} em {self.coluna}"
        return f"Card '{self.titulo}' em {self.coluna}"


class KanbanCardComentario(models.Model):
    """Comentário em um card avulso do Kanban."""
    card = models.ForeignKey(KanbanCard, on_delete=models.CASCADE, related_name='comentarios')
    texto = models.TextField()
    autor = models.ForeignKey(User, on_delete=models.CASCADE)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']

    def __str__(self):
        return f"Comentário de {self.autor} no card #{self.card_id}"


class Etiqueta(models.Model):
    """Etiqueta colorida aplicável a cards do Kanban (estilo Trello).

    Conjunto global e compartilhado; o nome é opcional (etiqueta só-cor, como no
    Trello). Relaciona-se a KanbanCard via M2M (KanbanCard.etiquetas)."""

    nome = models.CharField(max_length=40, blank=True, default='')
    cor = models.CharField(max_length=7, default='#61bd4f')  # hex
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['criado_em', 'id']
        verbose_name = 'Etiqueta'
        verbose_name_plural = 'Etiquetas'

    def __str__(self):
        return self.nome or self.cor


def validate_file_size(value):
    filesize = value.size
    
    # Garantir que estamos lidando com um arquivo carregado na request
    if hasattr(value, 'content_type'):
        content_type = value.content_type
    else:
        content_type = ''

    if content_type.startswith('image'):
        if filesize > 300 * 1024:
            raise ValidationError("A imagem não pode ser maior que 300KB")
    else:
        if filesize > 30 * 1024 * 1024:
            raise ValidationError("O arquivo não pode ser maior que 30MB")

def upload_to(instance, filename):
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"  # Garante nomes únicos
    return os.path.join('comentarios', filename)

def resize_image(self):
    img = Image.open(self.imagem.path)
    if img.size > (300, 300):
        img.thumbnail((300, 300), Image.LANCZOS)
        img.save(self.imagem.path)

class Solucao(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE)
    criado_em = models.DateTimeField(auto_now_add=True)
    texto = models.TextField()
    autor = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return self.texto

class Comentario(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="comentarios") 
    texto = models.TextField()
    proximo_contato = models.DateTimeField(null=True, blank=True)
    tipo = models.ForeignKey(TipoAcao, on_delete=models.PROTECT, null=True, blank=True, default=1)
    criado_em = models.DateTimeField(auto_now_add=True)
    autor = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return f"Comentário de {self.autor} no Ticket #{self.ticket.id}"
    
    def delete(self, *args, **kwargs):
        # Deletar todas as imagens associadas
        for imagem in self.imagens.all():
            imagem.delete()
        # Deletar todos os arquivos associados
        for arquivo in self.arquivos.all():
            arquivo.delete()
        super().delete(*args, **kwargs)

class ComentarioArquivo(models.Model):
    comentario = models.ForeignKey(Comentario, on_delete=models.CASCADE, related_name='arquivos')
    arquivo = models.FileField(upload_to='comentarios_arquivos/')
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Arquivo ({self.arquivo.name})"

class ComentarioImagem(models.Model):
    comentario = models.ForeignKey(Comentario, on_delete=models.CASCADE, related_name='imagens')
    imagem = models.ImageField(upload_to='comentarios_imagens/')
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Imagem ({self.imagem.name})"
    
class CertificadoCliente(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='certificados')
    arquivo = models.FileField(upload_to='clientes_certificados/')
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Arquivo ({self.arquivo.name})"