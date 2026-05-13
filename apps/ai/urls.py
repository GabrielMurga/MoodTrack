from django.urls import path

from . import views

app_name = "ai"

urlpatterns = [
    path("diario/insights/", views.patient_insights, name="patient_insights"),
    path("diario/insights/gerar/", views.patient_generate_weekly, name="patient_generate_weekly"),
    path(
        "pacientes/<int:patient_id>/briefing/gerar/",
        views.provider_generate_briefing,
        name="provider_generate_briefing",
    ),
    path(
        "pacientes/<int:patient_id>/briefing/",
        views.provider_briefing_detail,
        name="provider_briefing_detail",
    ),
]
