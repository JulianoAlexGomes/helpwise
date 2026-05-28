from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from tiqt.apps.core import views
from django.conf import settings
from django.conf.urls.static import static
from tiqt.apps.core.views import excluir_arquivo, download_certificado, CertificadoDeleteView

urlpatterns = [
    path('', views.HomeView, name='home'),
    path('ticket/new/', views.NewTicketView.as_view(), name='new_ticket'),
    path('ticket/my/', views.MyTicketsView.as_view(), name='my_tickets'),
    path('ticket/open/', views.OpenTicketsView.as_view(), name='open_tickets'),
    path('ticket/inprogress/', views.InProgressTicketsView.as_view(), name='inprogress_tickets'),
    path('ticket/closed/', views.ClosedTicketsView.as_view(), name='closed_tickets'),
    path('ticket/canceled/', views.CanceledTicketsView.as_view(), name='canceled_tickets'),
    path('ticket/everyone/', views.EveryoneTicketsView.as_view(), name='everyone_tickets'),
    path('ticket/<int:pk>/', views.TicketDetailView.as_view(), name='ticket_detail'),
    path('ticket/<int:pk>/update/', views.TicketUpdateView.as_view(), name='ticket_update'),
    path('ticket/<int:pk>/accept', views.TicketAcceptView.as_view(), name='ticket_accept'),
    path('ticket/<int:pk>/cancel', views.TicketCancelView.as_view(), name='ticket_cancel'),
    path('ticket/<int:pk>/close', views.CloseTicketView.as_view(), name='ticket_close'),
    path('ticket/development/', views.DesenvTicketsView.as_view(), name='ticket_desenv'),
    path('ticket/<int:ticket_pk>/comment', views.CommentView.as_view(), name='ticket_comment'),
    path('clientes/', views.ClienteListView.as_view(), name='cliente_list'),
    path('cliente/novo/', views.ClienteCreateView.as_view(), name='cliente_create'),
    path('cliente/<int:pk>/editar/', views.ClienteUpdateView.as_view(), name='cliente_update'),

    path('cliente/<int:cliente_id>/download/', download_certificado, name='cliente_certificado'),
    
    # path('cliente/certificado/<int:pk>/download/',download_certificado_cliente,name='download_certificado_cliente'),

    # path('cliente/certificado/<int:pk>/download/',download_certificado_cliente,name='download_certificado_cliente'),

    path('certificado/<int:pk>/delete/', CertificadoDeleteView.as_view(), name='certificado_delete'),
    path('cliente/<int:pk>/delete/', views.ClienteDeleteView.as_view(), name='cliente_delete'),
    path('login/', auth_views.LoginView.as_view(redirect_authenticated_user=True),name='login'), 
    path('logout', auth_views.LogoutView.as_view(), name='logout'),
    path('admin/', admin.site.urls),
    path('select2/', include('django_select2.urls')), 
    path('comentario/<int:comentario_id>/excluir/<str:tipo>/', excluir_arquivo, name='excluir_arquivo'),
    path('comentario/excluir/<int:comentario_id>/', views.excluir_comentario, name='excluir_comentario'),
    path('clientes/autocomplete/',views.clientes_autocomplete,name='clientes_autocomplete'),
    path('api/clientes/autocomplete/',views.clientes_autocomplete,name='clientes_autocomplete'),
    path('api/clientes/busca/', views.clientes_busca_api, name='clientes_busca_api'),
    path('api/cep/<str:cep>/', views.buscar_cep, name='buscar_cep'),
    path('api/cnpj/<str:cnpj>/', views.buscar_cnpj, name='buscar_cnpj'),
    path('ticket/quick-create/', views.QuickTicketCreateView.as_view(), name='quick_ticket_create'),

    path('notifications/', include('tiqt.apps.notifications.urls')),

    # API
    path('api/', include('tiqt.apps.core.api_urls')),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)                                 