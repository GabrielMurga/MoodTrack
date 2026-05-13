from django.urls import path

from . import views

app_name = "clinical"

urlpatterns = [
    path(
        "pacientes/<int:patient_id>/medicacao/nova/",
        views.medication_create,
        name="medication_create",
    ),
    path(
        "medicacao/<int:medication_id>/editar/",
        views.medication_edit,
        name="medication_edit",
    ),
    path(
        "medicacao/<int:medication_id>/descontinuar/",
        views.medication_discontinue,
        name="medication_discontinue",
    ),
    path(
        "minhas-medicacoes/",
        views.patient_reported_medication,
        name="patient_reported_medication",
    ),
]
