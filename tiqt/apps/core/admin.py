from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Ticket, Comentario, Departamento, Cliente

# Register your models here.

class ComentarioInline(admin.TabularInline):
    model = Comentario
    extra = 1


class TicketAdmin(admin.ModelAdmin):
    inlines = [ComentarioInline]
    exclude = ('criado_por',)
    list_display = ('id','departamento','status','responsavel')


admin.site.register(User, UserAdmin)
admin.site.register(Ticket, TicketAdmin)
admin.site.register(Departamento)
admin.site.register(Cliente)