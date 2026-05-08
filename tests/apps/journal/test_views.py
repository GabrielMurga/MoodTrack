"""Testes de view do journal — auth, role, fail-closed, audit."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.journal.models import MoodEntry, MoodLevel
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


class TestPatientJournalAuth:
    def test_list_requires_login(self, client):
        resp = client.get(reverse("journal:patient_list"))
        assert resp.status_code == 302

    def test_psychologist_blocked_from_patient_list(self, client):
        psych = PsychologistProfileFactory()
        _login(client, psych.user)
        resp = client.get(reverse("journal:patient_list"))
        assert resp.status_code == 404


class TestPatientJournalCRUD:
    def test_patient_creates_entry(self, client):
        patient = PatientProfileFactory()
        _login(client, patient.user)

        resp = client.post(
            reverse("journal:patient_create"),
            {
                "mood": MoodLevel.GOOD,
                "content": "Hoje foi um dia tranquilo.",
                "is_shared_with_psychologist": "on",
            },
            follow=True,
        )
        assert resp.status_code == 200
        entries = MoodEntry.objects.for_patient(patient)
        assert entries.count() == 1
        assert entries.first().is_shared_with_psychologist is True

        # Audit registrado
        assert AuditLog.objects.filter(action="mood_entry.created").count() == 1

    def test_patient_default_create_is_private(self, client):
        """Sem checkbox de share, entry nasce privada."""
        patient = PatientProfileFactory()
        _login(client, patient.user)
        client.post(
            reverse("journal:patient_create"),
            {"mood": MoodLevel.NEUTRAL, "content": ""},
        )
        entry = MoodEntry.objects.for_patient(patient).first()
        assert entry.is_shared_with_psychologist is False

    def test_patient_cannot_edit_others_entry(self, client):
        owner = PatientProfileFactory()
        intruder = PatientProfileFactory()
        entry = MoodEntry.objects.create(patient=owner, mood=MoodLevel.SAD)

        _login(client, intruder.user)
        resp = client.get(reverse("journal:patient_edit", args=[entry.id]))
        assert resp.status_code == 404

    def test_toggle_share_flips_and_audits(self, client):
        patient = PatientProfileFactory()
        entry = MoodEntry.objects.create(patient=patient, mood=MoodLevel.GOOD)
        assert entry.is_shared_with_psychologist is False

        _login(client, patient.user)
        client.post(reverse("journal:patient_toggle_share", args=[entry.id]))
        entry.refresh_from_db()
        assert entry.is_shared_with_psychologist is True
        assert AuditLog.objects.filter(action="mood_entry.share_toggled").count() == 1


class TestPsychologistView:
    def test_patient_blocked_from_psychologist_views(self, client):
        patient = PatientProfileFactory()
        _login(client, patient.user)
        resp = client.get(reverse("journal:psychologist_patients"))
        assert resp.status_code == 404

    def test_psychologist_sees_only_active_bonded_patients(self, client):
        psych = PsychologistProfileFactory()
        active_patient = PatientProfileFactory()
        ended_patient = PatientProfileFactory()
        BondFactory(active=True, psychologist=psych, patient=active_patient)
        BondFactory(ended=True, psychologist=psych, patient=ended_patient)

        _login(client, psych.user)
        resp = client.get(reverse("journal:psychologist_patients"))
        assert resp.status_code == 200
        # Active sim, ended não.
        assert active_patient.user.email.encode() in resp.content
        assert ended_patient.user.email.encode() not in resp.content

    def test_private_entry_never_visible_in_timeline(self, client):
        """Cenário crítico: entry privada NUNCA aparece pro psicólogo."""
        psych = PsychologistProfileFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, psychologist=psych, patient=patient)

        secret = "TEXTO_SECRETO_DO_PACIENTE_42"
        MoodEntry.objects.create(
            patient=patient,
            mood=MoodLevel.SAD,
            content=secret,
            is_shared_with_psychologist=False,
        )

        _login(client, psych.user)
        resp = client.get(
            reverse("journal:psychologist_patient_detail", args=[patient.id])
        )
        assert resp.status_code == 200
        assert secret.encode() not in resp.content

    def test_shared_entry_visible_in_timeline_and_audited(self, client):
        psych = PsychologistProfileFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, psychologist=psych, patient=patient)
        MoodEntry.objects.create(
            patient=patient,
            mood=MoodLevel.GOOD,
            content="Texto compartilhado.",
            is_shared_with_psychologist=True,
        )

        _login(client, psych.user)
        resp = client.get(
            reverse("journal:psychologist_patient_detail", args=[patient.id])
        )
        assert resp.status_code == 200
        assert b"compartilhado" in resp.content.lower()

        # Acesso à timeline foi auditado (regra 8).
        assert AuditLog.objects.filter(
            actor=psych.user,
            action="patient_timeline.viewed",
        ).count() == 1

    def test_psychologist_cannot_view_unbonded_patient_timeline(self, client):
        """Acesso direto via URL a paciente sem bond ativo → 404."""
        psych = PsychologistProfileFactory()
        other_patient = PatientProfileFactory()  # sem bond com psych
        MoodEntry.objects.create(
            patient=other_patient,
            mood=MoodLevel.GREAT,
            is_shared_with_psychologist=True,
        )

        _login(client, psych.user)
        resp = client.get(
            reverse("journal:psychologist_patient_detail", args=[other_patient.id])
        )
        assert resp.status_code == 404


class TestBondAuditInstrumentation:
    def test_bond_confirm_creates_audit(self, client):
        psych = PsychologistProfileFactory()
        bond = BondFactory(pending=True, psychologist=psych)

        bond.confirm()
        assert AuditLog.objects.filter(action="bond.confirmed").count() == 1

    def test_bond_accept_invite_creates_audit(self):
        bond = BondFactory()
        patient = PatientProfileFactory()
        bond.accept_invite(patient)

        assert AuditLog.objects.filter(action="bond.invite_accepted").count() == 1

    def test_bond_end_creates_audit(self):
        bond = BondFactory(active=True)
        user = UserFactory()
        bond.end(by_user=user)

        assert AuditLog.objects.filter(action="bond.ended").count() == 1
