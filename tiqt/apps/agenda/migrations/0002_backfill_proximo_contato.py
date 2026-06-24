from django.db import migrations


def backfill(apps, schema_editor):
    """Cria agendamentos para os comentários que já tinham `proximo_contato`
    antes de a agenda existir."""
    Comentario = apps.get_model('core', 'Comentario')
    Agendamento = apps.get_model('agenda', 'Agendamento')

    comentarios = (
        Comentario.objects
        .filter(proximo_contato__isnull=False, agendamento__isnull=True)
        .select_related('ticket', 'ticket__cliente', 'autor', 'ticket__responsavel')
    )

    novos = []
    for c in comentarios:
        ticket = c.ticket
        responsavel = ticket.responsavel or c.autor
        titulo = (ticket.titulo or '').strip() or f"Contato ticket #{ticket.pk}"
        novos.append(Agendamento(
            titulo=titulo,
            descricao=c.texto,
            inicio=c.proximo_contato,
            responsavel=responsavel,
            origem='ticket',
            status=0,
            ticket=ticket,
            cliente=ticket.cliente,
            comentario=c,
            criado_por=c.autor,
        ))

    Agendamento.objects.bulk_create(novos)


def reverse(apps, schema_editor):
    Agendamento = apps.get_model('agenda', 'Agendamento')
    Agendamento.objects.filter(origem='ticket', comentario__isnull=False).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agenda', '0001_initial'),
        ('core', '0004_user_foto'),
    ]

    operations = [
        migrations.RunPython(backfill, reverse),
    ]
