from django.urls import path

from . import views

urlpatterns = [
    path('agenda/', views.CalendarioView.as_view(), name='agenda'),
    path('agenda/novo/', views.AgendamentoCreateView.as_view(), name='agendamento_create'),
    path('agenda/<int:pk>/editar/', views.AgendamentoUpdateView.as_view(), name='agendamento_update'),
    path('agenda/<int:pk>/concluir/', views.AgendamentoConcluirView.as_view(), name='agendamento_concluir'),
    path('agenda/<int:pk>/cancelar/', views.AgendamentoCancelarView.as_view(), name='agendamento_cancelar'),
    path('agenda/<int:pk>/excluir/', views.AgendamentoDeleteView.as_view(), name='agendamento_delete'),
    path('agenda/alertas/', views.AlertasDoDiaView.as_view(), name='agenda_alertas'),
]
