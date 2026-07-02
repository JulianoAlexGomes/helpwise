from django.db import migrations

# Categorias-exemplo para o mural já nascer útil. Podem ser editadas/desativadas.
CATEGORIAS = [
    # (nome, cor, icone, ordem)
    ('Geral', '#607d8b', 'push_pin', 0),
    ('Boletos', '#00897b', 'receipt_long', 1),
    ('Treinamentos', '#5c6bc0', 'school', 2),
    ('Operações', '#f5a623', 'settings', 3),
    ('RH', '#8e24aa', 'groups', 4),
    ('Segurança', '#e53935', 'shield', 5),
]


def seed(apps, schema_editor):
    CategoriaNota = apps.get_model('mural', 'CategoriaNota')
    for nome, cor, icone, ordem in CATEGORIAS:
        CategoriaNota.objects.get_or_create(
            nome=nome,
            defaults={'cor': cor, 'icone': icone, 'ordem': ordem, 'ativo': True},
        )


def unseed(apps, schema_editor):
    CategoriaNota = apps.get_model('mural', 'CategoriaNota')
    CategoriaNota.objects.filter(nome__in=[c[0] for c in CATEGORIAS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('mural', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
