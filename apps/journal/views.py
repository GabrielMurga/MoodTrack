"""Views do diário (journal).

Aplica fail-closed (CLAUDE.md regra 5) e auditoria (regra 8) em todas
as operações sensíveis. Acesso de psicólogo a entries de paciente
**também é auditado** — leitura é operação sensível por definição.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import PatientProfile
from apps.audit.models import log_event
from apps.bonds.models import Bond, BondStatus

from .forms import MoodEntryForm
from .models import MoodEntry

# ---------- helpers ----------

def _require_patient(request: HttpRequest) -> PatientProfile:
    if not request.user.is_patient:
        raise Http404("Perfil de paciente não encontrado.")
    return request.user.patient_profile


def _require_psychologist(request: HttpRequest):
    if not request.user.is_psychologist:
        raise Http404("Perfil de psicólogo não encontrado.")
    return request.user.psychologist_profile


# ---------- paciente ----------

@login_required
def patient_journal_list(request: HttpRequest) -> HttpResponse:
    profile = _require_patient(request)
    entries = MoodEntry.objects.for_patient(profile)
    return render(
        request,
        "journal/patient_list.html",
        {"entries": entries},
    )


@login_required
def patient_journal_create(request: HttpRequest) -> HttpResponse:
    profile = _require_patient(request)
    if request.method == "POST":
        form = MoodEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.patient = profile
            entry.save()
            log_event(
                actor=request.user,
                action="mood_entry.created",
                target=entry,
                shared=entry.is_shared_with_psychologist,
            )
            messages.success(request, "Registro salvo.")
            return redirect("journal:patient_list")
    else:
        form = MoodEntryForm()
    return render(request, "journal/patient_form.html", {"form": form, "mode": "create"})


@login_required
def patient_journal_edit(request: HttpRequest, entry_id: int) -> HttpResponse:
    profile = _require_patient(request)
    entry = get_object_or_404(MoodEntry.objects.for_patient(profile), pk=entry_id)
    if request.method == "POST":
        form = MoodEntryForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            log_event(
                actor=request.user,
                action="mood_entry.edited",
                target=entry,
                fields=list(form.changed_data),
            )
            messages.success(request, "Registro atualizado.")
            return redirect("journal:patient_list")
    else:
        form = MoodEntryForm(instance=entry)
    return render(request, "journal/patient_form.html", {"form": form, "mode": "edit", "entry": entry})


@login_required
@require_POST
def patient_journal_toggle_share(request: HttpRequest, entry_id: int) -> HttpResponse:
    profile = _require_patient(request)
    entry = get_object_or_404(MoodEntry.objects.for_patient(profile), pk=entry_id)
    entry.is_shared_with_psychologist = not entry.is_shared_with_psychologist
    entry.save(update_fields=["is_shared_with_psychologist", "updated_at"])
    log_event(
        actor=request.user,
        action="mood_entry.share_toggled",
        target=entry,
        shared=entry.is_shared_with_psychologist,
    )
    if entry.is_shared_with_psychologist:
        messages.success(request, "Registro compartilhado com o psicólogo.")
    else:
        messages.success(request, "Registro voltou a ser privado.")
    return redirect("journal:patient_list")


# ---------- psicólogo ----------

@login_required
def psychologist_patient_list(request: HttpRequest) -> HttpResponse:
    """Lista pacientes com bond ATIVO ao psicólogo logado."""
    profile = _require_psychologist(request)
    active_bonds = (
        Bond.objects.filter(psychologist=profile, status=BondStatus.ACTIVE)
        .select_related("patient__user")
    )
    return render(
        request,
        "journal/psychologist_patient_list.html",
        {"bonds": active_bonds},
    )


@login_required
def psychologist_patient_detail(request: HttpRequest, patient_id: int) -> HttpResponse:
    """Timeline de entries shared do paciente.

    Fail-closed em duas camadas:
    1. Bond ATIVO precisa existir entre psicólogo logado e paciente.
    2. MoodEntry.shared_with_psychologist filtra duplo (bond ativo + flag).

    Se passo 1 falha: 404 (não 403, pra não vazar existência).
    """
    profile = _require_psychologist(request)

    bond = Bond.objects.filter(
        psychologist=profile,
        patient_id=patient_id,
        status=BondStatus.ACTIVE,
    ).select_related("patient__user").first()
    if bond is None:
        raise Http404("Paciente não encontrado entre seus vínculos ativos.")

    entries = MoodEntry.objects.shared_with_psychologist(profile).filter(
        patient_id=patient_id
    )

    log_event(
        actor=request.user,
        action="patient_timeline.viewed",
        target=bond.patient,
        entry_count=entries.count(),
    )

    return render(
        request,
        "journal/psychologist_patient_detail.html",
        {"bond": bond, "patient": bond.patient, "entries": entries},
    )
