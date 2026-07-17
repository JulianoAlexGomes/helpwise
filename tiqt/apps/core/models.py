from django.db import models, transaction
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
    # Só ordena a fila do painel de TV. Quem define a meta de SLA é SlaPolitica —
    # derivar minutos do peso por fórmula quebra assim que um departamento tiver
    # meta diferente para a mesma prioridade.
    peso = models.PositiveSmallIntegerField(
        default=0, help_text='Maior = mais urgente. Ordena a fila do painel de TV.')

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

    def save(self, *args, **kwargs):
        if not (self.fantasia or '').strip():
            self.fantasia = self.razao_social
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.fantasia or ''} - {self.cidade or ''}/{self.uf or ''}"



class TicketGrupo(models.Model):
    """Tickets do MESMO cliente agrupados para tratar e encerrar juntos.

    A mesma solução vale para todo o grupo: encerrar qualquer membro encerra os
    demais com o mesmo texto. Espelha a ideia do KanbanGrupo (cards que andam
    juntos), mas aqui o vínculo vive no próprio Ticket (`Ticket.grupo`).

    Invariante garantida nas views (não no banco): todos os tickets do grupo têm
    o mesmo `cliente`. Grupo que fica com menos de 2 tickets é desfeito."""

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='ticket_grupos')
    nome = models.CharField(max_length=80, blank=True, default='')
    criado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nome or f"Grupo #{self.pk}"

    def dissolver_se_pequeno(self):
        """Desfaz o grupo quando sobra menos de 2 tickets — um ticket sozinho não
        é grupo. Ao deletar, o on_delete=SET_NULL de Ticket.grupo solta o que
        restou. Retorna True se dissolveu."""
        if self.tickets.count() < 2:
            self.delete()
            return True
        return False


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
    # Agrupamento de tickets do MESMO cliente, tratados/encerrados juntos (a mesma
    # solução vale para todo o grupo). Nulo = ticket solto. Ver TicketGrupo.
    grupo = models.ForeignKey('TicketGrupo', on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')


    class Meta:
        ordering = ["criado_em"]

    def save(self, *args, **kwargs):
        """Grava o evento CRIADO no nascimento do ticket.

        É aqui e não numa view porque ticket é criado em vários pontos (form,
        kanban, API) e o evento não pode depender de ninguém lembrar de chamá-lo.
        Autor fica nulo: o Ticket não guarda quem o criou."""
        from .services import eventos
        novo = self._state.adding
        super().save(*args, **kwargs)
        if novo:
            eventos.registrar(self, TicketEvento.CRIADO, ocorrido_em=self.criado_em)

    def iniciar_atendimento(self, user, origem=''):
        from .services import eventos
        with transaction.atomic():
            status_de = self.status
            self.responsavel = user
            self.status = self.EM_ATENDIMENTO
            self.iniciado_em = timezone.localtime()
            self.save()
            # ocorrido_em = o mesmo instante que ficou no ticket, não uma segunda
            # leitura do relógio: evento e timestamp não podem divergir.
            eventos.registrar(self, TicketEvento.INICIADO, usuario=user,
                              status_de=status_de, origem=origem,
                              ocorrido_em=self.iniciado_em)

    def encerrar_atendimento(self, user=None, origem=''):
        from .services import eventos
        with transaction.atomic():
            status_de = self.status
            self.status = self.ENCERRADO
            self.encerrado_em = timezone.localtime()
            self.save()
            eventos.registrar(self, TicketEvento.ENCERRADO, usuario=user,
                              status_de=status_de, origem=origem,
                              ocorrido_em=self.encerrado_em)

    def cancelar_atendimento(self, user, origem=''):
        from .services import eventos
        with transaction.atomic():
            status_de = self.status
            self.cancelado = user
            self.status = self.CANCELADO
            self.cancelado_em = timezone.localtime()
            self.save()
            eventos.registrar(self, TicketEvento.CANCELADO, usuario=user,
                              status_de=status_de, origem=origem,
                              ocorrido_em=self.cancelado_em)

    def reabrir(self, user, novo_status=None, origem=''):
        """Reabre um ticket encerrado ou cancelado.

        Limpa as datas/autoria do fechamento, senão o ticket volta a ficar ativo
        carregando um `encerrado_em` antigo — e o guard "já está encerrado" das views
        continuaria barrando um novo encerramento.

        As Soluções antigas são mantidas (é histórico); ao encerrar de novo, uma nova
        é criada e passa a ser a mais recente.

        O fechamento anterior não se perde mais: ele já está gravado como um
        TicketEvento próprio, que esta função não toca. Limpar os campos aqui é
        só estado atual, não histórico."""
        from .services import eventos
        if novo_status is None:
            novo_status = self.EM_ATENDIMENTO
        with transaction.atomic():
            status_de = self.status
            self.status = novo_status
            self.encerrado_em = None
            self.cancelado_em = None
            self.cancelado = None
            # Voltando para "Em atendimento" sem responsável, assume quem reabriu.
            if novo_status == self.EM_ATENDIMENTO:
                if not self.responsavel_id:
                    self.responsavel = user
                if not self.iniciado_em:
                    self.iniciado_em = timezone.localtime()
            self.save()
            eventos.registrar(self, TicketEvento.REABERTO, usuario=user,
                              status_de=status_de, origem=origem)

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
    # Quem pode entrar no quadro. VAZIO = quadro público (todos veem).
    # Com grupos, só entra quem está em pelo menos um deles (superusuário sempre entra).
    # Só superusuário pode definir isso. Ver pode_ver_quadro() em views.py.
    grupos = models.ManyToManyField('auth.Group', blank=True, related_name='quadros_kanban')
    # Quando preenchido, o quadro ganha uma Caixa de entrada: os tickets abertos
    # deste departamento entram numa fila de triagem para serem aprovados (viram
    # card numa coluna) ou recusados. Ver CaixaEntradaRecusa.
    departamento_entrada = models.ForeignKey(
        Departamento, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
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


class KanbanGrupo(models.Model):
    """Cards que andam juntos pelo quadro (ex.: todos os tickets da mesma branch).

    Os cards de um grupo ficam sempre na MESMA coluna e contíguos em `ordem` —
    arrastar o grupo move todos de uma vez. Grupo que fica com um card só é
    desfeito (o card sobrevive, solto)."""

    # 'card_grupos' porque KanbanQuadro.grupos já é o dos grupos de permissão
    quadro = models.ForeignKey(KanbanQuadro, on_delete=models.CASCADE, related_name='card_grupos')
    nome = models.CharField(max_length=80, blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nome or f"Grupo #{self.pk}"


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
    # Selo "concluído" do card (estilo Trello). É só visual: não muda o status do
    # ticket/nota vinculado nem move o card de coluna.
    concluido = models.BooleanField(default=False)
    grupo = models.ForeignKey(KanbanGrupo, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='cards')
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


class CaixaEntradaRecusa(models.Model):
    """Ticket recusado na triagem da Caixa de entrada de um quadro.

    Aprovar um ticket é simplesmente criar o KanbanCard dele numa coluna — por isso
    só a recusa precisa de registro próprio. O ticket NÃO é alterado: ele apenas
    deixa de aparecer na caixa daquele quadro."""

    quadro = models.ForeignKey(KanbanQuadro, on_delete=models.CASCADE, related_name='recusas')
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='+')
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    motivo = models.TextField(blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('quadro', 'ticket')
        ordering = ['-criado_em']
        verbose_name = 'Recusa da caixa de entrada'
        verbose_name_plural = 'Recusas da caixa de entrada'

    def __str__(self):
        return f"Ticket #{self.ticket_id} recusado em {self.quadro}"


class Etiqueta(models.Model):
    """Etiqueta colorida aplicável a cards do Kanban (estilo Trello).

    Vive dentro de um quadro: cada quadro tem o seu próprio conjunto (antes eram
    globais e compartilhadas). O nome é opcional (etiqueta só-cor, como no Trello).
    Relaciona-se a KanbanCard via M2M (KanbanCard.etiquetas). O `quadro` é nulo só
    em etiquetas órfãs herdadas da época global que não estavam em nenhum card."""

    quadro = models.ForeignKey(KanbanQuadro, on_delete=models.CASCADE,
                               related_name='etiquetas', null=True, blank=True)
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


class TicketEvento(models.Model):
    """Histórico append-only das transições de um ticket.

    Existe porque os timestamps do próprio Ticket não são histórico: `reabrir()`
    zera `encerrado_em`/`cancelado_em`, apagando o passado de forma irreversível.
    Nada aqui é atualizado ou apagado — só inserido.
    """

    CRIADO = 0
    INICIADO = 1
    ENCERRADO = 2
    CANCELADO = 3
    REABERTO = 4
    RESPONSAVEL_ALTERADO = 5

    TIPOS = (
        (CRIADO, 'Criado'),
        (INICIADO, 'Atendimento iniciado'),
        (ENCERRADO, 'Encerrado'),
        (CANCELADO, 'Cancelado'),
        (REABERTO, 'Reaberto'),
        (RESPONSAVEL_ALTERADO, 'Responsável alterado'),
    )

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='eventos')
    tipo = models.SmallIntegerField(choices=TIPOS)
    # default e não auto_now_add: o backfill precisa gravar instantes do passado.
    ocorrido_em = models.DateTimeField(default=timezone.now)
    # SET_NULL e não PROTECT (que é o padrão do resto do projeto): evento é
    # histórico imutável, não pode virar âncora que impede apagar um usuário.
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='eventos_ticket')
    status_de = models.SmallIntegerField(null=True, blank=True)
    status_para = models.SmallIntegerField(null=True, blank=True)
    origem = models.CharField(max_length=20, blank=True, default='')
    # True = reconstruído por aproximação (backfill), não observado. Sem isso o
    # backfill contamina os relatórios em silêncio.
    estimado = models.BooleanField(default=False)
    registrado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['ocorrido_em', 'id']
        indexes = [
            models.Index(fields=['ticket', 'ocorrido_em'], name='tktevt_ticket_ocor_idx'),
            models.Index(fields=['tipo', 'ocorrido_em'], name='tktevt_tipo_ocor_idx'),
        ]

    def __str__(self):
        return f"#{self.ticket_id} {self.get_tipo_display()} em {self.ocorrido_em:%d/%m/%Y %H:%M}"


class Expediente(models.Model):
    """Uma faixa de atendimento num dia da semana.

    Vários registros no mesmo dia = intervalo de almoço
    (ex.: seg 08:00-12:00 e seg 13:00-18:00).
    """

    DIAS = (
        (0, 'Segunda'), (1, 'Terça'), (2, 'Quarta'), (3, 'Quinta'),
        (4, 'Sexta'), (5, 'Sábado'), (6, 'Domingo'),
    )

    dia_semana = models.SmallIntegerField(choices=DIAS)  # 0=segunda, igual a date.weekday()
    hora_inicio = models.TimeField()
    hora_fim = models.TimeField()
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ['dia_semana', 'hora_inicio']
        unique_together = [('dia_semana', 'hora_inicio')]
        verbose_name = 'Expediente'
        verbose_name_plural = 'Expediente'

    def __str__(self):
        return f"{self.get_dia_semana_display()} {self.hora_inicio:%H:%M}-{self.hora_fim:%H:%M}"

    def clean(self):
        if self.hora_fim <= self.hora_inicio:
            raise ValidationError('A hora final deve ser maior que a inicial.')


class Feriado(models.Model):
    data = models.DateField()
    descricao = models.CharField(max_length=60)
    # Só resolve feriado de data fixa (Natal, Tiradentes). Carnaval e Páscoa são
    # móveis: cadastre uma linha por ano.
    recorrente_anual = models.BooleanField(
        default=False, help_text='Repete todo ano na mesma data (Natal, Tiradentes...). '
                                 'Feriado móvel (Carnaval, Páscoa) deixe desmarcado e cadastre ano a ano.')

    class Meta:
        ordering = ['data']

    def __str__(self):
        return f"{self.data:%d/%m} {self.descricao}"


class SlaPolitica(models.Model):
    """Meta de resposta e resolução, em minutos de expediente.

    Departamento e prioridade vazios funcionam como curinga. A política mais
    específica vence — ver sla.politica_para().
    """

    departamento = models.ForeignKey(Departamento, on_delete=models.CASCADE, null=True, blank=True,
                                     help_text='Vazio = vale para qualquer departamento.')
    prioridade = models.ForeignKey(Prioridade, on_delete=models.CASCADE, null=True, blank=True,
                                   help_text='Vazio = vale para qualquer prioridade.')
    minutos_resposta = models.PositiveIntegerField(
        help_text='Minutos úteis entre a abertura e o início do atendimento.')
    minutos_resolucao = models.PositiveIntegerField(
        help_text='Minutos úteis entre a abertura e o encerramento.')
    ativo = models.BooleanField(default=True)

    class Meta:
        unique_together = [('departamento', 'prioridade')]
        verbose_name = 'Política de SLA'
        verbose_name_plural = 'Políticas de SLA'

    def __str__(self):
        dep = self.departamento or 'qualquer depto'
        pri = self.prioridade or 'qualquer prioridade'
        return f"{dep} / {pri}: {self.minutos_resposta}min resposta, {self.minutos_resolucao}min resolução"