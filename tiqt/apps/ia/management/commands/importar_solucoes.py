"""
Popula a BaseConhecimento a partir das soluções já registradas nos tickets
encerrados (modelo core.Solucao). Roda com:

    python manage.py importar_solucoes
"""
from django.core.management.base import BaseCommand

from tiqt.apps.core.models import Solucao
from tiqt.apps.ia.sync import sincronizar_solucao


class Command(BaseCommand):
    help = "Importa soluções do histórico de tickets para a base de conhecimento da IA."

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-chars",
            type=int,
            default=20,
            help="Ignora soluções com menos que N caracteres (padrão: 20).",
        )

    def handle(self, *args, **options):
        min_chars = options["min_chars"]
        criados = 0
        ignorados = 0

        for solucao in Solucao.objects.select_related("ticket", "ticket__departamento"):
            if sincronizar_solucao(solucao, min_chars=min_chars):
                criados += 1
            else:
                ignorados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Importação concluída: {criados} criados, {ignorados} ignorados."
            )
        )
