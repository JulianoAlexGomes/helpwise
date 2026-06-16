from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def list_notifications(request):
    """Lista as notificações recentes do usuário logado + total não lidas."""
    qs = Notification.objects.filter(recipient=request.user)[:20]
    data = [
        {
            'id': n.id,
            'message': n.message,
            'url': n.url,
            'is_read': n.is_read,
            'created_at': n.created_at.strftime('%d/%m/%Y %H:%M'),
        }
        for n in qs
    ]
    unread = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'notifications': data, 'unread': unread})


@login_required
@require_POST
def mark_read(request):
    """Marca como lidas as notificações do usuário (todas, ou apenas uma se vier `id`)."""
    qs = Notification.objects.filter(recipient=request.user, is_read=False)
    notif_id = request.POST.get('id')
    if notif_id:
        qs = qs.filter(id=notif_id)
    qs.update(is_read=True)
    return JsonResponse({'ok': True})
