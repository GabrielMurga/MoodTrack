from django.contrib import admin

from .models import ClinicalNote, JournalEntry, MoodLog


@admin.register(MoodLog)
class MoodLogAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "mood", "is_shared_with_psychologist", "recorded_at")
    list_filter = ("mood", "is_shared_with_psychologist")
    search_fields = ("patient__user__email",)
    readonly_fields = ("recorded_at",)
    autocomplete_fields = ("patient",)


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "kind", "mood", "is_shared_with_psychologist", "created_at")
    list_filter = ("kind", "mood", "is_shared_with_psychologist")
    search_fields = ("patient__user__email", "title")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("patient",)


@admin.register(ClinicalNote)
class ClinicalNoteAdmin(admin.ModelAdmin):
    list_display = ("id", "bond", "session_date", "created_at")
    search_fields = ("bond__psychologist__user__email", "bond__patient__user__email")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("bond",)
