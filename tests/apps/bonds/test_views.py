"""Testes de view: login_required, role isolation, fail-closed nas ações."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.bonds.models import Bond, BondStatus
from tests.factories import (
    BondFactory,
    HealthcareProviderFactory,
    PatientProfileFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def _login(client, user, password="t3st"):
    user.set_password(password)
    user.save()
    assert client.login(email=user.email, password=password)


class TestAuthRequired:
    def test_provider_dashboard_redirects_to_login(self, client):
        resp = client.get(reverse("bonds:provider_dashboard"))
        assert resp.status_code == 302
        assert "/login/" in resp.url

    def test_patient_dashboard_redirects_to_login(self, client):
        resp = client.get(reverse("bonds:patient_dashboard"))
        assert resp.status_code == 302

    def test_create_invite_requires_login(self, client):
        resp = client.post(reverse("bonds:create_invite"))
        assert resp.status_code == 302


class TestRoleIsolation:
    def test_patient_cannot_open_provider_dashboard(self, client):
        patient_profile = PatientProfileFactory()
        _login(client, patient_profile.user)
        resp = client.get(reverse("bonds:provider_dashboard"))
        assert resp.status_code == 404

    def test_provider_cannot_open_patient_dashboard(self, client):
        provider = HealthcareProviderFactory()
        _login(client, provider.user)
        resp = client.get(reverse("bonds:patient_dashboard"))
        assert resp.status_code == 404

    def test_user_without_profile_redirected_to_onboarding(self, client):
        user = UserFactory()
        _login(client, user)
        resp = client.get(reverse("bonds:home"), follow=True)
        assert resp.status_code == 200
        # Tela de escolha de perfil (accounts:choose_profile)
        assert b"Sou paciente" in resp.content
        assert b"Sou profissional" in resp.content


class TestProviderFlow:
    def test_create_invite(self, client):
        provider = HealthcareProviderFactory()
        _login(client, provider.user)

        resp = client.post(reverse("bonds:create_invite"), follow=True)
        assert resp.status_code == 200

        bonds = Bond.objects.for_provider(provider)
        assert bonds.count() == 1
        assert bonds.first().status == BondStatus.INVITED

    def test_create_invite_with_label(self, client):
        """Profissional pode rotular o convite pra lembrar quem é o destinatário."""
        provider = HealthcareProviderFactory()
        _login(client, provider.user)

        resp = client.post(
            reverse("bonds:create_invite"),
            {"invitee_label": "João Silva"},
            follow=True,
        )
        assert resp.status_code == 200

        bond = Bond.objects.for_provider(provider).first()
        assert bond.invitee_label == "João Silva"
        # Label aparece na mensagem de sucesso e no dashboard
        assert b"Jo\xc3\xa3o Silva" in resp.content

    def test_create_invite_label_is_optional(self, client):
        provider = HealthcareProviderFactory()
        _login(client, provider.user)

        client.post(reverse("bonds:create_invite"), {"invitee_label": ""})
        bond = Bond.objects.for_provider(provider).first()
        assert bond is not None
        assert bond.invitee_label == ""

    def test_dashboard_shows_invitee_label_on_pending_bond(self, client):
        """Antes do paciente aceitar, o label é o único identificador do convite."""
        provider = HealthcareProviderFactory()
        BondFactory(provider=provider, invitee_label="Maria - nova consulta")
        _login(client, provider.user)

        resp = client.get(reverse("bonds:provider_dashboard"))
        assert resp.status_code == 200
        assert b"Maria - nova consulta" in resp.content

    def test_provider_cannot_confirm_others_bond(self, client):
        """Fail-closed: profissional A tentando confirmar bond do profissional B → 404."""
        provider_a = HealthcareProviderFactory()
        provider_b = HealthcareProviderFactory()
        bond_b = BondFactory(pending=True, provider=provider_b)

        _login(client, provider_a.user)
        resp = client.post(reverse("bonds:confirm_bond", args=[bond_b.id]))
        assert resp.status_code == 404

        bond_b.refresh_from_db()
        assert bond_b.status == BondStatus.PENDING_CONFIRMATION  # não mudou

    def test_provider_can_confirm_own_pending_bond(self, client):
        provider = HealthcareProviderFactory()
        bond = BondFactory(pending=True, provider=provider)

        _login(client, provider.user)
        resp = client.post(reverse("bonds:confirm_bond", args=[bond.id]), follow=True)
        assert resp.status_code == 200

        bond.refresh_from_db()
        assert bond.status == BondStatus.ACTIVE


class TestPatientFlow:
    def test_patient_enters_invite_code(self, client):
        provider = HealthcareProviderFactory()
        bond = BondFactory(provider=provider)
        patient = PatientProfileFactory()

        _login(client, patient.user)
        resp = client.post(
            reverse("bonds:enter_invite"),
            {"invite_code": bond.invite_code},
            follow=True,
        )
        assert resp.status_code == 200

        bond.refresh_from_db()
        assert bond.status == BondStatus.PENDING_CONFIRMATION
        assert bond.patient == patient

    def test_patient_with_existing_alive_bond_blocked(self, client):
        patient = PatientProfileFactory()
        BondFactory(active=True, patient=patient)

        new_provider = HealthcareProviderFactory()
        new_bond = BondFactory(provider=new_provider)

        _login(client, patient.user)
        resp = client.post(
            reverse("bonds:enter_invite"),
            {"invite_code": new_bond.invite_code},
            follow=True,
        )
        assert resp.status_code == 200
        new_bond.refresh_from_db()
        assert new_bond.status == BondStatus.INVITED  # não mudou

    def test_invalid_invite_code_returns_form_error(self, client):
        patient = PatientProfileFactory()
        _login(client, patient.user)
        resp = client.post(
            reverse("bonds:enter_invite"),
            {"invite_code": "ZZZZZZZZ"},
        )
        assert resp.status_code == 200
        assert b"n\xc3\xa3o encontrado" in resp.content.lower() or b"encontrado" in resp.content

    def test_dual_user_cannot_accept_own_invite(self, client):
        """User com ambos perfis não pode usar próprio código."""
        user = UserFactory()
        provider = HealthcareProviderFactory(user=user)
        PatientProfileFactory(user=user)
        own_bond = BondFactory(provider=provider)

        _login(client, user)
        resp = client.post(
            reverse("bonds:enter_invite"),
            {"invite_code": own_bond.invite_code},
            follow=True,
        )
        assert resp.status_code == 200
        own_bond.refresh_from_db()
        assert own_bond.status == BondStatus.INVITED  # não mudou
        assert own_bond.patient is None
        # Mensagem de erro chegou ao usuário.
        assert b"pr\xc3\xb3prio c\xc3\xb3digo" in resp.content


class TestEndBond:
    def test_either_side_can_end_their_bond(self, client):
        provider = HealthcareProviderFactory()
        patient = PatientProfileFactory()
        bond = BondFactory(active=True, provider=provider, patient=patient)

        _login(client, patient.user)
        resp = client.post(reverse("bonds:end_bond", args=[bond.id]), follow=True)
        assert resp.status_code == 200
        bond.refresh_from_db()
        assert bond.status == BondStatus.ENDED
        assert bond.ended_by == patient.user

    def test_unrelated_user_cannot_end_bond(self, client):
        bond = BondFactory(active=True)
        outsider = UserFactory()
        _login(client, outsider)
        resp = client.post(reverse("bonds:end_bond", args=[bond.id]))
        assert resp.status_code == 404
        bond.refresh_from_db()
        assert bond.status == BondStatus.ACTIVE
