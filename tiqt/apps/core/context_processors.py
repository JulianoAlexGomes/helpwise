from .models import Departamento, Tipo, Prioridade
from django.contrib.auth import get_user_model


def ticket_modal_data(request):
    """Injeta dados necessários para o modal de abertura rápida de ticket."""
    if not request.user.is_authenticated:
        return {}
    User = get_user_model()
    return {
        'modal_departamentos': Departamento.objects.all(),
        'modal_tipos': Tipo.objects.all(),
        'modal_prioridades': Prioridade.objects.all(),
        'modal_usuarios': User.objects.filter(is_active=True).order_by('first_name', 'last_name'),
    }
