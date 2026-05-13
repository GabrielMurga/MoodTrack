"""Testes das views de medicação — apps/clinical/views.py.

Cobre obrigatoriamente (CLAUDE.md):
- Autorização: psicólogo não prescreve (404).
- Autorização: não-logado bloqueado (redirect para login).
- Autorização: psiquiatra só edita/descontinua próprias prescrições.
- Happy path: psiquiatra cria prescrição para paciente vinculado.
- Paciente cria auto-reporte.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.clinical.models import Medication, PatientReportedMedication
from tests.factories import (
    BondFactory,
    HealthcareProviderFactory,
    MedicationFactory,
    PatientProfileFactory,
    PsychiatristProviderFactory,
)

pytestmark = pytest.mark.django_db


class TestMedicationCreate:
    def test_requires_login(self, client):
        url = reverse("clinical:medication_create", args=[1])
        resp = client.get(url)
        assert resp.status_code == 302
        assert "/login" in resp["Location"] or "login" in resp["Location"]

    def test_psychologist_cannot_prescribe(self, client):
        psicologo = HealthcareProviderFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=psicologo, patient=patient)

        client.force_login(psicologo.user)
        url = reverse("clinical:medication_create", args=[patient.id])
        resp = client.get(url)
        assert resp.status_code == 404

    def test_unbonded_psychiatrist_gets_404(self, client):
        psiquiatra = PsychiatristProviderFactory()
        patient = PatientProfileFactory()  # sem bond com psiquiatra

        client.force_login(psiquiatra.user)
        url = reverse("clinical:medication_create", args=[patient.id])
        resp = client.get(url)
        assert resp.status_code == 404

    def test_psychiatrist_creates_medication(self, client):
        psiquiatra = PsychiatristProviderFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=psiquiatra, patient=patient)

        client.force_login(psiquiatra.user)
        url = reverse("clinical:medication_create", args=[patient.id])
        resp = client.post(url, {
            "name": "Sertralina",
            "dosage": "50mg",
            "frequency": "1x ao dia",
            "notes": "",
            "started_at": "2026-05-01",
        })

        assert resp.status_code == 302
        assert Medication.objects.filter(patient=patient, prescribed_by=psiquiatra).count() == 1

    def test_medication_form_renders_for_psychiatrist(self, client):
        psiquiatra = PsychiatristProviderFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=psiquiatra, patient=patient)

        client.force_login(psiquiatra.user)
        resp = client.get(reverse("clinical:medication_create", args=[patient.id]))
        assert resp.status_code == 200


class TestMedicationEdit:
    def test_only_prescriber_can_edit(self, client):
        psiquiatra_a = PsychiatristProviderFactory()
        psiquiatra_b = PsychiatristProviderFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=psiquiatra_b, patient=patient)

        med = MedicationFactory(patient=patient, prescribed_by=psiquiatra_a)

        client.force_login(psiquiatra_b.user)
        url = reverse("clinical:medication_edit", args=[med.id])
        resp = client.get(url)
        assert resp.status_code == 404

    def test_prescriber_can_edit(self, client):
        psiquiatra = PsychiatristProviderFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=psiquiatra, patient=patient)
        med = MedicationFactory(patient=patient, prescribed_by=psiquiatra)

        client.force_login(psiquiatra.user)
        resp = client.post(
            reverse("clinical:medication_edit", args=[med.id]),
            {"name": "Fluoxetina", "dosage": "20mg", "frequency": "1x ao dia", "notes": "", "started_at": ""},
        )
        assert resp.status_code == 302
        med.refresh_from_db()
        assert med.name == "Fluoxetina"


class TestMedicationDiscontinue:
    def test_psychologist_cannot_discontinue(self, client):
        psicologo = HealthcareProviderFactory()
        med = MedicationFactory()

        client.force_login(psicologo.user)
        resp = client.post(reverse("clinical:medication_discontinue", args=[med.id]))
        assert resp.status_code == 404

    def test_psychiatrist_discontinues_own_prescription(self, client):
        psiquiatra = PsychiatristProviderFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=psiquiatra, patient=patient)
        med = MedicationFactory(patient=patient, prescribed_by=psiquiatra, ended_at=None)

        client.force_login(psiquiatra.user)
        resp = client.post(reverse("clinical:medication_discontinue", args=[med.id]))
        assert resp.status_code == 302
        med.refresh_from_db()
        assert med.ended_at is not None


class TestPatientReportedMedication:
    def test_requires_login(self, client):
        url = reverse("clinical:patient_reported_medication")
        resp = client.get(url)
        assert resp.status_code == 302

    def test_provider_cannot_access(self, client):
        provider = HealthcareProviderFactory()
        client.force_login(provider.user)
        resp = client.get(reverse("clinical:patient_reported_medication"))
        assert resp.status_code == 404

    def test_patient_creates_report(self, client):
        patient = PatientProfileFactory()
        client.force_login(patient.user)

        resp = client.post(
            reverse("clinical:patient_reported_medication"),
            {"content": "Ômega 3, 1g ao dia"},
        )
        assert resp.status_code == 302
        assert PatientReportedMedication.objects.filter(patient=patient).count() == 1
