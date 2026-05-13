from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("perfil/escolher/", views.choose_profile, name="choose_profile"),
    path(
        "perfil/profissional/novo/",
        views.create_provider_profile,
        name="create_provider_profile",
    ),
    path(
        "perfil/paciente/novo/",
        views.create_patient_profile,
        name="create_patient_profile",
    ),
]
