from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from tiqt.apps.core import views
from tiqt.apps.core import views_painel
from tiqt.apps.core import views_relatorios
from django.conf import settings
from django.conf.urls.static import static
from tiqt.apps.core.views import excluir_arquivo, download_certificado, CertificadoDeleteView

urlpatterns = [
    path('', views.HomeView, name='home'),
    path('tv/', views_painel.painel_tv, name='painel_tv'),
    path('tv/dados/', views_painel.painel_tv_dados, name='painel_tv_dados'),
    path('relatorios/', views_relatorios.relatorios_view, name='relatorios'),
    path('relatorios/pdf/', views_relatorios.relatorios_pdf, name='relatorios_pdf'),
    path('relatorios/excel/', views_relatorios.relatorios_excel, name='relatorios_excel'),
    path('perfil/', views.PerfilView.as_view(), name='perfil'),
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
    path('ticket/lote/encerrar/', views.TicketLoteEncerrarView.as_view(), name='ticket_lote_encerrar'),
    path('ticket/lote/cancelar/', views.TicketLoteCancelarView.as_view(), name='ticket_lote_cancelar'),
    path('ticket/grupo/agrupar/', views.TicketGrupoAgruparView.as_view(), name='ticket_grupo_agrupar'),
    path('ticket/grupo/desagrupar/', views.TicketGrupoDesagruparView.as_view(), name='ticket_grupo_desagrupar'),
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
    path('cliente/<int:pk>/inativar/', views.ClienteInativarView.as_view(), name='cliente_inativar'),
    path('cliente/<int:pk>/reativar/', views.ClienteReativarView.as_view(), name='cliente_reativar'),
    path('login/', auth_views.LoginView.as_view(redirect_authenticated_user=True),name='login'), 
    path('logout', auth_views.LogoutView.as_view(), name='logout'),
    path('admin/', admin.site.urls),
    path('select2/', include('django_select2.urls')), 
    path('comentario/<int:comentario_id>/excluir/<str:tipo>/', excluir_arquivo, name='excluir_arquivo'),
    path('comentario/excluir/<int:comentario_id>/', views.excluir_comentario, name='excluir_comentario'),
    path('clientes/autocomplete/',views.clientes_autocomplete,name='clientes_autocomplete'),
    path('api/clientes/autocomplete/',views.clientes_autocomplete,name='clientes_autocomplete'),
    path('api/clientes/busca/', views.clientes_busca_api, name='clientes_busca_api'),
    path('api/clientes/quick-create/', views.ClienteQuickCreateView.as_view(), name='cliente_quick_create'),
    path('api/cep/<str:cep>/', views.buscar_cep, name='buscar_cep'),
    path('api/cnpj/<str:cnpj>/', views.buscar_cnpj, name='buscar_cnpj'),
    path('ticket/quick-create/', views.QuickTicketCreateView.as_view(), name='quick_ticket_create'),
    path('ticket/kanban/', views.KanbanView.as_view(), name='ticket_kanban'),
    path('ticket/<int:pk>/accept-ajax/', views.TicketAcceptAjaxView.as_view(), name='ticket_accept_ajax'),
    path('ticket/<int:pk>/close-ajax/', views.TicketCloseAjaxView.as_view(), name='ticket_close_ajax'),
    path('ticket/<int:pk>/preview-ajax/', views.TicketPreviewAjaxView.as_view(), name='ticket_preview_ajax'),
    path('ticket/<int:pk>/mover-coluna/', views.TicketMoverColunaView.as_view(), name='ticket_mover_coluna'),
    path('ticket/<int:pk>/comentar-ajax/', views.TicketComentarAjaxView.as_view(), name='ticket_comentar_ajax'),
    path('ticket/<int:pk>/enviar-mural/', views.TicketEnviarMuralView.as_view(), name='ticket_enviar_mural'),
    path('ticket/busca-ajax/', views.TicketBuscaAjaxView.as_view(), name='ticket_busca_ajax'),
    path('kanban/quadro/criar/', views.KanbanQuadroCriarView.as_view(), name='kanban_quadro_criar'),
    path('kanban/quadro/<int:pk>/editar/', views.KanbanQuadroEditarView.as_view(), name='kanban_quadro_editar'),
    path('kanban/quadro/<int:pk>/excluir/', views.KanbanQuadroExcluirView.as_view(), name='kanban_quadro_excluir'),
    path('kanban/coluna/criar/', views.KanbanColunaCriarView.as_view(), name='kanban_coluna_criar'),
    path('kanban/coluna/<int:pk>/editar/', views.KanbanColunaEditarView.as_view(), name='kanban_coluna_editar'),
    path('kanban/coluna/<int:pk>/excluir/', views.KanbanColunaExcluirView.as_view(), name='kanban_coluna_excluir'),
    path('kanban/colunas/reordenar/', views.KanbanColunasReordenarView.as_view(), name='kanban_colunas_reordenar'),
    path('nota/busca-ajax/', views.NotaBuscaAjaxView.as_view(), name='nota_busca_ajax'),
    path('kanban/card/adicionar/', views.KanbanCardAdicionarView.as_view(), name='kanban_card_adicionar'),
    path('kanban/card/adicionar-nota/', views.KanbanCardAdicionarNotaView.as_view(), name='kanban_card_adicionar_nota'),
    path('kanban/card/avulso/', views.KanbanCardAvulsoSalvarView.as_view(), name='kanban_card_avulso'),
    path('kanban/card/detalhe/', views.KanbanCardDetalheView.as_view(), name='kanban_card_detalhe'),
    path('kanban/card/comentar/', views.KanbanCardComentarView.as_view(), name='kanban_card_comentar'),
    path('kanban/card/mover/', views.KanbanCardMoverView.as_view(), name='kanban_card_mover'),
    path('kanban/card/remover/', views.KanbanCardRemoverView.as_view(), name='kanban_card_remover'),
    path('kanban/card/concluir/', views.KanbanCardConcluirView.as_view(), name='kanban_card_concluir'),
    path('kanban/grupo/criar/', views.KanbanGrupoCriarView.as_view(), name='kanban_grupo_criar'),
    path('kanban/grupo/desfazer/', views.KanbanGrupoDesfazerView.as_view(), name='kanban_grupo_desfazer'),
    path('kanban/grupo/mover/', views.KanbanGrupoMoverView.as_view(), name='kanban_grupo_mover'),
    path('kanban/cards/reordenar/', views.KanbanCardsReordenarView.as_view(), name='kanban_cards_reordenar'),
    path('kanban/coluna/<int:pk>/cards/', views.KanbanColunaCardsView.as_view(), name='kanban_coluna_cards'),
    path('kanban/etiquetas/', views.EtiquetaListView.as_view(), name='kanban_etiquetas'),
    path('kanban/etiqueta/criar/', views.EtiquetaCriarView.as_view(), name='kanban_etiqueta_criar'),
    path('kanban/etiqueta/editar/', views.EtiquetaEditarView.as_view(), name='kanban_etiqueta_editar'),
    path('kanban/etiqueta/excluir/', views.EtiquetaExcluirView.as_view(), name='kanban_etiqueta_excluir'),
    path('kanban/card/etiqueta/toggle/', views.CardEtiquetaToggleView.as_view(), name='kanban_card_etiqueta_toggle'),
    path('kanban/quadro/fundo/', views.KanbanQuadroFundoView.as_view(), name='kanban_quadro_fundo'),
    path('kanban/card/membros/', views.CardMembrosSalvarView.as_view(), name='kanban_card_membros'),
    path('kanban/caixa-entrada/', views.CaixaEntradaListView.as_view(), name='kanban_caixa_entrada'),
    path('kanban/caixa-entrada/recusar/', views.CaixaEntradaRecusarView.as_view(), name='kanban_caixa_entrada_recusar'),

    path('notifications/', include('tiqt.apps.notifications.urls')),
    path('', include('tiqt.apps.ia.urls')),
    path('', include('tiqt.apps.agenda.urls')),
    path('', include('tiqt.apps.mural.urls')),

    # API
    path('api/', include('tiqt.apps.core.api_urls')),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)                                 