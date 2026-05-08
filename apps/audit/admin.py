from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "actor", "action", "target_type", "target_id")
    list_filter = ("action", "target_type")
    search_fields = ("action", "target_type", "actor__email")
    readonly_fields = ("actor", "action", "target_type", "target_id", "timestamp", "metadata")
    ordering = ("-timestamp",)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
