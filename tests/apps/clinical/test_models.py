"""Testes dos modelos do prontuário clínico:
PatientOverview, Medication, PatientReportedMedication.

Cobre:
- Criptografia em DB
- Querysets fail-closed (visible_to_provider)
- Validação fail-closed: psicólogo não prescreve (regra 5)
- Auto-reporte separado da prescrição
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db import connection

from apps.clinical.models import Medication, PatientOverview, PatientReportedMedication
from tests.factories import (
    BondFactory,
    HealthcareProviderFactory,
    MedicationFactory,
    PatientOverviewFactory,
    PatientProfileFactory,
    PatientReportedMedicationFactory,
    PsychiatristProviderFactory,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# PatientOverview
# ---------------------------------------------------------------------------


class TestPatientOverview:
    def test_summary_encrypted_in_db(self):
        secret = "RESUMO_CONFIDENCIAL_ABC123"
        overview = PatientOverviewFactory(summary=secret)

        with connection.cursor() as cur:
            cur.execute(
                "SELECT summary FROM clinical_patientoverview WHERE id = %s",
                [overview.pk],
            )
            raw = cur.fetchone()[0]
        raw_str = (
            bytes(raw).decode("utf-8", errors="replace")
            if isinstance(raw, memoryview | bytes)
            else str(raw)
        )
        assert "ABC123" not in raw_str

    def test_one_overview_per_patient(self):
        overview = PatientOverviewFactory()
        with pytest.raises(Exception):  # IntegrityError ou similar
            PatientOverview.objects.create(patient=overview.patient, summary="dup")

    def test_visible_only_to_bonded_provider(self):
        provider_a = HealthcareProviderFactory()
        provider_b = HealthcareProviderFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider_a, patient=patient)

        PatientOverviewFactory(patient=patient)
        # Outro paciente não-vinculado a A
        PatientOverviewFactory()

        # A vê 1, B vê 0.
        assert PatientOverview.objects.for_provider(provider_a).count() == 1
        assert PatientOverview.objects.for_provider(provider_b).count() == 0


# ---------------------------------------------------------------------------
# Medication — fail-closed: só psiquiatra prescreve
# ---------------------------------------------------------------------------


class TestMedicationFailClosed:
    def test_psychiatrist_can_prescribe(self):
        psy = PsychiatristProviderFactory()
        med = MedicationFactory(prescribed_by=psy)
        assert med.pk is not None
        assert med.prescribed_by.can_prescribe is True

    def test_psychologist_cannot_prescribe_via_full_clean(self):
        psicologo = HealthcareProviderFactory()  # default kind=psychologist
        patient = PatientProfileFactory()
        with pytest.raises(ValidationError):
            Medication.objects.create(
                patient=patient,
                prescribed_by=psicologo,
                name="Sertralina",
                dosage="50mg",
                frequency="1x ao dia",
            )

    def test_psychologist_cannot_prescribe_via_save(self):
        """save() chama full_clean() — bloqueia mesmo sem passar por form."""
        psicologo = HealthcareProviderFactory()
        patient = PatientProfileFactory()
        med = Medication(
            patient=patient,
            prescribed_by=psicologo,
            name="X",
            dosage="",
            frequency="",
        )
        with pytest.raises(ValidationError):
            med.save()


class TestMedicationContent:
    def test_name_encrypted_in_db(self):
        med = MedicationFactory(name="SECRETO_FARM_999")
        with connection.cursor() as cur:
            cur.execute(
                "SELECT name FROM clinical_medication WHERE id = %s",
                [med.pk],
            )
            raw = cur.fetchone()[0]
        raw_str = (
            bytes(raw).decode("utf-8", errors="replace")
            if isinstance(raw, memoryview | bytes)
            else str(raw)
        )
        assert "999" not in raw_str

    def test_active_filter(self):
        active = MedicationFactory(ended_at=None)
        from datetime import date

        ended = MedicationFactory(ended_at=date(2026, 1, 1))
        assert active.is_active is True
        assert ended.is_active is False
        assert Medication.objects.active().count() == 1


class TestMedicationVisibility:
    def test_psychologist_can_see_medications_of_bonded_patient(self):
        """Psicólogo vê medicação prescrita por psiquiatra de paciente que está vinculado a ele.

        Caso real: paciente tem psiquiatra (que prescreve) e psicólogo
        (que faz acompanhamento). O psicólogo precisa ver o que está sendo
        prescrito porque humor/sono/energia podem ter causa farmacológica.
        """
        psicologo = HealthcareProviderFactory()
        psiquiatra = PsychiatristProviderFactory()
        patient = PatientProfileFactory()

        BondFactory(active=True, provider=psicologo, patient=patient)
        # Bond do psiquiatra com mesmo paciente (sem violar unique_alive_bond_per_pair —
        # constraint é por par, não global).
        BondFactory(active=True, provider=psiquiatra, patient=patient)

        MedicationFactory(patient=patient, prescribed_by=psiquiatra)

        assert Medication.objects.visible_to_provider(psicologo).count() == 1
        assert Medication.objects.visible_to_provider(psiquiatra).count() == 1

    def test_unbonded_provider_sees_nothing(self):
        outsider = HealthcareProviderFactory()
        MedicationFactory()  # paciente não-vinculado a outsider
        assert Medication.objects.visible_to_provider(outsider).count() == 0


# ---------------------------------------------------------------------------
# PatientReportedMedication
# ---------------------------------------------------------------------------


class TestPatientReportedMedication:
    def test_content_encrypted(self):
        report = PatientReportedMedicationFactory(content="TOMANDO_SEGREDO_777")
        with connection.cursor() as cur:
            cur.execute(
                "SELECT content FROM clinical_patientreportedmedication WHERE id = %s",
                [report.pk],
            )
            raw = cur.fetchone()[0]
        raw_str = (
            bytes(raw).decode("utf-8", errors="replace")
            if isinstance(raw, memoryview | bytes)
            else str(raw)
        )
        assert "777" not in raw_str

    def test_visible_only_to_bonded_provider(self):
        provider = HealthcareProviderFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider, patient=patient)

        PatientReportedMedicationFactory(patient=patient)
        # Outro paciente não-vinculado.
        PatientReportedMedicationFactory()

        assert PatientReportedMedication.objects.visible_to_provider(provider).count() == 1
