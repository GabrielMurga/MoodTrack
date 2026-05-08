from django.urls import path

from . import views

app_name = "bonds"

urlpatterns = [
    path("", views.home, name="home"),
    path("psicologo/", views.psychologist_dashboard, name="psychologist_dashboard"),
    path("paciente/", views.patient_dashboard, name="patient_dashboard"),
    path("invite/", views.create_invite, name="create_invite"),
    path("enter/", views.enter_invite, name="enter_invite"),
    path("<int:bond_id>/confirm/", views.confirm_bond, name="confirm_bond"),
    path("<int:bond_id>/end/", views.end_bond, name="end_bond"),
]
