from django.apps import AppConfig


class IaConfig(AppConfig):
    name = 'tiqt.apps.ia'
    verbose_name = 'Assistente de IA'

    def ready(self):
        from . import signals  # noqa: F401  (registra o signal)
