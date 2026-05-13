"""Views da camada de IA.

Cada view:
- exige login + perfil correto (fail-closed)
- valida ownership/visibilidade do alvo
- passa pelo gate de acesso (`apps.ai.access.check`) antes de chamar a LLM
- registra uso após sucesso (`apps.ai.access.record_usage`)
- captura `AnthropicClientError` e mostra erro amigável (sem expor detalhes)
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from django.conf import settings

from apps.accounts.models import ProviderPlan
from apps.audit.models import log_event
from apps.bonds.models import Bond, BondStatus

from .access import AIAction, Allowed, NoFeature, QuotaExceeded, check, record_usage
from .anthropic_client import AnthropicClientError
from .models import AISummary
from .tasks import generate_session_briefing, generate_weekly_summary


def _require_patient(request: HttpRequest):
    if not request.user.is_patient:
        raise Http404("Perfil de paciente não encontrado.")
    return request.user.patient_profile


def _require_provider(request: HttpRequest):
    if not request.user.is_provider:
        raise Http404("Perfil de profissional não encontrado.")
    return request.user.provider_profile


def _resolve_provider_for_patient(patient_profile):
    """Provider responsável pela cota de IA do paciente, ou None.

    No modo individual (paciente sem Bond ativo), não há ninguém pagando —
    retorna None e o gate decide NoFeature.
    """
    bond = (
        Bond.objects.filter(patient=patient_profile, status=BondStatus.ACTIVE)
        .select_related("provider")
        .first()
    )
    return bond.provider if bond else None


def _model_for_provider(provider) -> str:
    """Haiku para Pro (custo menor), Sonnet para Premium (melhor qualidade)."""
    if provider.plan == ProviderPlan.PRO:
        return settings.ANTHROPIC_PRO_MODEL
    return settings.ANTHROPIC_PREMIUM_MODEL


def _handle_blocked(request: HttpRequest, decision, redirect_url: str) -> HttpResponse:
    """Mensagem amigável e redirect quando o gate nega acesso."""
    if isinstance(decision, NoFeature):
        messages.error(
            request,
            "Geração com IA não está disponível no seu plano atual.",
        )
    elif isinstance(decision, QuotaExceeded):
        messages.error(
            request,
            "Você atingiu o limite mensal de uso de IA. Tente no próximo ciclo.",
        )
    return redirect(redirect_url)


# ---------- paciente ----------


@login_required
def patient_insights(request: HttpRequest) -> HttpResponse:
    profile = _require_patient(request)
    summaries = AISummary.objects.for_patient(profile)
    log_event(
        actor=request.user,
        action="ai.insights_viewed",
        target=profile,
        summary_count=summaries.count(),
    )
    return render(request, "ai/patient_insights.html", {"summaries": summaries})


@login_required
@require_POST
def patient_generate_weekly(request: HttpRequest) -> HttpResponse:
    profile = _require_patient(request)

    # Modo individual = sem provider responsável → gate retorna NoFeature.
    provider = _resolve_provider_for_patient(profile)
    decision = check(provider, AIAction.WEEKLY_SUMMARY)
    if not isinstance(decision, Allowed):
        return _handle_blocked(request, decision, "ai:patient_insights")

    model = _model_for_provider(provider)
    compact = provider.plan == ProviderPlan.PRO

    try:
        summary = generate_weekly_summary(
            profile, actor=request.user, model=model, compact=compact
        )
    except AnthropicClientError as exc:
        messages.error(request, f"Geração indisponível: {exc}")
        return redirect("ai:patient_insights")

    record_usage(
        provider,
        AIAction.WEEKLY_SUMMARY,
        input_tokens=summary.token_metadata.get("input_tokens", 0),
        output_tokens=summary.token_metadata.get("output_tokens", 0),
        model=summary.model_used,
    )
    messages.success(request, "Resumo gerado.")
    return redirect("ai:patient_insights")


# ---------- profissional ----------


@login_required
@require_POST
def provider_generate_briefing(request: HttpRequest, patient_id: int) -> HttpResponse:
    profile = _require_provider(request)
    bond = Bond.objects.filter(
        provider=profile,
        patient_id=patient_id,
        status=BondStatus.ACTIVE,
    ).first()
    if bond is None:
        raise Http404("Paciente não encontrado entre seus vínculos ativos.")

    decision = check(profile, AIAction.SESSION_BRIEFING)
    if not isinstance(decision, Allowed):
        return _handle_blocked(
            request,
            decision,
            reverse("journal:provider_patient_detail", args=[patient_id]),
        )

    model = _model_for_provider(profile)
    compact = profile.plan == ProviderPlan.PRO

    try:
        summary = generate_session_briefing(
            bond, actor=request.user, model=model, compact=compact
        )
    except AnthropicClientError as exc:
        messages.error(request, f"Geração indisponível: {exc}")
        return redirect("journal:provider_patient_detail", patient_id=patient_id)

    record_usage(
        profile,
        AIAction.SESSION_BRIEFING,
        input_tokens=summary.token_metadata.get("input_tokens", 0),
        output_tokens=summary.token_metadata.get("output_tokens", 0),
        model=summary.model_used,
    )
    messages.success(request, "Briefing gerado.")
    return redirect("ai:provider_briefing_detail", patient_id=patient_id)


@login_required
def provider_briefing_detail(request: HttpRequest, patient_id: int) -> HttpResponse:
    profile = _require_provider(request)
    bond = (
        Bond.objects.filter(
            provider=profile,
            patient_id=patient_id,
            status=BondStatus.ACTIVE,
        )
        .select_related("patient__user")
        .first()
    )
    if bond is None:
        raise Http404("Paciente não encontrado entre seus vínculos ativos.")

    briefings = AISummary.objects.for_bond(bond)
    log_event(
        actor=request.user,
        action="ai.briefings_viewed",
        target=bond,
        briefing_count=briefings.count(),
    )
    return render(
        request,
        "ai/provider_briefing_detail.html",
        {"bond": bond, "briefings": briefings},
    )
