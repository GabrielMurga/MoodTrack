"""Views do app bonds.

Cada view aplica fail-closed (CLAUDE.md regra 5): permissão derivada do
perfil do usuário, queryset filtrado pelo manager `for_user/for_psychologist
/for_patient` antes de qualquer lógica. Tentativa de operar em Bond fora
do escopo do perfil retorna 404 (não 403, para não vazar existência).
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import EnterInviteCodeForm
from .models import Bond, BondStatus, InvalidBondTransition

# ---------- helpers ----------

def _require_psychologist(request: HttpRequest):
    if not request.user.is_psychologist:
        from django.http import Http404

        raise Http404("Perfil de psicólogo não encontrado.")
    return request.user.psychologist_profile


def _require_patient(request: HttpRequest):
    if not request.user.is_patient:
        from django.http import Http404

        raise Http404("Perfil de paciente não encontrado.")
    return request.user.patient_profile


# ---------- home/router ----------

@login_required
def home(request: HttpRequest) -> HttpResponse:
    """Roteia o usuário para o dashboard adequado.

    Se tem ambos perfis, default para psicólogo (decisão arbitrária; troca
    explícita pela nav).
    """
    user = request.user
    if user.is_psychologist:
        return redirect("bonds:psychologist_dashboard")
    if user.is_patient:
        return redirect("bonds:patient_dashboard")
    return render(request, "bonds/no_profile.html", status=200)


# ---------- psicólogo ----------

@login_required
def psychologist_dashboard(request: HttpRequest) -> HttpResponse:
    profile = _require_psychologist(request)
    bonds = Bond.objects.for_psychologist(profile).order_by("-invited_at")
    return render(
        request,
        "bonds/psychologist_dashboard.html",
        {"bonds": bonds, "BondStatus": BondStatus},
    )


@login_required
@require_POST
def create_invite(request: HttpRequest) -> HttpResponse:
    profile = _require_psychologist(request)
    bond = Bond.objects.create(psychologist=profile)
    messages.success(
        request,
        f"Convite gerado. Código: {bond.invite_code}",
    )
    return redirect("bonds:psychologist_dashboard")


@login_required
@require_POST
def confirm_bond(request: HttpRequest, bond_id: int) -> HttpResponse:
    profile = _require_psychologist(request)
    bond = get_object_or_404(
        Bond.objects.for_psychologist(profile),
        pk=bond_id,
    )
    try:
        bond.confirm()
    except InvalidBondTransition as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Vínculo confirmado.")
    return redirect("bonds:psychologist_dashboard")


# ---------- paciente ----------

@login_required
def patient_dashboard(request: HttpRequest) -> HttpResponse:
    profile = _require_patient(request)
    alive_bond = Bond.objects.for_patient(profile).alive().first()
    form = EnterInviteCodeForm() if alive_bond is None else None
    return render(
        request,
        "bonds/patient_dashboard.html",
        {"bond": alive_bond, "form": form, "BondStatus": BondStatus},
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
    if request.user.is_psychologist:
        return redirect("bonds:psychologist_dashboard")
    return redirect("bonds:patient_dashboard")
