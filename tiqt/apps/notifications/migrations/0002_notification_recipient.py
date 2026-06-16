from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def limpar_antigas(apps, schema_editor):
    """As notificações existentes eram apenas testes e não tinham destinatário."""
    Notification = apps.get_model('notifications', 'Notification')
    Notification.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(limpar_antigas, migrations.RunPython.noop),
        migrations.AddField(
            model_name='notification',
            name='recipient',
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='notifications',
                to=settings.AUTH_USER_MODEL,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='notification',
            name='url',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='notification',
            name='is_read',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterModelOptions(
            name='notification',
            options={'ordering': ['-created_at']},
        ),
    ]
