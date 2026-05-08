from django.urls import path

from . import views

app_name = "journal"

urlpatterns = [
    # Paciente
    path("diario/", views.patient_journal_list, name="patient_list"),
    path("diario/novo/", views.patient_journal_create, name="patient_create"),
    path("diario/<int:entry_id>/editar/", views.patient_journal_edit, name="patient_edit"),
    path(
        "diario/<int:entry_id>/share/",
        views.patient_journal_toggle_share,
        name="patient_toggle_share",
    ),
    # Psicólogo
    path("pacientes/", views.psychologist_patient_list, name="psychologist_patients"),
    path(
        "pacientes/<int:patient_id>/",
        views.psychologist_patient_detail,
        name="psychologist_patient_detail",
    ),
]
