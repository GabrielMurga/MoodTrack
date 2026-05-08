from django.contrib import admin

from .models import MoodEntry


@admin.register(MoodEntry)
class MoodEntryAdmin(admin.ModelAdmin):
    """Admin do MoodEntry — usar com extrema parcimônia.

    Mesmo aqui, content aparece descriptografado — só ative em ambientes
    onde admins são pessoal de operação confiável e auditado.
    Em produção, remover do admin é uma decisão razoável.
    """

    list_display = ("id", "patient", "mood", "is_shared_with_psychologist", "created_at")
    list_filter = ("mood", "is_shared_with_psychologist")
    search_fields = ("patient__user__email",)
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("patient",)
