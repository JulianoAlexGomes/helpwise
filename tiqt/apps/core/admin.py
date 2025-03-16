from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Ticket, Comentario, Departamento, Cliente

class ComentarioInline(admin.TabularInline):  
    model = Comentario
    extra = 1  

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ['id', 'titulo', 'criado_em']
    inlines = [ComentarioInline]  

@admin.register(Comentario)
class ComentarioAdmin(admin.ModelAdmin):
    list_display = ['id', 'ticket', 'autor', 'criado_em']
    list_filter = ['ticket', 'autor']