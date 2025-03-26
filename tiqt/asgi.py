import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import tiqt.apps.notifications.routing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tiqt.settings")

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(tiqt.apps.notifications.routing.websocket_urlpatterns)
    ),
})
