"""Gate de acesso a IA — feature gate + controle de custo mensal.

Ver ADR 0010 e ADR 0011.

Fluxo obrigatório em toda chamada à LLM:
  1. decision = check(provider, action)     ← antes de chamar
  2. if not isinstance(decision, Allowed): return / redirect
  3. result = client.complete(...)          ← chamada real
  4. record_usage(provider, action, input_tokens=..., output_tokens=..., model=...)

Decisões possíveis:
- Allowed: pode prosseguir.
- NoFeature(plan): plano Básico — IA não inclusa.
- QuotaExceeded(used, limit): custo mensal em R$ atingiu o teto do plano.

Fail-closed (CLAUDE.md regra 5): qualquer caminho não-Allowed inesperado vira
NoFeature. Exceção dentro de check() também vira NoFeature — nunca Allowed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from django.conf import settings
from django.db.models import F
from django.utils import timezone

from apps.accounts.models import HealthcareProvider, ProviderPlan

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pricing: USD por token por modelo (input / output).
# Fonte: console.anthropic.com/pricing — atualizar quando Anthropic mudar.
# ---------------------------------------------------------------------------

_MODEL_PRICING_USD: dict[str, dict[str, Decimal]] = {
    "claude-haiku-4-5-20251001": {
        "input": Decimal("0.0000008"),   # $0.80/MTok
        "output": Decimal("0.000004"),   # $4.00/MTok
    },
    "claude-sonnet-4-6": {
        "input": Decimal("0.000003"),    # $3.00/MTok
        "output": Decimal("0.000015"),   # $15.00/MTok
    },
    "claude-opus-4-7": {
        "input": Decimal("0.000015"),    # $15.00/MTok
        "output": Decimal("0.000075"),   # $75.00/MTok
    },
}
_FALLBACK_PRICING = _MODEL_PRICING_USD["claude-sonnet-4-6"]


def _cost_brl(input_tokens: int, output_tokens: int, model: str) -> Decimal:
    """Converte contagem de tokens em custo em reais."""
    pricing = _MODEL_PRICING_USD.get(model, _FALLBACK_PRICING)
    cost_usd = (
        Decimal(input_tokens) * pricing["input"]
        + Decimal(output_tokens) * pricing["output"]
    )
    rate = Decimal(str(settings.AI_USD_TO_BRL_RATE))
    return (cost_usd * rate).quantize(Decimal("0.000001"))


# ---------------------------------------------------------------------------
# Tipos de ação e decisões
# ---------------------------------------------------------------------------


class AIAction(StrEnum):
    WEEKLY_SUMMARY = "weekly_summary"
    SESSION_BRIEFING = "session_briefing"
    PATIENT_OVERVIEW = "patient_overview"


@dataclass(frozen=True)
class Allowed:
    """Pode prosseguir com a chamada à LLM."""


@dataclass(frozen=True)
class NoFeature:
    """Plano não inclui IA (Básico) ou provider ausente."""
    plan: ProviderPlan | None = None


@dataclass(frozen=True)
class QuotaExceeded:
    """Custo mensal acumulado atingiu o teto do plano."""
    used: float   # R$ gasto no mês
    limit: float  # R$ teto do plano


AccessDecision = Allowed | NoFeature | QuotaExceeded


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _current_period() -> date:
    today = timezone.now().date()
    return today.replace(day=1)


def _limit_for(plan: ProviderPlan) -> Decimal:
    if plan == ProviderPlan.PRO:
        return settings.AI_PRO_MONTHLY_LIMIT_BRL
    return settings.AI_PREMIUM_MONTHLY_LIMIT_BRL


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def check(provider: HealthcareProvider | None, action: AIAction) -> AccessDecision:
    """Decide se a `action` pode rodar para este `provider`.

    `provider=None` modela paciente em modo individual (sem bond) — não há
    quem pague pela IA, resultado é NoFeature.

    Fail-closed: qualquer exceção inesperada retorna NoFeature.
    """
    try:
        if provider is None:
            return NoFeature()

        if provider.plan == ProviderPlan.BASIC:
            return NoFeature(plan=ProviderPlan.BASIC)

        limit = _limit_for(provider.plan)

        from .models import AIUsageCounter  # import local evita ciclo

        counter = AIUsageCounter.objects.filter(
            provider=provider, period=_current_period()
        ).first()
        used = counter.cost_brl if counter else Decimal("0")

        if used >= limit:
            return QuotaExceeded(used=float(used), limit=float(limit))

        return Allowed()

    except Exception:
        logger.exception("ai_access.check raised — fail-closed to NoFeature")
        return NoFeature()


def record_usage(
    provider: HealthcareProvider,
    action: AIAction,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    model: str = "",
) -> None:
    """Incrementa contador mensal e acumula custo após chamada bem-sucedida.

    Chamado APÓS a LLM responder com sucesso — não antes (evita cobrar por
    erro da Anthropic). Falha silenciosa não derruba o request.
    """
    from .models import AIUsageCounter  # import local evita ciclo

    try:
        effective_model = model or settings.ANTHROPIC_DEFAULT_MODEL
        cost = _cost_brl(input_tokens, output_tokens, effective_model)
        period = _current_period()
        counter, _ = AIUsageCounter.objects.get_or_create(provider=provider, period=period)
        AIUsageCounter.objects.filter(pk=counter.pk).update(
            count=F("count") + 1,
            cost_brl=F("cost_brl") + cost,
        )
    except Exception:
        logger.exception(
            "ai_access.record_usage failed for provider=%s action=%s",
            provider.pk,
            action,
        )
