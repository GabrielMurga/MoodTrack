from django.urls import path

from . import views

app_name = "ai"

urlpatterns = [
    path("diario/insights/", views.patient_insights, name="patient_insights"),
    path("diario/insights/gerar/", views.patient_generate_weekly, name="patient_generate_weekly"),
    path(
        "pacientes/<int:patient_id>/briefing/gerar/",
        views.psychologist_generate_briefing,
        name="psychologist_generate_briefing",
    ),
    path(
        "pacientes/<int:patient_id>/briefing/",
        views.psychologist_briefing_detail,
        name="psychologist_briefing_detail",
    ),
]
