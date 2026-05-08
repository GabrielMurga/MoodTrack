from django.contrib import admin

from .models import PatientProfile, PsychologistProfile, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "full_name", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("email", "full_name")
    ordering = ("-date_joined",)
    readonly_fields = ("date_joined", "last_login")


@admin.register(PsychologistProfile)
class PsychologistProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "crp_number", "created_at")
    search_fields = ("user__email", "crp_number")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "preferred_name", "birth_date", "created_at")
    search_fields = ("user__email", "preferred_name")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")
