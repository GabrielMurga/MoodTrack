"""Views da camada de IA.

Cada view:
- exige login + perfil correto (fail-closed)
- valida ownership/visibilidade do alvo
- chama task de geração com `actor=request.user`
- captura `AnthropicClientError` e mostra erro amigável (sem expor detalhes)
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.audit.models import log_event
from apps.bonds.models import Bond, BondStatus

from .anthropic_client import AnthropicClientError
from .models import AISummary
from .tasks import generate_session_briefing, generate_weekly_summary


def _require_patient(request: HttpRequest):
    if not request.user.is_patient:
        raise Http404("Perfil de paciente não encontrado.")
    return request.user.patient_profile


def _require_psychologist(request: HttpRequest):
    if not request.user.is_psychologist:
        raise Http404("Perfil de psicólogo não encontrado.")
    return request.user.psychologist_profile


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
    try:
        generate_weekly_summary(profile, actor=request.user)
    except AnthropicClientError as exc:
        messages.error(request, f"Geração indisponível: {exc}")
        return redirect("ai:patient_insights")

    messages.success(request, "Resumo gerado.")
    return redirect("ai:patient_insights")


# ---------- psicólogo ----------


@login_required
@require_POST
def psychologist_generate_briefing(request: HttpRequest, patient_id: int) -> HttpResponse:
    profile = _require_psychologist(request)
    bond = (
        Bond.objects.filter(
            psychologist=profile,
            patient_id=patient_id,
            status=BondStatus.ACTIVE,
        )
        .first()
    )
    if bond is None:
        raise Http404("Paciente não encontrado entre seus vínculos ativos.")

    try:
        generate_session_briefing(bond, actor=request.user)
    except AnthropicClientError as exc:
        messages.error(request, f"Geração indisponível: {exc}")
        return redirect("journal:psychologist_patient_detail", patient_id=patient_id)

    messages.success(request, "Briefing gerado.")
    return redirect("ai:psychologist_briefing_detail", patient_id=patient_id)


@login_required
def psychologist_briefing_detail(request: HttpRequest, patient_id: int) -> HttpResponse:
    profile = _require_psychologist(request)
    bond = (
        Bond.objects.filter(
            psychologist=profile,
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
        "ai/psychologist_briefing_detail.html",
        {"bond": bond, "briefings": briefings},
    )
