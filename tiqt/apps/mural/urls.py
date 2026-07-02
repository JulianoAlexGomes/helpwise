from django.urls import path

from . import views

urlpatterns = [
    path('mural/', views.MuralView.as_view(), name='mural'),

    path('mural/nota/novo/', views.NotaCreateView.as_view(), name='nota_create'),
    path('mural/nota/<int:pk>/editar/', views.NotaUpdateView.as_view(), name='nota_update'),
    path('mural/nota/<int:pk>/status/', views.NotaStatusView.as_view(), name='nota_status'),
    path('mural/nota/<int:pk>/fixar/', views.NotaFixarView.as_view(), name='nota_fixar'),
    path('mural/nota/<int:pk>/excluir/', views.NotaDeleteView.as_view(), name='nota_delete'),
    path('mural/nota/<int:pk>/posicao/', views.NotaPosicaoView.as_view(), name='nota_posicao'),
    path('mural/nota/arquivo/<int:pk>/excluir/', views.NotaArquivoDeleteView.as_view(), name='nota_arquivo_delete'),
    path('mural/organizar/', views.NotaOrganizarView.as_view(), name='nota_organizar'),

    path('mural/categoria/novo/', views.CategoriaCreateView.as_view(), name='categoria_create'),
    path('mural/categoria/<int:pk>/editar/', views.CategoriaUpdateView.as_view(), name='categoria_update'),
    path('mural/categoria/<int:pk>/excluir/', views.CategoriaDeleteView.as_view(), name='categoria_delete'),
]
