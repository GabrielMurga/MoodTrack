from django.contrib import admin

from .models import Bond


@admin.register(Bond)
class BondAdmin(admin.ModelAdmin):
    list_display = (
        "invite_code",
        "provider",
        "patient",
        "status",
        "invited_at",
        "provider_confirmed_at",
    )
    list_filter = ("status",)
    search_fields = ("invite_code", "provider__user__email", "patient__user__email")
    readonly_fields = (
        "invite_code",
        "invited_at",
        "patient_entered_at",
        "provider_confirmed_at",
        "ended_at",
        "ended_by",
    )
    autocomplete_fields = ("provider", "patient")
