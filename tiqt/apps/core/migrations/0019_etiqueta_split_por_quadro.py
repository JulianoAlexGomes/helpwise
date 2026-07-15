from django.db import migrations


def split_por_quadro(apps, schema_editor):
    """Torna cada etiqueta específica de um quadro.

    Antes as etiquetas eram globais e uma mesma etiqueta podia estar em cards de
    quadros diferentes. Agora cada quadro tem o seu conjunto: a etiqueta original
    fica no primeiro quadro que a usa e, para cada quadro adicional, criamos uma
    cópia (mesmo nome e cor) e reapontamos os cards daquele quadro para ela — os
    chips continuam idênticos na tela.
    """
    Etiqueta = apps.get_model('core', 'Etiqueta')
    KanbanCard = apps.get_model('core', 'KanbanCard')

    # list(...) fixa o conjunto ANTES de criar cópias: senão o próprio loop pega
    # as cópias recém-criadas e sai duplicando em cascata.
    for etiqueta in list(Etiqueta.objects.all()):
        # set() e não .distinct(): KanbanCard tem Meta.ordering, e isso faz o
        # Django incluir as colunas de ordenação no SELECT do DISTINCT, que passa
        # a devolver o mesmo quadro repetido — cada repetição viraria uma cópia vazia.
        quadros = sorted(set(
            KanbanCard.objects
            .filter(etiquetas=etiqueta)
            .values_list('coluna__quadro_id', flat=True)
        ))
        if not quadros:
            # Órfã (não está em nenhum card): fica sem quadro e simplesmente não
            # aparece em lugar nenhum. Não apagamos para não perder histórico.
            continue

        etiqueta.quadro_id = quadros[0]
        etiqueta.save(update_fields=['quadro'])

        for quadro_id in quadros[1:]:
            copia = Etiqueta.objects.create(
                quadro_id=quadro_id, nome=etiqueta.nome, cor=etiqueta.cor)
            cards = KanbanCard.objects.filter(etiquetas=etiqueta, coluna__quadro_id=quadro_id)
            for card in cards:
                card.etiquetas.remove(etiqueta)
                card.etiquetas.add(copia)


def noop(apps, schema_editor):
    # Sem volta: as cópias já não sabem que eram uma etiqueta só. Reverter o
    # AddField (migração anterior) é o suficiente para desfazer o schema.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_etiqueta_quadro'),
    ]

    operations = [
        migrations.RunPython(split_por_quadro, noop),
    ]
