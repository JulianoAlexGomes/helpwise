# from django.shortcuts import render

# from django.http import JsonResponse
# from .models import Notification
# from asgiref.sync import async_to_sync
# from channels.layers import get_channel_layer

# def send_notification(request):
#     message = "Uma nova informação foi adicionada ao banco!"
#     Notification.objects.create(message=message)

#     # Envia a notificação para os WebSockets
#     channel_layer = get_channel_layer()
#     async_to_sync(channel_layer.group_send)(
#         "notifications",
#         {"type": "send_notification", "message": message},
#     )

#     return JsonResponse({"message": "Notificação enviada!"})


import json
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.http import JsonResponse

def send_notification(request):
    channel_layer = get_channel_layer()
    message = "Teste de notificação em tempo real!"
    
    # Enviar a mensagem para o grupo "notifications"
    async_to_sync(channel_layer.group_send)(
        "notifications",  
        {
            "type": "send_message",
            "message": message
        }
    )

    return JsonResponse({"message": "Notificação enviada!"})

from django.shortcuts import render

def notification_test(request):
    return render(request, "notifications/test.html")
