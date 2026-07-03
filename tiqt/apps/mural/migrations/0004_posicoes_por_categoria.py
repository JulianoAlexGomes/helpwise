from django.db import migrations, models


def backfill(apps, schema_editor):
    """Move a posição global antiga para a visão 'todas'."""
    Nota = apps.get_model('mural', 'Nota')
    for n in Nota.objects.all():
        if n.pos_x is not None and n.pos_y is not None:
            n.posicoes = {'todas': {'x': n.pos_x, 'y': n.pos_y, 'z': n.z or 0}}
            n.save(update_fields=['posicoes'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('mural', '0003_nota_pos_x_nota_pos_y_nota_z'),
    ]

    operations = [
        migrations.AddField(
            model_name='nota',
            name='posicoes',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.RunPython(backfill, noop),
        migrations.RemoveField(model_name='nota', name='pos_x'),
        migrations.RemoveField(model_name='nota', name='pos_y'),
        migrations.RemoveField(model_name='nota', name='z'),
    ]
