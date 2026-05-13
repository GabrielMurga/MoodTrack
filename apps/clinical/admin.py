from django.contrib import admin

from .models import Medication, PatientOverview, PatientReportedMedication


@admin.register(PatientOverview)
class PatientOverviewAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "last_edited_by", "updated_at")
    search_fields = ("patient__user__email",)
    autocomplete_fields = ("patient", "last_edited_by")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Medication)
class MedicationAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "prescribed_by", "started_at", "ended_at")
    list_filter = ("ended_at",)
    search_fields = ("patient__user__email", "prescribed_by__user__email")
    autocomplete_fields = ("patient", "prescribed_by")
    readonly_fields = ("created_at", "updated_at")


@admin.register(PatientReportedMedication)
class PatientReportedMedicationAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "updated_at")
    search_fields = ("patient__user__email",)
    autocomplete_fields = ("patient",)
    readonly_fields = ("created_at", "updated_at")
