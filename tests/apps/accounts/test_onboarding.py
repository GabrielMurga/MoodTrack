"""Testes do onboarding — escolha + criação de perfil (psicólogo, psiquiatra, paciente)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import HealthcareProvider, PatientProfile, ProviderKind, ProviderPlan
from apps.audit.models import AuditLog
from tests.factories import (
    HealthcareProviderFactory,
    PatientProfileFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def _login(client, user, password="t3st"):
    user.set_password(password)
    user.save()
    assert client.login(email=user.email, password=password)


class TestChooseProfile:
    def test_requires_login(self, client):
        resp = client.get(reverse("accounts:choose_profile"))
        assert resp.status_code == 302

    def test_user_without_profile_sees_choices(self, client):
        user = UserFactory()
        _login(client, user)
        resp = client.get(reverse("accounts:choose_profile"))
        assert resp.status_code == 200
        assert b"Sou paciente" in resp.content
        assert b"Sou profissional" in resp.content

    def test_user_with_provider_profile_redirected_home(self, client):
        provider = HealthcareProviderFactory()
        _login(client, provider.user)
        resp = client.get(reverse("accounts:choose_profile"))
        assert resp.status_code == 302

    def test_user_with_patient_profile_redirected_home(self, client):
        patient = PatientProfileFactory()
        _login(client, patient.user)
        resp = client.get(reverse("accounts:choose_profile"))
        assert resp.status_code == 302


class TestCreateProviderProfile:
    def test_psychologist_happy_path(self, client):
        user = UserFactory()
        _login(client, user)
        resp = client.post(
            reverse("accounts:create_provider_profile"),
            {
                "kind": ProviderKind.PSYCHOLOGIST,
                "crp_number": "06/12345",
                "crm_number": "",
                "bio": "Psicóloga clínica.",
            },
            follow=True,
        )
        assert resp.status_code == 200
        provider = HealthcareProvider.objects.get(user=user)
        assert provider.kind == ProviderKind.PSYCHOLOGIST
        assert provider.crp_number == "06/12345"
        assert provider.crm_number == ""
        # Default sempre nasce em Básico (ADR 0010).
        assert provider.plan == ProviderPlan.BASIC
        # Audit logado.
        assert AuditLog.objects.filter(action="provider_profile.created").count() == 1

    def test_psychiatrist_happy_path(self, client):
        user = UserFactory()
        _login(client, user)
        resp = client.post(
            reverse("accounts:create_provider_profile"),
            {
                "kind": ProviderKind.PSYCHIATRIST,
                "crp_number": "",
                "crm_number": "SP/54321",
                "bio": "Psiquiatra clínico.",
            },
            follow=True,
        )
        assert resp.status_code == 200
        provider = HealthcareProvider.objects.get(user=user)
        assert provider.kind == ProviderKind.PSYCHIATRIST
        assert provider.crm_number == "SP/54321"
        assert provider.can_prescribe is True

    def test_psychologist_without_crp_rejected(self, client):
        user = UserFactory()
        _login(client, user)
        resp = client.post(
            reverse("accounts:create_provider_profile"),
            {
                "kind": ProviderKind.PSYCHOLOGIST,
                "crp_number": "",
                "crm_number": "",
                "bio": "",
            },
        )
        assert resp.status_code == 200  # form re-render
        assert HealthcareProvider.objects.count() == 0
        assert b"obrigat" in resp.content.lower()

    def test_psychiatrist_without_crm_rejected(self, client):
        user = UserFactory()
        _login(client, user)
        resp = client.post(
            reverse("accounts:create_provider_profile"),
            {
                "kind": ProviderKind.PSYCHIATRIST,
                "crp_number": "",
                "crm_number": "",
                "bio": "",
            },
        )
        assert resp.status_code == 200
        assert HealthcareProvider.objects.count() == 0

    def test_psychologist_with_crm_rejected(self, client):
        """Mistura inválida — psicólogo não pode ter CRM."""
        user = UserFactory()
        _login(client, user)
        resp = client.post(
            reverse("accounts:create_provider_profile"),
            {
                "kind": ProviderKind.PSYCHOLOGIST,
                "crp_number": "06/12345",
                "crm_number": "SP/9999",
                "bio": "",
            },
        )
        assert resp.status_code == 200
        assert HealthcareProvider.objects.count() == 0

    def test_existing_provider_redirected_to_dashboard(self, client):
        provider = HealthcareProviderFactory()
        _login(client, provider.user)
        resp = client.get(reverse("accounts:create_provider_profile"))
        assert resp.status_code == 302
        # Não cria duplicado.
        assert HealthcareProvider.objects.filter(user=provider.user).count() == 1


class TestCreatePatientProfile:
    def test_happy_path(self, client):
        user = UserFactory()
        _login(client, user)
        resp = client.post(
            reverse("accounts:create_patient_profile"),
            {"preferred_name": "Bruno", "birth_date": ""},
            follow=True,
        )
        assert resp.status_code == 200
        profile = PatientProfile.objects.get(user=user)
        assert profile.preferred_name == "Bruno"
        assert AuditLog.objects.filter(action="patient_profile.created").count() == 1

    def test_existing_patient_redirected_to_dashboard(self, client):
        patient = PatientProfileFactory()
        _login(client, patient.user)
        resp = client.get(reverse("accounts:create_patient_profile"))
        assert resp.status_code == 302
        assert PatientProfile.objects.filter(user=patient.user).count() == 1


class TestDualProfile:
    def test_user_can_have_both_profiles(self, client):
        """Profissional que também faz terapia: cria provider, depois patient."""
        user = UserFactory()
        _login(client, user)

        # Cria provider
        client.post(
            reverse("accounts:create_provider_profile"),
            {
                "kind": ProviderKind.PSYCHOLOGIST,
                "crp_number": "06/99999",
                "crm_number": "",
                "bio": "",
            },
        )
        assert HealthcareProvider.objects.filter(user=user).exists()

        # Cria patient — não deve ser bloqueado mesmo com provider já existente.
        client.post(
            reverse("accounts:create_patient_profile"),
            {"preferred_name": "Eu mesma", "birth_date": ""},
        )
        assert PatientProfile.objects.filter(user=user).exists()
