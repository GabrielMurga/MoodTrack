"""Testes de view: login_required, role isolation, fail-closed nas ações."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.bonds.models import Bond, BondStatus
from tests.factories import (
    BondFactory,
    PatientProfileFactory,
    PsychologistProfileFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def _login(client, user, password="t3st"):
    user.set_password(password)
    user.save()
    assert client.login(email=user.email, password=password)


class TestAuthRequired:
    def test_psychologist_dashboard_redirects_to_login(self, client):
        resp = client.get(reverse("bonds:psychologist_dashboard"))
        assert resp.status_code == 302
        assert "/login/" in resp.url

    def test_patient_dashboard_redirects_to_login(self, client):
        resp = client.get(reverse("bonds:patient_dashboard"))
        assert resp.status_code == 302

    def test_create_invite_requires_login(self, client):
        resp = client.post(reverse("bonds:create_invite"))
        assert resp.status_code == 302


class TestRoleIsolation:
    def test_patient_cannot_open_psychologist_dashboard(self, client):
        patient_profile = PatientProfileFactory()
        _login(client, patient_profile.user)
        resp = client.get(reverse("bonds:psychologist_dashboard"))
        assert resp.status_code == 404

    def test_psychologist_cannot_open_patient_dashboard(self, client):
        psych_profile = PsychologistProfileFactory()
        _login(client, psych_profile.user)
        resp = client.get(reverse("bonds:patient_dashboard"))
        assert resp.status_code == 404

    def test_user_without_profile_lands_on_no_profile(self, client):
        user = UserFactory()
        _login(client, user)
        resp = client.get(reverse("bonds:home"), follow=True)
        assert resp.status_code == 200
        assert b"perfil" in resp.content.lower()


class TestPsychologistFlow:
    def test_create_invite(self, client):
        psych_profile = PsychologistProfileFactory()
        _login(client, psych_profile.user)

        resp = client.post(reverse("bonds:create_invite"), follow=True)
        assert resp.status_code == 200

        bonds = Bond.objects.for_psychologist(psych_profile)
        assert bonds.count() == 1
        assert bonds.first().status == BondStatus.INVITED

    def test_psychologist_cannot_confirm_others_bond(self, client):
        """Fail-closed: psicólogo A tentando confirmar bond do psicólogo B → 404."""
        psych_a = PsychologistProfileFactory()
        psych_b = PsychologistProfileFactory()
        bond_b = BondFactory(pending=True, psychologist=psych_b)

        _login(client, psych_a.user)
        resp = client.post(reverse("bonds:confirm_bond", args=[bond_b.id]))
        assert resp.status_code == 404

        bond_b.refresh_from_db()
        assert bond_b.status == BondStatus.PENDING_CONFIRMATION  # não mudou

    def test_psychologist_can_confirm_own_pending_bond(self, client):
        psych = PsychologistProfileFactory()
        bond = BondFactory(pending=True, psychologist=psych)

        _login(client, psych.user)
        resp = client.post(reverse("bonds:confirm_bond", args=[bond.id]), follow=True)
        assert resp.status_code == 200

        bond.refresh_from_db()
        assert bond.status == BondStatus.ACTIVE


class TestPatientFlow:
    def test_patient_enters_invite_code(self, client):
        psych = PsychologistProfileFactory()
        bond = BondFactory(psychologist=psych)
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

        new_psych = PsychologistProfileFactory()
        new_bond = BondFactory(psychologist=new_psych)

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
        psych = PsychologistProfileFactory(user=user)
        PatientProfileFactory(user=user)
        own_bond = BondFactory(psychologist=psych)

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
        psych = PsychologistProfileFactory()
        patient = PatientProfileFactory()
        bond = BondFactory(active=True, psychologist=psych, patient=patient)

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
