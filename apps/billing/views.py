"""Views de billing — checkout, portal, webhook (ADR 0012).

Princípios:
- `provider.plan` NUNCA é modificado em view de UI. Mesmo no callback de sucesso
  do checkout, o plano só vira o que Stripe confirmou via webhook (regra 5).
- Webhook é CSRF-exempt (Stripe não envia token), mas exige assinatura válida.
- Toda mudança de plano gera audit (em `events.py`).
"""

from __future__ import annotations

import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.accounts.models import HealthcareProvider, ProviderPlan

from . import events
from .models import WebhookEvent
from .stripe_client import StripeBillingError, default_client

logger = logging.getLogger(__name__)


def _require_provider(request: HttpRequest) -> HealthcareProvider:
    if not request.user.is_provider:
        raise Http404("Perfil de profissional não encontrado.")
    return request.user.provider_profile


def _absolute_url(request: HttpRequest, name: str, *args) -> str:
    return request.build_absolute_uri(reverse(name, args=args))


# ---------------------------------------------------------------------------
# UI do profissional
# ---------------------------------------------------------------------------


@login_required
def billing_dashboard(request: HttpRequest) -> HttpResponse:
    """Tela 'Meu plano' — mostra plano atual + ações disponíveis."""
    profile = _require_provider(request)
    return render(
        request,
        "billing/dashboard.html",
        {
            "provider": profile,
            "ProviderPlan": ProviderPlan,
        },
    )


@login_required
@require_POST
def create_checkout(request: HttpRequest) -> HttpResponse:
    """Inicia checkout pra plano `pro` ou `premium`. Redireciona pra Stripe."""
    profile = _require_provider(request)
    plan = request.POST.get("plan", "")

    from django.conf import settings

    if plan == "pro":
        price_id = settings.STRIPE_PRO_PRICE_ID
    elif plan == "premium":
        price_id = settings.STRIPE_PREMIUM_PRICE_ID
    else:
        messages.error(request, "Plano inválido.")
        return redirect("billing:dashboard")

    if not price_id:
        messages.error(
            request,
            "Cobrança ainda não configurada — peça ao admin configurar os preços no Stripe.",
        )
        return redirect("billing:dashboard")

    try:
        url = default_client.create_checkout_session(
            provider=profile,
            price_id=price_id,
            success_url=_absolute_url(request, "billing:checkout_success")
            + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=_absolute_url(request, "billing:dashboard"),
        )
    except StripeBillingError as exc:
        logger.exception("Falha ao criar checkout session")
        messages.error(request, f"Não foi possível iniciar pagamento: {exc}")
        return redirect("billing:dashboard")

    return redirect(url)


@login_required
def checkout_success(request: HttpRequest) -> HttpResponse:
    """Callback de sucesso da Stripe.

    NÃO promove plano. Só renderiza "estamos processando". O webhook é quem
    de fato muda o plano após receber `checkout.session.completed`.
    """
    profile = _require_provider(request)
    return render(request, "billing/checkout_success.html", {"provider": profile})


@login_required
@require_POST
def open_portal(request: HttpRequest) -> HttpResponse:
    """Redireciona pro Customer Portal da Stripe pra gerenciar assinatura."""
    profile = _require_provider(request)
    try:
        url = default_client.create_portal_session(
            provider=profile,
            return_url=_absolute_url(request, "billing:dashboard"),
        )
    except StripeBillingError as exc:
        messages.error(request, str(exc))
        return redirect("billing:dashboard")
    return redirect(url)


# ---------------------------------------------------------------------------
# Webhook (Stripe → MoodTrack)
# ---------------------------------------------------------------------------


@csrf_exempt
@require_POST
def stripe_webhook(request: HttpRequest) -> HttpResponse:
    """Endpoint público que recebe eventos da Stripe.

    Fluxo:
    1. Lê payload bruto e header Stripe-Signature.
    2. Verifica assinatura (StripeBillingError → 400, sem processar).
    3. Tenta inserir WebhookEvent com event_id único.
       - Conflito (já existe) → 200, já foi processado antes.
    4. Dispatch para handler em events.py.
    5. Erro no handler → grava em WebhookEvent.error, retorna 500
       (Stripe re-tenta).
    """
    payload = request.body
    signature = request.headers.get("Stripe-Signature", "")

    try:
        event = default_client.verify_webhook(payload, signature)
    except StripeBillingError as exc:
        logger.warning("Webhook recusado: %s", exc)
        return HttpResponse(status=400)

    event_id = event["id"]
    event_type = event["type"]

    # Idempotência: tenta criar; se já existe, foi processado.
    try:
        with transaction.atomic():
            webhook_event = WebhookEvent.objects.create(
                event_id=event_id,
                event_type=event_type,
                payload=json.loads(payload) if isinstance(payload, bytes | str) else event,
            )
    except IntegrityError:
        # Já processado em delivery anterior — responde 200 sem reprocessar.
        return HttpResponse(status=200)

    try:
        events.dispatch(event)
    except Exception as exc:
        logger.exception("Falha ao processar evento %s", event_id)
        events.mark_processed(webhook_event, success=False, error=str(exc))
        return HttpResponse(status=500)

    events.mark_processed(webhook_event, success=True)
    return HttpResponse(status=200)
