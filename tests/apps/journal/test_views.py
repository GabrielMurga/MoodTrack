"""Testes de view do journal — auth, role, fail-closed, audit.

Cobre os 3 modelos novos (MoodLog, JournalEntry, ClinicalNote) e
a regra de visibilidade unilateral da ClinicalNote.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.journal.models import (
    ClinicalNote,
    JournalEntry,
    JournalEntryKind,
    MoodLevel,
    MoodLog,
)
from tests.factories import (
    BondFactory,
    ClinicalNoteFactory,
    HealthcareProviderFactory,
    JournalEntryFactory,
    MedicationFactory,
    MoodLogFactory,
    PatientProfileFactory,
    PsychiatristProviderFactory,
)

pytestmark = pytest.mark.django_db


def _login(client, user, password="t3st"):
    user.set_password(password)
    user.save()
    assert client.login(email=user.email, password=password)


# ---------------------------------------------------------------------------
# MoodLog (paciente)
# ---------------------------------------------------------------------------


class TestPatientMoodViews:
    def test_list_requires_login(self, client):
        resp = client.get(reverse("journal:patient_mood_list"))
        assert resp.status_code == 302

    def test_provider_blocked_from_mood_list(self, client):
        provider = HealthcareProviderFactory()
        _login(client, provider.user)
        resp = client.get(reverse("journal:patient_mood_list"))
        assert resp.status_code == 404

    def test_create_mood_log(self, client):
        patient = PatientProfileFactory()
        _login(client, patient.user)
        resp = client.post(
            reverse("journal:patient_mood_create"),
            {"mood": MoodLevel.GOOD},
            follow=True,
        )
        assert resp.status_code == 200
        assert MoodLog.objects.for_patient(patient).count() == 1
        assert AuditLog.objects.filter(action="mood_log.created").count() == 1

    def test_default_create_is_private(self, client):
        patient = PatientProfileFactory()
        _login(client, patient.user)
        client.post(
            reverse("journal:patient_mood_create"),
            {"mood": MoodLevel.NEUTRAL},
        )
        log = MoodLog.objects.for_patient(patient).first()
        assert log.is_shared_with_provider is False

    def test_toggle_share_audited(self, client):
        patient = PatientProfileFactory()
        log = MoodLogFactory(patient=patient)
        _login(client, patient.user)
        client.post(reverse("journal:patient_mood_toggle_share", args=[log.id]))
        log.refresh_from_db()
        assert log.is_shared_with_provider is True
        assert AuditLog.objects.filter(action="mood_log.share_toggled").count() == 1


# ---------------------------------------------------------------------------
# JournalEntry (paciente)
# ---------------------------------------------------------------------------


class TestPatientJournalViews:
    def test_create_entry(self, client):
        patient = PatientProfileFactory()
        _login(client, patient.user)
        resp = client.post(
            reverse("journal:patient_journal_create"),
            {
                "kind": JournalEntryKind.THOUGHT,
                "title": "",
                "content": "Hoje pensei em algo.",
                "mood": "",  # opcional
                "is_shared_with_provider": "on",
            },
            follow=True,
        )
        assert resp.status_code == 200
        entries = JournalEntry.objects.for_patient(patient)
        assert entries.count() == 1
        e = entries.first()
        assert e.kind == JournalEntryKind.THOUGHT
        assert e.mood is None
        assert e.is_shared_with_provider is True

    def test_cannot_edit_others_entry(self, client):
        owner = PatientProfileFactory()
        intruder = PatientProfileFactory()
        entry = JournalEntryFactory(patient=owner)
        _login(client, intruder.user)
        resp = client.get(reverse("journal:patient_journal_edit", args=[entry.id]))
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# ClinicalNote — provider only, visibilidade unilateral
# ---------------------------------------------------------------------------


class TestClinicalNoteViews:
    def test_patient_blocked_from_clinical_note_create(self, client):
        """Paciente NUNCA acessa rotas de ClinicalNote."""
        provider = HealthcareProviderFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider, patient=patient)
        _login(client, patient.user)
        resp = client.get(reverse("journal:clinical_note_create", args=[patient.id]))
        assert resp.status_code == 404

    def test_provider_creates_clinical_note(self, client):
        provider = HealthcareProviderFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider, patient=patient)
        _login(client, provider.user)

        resp = client.post(
            reverse("journal:clinical_note_create", args=[patient.id]),
            {"content": "Anotação da sessão.", "session_date": ""},
            follow=True,
        )
        assert resp.status_code == 200
        assert ClinicalNote.objects.for_provider(provider).count() == 1
        assert AuditLog.objects.filter(action="clinical_note.created").count() == 1

    def test_provider_cannot_create_note_for_unbonded_patient(self, client):
        provider = HealthcareProviderFactory()
        unrelated_patient = PatientProfileFactory()
        _login(client, provider.user)
        resp = client.post(
            reverse("journal:clinical_note_create", args=[unrelated_patient.id]),
            {"content": "x"},
        )
        assert resp.status_code == 404
        assert ClinicalNote.objects.count() == 0

    def test_provider_cannot_edit_others_note(self, client):
        provider_a = HealthcareProviderFactory()
        provider_b = HealthcareProviderFactory()
        note_b = ClinicalNoteFactory(bond=BondFactory(active=True, provider=provider_b))

        _login(client, provider_a.user)
        resp = client.get(reverse("journal:clinical_note_edit", args=[note_b.id]))
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Timeline do profissional — combina mood + journal + clinical notes
# ---------------------------------------------------------------------------


class TestProviderTimeline:
    def test_timeline_shows_only_shared_and_own_clinical_notes(self, client):
        provider = HealthcareProviderFactory()
        patient = PatientProfileFactory()
        bond = BondFactory(active=True, provider=provider, patient=patient)

        # Paciente: 1 shared + 1 privado em cada tipo
        MoodLogFactory(patient=patient, is_shared_with_provider=False)
        MoodLogFactory(patient=patient, is_shared_with_provider=True)
        JournalEntryFactory(
            patient=patient,
            content="PRIVADO_xyz",
            is_shared_with_provider=False,
        )
        JournalEntryFactory(
            patient=patient,
            content="COMPARTILHADO_abc",
            is_shared_with_provider=True,
        )

        # ClinicalNote — só do profissional logado
        ClinicalNoteFactory(bond=bond, content="MINHA_NOTA_42")
        # Outro profissional — nota não deve aparecer aqui
        other_provider = HealthcareProviderFactory()
        ClinicalNoteFactory(
            bond=BondFactory(active=True, provider=other_provider, patient=patient),
            content="NOTA_DO_OUTRO_99",
        )

        _login(client, provider.user)
        resp = client.get(reverse("journal:provider_patient_detail", args=[patient.id]))
        assert resp.status_code == 200

        # Privado do paciente não vaza
        assert b"PRIVADO_xyz" not in resp.content
        # Compartilhado aparece
        assert b"COMPARTILHADO_abc" in resp.content
        # Própria nota aparece
        assert b"MINHA_NOTA_42" in resp.content
        # Nota de outro profissional nunca vaza
        assert b"NOTA_DO_OUTRO_99" not in resp.content

        # Audit registrado
        assert (
            AuditLog.objects.filter(action="patient_timeline.viewed", actor=provider.user).count()
            == 1
        )

    def test_unbonded_patient_returns_404(self, client):
        provider = HealthcareProviderFactory()
        unrelated = PatientProfileFactory()
        _login(client, provider.user)
        resp = client.get(reverse("journal:provider_patient_detail", args=[unrelated.id]))
        assert resp.status_code == 404


class TestProviderSession:
    def test_requires_login(self, client):
        resp = client.get(reverse("journal:provider_session", args=[1]))
        assert resp.status_code == 302

    def test_patient_blocked(self, client):
        patient = PatientProfileFactory()
        _login(client, patient.user)
        resp = client.get(reverse("journal:provider_session", args=[1]))
        assert resp.status_code == 404

    def test_unbonded_provider_gets_404(self, client):
        provider = HealthcareProviderFactory()
        unrelated = PatientProfileFactory()
        _login(client, provider.user)
        resp = client.get(reverse("journal:provider_session", args=[unrelated.id]))
        assert resp.status_code == 404

    def test_psychologist_can_access_session(self, client):
        provider = HealthcareProviderFactory()  # psicólogo (default)
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider, patient=patient)
        _login(client, provider.user)
        resp = client.get(reverse("journal:provider_session", args=[patient.id]))
        assert resp.status_code == 200

    def test_psychiatrist_can_access_session(self, client):
        provider = PsychiatristProviderFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider, patient=patient)
        _login(client, provider.user)
        resp = client.get(reverse("journal:provider_session", args=[patient.id]))
        assert resp.status_code == 200

    def test_session_shows_active_medications(self, client):
        provider = HealthcareProviderFactory()  # psicólogo vê meds prescritas
        psiquiatra = PsychiatristProviderFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider, patient=patient)
        BondFactory(active=True, provider=psiquiatra, patient=patient)
        MedicationFactory(
            patient=patient, prescribed_by=psiquiatra, name="MEDICAMENTO_VISIVEL_777"
        )

        _login(client, provider.user)
        resp = client.get(reverse("journal:provider_session", args=[patient.id]))
        assert resp.status_code == 200
        assert b"MEDICAMENTO_VISIVEL_777" in resp.content

    def test_session_shows_recent_notes(self, client):
        provider = HealthcareProviderFactory()
        patient = PatientProfileFactory()
        bond = BondFactory(active=True, provider=provider, patient=patient)
        ClinicalNoteFactory(bond=bond, content="NOTA_ANTERIOR_555")

        _login(client, provider.user)
        resp = client.get(reverse("journal:provider_session", args=[patient.id]))
        assert resp.status_code == 200
        assert b"NOTA_ANTERIOR_555" in resp.content

    def test_save_note_from_session_view(self, client):
        provider = HealthcareProviderFactory()
        patient = PatientProfileFactory()
        bond = BondFactory(active=True, provider=provider, patient=patient)

        _login(client, provider.user)
        resp = client.post(
            reverse("journal:provider_session", args=[patient.id]),
            {"content": "Conteúdo da sessão de hoje", "session_date": ""},
        )
        assert resp.status_code == 302
        assert ClinicalNote.objects.filter(bond=bond).count() == 1
        assert AuditLog.objects.filter(
            action="clinical_note.created", actor=provider.user
        ).exists()

    def test_session_open_emits_audit(self, client):
        provider = HealthcareProviderFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider, patient=patient)
        _login(client, provider.user)
        client.get(reverse("journal:provider_session", args=[patient.id]))
        assert AuditLog.objects.filter(
            action="provider_session.opened", actor=provider.user
        ).exists()
