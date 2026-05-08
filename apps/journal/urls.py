from django.urls import path

from . import views

app_name = "journal"

urlpatterns = [
    # Paciente — humor (calendário)
    path("diario/humor/", views.patient_mood_list, name="patient_mood_list"),
    path("diario/humor/novo/", views.patient_mood_create, name="patient_mood_create"),
    path(
        "diario/humor/<int:log_id>/share/",
        views.patient_mood_toggle_share,
        name="patient_mood_toggle_share",
    ),

    # Paciente — diário de eventos
    path("diario/eventos/", views.patient_journal_list, name="patient_journal_list"),
    path(
        "diario/eventos/novo/",
        views.patient_journal_create,
        name="patient_journal_create",
    ),
    path(
        "diario/eventos/<int:entry_id>/editar/",
        views.patient_journal_edit,
        name="patient_journal_edit",
    ),
    path(
        "diario/eventos/<int:entry_id>/share/",
        views.patient_journal_toggle_share,
        name="patient_journal_toggle_share",
    ),

    # Psicólogo
    path("pacientes/", views.psychologist_patient_list, name="psychologist_patients"),
    path(
        "pacientes/<int:patient_id>/",
        views.psychologist_patient_detail,
        name="psychologist_patient_detail",
    ),
    path(
        "pacientes/<int:patient_id>/anotacao/",
        views.clinical_note_create,
        name="clinical_note_create",
    ),
    path(
        "anotacao/<int:note_id>/editar/",
        views.clinical_note_edit,
        name="clinical_note_edit",
    ),
]
