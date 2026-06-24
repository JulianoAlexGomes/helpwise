from django.apps import AppConfig


class AgendaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tiqt.apps.agenda'
    verbose_name = 'Agenda'

    def ready(self):
        # Registra os signals de sincronização com os comentários de ticket
        from . import signals  # noqa: F401
