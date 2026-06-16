from django.urls import path
from . import views

urlpatterns = [
    path("list/", views.list_notifications, name="notifications_list"),
    path("mark-read/", views.mark_read, name="notifications_mark_read"),
]
