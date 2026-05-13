"""Views do app bonds.

Cada view aplica fail-closed (CLAUDE.md regra 5): permissão derivada do
perfil do usuário, queryset filtrado pelo manager `for_user/for_provider
/for_patient` antes de qualquer lógica. Tentativa de operar em Bond fora
do escopo do perfil retorna 404 (não 403, para não vazar existência).
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.clinical.models import Medication, PatientReportedMedication

from .forms import CreateInviteForm, EnterInviteCodeForm
from .models import Bond, BondStatus, InvalidBondTransition

# ---------- helpers ----------


def _require_provider(request: HttpRequest):
    if not request.user.is_provider:
        from django.http import Http404

        raise Http404("Perfil de profissional não encontrado.")
    return request.user.provider_profile


def _require_patient(request: HttpRequest):
    if not request.user.is_patient:
        from django.http import Http404

        raise Http404("Perfil de paciente não encontrado.")
    return request.user.patient_profile


# ---------- home/router ----------


@login_required
def home(request: HttpRequest) -> HttpResponse:
    """Roteia o usuário para o dashboard adequado.

    Se tem ambos perfis, default para profissional (decisão arbitrária; troca
    explícita pela nav). Se não tem nenhum, manda pro onboarding.
    """
    user = request.user
    if user.is_provider:
        return redirect("bonds:provider_dashboard")
    if user.is_patient:
        return redirect("bonds:patient_dashboard")
    return redirect("accounts:choose_profile")


# ---------- profissional ----------


@login_required
def provider_dashboard(request: HttpRequest) -> HttpResponse:
    profile = _require_provider(request)
    bonds = Bond.objects.for_provider(profile).order_by("-invited_at")
    return render(
        request,
        "bonds/provider_dashboard.html",
        {
            "bonds": bonds,
            "BondStatus": BondStatus,
            "invite_form": CreateInviteForm(),
        },
    )


@login_required
@require_POST
def create_invite(request: HttpRequest) -> HttpResponse:
    profile = _require_provider(request)
    form = CreateInviteForm(request.POST)
    if not form.is_valid():
        bonds = Bond.objects.for_provider(profile).order_by("-invited_at")
        return render(
            request,
            "bonds/provider_dashboard.html",
            {"bonds": bonds, "BondStatus": BondStatus, "invite_form": form},
        )

    bond = form.save(commit=False)
    bond.provider = profile
    bond.save()

    label_suffix = f" para {bond.invitee_label}" if bond.invitee_label else ""
    messages.success(
        request,
        f"Convite gerado{label_suffix}. Código: {bond.invite_code}",
    )
    return redirect("bonds:provider_dashboard")


@login_required
@require_POST
def confirm_bond(request: HttpRequest, bond_id: int) -> HttpResponse:
    profile = _require_provider(request)
    bond = get_object_or_404(
        Bond.objects.for_provider(profile),
        pk=bond_id,
    )
    try:
        bond.confirm()
    except InvalidBondTransition as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Vínculo confirmado.")
    return redirect("bonds:provider_dashboard")


# ---------- paciente ----------


@login_required
def patient_dashboard(request: HttpRequest) -> HttpResponse:
    profile = _require_patient(request)
    alive_bond = Bond.objects.for_patient(profile).alive().first()
    form = EnterInviteCodeForm() if alive_bond is None else None
    medications = Medication.objects.for_patient(profile).active().select_related(
        "prescribed_by__user"
    )
    reported_medication = (
        PatientReportedMedication.objects.for_patient(profile).order_by("-updated_at").first()
    )
    return render(
        request,
        "bonds/patient_dashboard.html",
        {
            "bond": alive_bond,
            "form": form,
            "BondStatus": BondStatus,
            "medications": medications,
            "reported_medication": reported_medication,
        },
    )


@login_required
@require_POST
def enter_invite(request: HttpRequest) -> HttpResponse:
    profile = _require_patient(request)

    if Bond.objects.for_patient(profile).alive().exists():
        messages.error(request, "Você já tem um vínculo em andamento.")
        return redirect("bonds:patient_dashboard")

    form = EnterInviteCodeForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "bonds/patient_dashboard.html",
            {"bond": None, "form": form, "BondStatus": BondStatus},
        )

    bond = form.bond
    try:
        bond.accept_invite(profile)
    except InvalidBondTransition as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Código aceito. Aguardando confirmação do psicólogo.")
    return redirect("bonds:patient_dashboard")


# ---------- ações comuns (encerrar de qualquer lado) ----------


@login_required
@require_POST
def end_bond(request: HttpRequest, bond_id: int) -> HttpResponse:
    bond = get_object_or_404(Bond.objects.for_user(request.user), pk=bond_id)
    try:
        bond.end(by_user=request.user)
    except InvalidBondTransition as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Vínculo encerrado.")
    return _back_to_dashboard(request)


def _back_to_dashboard(request: HttpRequest) -> HttpResponseRedirect:
    if request.user.is_provider:
        return redirect("bonds:provider_dashboard")
    return redirect("bonds:patient_dashboard")
