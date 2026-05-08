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
    JournalEntryFactory,
    MoodLogFactory,
    PatientProfileFactory,
    PsychologistProfileFactory,
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

    def test_psychologist_blocked_from_mood_list(self, client):
        psych = PsychologistProfileFactory()
        _login(client, psych.user)
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
        assert log.is_shared_with_psychologist is False

    def test_toggle_share_audited(self, client):
        patient = PatientProfileFactory()
        log = MoodLogFactory(patient=patient)
        _login(client, patient.user)
        client.post(reverse("journal:patient_mood_toggle_share", args=[log.id]))
        log.refresh_from_db()
        assert log.is_shared_with_psychologist is True
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
                "is_shared_with_psychologist": "on",
            },
            follow=True,
        )
        assert resp.status_code == 200
        entries = JournalEntry.objects.for_patient(patient)
        assert entries.count() == 1
        e = entries.first()
        assert e.kind == JournalEntryKind.THOUGHT
        assert e.mood is None
        assert e.is_shared_with_psychologist is True

    def test_cannot_edit_others_entry(self, client):
        owner = PatientProfileFactory()
        intruder = PatientProfileFactory()
        entry = JournalEntryFactory(patient=owner)
        _login(client, intruder.user)
        resp = client.get(reverse("journal:patient_journal_edit", args=[entry.id]))
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# ClinicalNote — psicólogo only, visibilidade unilateral
# ---------------------------------------------------------------------------


class TestClinicalNoteViews:
    def test_patient_blocked_from_clinical_note_create(self, client):
        """Paciente NUNCA acessa rotas de ClinicalNote."""
        psych = PsychologistProfileFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, psychologist=psych, patient=patient)
        _login(client, patient.user)
        resp = client.get(reverse("journal:clinical_note_create", args=[patient.id]))
        assert resp.status_code == 404

    def test_psychologist_creates_clinical_note(self, client):
        psych = PsychologistProfileFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, psychologist=psych, patient=patient)
        _login(client, psych.user)

        resp = client.post(
            reverse("journal:clinical_note_create", args=[patient.id]),
            {"content": "Anotação da sessão.", "session_date": ""},
            follow=True,
        )
        assert resp.status_code == 200
        assert ClinicalNote.objects.for_psychologist(psych).count() == 1
        assert AuditLog.objects.filter(action="clinical_note.created").count() == 1

    def test_psychologist_cannot_create_note_for_unbonded_patient(self, client):
        psych = PsychologistProfileFactory()
        unrelated_patient = PatientProfileFactory()
        _login(client, psych.user)
        resp = client.post(
            reverse("journal:clinical_note_create", args=[unrelated_patient.id]),
            {"content": "x"},
        )
        assert resp.status_code == 404
        assert ClinicalNote.objects.count() == 0

    def test_psychologist_cannot_edit_others_note(self, client):
        psych_a = PsychologistProfileFactory()
        psych_b = PsychologistProfileFactory()
        note_b = ClinicalNoteFactory(bond=BondFactory(active=True, psychologist=psych_b))

        _login(client, psych_a.user)
        resp = client.get(reverse("journal:clinical_note_edit", args=[note_b.id]))
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Timeline do psicólogo — combina mood + journal + clinical notes
# ---------------------------------------------------------------------------


class TestPsychologistTimeline:
    def test_timeline_shows_only_shared_and_own_clinical_notes(self, client):
        psych = PsychologistProfileFactory()
        patient = PatientProfileFactory()
        bond = BondFactory(active=True, psychologist=psych, patient=patient)

        # Paciente: 1 shared + 1 privado em cada tipo
        MoodLogFactory(patient=patient, is_shared_with_psychologist=False)
        MoodLogFactory(patient=patient, is_shared_with_psychologist=True)
        JournalEntryFactory(
            patient=patient,
            content="PRIVADO_xyz",
            is_shared_with_psychologist=False,
        )
        JournalEntryFactory(
            patient=patient,
            content="COMPARTILHADO_abc",
            is_shared_with_psychologist=True,
        )

        # ClinicalNote — só do psicólogo logado
        ClinicalNoteFactory(bond=bond, content="MINHA_NOTA_42")
        # Outro psicólogo — nota não deve aparecer aqui
        other_psych = PsychologistProfileFactory()
        ClinicalNoteFactory(
            bond=BondFactory(active=True, psychologist=other_psych, patient=patient),
            content="NOTA_DO_OUTRO_99",
        )

        _login(client, psych.user)
        resp = client.get(
            reverse("journal:psychologist_patient_detail", args=[patient.id])
        )
        assert resp.status_code == 200

        # Privado do paciente não vaza
        assert b"PRIVADO_xyz" not in resp.content
        # Compartilhado aparece
        assert b"COMPARTILHADO_abc" in resp.content
        # Própria nota aparece
        assert b"MINHA_NOTA_42" in resp.content
        # Nota de outro psicólogo nunca vaza
        assert b"NOTA_DO_OUTRO_99" not in resp.content

        # Audit registrado
        assert AuditLog.objects.filter(
            action="patient_timeline.viewed", actor=psych.user
        ).count() == 1

    def test_unbonded_patient_returns_404(self, client):
        psych = PsychologistProfileFactory()
        unrelated = PatientProfileFactory()
        _login(client, psych.user)
        resp = client.get(
            reverse("journal:psychologist_patient_detail", args=[unrelated.id])
        )
        assert resp.status_code == 404
