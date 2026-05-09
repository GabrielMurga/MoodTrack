"""Testes de view da camada de IA — auth, fail-closed, error handling."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.ai.anthropic_client import AnthropicClientError
from tests.factories import (
    BondFactory,
    PatientProfileFactory,
    PsychologistProfileFactory,
)

pytestmark = pytest.mark.django_db


def _login(client, user, password="t3st"):
    user.set_password(password)
    user.save()
    assert client.login(email=user.email, password=password)


class TestPatientInsightsAuth:
    def test_requires_login(self, client):
        resp = client.get(reverse("ai:patient_insights"))
        assert resp.status_code == 302

    def test_psychologist_blocked(self, client):
        psych = PsychologistProfileFactory()
        _login(client, psych.user)
        resp = client.get(reverse("ai:patient_insights"))
        assert resp.status_code == 404


class TestPatientGenerateWeekly:
    @patch("apps.ai.views.generate_weekly_summary")
    def test_success_redirects(self, mock_gen, client):
        patient = PatientProfileFactory()
        _login(client, patient.user)
        resp = client.post(reverse("ai:patient_generate_weekly"), follow=True)
        assert resp.status_code == 200
        assert mock_gen.called

    @patch("apps.ai.views.generate_weekly_summary")
    def test_anthropic_error_shown_amigavelmente(self, mock_gen, client):
        """Sem API key / sem ZDR: erro amigável, não 500."""
        mock_gen.side_effect = AnthropicClientError("API_KEY ausente")
        patient = PatientProfileFactory()
        _login(client, patient.user)
        resp = client.post(reverse("ai:patient_generate_weekly"), follow=True)
        assert resp.status_code == 200
        assert b"indispon" in resp.content.lower()


class TestPsychologistBriefing:
    def test_psychologist_cannot_generate_briefing_for_unbonded(self, client):
        psych = PsychologistProfileFactory()
        unrelated = PatientProfileFactory()
        _login(client, psych.user)
        resp = client.post(
            reverse("ai:psychologist_generate_briefing", args=[unrelated.id])
        )
        assert resp.status_code == 404

    @patch("apps.ai.views.generate_session_briefing")
    def test_psychologist_generates_for_own_bonded_patient(self, mock_gen, client):
        psych = PsychologistProfileFactory()
        patient = PatientProfileFactory()
        BondFactory(active=True, psychologist=psych, patient=patient)

        _login(client, psych.user)
        resp = client.post(
            reverse("ai:psychologist_generate_briefing", args=[patient.id]),
            follow=True,
        )
        assert resp.status_code == 200
        assert mock_gen.called

    def test_briefing_detail_404_for_unbonded(self, client):
        psych = PsychologistProfileFactory()
        unrelated = PatientProfileFactory()
        _login(client, psych.user)
        resp = client.get(
            reverse("ai:psychologist_briefing_detail", args=[unrelated.id])
        )
        assert resp.status_code == 404
