from django.urls import path
from .views import send_notification, notification_test

urlpatterns = [
    path("send/", send_notification, name="send_notification"),
    path("test/", notification_test, name="notification_test"),
]
