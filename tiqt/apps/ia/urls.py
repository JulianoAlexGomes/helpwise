from django.urls import path

from . import views

urlpatterns = [
    path("assistente/", views.AssistenteView.as_view(), name="ia_assistente"),
    path(
        "assistente/<int:pk>/feedback/",
        views.FeedbackView.as_view(),
        name="ia_feedback",
    ),
]
