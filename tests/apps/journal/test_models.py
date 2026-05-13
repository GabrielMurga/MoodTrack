"""Testes dos 3 modelos do journal: MoodLog, JournalEntry, ClinicalNote.

Cobre:
- Defaults (privado por default em registros do paciente)
- Criptografia de campos textuais
- Querysets fail-closed
- Visibilidade unilateral da ClinicalNote (paciente nunca vê)
"""

from __future__ import annotations

import pytest
from django.db import connection

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
    MoodLogFactory,
    PatientProfileFactory,
)

pytestmark = pytest.mark.django_db


# ===========================================================================
# MoodLog
# ===========================================================================


class TestMoodLog:
    def test_default_visibility_is_private(self):
        log = MoodLog.objects.create(patient=PatientProfileFactory(), mood=MoodLevel.NEUTRAL)
        assert log.is_shared_with_provider is False

    def test_for_patient_filters_owner(self):
        a = PatientProfileFactory()
        b = PatientProfileFactory()
        MoodLogFactory(patient=a)
        MoodLogFactory(patient=b)

        assert MoodLog.objects.for_patient(a).count() == 1

    def test_shared_with_provider_double_filter(self):
        provider = HealthcareProviderFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider, patient=patient)

        MoodLogFactory(patient=patient, is_shared_with_provider=False)
        shared = MoodLogFactory(patient=patient, is_shared_with_provider=True)

        visible = MoodLog.objects.shared_with_provider(provider)
        assert visible.count() == 1
        assert visible.first().pk == shared.pk

    def test_shared_with_provider_excludes_inactive_bond(self):
        provider = HealthcareProviderFactory()
        patient = PatientProfileFactory()
        BondFactory(ended=True, provider=provider, patient=patient)
        MoodLogFactory(patient=patient, is_shared_with_provider=True)

        assert MoodLog.objects.shared_with_provider(provider).count() == 0


# ===========================================================================
# JournalEntry
# ===========================================================================


class TestJournalEntry:
    def test_default_visibility_is_private(self):
        entry = JournalEntry.objects.create(
            patient=PatientProfileFactory(),
            kind=JournalEntryKind.SITUATION,
            content="qualquer",
        )
        assert entry.is_shared_with_provider is False
        assert entry.mood is None

    def test_mood_optional(self):
        entry = JournalEntryFactory()
        assert entry.mood is None

    def test_mood_can_be_set(self):
        entry = JournalEntryFactory(mood=MoodLevel.GOOD)
        assert entry.mood == MoodLevel.GOOD

    def test_content_encrypted_in_db(self):
        secret = "TEXTO_SECRETO_xyzABC987"
        entry = JournalEntryFactory(content=secret)

        with connection.cursor() as cur:
            cur.execute(
                "SELECT content FROM journal_journalentry WHERE id = %s",
                [entry.pk],
            )
            raw = cur.fetchone()[0]

        raw_str = (
            bytes(raw).decode("utf-8", errors="replace")
            if isinstance(raw, memoryview | bytes)
            else str(raw)
        )
        assert "xyzABC987" not in raw_str

    def test_content_decrypts_on_read(self):
        secret = "Algo bem específico que escrevi."
        entry = JournalEntryFactory(content=secret)
        reloaded = JournalEntry.objects.get(pk=entry.pk)
        assert reloaded.content == secret

    def test_shared_with_provider_filters_correctly(self):
        provider = HealthcareProviderFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider, patient=patient)

        JournalEntryFactory(patient=patient, is_shared_with_provider=False)
        shared = JournalEntryFactory(patient=patient, is_shared_with_provider=True)

        visible = JournalEntry.objects.shared_with_provider(provider)
        assert visible.count() == 1
        assert visible.first().pk == shared.pk


# ===========================================================================
# ClinicalNote — visibilidade unilateral (profissional só)
# ===========================================================================


class TestClinicalNote:
    def test_for_provider_returns_only_own_notes(self):
        provider_a = HealthcareProviderFactory()
        provider_b = HealthcareProviderFactory()
        bond_a = BondFactory(active=True, provider=provider_a)
        bond_b = BondFactory(active=True, provider=provider_b)

        own = ClinicalNoteFactory(bond=bond_a)
        ClinicalNoteFactory(bond=bond_b)

        notes = ClinicalNote.objects.for_provider(provider_a)
        assert notes.count() == 1
        assert notes.first().pk == own.pk

    def test_content_encrypted_in_db(self):
        secret = "HIPOTESE_DIAGNOSTICA_SENSIVEL_999"
        note = ClinicalNoteFactory(content=secret)

        with connection.cursor() as cur:
            cur.execute(
                "SELECT content FROM journal_clinicalnote WHERE id = %s",
                [note.pk],
            )
            raw = cur.fetchone()[0]

        raw_str = (
            bytes(raw).decode("utf-8", errors="replace")
            if isinstance(raw, memoryview | bytes)
            else str(raw)
        )
        assert "999" not in raw_str

    def test_clinical_note_does_not_leak_via_journal_querysets(self):
        """ClinicalNote NÃO é JournalEntry — não vaza por nenhum queryset
        de patient-side. Mais um teste de regressão estrutural que de lógica.
        """
        bond = BondFactory(active=True)
        ClinicalNoteFactory(bond=bond)
        # JournalEntry e MoodLog não devem encontrar nada do paciente.
        assert JournalEntry.objects.for_patient(bond.patient).count() == 0
        assert MoodLog.objects.for_patient(bond.patient).count() == 0
