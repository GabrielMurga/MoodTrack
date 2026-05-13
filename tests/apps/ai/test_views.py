"""Testes de view da camada de IA — auth, gate de plano, fail-closed, error handling."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.ai.anthropic_client import AnthropicClientError
from tests.factories import (
    BondFactory,
    HealthcareProviderFactory,
    PatientProfileFactory,
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

    def test_provider_blocked(self, client):
        provider = HealthcareProviderFactory()
        _login(client, provider.user)
        resp = client.get(reverse("ai:patient_insights"))
        assert resp.status_code == 404


class TestPatientGenerateWeekly:
    @patch("apps.ai.views.generate_weekly_summary")
    def test_success_with_pro_provider(self, mock_gen, client):
        """Paciente com bond ativo a um provider Pro gera resumo normalmente."""
        provider = HealthcareProviderFactory(pro_plan=True)
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider, patient=patient)

        _login(client, patient.user)
        resp = client.post(reverse("ai:patient_generate_weekly"), follow=True)
        assert resp.status_code == 200
        assert mock_gen.called

    @patch("apps.ai.views.generate_weekly_summary")
    def test_anthropic_error_shown_amigavelmente(self, mock_gen, client):
        """Sem API key / sem ZDR: erro amigável, não 500."""
        mock_gen.side_effect = AnthropicClientError("API_KEY ausente")
        provider = HealthcareProviderFactory(pro_plan=True)
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider, patient=patient)

        _login(client, patient.user)
        resp = client.post(reverse("ai:patient_generate_weekly"), follow=True)
        assert resp.status_code == 200
        assert b"indispon" in resp.content.lower()

    @patch("apps.ai.views.generate_weekly_summary")
    def test_individual_patient_blocked_no_feature(self, mock_gen, client):
        """Modo individual (sem bond ativo) → gate retorna NoFeature, IA não roda."""
        patient = PatientProfileFactory()
        _login(client, patient.user)
        resp = client.post(reverse("ai:patient_generate_weekly"), follow=True)
        assert resp.status_code == 200
        assert mock_gen.called is False
        assert b"plano" in resp.content.lower()

    @patch("apps.ai.views.generate_weekly_summary")
    def test_basic_plan_provider_blocks_patient_generation(self, mock_gen, client):
        """Bond ativo a provider Básico → NoFeature, IA não roda."""
        provider = HealthcareProviderFactory()  # default basic
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider, patient=patient)

        _login(client, patient.user)
        resp = client.post(reverse("ai:patient_generate_weekly"), follow=True)
        assert resp.status_code == 200
        assert mock_gen.called is False


class TestProviderBriefing:
    def test_provider_cannot_generate_briefing_for_unbonded(self, client):
        provider = HealthcareProviderFactory(pro_plan=True)
        unrelated = PatientProfileFactory()
        _login(client, provider.user)
        resp = client.post(reverse("ai:provider_generate_briefing", args=[unrelated.id]))
        assert resp.status_code == 404

    @patch("apps.ai.views.generate_session_briefing")
    def test_provider_pro_generates_for_own_bonded_patient(self, mock_gen, client):
        provider = HealthcareProviderFactory(pro_plan=True)
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider, patient=patient)

        _login(client, provider.user)
        resp = client.post(
            reverse("ai:provider_generate_briefing", args=[patient.id]),
            follow=True,
        )
        assert resp.status_code == 200
        assert mock_gen.called

    @patch("apps.ai.views.generate_session_briefing")
    def test_basic_plan_provider_blocked(self, mock_gen, client):
        """Provider em plano Básico → IA não roda, mensagem de plano."""
        provider = HealthcareProviderFactory()  # default basic
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider, patient=patient)

        _login(client, provider.user)
        resp = client.post(
            reverse("ai:provider_generate_briefing", args=[patient.id]),
            follow=True,
        )
        assert resp.status_code == 200
        assert mock_gen.called is False
        assert b"plano" in resp.content.lower()

    def test_briefing_detail_404_for_unbonded(self, client):
        provider = HealthcareProviderFactory(pro_plan=True)
        unrelated = PatientProfileFactory()
        _login(client, provider.user)
        resp = client.get(reverse("ai:provider_briefing_detail", args=[unrelated.id]))
        assert resp.status_code == 404


class TestUIHidesAIPointsOnBasicPlan:
    def test_basic_provider_does_not_see_briefing_button_on_patient_detail(self, client):
        provider = HealthcareProviderFactory()  # default basic
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider, patient=patient)

        _login(client, provider.user)
        resp = client.get(reverse("journal:provider_patient_detail", args=[patient.id]))
        assert resp.status_code == 200
        assert b"briefing" not in resp.content.lower()

    def test_pro_provider_sees_briefing_button(self, client):
        provider = HealthcareProviderFactory(pro_plan=True)
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider, patient=patient)

        _login(client, provider.user)
        resp = client.get(reverse("journal:provider_patient_detail", args=[patient.id]))
        assert resp.status_code == 200
        assert b"briefing" in resp.content.lower()

    def test_individual_patient_no_insights_link_in_nav(self, client):
        """Paciente sem bond ativo a provider Pro+ não vê link Insights no nav."""
        patient = PatientProfileFactory()
        _login(client, patient.user)
        resp = client.get(reverse("journal:patient_mood_list"))
        assert resp.status_code == 200
        assert b"Insights" not in resp.content

    def test_patient_with_pro_provider_sees_insights_link(self, client):
        provider = HealthcareProviderFactory(pro_plan=True)
        patient = PatientProfileFactory()
        BondFactory(active=True, provider=provider, patient=patient)

        _login(client, patient.user)
        resp = client.get(reverse("journal:patient_mood_list"))
        assert resp.status_code == 200
        assert b"Insights" in resp.content

    def test_patient_insights_page_hides_generate_button_when_no_ai(self, client):
        """Paciente sem IA pode visitar a URL mas o form de gerar não aparece."""
        patient = PatientProfileFactory()
        _login(client, patient.user)
        resp = client.get(reverse("ai:patient_insights"))
        assert resp.status_code == 200
        assert b"Gerar resumo" not in resp.content
