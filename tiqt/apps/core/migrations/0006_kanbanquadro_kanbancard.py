import django.db.models.deletion
from django.db import migrations, models


def criar_quadro_padrao(apps, schema_editor):
    """Cria o quadro padrão (fluxo por status) e vincula as colunas já existentes a ele."""
    KanbanQuadro = apps.get_model('core', 'KanbanQuadro')
    KanbanColuna = apps.get_model('core', 'KanbanColuna')
    padrao, _ = KanbanQuadro.objects.get_or_create(
        is_padrao=True,
        defaults={'nome': 'Fluxo (padrão)', 'ordem': 0},
    )
    KanbanColuna.objects.filter(quadro__isnull=True).update(quadro=padrao)


def remover_quadro_padrao(apps, schema_editor):
    KanbanQuadro = apps.get_model('core', 'KanbanQuadro')
    KanbanQuadro.objects.filter(is_padrao=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_kanbancoluna_ticket_kanban_ordem_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='KanbanQuadro',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=60)),
                ('is_padrao', models.BooleanField(default=False)),
                ('ordem', models.PositiveIntegerField(default=0)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-is_padrao', 'ordem', 'id'],
            },
        ),
        migrations.AddField(
            model_name='kanbancoluna',
            name='quadro',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='colunas', to='core.kanbanquadro'),
        ),
        migrations.CreateModel(
            name='KanbanCard',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ordem', models.PositiveIntegerField(default=0)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('coluna', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cards', to='core.kanbancoluna')),
                ('ticket', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='kanban_cards', to='core.ticket')),
            ],
            options={
                'ordering': ['ordem', '-id'],
            },
        ),
        migrations.RunPython(criar_quadro_padrao, remover_quadro_padrao),
        migrations.AlterField(
            model_name='kanbancoluna',
            name='quadro',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='colunas', to='core.kanbanquadro'),
        ),
    ]
