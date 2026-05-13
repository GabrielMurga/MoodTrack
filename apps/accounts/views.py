"""Onboarding views — criação de perfil após login OAuth.

Fluxo: User logado mas sem `provider_profile` nem `patient_profile` →
`choose_profile` → `create_provider_profile` ou `create_patient_profile`.

Fail-closed (CLAUDE.md regra 5): se já tem o perfil que tenta criar,
redireciona pra dashboard correspondente em vez de duplicar.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from apps.audit.models import log_event

from .forms import PatientProfileForm, ProviderProfileForm
from .models import ProviderKind


@login_required
def choose_profile(request: HttpRequest) -> HttpResponse:
    """Tela de escolha — paciente ou profissional.

    Se já tem algum perfil, manda direto pra home (que rotea pra dashboard).
    """
    user = request.user
    if user.is_provider or user.is_patient:
        return redirect("bonds:home")
    return render(request, "accounts/choose_profile.html")


@login_required
def create_provider_profile(request: HttpRequest) -> HttpResponse:
    user = request.user

    # Já tem perfil de profissional → não duplicar.
    if user.is_provider:
        return redirect("bonds:provider_dashboard")

    if request.method == "POST":
        form = ProviderProfileForm(request.POST)
        if form.is_valid():
            provider = form.save(commit=False)
            provider.user = user
            provider.save()
            log_event(
                actor=user,
                action="provider_profile.created",
                target=provider,
                kind=provider.kind,
            )
            kind_label = (
                "Psicólogo" if provider.kind == ProviderKind.PSYCHOLOGIST else "Psiquiatra"
            )
            messages.success(
                request, f"Perfil de {kind_label} criado. Bem-vindo ao MoodTrack."
            )
            return redirect("bonds:provider_dashboard")
    else:
        form = ProviderProfileForm()

    return render(
        request,
        "accounts/provider_profile_form.html",
        {"form": form},
    )


@login_required
def create_patient_profile(request: HttpRequest) -> HttpResponse:
    user = request.user

    # Já tem perfil de paciente → não duplicar.
    if user.is_patient:
        return redirect("bonds:patient_dashboard")

    if request.method == "POST":
        form = PatientProfileForm(request.POST)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = user
            profile.save()
            log_event(
                actor=user,
                action="patient_profile.created",
                target=profile,
            )
            messages.success(request, "Perfil criado. Bem-vindo ao MoodTrack.")
            return redirect("bonds:patient_dashboard")
    else:
        form = PatientProfileForm()

    return render(
        request,
        "accounts/patient_profile_form.html",
        {"form": form},
    )
