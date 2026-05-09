from django.contrib import admin

from .models import AISummary


@admin.register(AISummary)
class AISummaryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "kind",
        "target_patient",
        "target_bond",
        "model_used",
        "generated_at",
    )
    list_filter = ("kind", "model_used")
    search_fields = (
        "target_patient__user__email",
        "target_bond__patient__user__email",
    )
    readonly_fields = ("generated_at", "model_used", "token_metadata", "requested_by")
    autocomplete_fields = ("target_patient", "target_bond", "requested_by")
