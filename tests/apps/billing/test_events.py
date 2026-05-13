"""Testes dos handlers de eventos da Stripe — apps/billing/events.py.

Cobre:
- Mapeamento price_id → ProviderPlan
- handle_checkout_completed promove o plano corretamente
- handle_subscription_updated trata troca Pro↔Premium
- handle_subscription_deleted faz downgrade pra Básico
- Eventos pra customer desconhecido são ignorados (não crasham)
- Idempotência: aplicar mesmo plano duas vezes não emite audit duplicado
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.accounts.models import ProviderPlan
from apps.audit.models import AuditLog
from apps.billing import events
from tests.factories import HealthcareProviderFactory

pytestmark = pytest.mark.django_db


class TestPlanMapping:
    def test_pro_price_maps_to_pro_plan(self, settings):
        settings.STRIPE_PRO_PRICE_ID = "price_pro_x"
        settings.STRIPE_PREMIUM_PRICE_ID = "price_premium_x"
        assert events._plan_from_price_id("price_pro_x") == ProviderPlan.PRO

    def test_premium_price_maps_to_premium_plan(self, settings):
        settings.STRIPE_PRO_PRICE_ID = "price_pro_x"
        settings.STRIPE_PREMIUM_PRICE_ID = "price_premium_x"
        assert events._plan_from_price_id("price_premium_x") == ProviderPlan.PREMIUM

    def test_unknown_price_returns_none(self, settings):
        settings.STRIPE_PRO_PRICE_ID = "price_pro_x"
        settings.STRIPE_PREMIUM_PRICE_ID = "price_premium_x"
        assert events._plan_from_price_id("price_unknown_xxx") is None


class TestHandleCheckoutCompleted:
    def test_upgrades_basic_to_pro(self, settings):
        settings.STRIPE_PRO_PRICE_ID = "price_pro_x"
        provider = HealthcareProviderFactory(stripe_customer_id="cus_test_1")

        event = {
            "id": "evt_1",
            "type": "checkout.session.completed",
            "data": {"object": {"customer": "cus_test_1", "subscription": "sub_test_1"}},
        }
        fake_sub = {"items": {"data": [{"price": {"id": "price_pro_x"}}]}}

        with patch("stripe.Subscription.retrieve", return_value=fake_sub):
            assert events.handle_checkout_completed(event) is True

        provider.refresh_from_db()
        assert provider.plan == ProviderPlan.PRO
        assert provider.stripe_subscription_id == "sub_test_1"
        assert AuditLog.objects.filter(action="billing.plan_changed").count() == 1

    def test_unknown_customer_returns_false(self, settings):
        settings.STRIPE_PRO_PRICE_ID = "price_pro_x"
        event = {
            "id": "evt_2",
            "type": "checkout.session.completed",
            "data": {"object": {"customer": "cus_doesnt_exist", "subscription": "sub_x"}},
        }
        fake_sub = {"items": {"data": [{"price": {"id": "price_pro_x"}}]}}
        with patch("stripe.Subscription.retrieve", return_value=fake_sub):
            assert events.handle_checkout_completed(event) is False

    def test_missing_customer_or_subscription_returns_false(self):
        event = {
            "id": "evt_3",
            "type": "checkout.session.completed",
            "data": {"object": {}},  # nenhum dos dois
        }
        assert events.handle_checkout_completed(event) is False


class TestHandleSubscriptionUpdated:
    def test_pro_to_premium_changes_plan(self, settings):
        settings.STRIPE_PRO_PRICE_ID = "price_pro_x"
        settings.STRIPE_PREMIUM_PRICE_ID = "price_premium_x"
        provider = HealthcareProviderFactory(
            pro_plan=True,
            stripe_customer_id="cus_pp_1",
            stripe_subscription_id="sub_pp_1",
        )
        event = {
            "id": "evt_upd_1",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_pp_1",
                    "customer": "cus_pp_1",
                    "status": "active",
                    "items": {"data": [{"price": {"id": "price_premium_x"}}]},
                }
            },
        }
        assert events.handle_subscription_updated(event) is True
        provider.refresh_from_db()
        assert provider.plan == ProviderPlan.PREMIUM

    def test_status_unpaid_does_not_change_plan(self, settings):
        settings.STRIPE_PRO_PRICE_ID = "price_pro_x"
        settings.STRIPE_PREMIUM_PRICE_ID = "price_premium_x"
        provider = HealthcareProviderFactory(pro_plan=True, stripe_customer_id="cus_unpaid_1")
        event = {
            "id": "evt_upd_2",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_unpaid",
                    "customer": "cus_unpaid_1",
                    "status": "unpaid",
                    "items": {"data": [{"price": {"id": "price_premium_x"}}]},
                }
            },
        }
        assert events.handle_subscription_updated(event) is False
        provider.refresh_from_db()
        assert provider.plan == ProviderPlan.PRO  # inalterado


class TestHandleSubscriptionDeleted:
    def test_active_subscription_downgrades_to_basic(self):
        provider = HealthcareProviderFactory(
            pro_plan=True,
            stripe_customer_id="cus_del_1",
            stripe_subscription_id="sub_del_1",
        )
        event = {
            "id": "evt_del_1",
            "type": "customer.subscription.deleted",
            "data": {"object": {"customer": "cus_del_1"}},
        }
        assert events.handle_subscription_deleted(event) is True
        provider.refresh_from_db()
        assert provider.plan == ProviderPlan.BASIC
        assert provider.stripe_subscription_id == ""

    def test_unknown_customer_returns_false(self):
        event = {
            "id": "evt_del_2",
            "type": "customer.subscription.deleted",
            "data": {"object": {"customer": "cus_nope"}},
        }
        assert events.handle_subscription_deleted(event) is False


class TestDispatcher:
    def test_unknown_event_type_returns_false(self):
        event = {"id": "evt_x", "type": "something.weird", "data": {"object": {}}}
        assert events.dispatch(event) is False

    def test_known_event_invokes_handler(self):
        # HANDLERS dict é populado em import time; patchar a função não substitui
        # a referência no dict. Patcha diretamente a entrada do dict.
        mock_handler = MagicMock(return_value=True)
        with patch.dict(
            events.HANDLERS,
            {"checkout.session.completed": mock_handler},
        ):
            events.dispatch({
                "id": "evt_disp_1",
                "type": "checkout.session.completed",
                "data": {"object": {"customer": "cus_x"}},
            })
            mock_handler.assert_called_once()


class TestApplyPlanChangeIdempotency:
    def test_same_plan_does_not_emit_audit_again(self):
        provider = HealthcareProviderFactory(
            pro_plan=True,
            stripe_subscription_id="sub_same",
        )
        # Já está em Pro com mesma subscription — re-aplicar não muda nada.
        events._apply_plan_change(
            provider,
            ProviderPlan.PRO,
            reason="checkout_completed",
            subscription_id="sub_same",
            event_id="evt_idem",
        )
        assert AuditLog.objects.filter(action="billing.plan_changed").count() == 0
