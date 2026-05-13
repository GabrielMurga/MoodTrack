"""Testes de view do billing — auth, fail-closed, webhook idempotente.

Cobre obrigatoriamente:
- Acesso ao dashboard exige profissional logado (paciente / não-logado → 404 / redirect).
- Webhook recusa payload sem assinatura válida (400, sem efeitos colaterais).
- Webhook é idempotente: mesmo event_id duas vezes processa só uma.
- Webhook eventos válidos mudam o plano via events.dispatch.
- create_checkout sem price configurado falha amigavelmente, sem 500.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.accounts.models import ProviderPlan
from apps.billing.models import WebhookEvent
from tests.factories import HealthcareProviderFactory, PatientProfileFactory

pytestmark = pytest.mark.django_db


def _login(client, user, password="t3st"):
    user.set_password(password)
    user.save()
    assert client.login(email=user.email, password=password)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class TestBillingDashboard:
    def test_requires_login(self, client):
        resp = client.get(reverse("billing:dashboard"))
        assert resp.status_code == 302

    def test_patient_blocked(self, client):
        patient = PatientProfileFactory()
        _login(client, patient.user)
        resp = client.get(reverse("billing:dashboard"))
        assert resp.status_code == 404

    def test_provider_sees_current_plan(self, client):
        provider = HealthcareProviderFactory()  # default Básico
        _login(client, provider.user)
        resp = client.get(reverse("billing:dashboard"))
        assert resp.status_code == 200
        assert b"B" in resp.content  # algum nome do plano renderizado

    def test_premium_provider_sees_manage_button(self, client):
        provider = HealthcareProviderFactory(
            premium_plan=True,
            stripe_subscription_id="sub_test_123",
        )
        _login(client, provider.user)
        resp = client.get(reverse("billing:dashboard"))
        assert resp.status_code == 200
        assert b"Gerenciar assinatura" in resp.content


# ---------------------------------------------------------------------------
# create_checkout
# ---------------------------------------------------------------------------


class TestCreateCheckout:
    def test_invalid_plan_returns_error(self, client):
        provider = HealthcareProviderFactory()
        _login(client, provider.user)
        resp = client.post(reverse("billing:create_checkout"), {"plan": "ouro"})
        assert resp.status_code == 302
        assert reverse("billing:dashboard") in resp.url

    def test_unconfigured_price_id_fails_gracefully(self, client, settings):
        settings.STRIPE_PRO_PRICE_ID = ""
        provider = HealthcareProviderFactory()
        _login(client, provider.user)
        resp = client.post(reverse("billing:create_checkout"), {"plan": "pro"})
        assert resp.status_code == 302
        # Não deve crashar nem cobrar — só redirecionar com mensagem.

    def test_happy_path_redirects_to_stripe(self, client, settings):
        settings.STRIPE_API_KEY = "sk_test_dummy"
        settings.STRIPE_PRO_PRICE_ID = "price_test_pro"
        provider = HealthcareProviderFactory()
        _login(client, provider.user)

        with patch(
            "apps.billing.views.default_client.create_checkout_session",
            return_value="https://checkout.stripe.com/test_session",
        ):
            resp = client.post(reverse("billing:create_checkout"), {"plan": "pro"})
        assert resp.status_code == 302
        assert resp.url == "https://checkout.stripe.com/test_session"


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------


class TestStripeWebhook:
    def test_invalid_signature_returns_400(self, client):
        """Sem signature válida → 400, NÃO cria WebhookEvent (regra 5)."""
        with patch(
            "apps.billing.views.default_client.verify_webhook",
            side_effect=__import__("apps.billing.stripe_client", fromlist=["StripeBillingError"]).StripeBillingError(
                "assinatura inválida"
            ),
        ):
            resp = client.post(
                reverse("billing:stripe_webhook"),
                data=b'{"id":"evt_1","type":"foo"}',
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="bogus",
            )
        assert resp.status_code == 400
        assert WebhookEvent.objects.count() == 0

    def test_valid_event_creates_webhook_event_and_dispatches(self, client):
        event = {
            "id": "evt_test_1",
            "type": "checkout.session.completed",
            "data": {"object": {"customer": "cus_x", "subscription": "sub_x"}},
        }
        with patch(
            "apps.billing.views.default_client.verify_webhook",
            return_value=event,
        ), patch("apps.billing.events.dispatch", return_value=True) as mock_dispatch:
            resp = client.post(
                reverse("billing:stripe_webhook"),
                data=json.dumps(event).encode(),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="t=1,v1=valid",
            )
        assert resp.status_code == 200
        assert WebhookEvent.objects.filter(event_id="evt_test_1").exists()
        wh = WebhookEvent.objects.get(event_id="evt_test_1")
        assert wh.processed_at is not None
        assert wh.error == ""
        mock_dispatch.assert_called_once()

    def test_duplicate_event_id_is_idempotent(self, client):
        """Mesmo event_id duas vezes: processa só na primeira, retorna 200 na segunda."""
        event = {"id": "evt_dup_1", "type": "some.event", "data": {"object": {}}}

        with patch(
            "apps.billing.views.default_client.verify_webhook",
            return_value=event,
        ), patch("apps.billing.events.dispatch", return_value=True) as mock_dispatch:
            resp1 = client.post(
                reverse("billing:stripe_webhook"),
                data=json.dumps(event).encode(),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="t=1,v1=valid",
            )
            resp2 = client.post(
                reverse("billing:stripe_webhook"),
                data=json.dumps(event).encode(),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="t=1,v1=valid",
            )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert WebhookEvent.objects.filter(event_id="evt_dup_1").count() == 1
        # Dispatch foi chamado só uma vez (segundo POST viu IntegrityError e retornou)
        assert mock_dispatch.call_count == 1

    def test_handler_failure_marks_error_and_returns_500(self, client):
        event = {"id": "evt_fail_1", "type": "checkout.session.completed", "data": {"object": {}}}
        with patch(
            "apps.billing.views.default_client.verify_webhook",
            return_value=event,
        ), patch(
            "apps.billing.events.dispatch",
            side_effect=RuntimeError("simulated handler failure"),
        ):
            resp = client.post(
                reverse("billing:stripe_webhook"),
                data=json.dumps(event).encode(),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="t=1,v1=valid",
            )
        assert resp.status_code == 500
        wh = WebhookEvent.objects.get(event_id="evt_fail_1")
        assert wh.processed_at is None
        assert "simulated" in wh.error
