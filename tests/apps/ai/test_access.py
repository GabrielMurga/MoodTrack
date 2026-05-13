"""Testes do gate de acesso a IA — apps/ai/access.py.

Cobre:
- Decisão por plano (basic = NoFeature, pro/premium = Allowed).
- None provider (modo individual) = NoFeature.
- Fail-closed em exceção.
- Counter mensal incrementa atomicamente com custo em BRL.
- Quota bloqueada quando custo acumulado >= limite do plano.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import ProviderPlan
from apps.ai.access import (
    AIAction,
    Allowed,
    NoFeature,
    QuotaExceeded,
    _cost_brl,
    check,
    record_usage,
)
from apps.ai.models import AIUsageCounter
from tests.factories import HealthcareProviderFactory

pytestmark = pytest.mark.django_db


class TestCheck:
    def test_basic_plan_returns_no_feature(self):
        provider = HealthcareProviderFactory()  # default basic
        decision = check(provider, AIAction.WEEKLY_SUMMARY)
        assert isinstance(decision, NoFeature)
        assert decision.plan == ProviderPlan.BASIC

    def test_pro_plan_returns_allowed_when_under_limit(self):
        provider = HealthcareProviderFactory(pro_plan=True)
        decision = check(provider, AIAction.SESSION_BRIEFING)
        assert isinstance(decision, Allowed)

    def test_premium_plan_returns_allowed_when_under_limit(self):
        provider = HealthcareProviderFactory(premium_plan=True)
        decision = check(provider, AIAction.SESSION_BRIEFING)
        assert isinstance(decision, Allowed)

    def test_none_provider_returns_no_feature(self):
        """Modo individual / user sem perfil → NoFeature."""
        decision = check(None, AIAction.WEEKLY_SUMMARY)
        assert isinstance(decision, NoFeature)
        assert decision.plan is None

    def test_exception_inside_check_falls_closed(self):
        """Erro inesperado vira NoFeature, nunca Allowed."""

        class BrokenProvider:
            @property
            def plan(self):
                raise RuntimeError("simulated DB outage")

        decision = check(BrokenProvider(), AIAction.SESSION_BRIEFING)
        assert isinstance(decision, NoFeature)

    def test_pro_quota_exceeded_blocks_access(self):
        """Pro com custo acumulado >= R$50 recebe QuotaExceeded."""
        provider = HealthcareProviderFactory(pro_plan=True)
        period = timezone.now().date().replace(day=1)
        AIUsageCounter.objects.create(provider=provider, period=period, cost_brl=Decimal("50.00"))

        decision = check(provider, AIAction.SESSION_BRIEFING)
        assert isinstance(decision, QuotaExceeded)
        assert decision.limit == 50.0

    def test_premium_quota_exceeded_blocks_access(self):
        """Premium com custo acumulado >= R$200 recebe QuotaExceeded."""
        provider = HealthcareProviderFactory(premium_plan=True)
        period = timezone.now().date().replace(day=1)
        AIUsageCounter.objects.create(provider=provider, period=period, cost_brl=Decimal("200.00"))

        decision = check(provider, AIAction.SESSION_BRIEFING)
        assert isinstance(decision, QuotaExceeded)

    def test_pro_just_under_limit_still_allowed(self):
        provider = HealthcareProviderFactory(pro_plan=True)
        period = timezone.now().date().replace(day=1)
        AIUsageCounter.objects.create(provider=provider, period=period, cost_brl=Decimal("49.99"))

        decision = check(provider, AIAction.SESSION_BRIEFING)
        assert isinstance(decision, Allowed)


class TestCostCalculation:
    def test_haiku_cost_is_cheaper_than_sonnet(self):
        haiku_cost = _cost_brl(1000, 500, "claude-haiku-4-5-20251001")
        sonnet_cost = _cost_brl(1000, 500, "claude-sonnet-4-6")
        assert haiku_cost < sonnet_cost

    def test_cost_is_positive(self):
        cost = _cost_brl(2000, 500, "claude-sonnet-4-6")
        assert cost > Decimal("0")

    def test_unknown_model_falls_back_to_sonnet_pricing(self):
        known = _cost_brl(1000, 500, "claude-sonnet-4-6")
        unknown = _cost_brl(1000, 500, "some-future-model-xyz")
        assert known == unknown

    def test_zero_tokens_zero_cost(self):
        assert _cost_brl(0, 0, "claude-sonnet-4-6") == Decimal("0")


class TestRecordUsage:
    def test_creates_counter_for_current_period(self):
        provider = HealthcareProviderFactory(pro_plan=True)
        record_usage(provider, AIAction.SESSION_BRIEFING, input_tokens=1000, output_tokens=300, model="claude-haiku-4-5-20251001")

        first_of_month = timezone.now().date().replace(day=1)
        counter = AIUsageCounter.objects.get(provider=provider, period=first_of_month)
        assert counter.count == 1
        assert counter.cost_brl > Decimal("0")

    def test_accumulates_cost_across_calls(self):
        provider = HealthcareProviderFactory(pro_plan=True)
        record_usage(provider, AIAction.SESSION_BRIEFING, input_tokens=1000, output_tokens=300, model="claude-sonnet-4-6")
        record_usage(provider, AIAction.SESSION_BRIEFING, input_tokens=1000, output_tokens=300, model="claude-sonnet-4-6")

        counter = AIUsageCounter.objects.get(provider=provider)
        assert counter.count == 2
        single_cost = _cost_brl(1000, 300, "claude-sonnet-4-6")
        assert counter.cost_brl == single_cost * 2

    def test_separate_providers_have_separate_counters(self):
        a = HealthcareProviderFactory(pro_plan=True)
        b = HealthcareProviderFactory(pro_plan=True)
        record_usage(a, AIAction.SESSION_BRIEFING)
        record_usage(a, AIAction.SESSION_BRIEFING)
        record_usage(b, AIAction.SESSION_BRIEFING)

        assert AIUsageCounter.objects.get(provider=a).count == 2
        assert AIUsageCounter.objects.get(provider=b).count == 1

    def test_record_usage_does_not_raise_on_db_error(self, monkeypatch):
        """Falha em record_usage NÃO derruba o request — chamada à LLM já aconteceu."""
        provider = HealthcareProviderFactory(pro_plan=True)

        def boom(*args, **kwargs):
            raise RuntimeError("simulated DB outage")

        monkeypatch.setattr(AIUsageCounter.objects, "get_or_create", boom)
        record_usage(provider, AIAction.SESSION_BRIEFING)


class TestPeriodKey:
    def test_period_is_first_of_month(self):
        from apps.ai.access import _current_period

        period = _current_period()
        assert isinstance(period, date)
        assert period.day == 1
        assert period.month == timezone.now().date().month
