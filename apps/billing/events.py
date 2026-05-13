"""Processadores de eventos da Stripe (ADR 0012).

Cada handler recebe o `event` (dict da Stripe) e aplica a mudança correspondente
em `HealthcareProvider`. Quem invoca: `views.stripe_webhook`, depois de
verificar assinatura e checar idempotência via `WebhookEvent`.

Fail-closed: handler que falha levanta exceção. `views.stripe_webhook` captura,
registra em `WebhookEvent.error` e retorna 500 — Stripe re-tenta. Eventos
desconhecidos são logados e ignorados (retorna `False`).
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.accounts.models import HealthcareProvider, ProviderPlan
from apps.audit.models import log_event

logger = logging.getLogger(__name__)


def _plan_from_price_id(price_id: str) -> ProviderPlan | None:
    """Mapeia price_id da Stripe para `ProviderPlan`. Retorna None se desconhecido."""
    if price_id == settings.STRIPE_PRO_PRICE_ID:
        return ProviderPlan.PRO
    if price_id == settings.STRIPE_PREMIUM_PRICE_ID:
        return ProviderPlan.PREMIUM
    return None


def _provider_from_customer_id(customer_id: str) -> HealthcareProvider | None:
    return HealthcareProvider.objects.filter(stripe_customer_id=customer_id).first()


def _apply_plan_change(
    provider: HealthcareProvider,
    new_plan: ProviderPlan,
    *,
    reason: str,
    subscription_id: str = "",
    event_id: str = "",
) -> None:
    """Aplica mudança de plano + audit log (regra 8: toda op sensível audita)."""
    old_plan = provider.plan
    if old_plan == new_plan and provider.stripe_subscription_id == subscription_id:
        return  # idempotente: nada mudou

    provider.plan = new_plan
    if subscription_id:
        provider.stripe_subscription_id = subscription_id
    provider.save(update_fields=["plan", "stripe_subscription_id", "updated_at"])

    log_event(
        actor=None,  # Stripe é o "ator"; o usuário foi efeito-secundário
        action="billing.plan_changed",
        target=provider,
        old_plan=old_plan,
        new_plan=new_plan.value,
        reason=reason,
        stripe_event_id=event_id,
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_checkout_completed(event: dict[str, Any]) -> bool:
    """Pagamento da primeira parcela confirmado — Subscription criada."""
    session = event["data"]["object"]
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    if not customer_id or not subscription_id:
        logger.warning("checkout.session.completed sem customer/subscription: %s", session.get("id"))
        return False

    provider = _provider_from_customer_id(customer_id)
    if provider is None:
        logger.error("checkout.session.completed para customer desconhecido: %s", customer_id)
        return False

    # Extrai o price_id do primeiro item (sempre 1 item — line_items na Session).
    # Mas Session não vem expandida por default; precisamos buscar a subscription.
    import stripe

    sub = stripe.Subscription.retrieve(subscription_id)
    price_id = sub["items"]["data"][0]["price"]["id"]

    new_plan = _plan_from_price_id(price_id)
    if new_plan is None:
        logger.error("Price id desconhecido no checkout.completed: %s", price_id)
        return False

    _apply_plan_change(
        provider,
        new_plan,
        reason="checkout_completed",
        subscription_id=subscription_id,
        event_id=event["id"],
    )
    return True


def handle_subscription_updated(event: dict[str, Any]) -> bool:
    """Profissional trocou de plano via Customer Portal (Pro ↔ Premium)."""
    sub = event["data"]["object"]
    customer_id = sub.get("customer")
    subscription_id = sub.get("id")
    price_id = sub["items"]["data"][0]["price"]["id"]

    provider = _provider_from_customer_id(customer_id)
    if provider is None:
        logger.error("subscription.updated para customer desconhecido: %s", customer_id)
        return False

    # Status `canceled`/`unpaid` é tratado em subscription.deleted ou
    # via invoice.payment_failed; aqui só lidamos com mudança de plano ativa.
    if sub.get("status") not in ("active", "trialing"):
        logger.info("subscription.updated com status %s — sem mudança de plano", sub.get("status"))
        return False

    new_plan = _plan_from_price_id(price_id)
    if new_plan is None:
        logger.error("Price id desconhecido em subscription.updated: %s", price_id)
        return False

    _apply_plan_change(
        provider,
        new_plan,
        reason="subscription_updated",
        subscription_id=subscription_id,
        event_id=event["id"],
    )
    return True


def handle_subscription_deleted(event: dict[str, Any]) -> bool:
    """Subscription cancelada — downgrade pra Básico."""
    sub = event["data"]["object"]
    customer_id = sub.get("customer")

    provider = _provider_from_customer_id(customer_id)
    if provider is None:
        logger.error("subscription.deleted para customer desconhecido: %s", customer_id)
        return False

    old_plan = provider.plan
    provider.plan = ProviderPlan.BASIC
    provider.stripe_subscription_id = ""
    provider.save(update_fields=["plan", "stripe_subscription_id", "updated_at"])

    log_event(
        actor=None,
        action="billing.plan_changed",
        target=provider,
        old_plan=old_plan,
        new_plan=ProviderPlan.BASIC.value,
        reason="subscription_deleted",
        stripe_event_id=event["id"],
    )
    return True


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


HANDLERS = {
    "checkout.session.completed": handle_checkout_completed,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
}


def dispatch(event: dict[str, Any]) -> bool:
    """Roteia o evento para o handler. Retorna True se foi processado."""
    handler = HANDLERS.get(event["type"])
    if handler is None:
        logger.info("Evento ignorado (sem handler): %s", event["type"])
        return False
    return handler(event)


def mark_processed(webhook_event, success: bool, error: str = "") -> None:
    from .models import WebhookEvent  # local pra evitar ciclo

    webhook_event.error = error
    if success:
        webhook_event.processed_at = timezone.now()
    webhook_event.save(update_fields=["processed_at", "error"])
