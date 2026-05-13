from django.contrib import admin

from .models import WebhookEvent


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "event_id", "received_at", "processed_at", "has_error")
    list_filter = ("event_type",)
    search_fields = ("event_id",)
    readonly_fields = (
        "event_id",
        "event_type",
        "payload",
        "received_at",
        "processed_at",
        "error",
    )

    def has_error(self, obj: WebhookEvent) -> bool:
        return bool(obj.error)

    has_error.boolean = True
    has_error.short_description = "erro?"

    # WebhookEvent é append-only por design (auditoria de billing).
    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
