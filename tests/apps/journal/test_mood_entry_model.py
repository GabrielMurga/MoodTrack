"""Testes do MoodEntry — encryption, defaults, queryset isolation."""

from __future__ import annotations

import pytest
from django.db import connection

from apps.bonds.models import Bond, BondStatus
from apps.journal.models import MoodEntry, MoodLevel
from tests.factories import (
    BondFactory,
    PatientProfileFactory,
    PsychologistProfileFactory,
)

pytestmark = pytest.mark.django_db


class TestMoodEntryDefaults:
    def test_default_visibility_is_private(self):
        """CLAUDE.md regra 3: default is_shared_with_psychologist=False."""
        entry = MoodEntry.objects.create(
            patient=PatientProfileFactory(),
            mood=MoodLevel.NEUTRAL,
        )
        assert entry.is_shared_with_psychologist is False

    def test_content_can_be_blank(self):
        """Paciente pode registrar só o nível de humor sem texto."""
        entry = MoodEntry.objects.create(
            patient=PatientProfileFactory(),
            mood=MoodLevel.GOOD,
            content="",
        )
        assert entry.content == ""


class TestEncryption:
    def test_content_stored_encrypted_in_db(self):
        """Conteúdo no DB raw NÃO contém o texto original em plaintext."""
        secret_text = "Estou pensando em algo muito específico hoje xyzABC123"
        entry = MoodEntry.objects.create(
            patient=PatientProfileFactory(),
            mood=MoodLevel.SAD,
            content=secret_text,
        )

        with connection.cursor() as cur:
            cur.execute(
                "SELECT content FROM journal_moodentry WHERE id = %s",
                [entry.pk],
            )
            raw_value = cur.fetchone()[0]

        # raw_value deve ser bytes/string criptografada — não deve conter o
        # texto original em nenhuma forma reconhecível.
        raw_str = bytes(raw_value).decode("utf-8", errors="replace") if isinstance(raw_value, memoryview | bytes) else str(raw_value)
        assert "xyzABC123" not in raw_str
        assert "específico" not in raw_str

    def test_content_decrypts_transparently_on_read(self):
        secret_text = "Texto sensível do paciente."
        entry = MoodEntry.objects.create(
            patient=PatientProfileFactory(),
            mood=MoodLevel.NEUTRAL,
            content=secret_text,
        )
        # Recarrega do DB pra forçar decrypt.
        reloaded = MoodEntry.objects.get(pk=entry.pk)
        assert reloaded.content == secret_text


class TestQuerysetIsolation:
    def test_for_patient_filters_to_owner(self):
        a = PatientProfileFactory()
        b = PatientProfileFactory()
        MoodEntry.objects.create(patient=a, mood=MoodLevel.GOOD)
        MoodEntry.objects.create(patient=b, mood=MoodLevel.SAD)

        assert MoodEntry.objects.for_patient(a).count() == 1
        assert MoodEntry.objects.for_patient(a).first().mood == MoodLevel.GOOD

    def test_shared_with_psychologist_requires_active_bond_AND_share_flag(self):
        """Filtro duplo: bond ATIVO E flag de share ambos têm que ser True."""
        psych = PsychologistProfileFactory()
        patient = PatientProfileFactory()
        # bond ativo
        BondFactory(active=True, psychologist=psych, patient=patient)

        # 4 entries com combinações de shared/not shared
        e_priv = MoodEntry.objects.create(patient=patient, mood=MoodLevel.SAD)
        e_shared = MoodEntry.objects.create(
            patient=patient, mood=MoodLevel.GOOD, is_shared_with_psychologist=True
        )

        # Outra paciente, com bond ativo, mas com OUTRO psicólogo.
        other_psych = PsychologistProfileFactory()
        other_patient = PatientProfileFactory()
        BondFactory(active=True, psychologist=other_psych, patient=other_patient)
        MoodEntry.objects.create(
            patient=other_patient,
            mood=MoodLevel.GREAT,
            is_shared_with_psychologist=True,
        )

        visible = MoodEntry.objects.shared_with_psychologist(psych)
        assert visible.count() == 1
        assert visible.first().pk == e_shared.pk
        # Privada e do outro psicólogo NÃO aparecem.
        assert not visible.filter(pk=e_priv.pk).exists()

    def test_shared_with_psychologist_excludes_pending_bond(self):
        """Bond PENDING (não ACTIVE) → entries não aparecem mesmo se shared."""
        psych = PsychologistProfileFactory()
        patient = PatientProfileFactory()
        Bond.objects.create(
            psychologist=psych, patient=patient, status=BondStatus.PENDING_CONFIRMATION
        )
        MoodEntry.objects.create(
            patient=patient, mood=MoodLevel.GOOD, is_shared_with_psychologist=True
        )

        assert MoodEntry.objects.shared_with_psychologist(psych).count() == 0

    def test_shared_with_psychologist_excludes_ended_bond(self):
        """Bond ENDED → entries antigas não vazam pro psicólogo."""
        psych = PsychologistProfileFactory()
        patient = PatientProfileFactory()
        Bond.objects.create(
            psychologist=psych, patient=patient, status=BondStatus.ENDED
        )
        MoodEntry.objects.create(
            patient=patient, mood=MoodLevel.GOOD, is_shared_with_psychologist=True
        )

        assert MoodEntry.objects.shared_with_psychologist(psych).count() == 0
