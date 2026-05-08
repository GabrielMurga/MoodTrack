"""Views do diário e da clínica.

Aplicação rigorosa de:
- CLAUDE.md regra 5: fail-closed em toda view.
- Regra 6/7: queryset filtra antes da view tocar (manager).
- Regra 8: cada operação sensível gera audit; leitura também conta.

Observações importantes de visibilidade:
- ClinicalNote é UNILATERAL — só o psicólogo dono enxerga.
- JournalEntry/MoodLog do paciente: psicólogo só vê se shared E se tem
  bond ATIVO ao paciente.
- Acesso via URL direta a recursos fora do escopo de perfil → 404.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.audit.models import log_event
from apps.bonds.models import Bond, BondStatus

from .forms import ClinicalNoteForm, JournalEntryForm, MoodLogForm
from .models import ClinicalNote, JournalEntry, MoodLog

# ---------- helpers ----------

def _require_patient(request: HttpRequest):
    if not request.user.is_patient:
        raise Http404("Perfil de paciente não encontrado.")
    return request.user.patient_profile


def _require_psychologist(request: HttpRequest):
    if not request.user.is_psychologist:
        raise Http404("Perfil de psicólogo não encontrado.")
    return request.user.psychologist_profile


def _bond_or_404_for_psych(psych, patient_id: int) -> Bond:
    """Retorna Bond ATIVO entre psicólogo logado e patient_id, ou 404."""
    bond = (
        Bond.objects.filter(
            psychologist=psych,
            patient_id=patient_id,
            status=BondStatus.ACTIVE,
        )
        .select_related("patient__user")
        .first()
    )
    if bond is None:
        raise Http404("Paciente não encontrado entre seus vínculos ativos.")
    return bond


# ===========================================================================
# Paciente — calendário de humor (MoodLog)
# ===========================================================================


@login_required
def patient_mood_list(request: HttpRequest) -> HttpResponse:
    profile = _require_patient(request)
    logs = MoodLog.objects.for_patient(profile)
    return render(request, "journal/patient_mood_list.html", {"logs": logs})


@login_required
def patient_mood_create(request: HttpRequest) -> HttpResponse:
    profile = _require_patient(request)
    if request.method == "POST":
        form = MoodLogForm(request.POST)
        if form.is_valid():
            log = form.save(commit=False)
            log.patient = profile
            log.save()
            log_event(
                actor=request.user,
                action="mood_log.created",
                target=log,
                shared=log.is_shared_with_psychologist,
                mood=log.mood,
            )
            messages.success(request, "Humor registrado.")
            return redirect("journal:patient_mood_list")
    else:
        form = MoodLogForm()
    return render(request, "journal/patient_mood_form.html", {"form": form})


@login_required
@require_POST
def patient_mood_toggle_share(request: HttpRequest, log_id: int) -> HttpResponse:
    profile = _require_patient(request)
    log = get_object_or_404(MoodLog.objects.for_patient(profile), pk=log_id)
    log.is_shared_with_psychologist = not log.is_shared_with_psychologist
    log.save(update_fields=["is_shared_with_psychologist"])
    log_event(
        actor=request.user,
        action="mood_log.share_toggled",
        target=log,
        shared=log.is_shared_with_psychologist,
    )
    return redirect("journal:patient_mood_list")


# ===========================================================================
# Paciente — diário de eventos (JournalEntry)
# ===========================================================================


@login_required
def patient_journal_list(request: HttpRequest) -> HttpResponse:
    profile = _require_patient(request)
    entries = JournalEntry.objects.for_patient(profile)
    return render(request, "journal/patient_journal_list.html", {"entries": entries})


@login_required
def patient_journal_create(request: HttpRequest) -> HttpResponse:
    profile = _require_patient(request)
    if request.method == "POST":
        form = JournalEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.patient = profile
            entry.save()
            log_event(
                actor=request.user,
                action="journal_entry.created",
                target=entry,
                kind=entry.kind,
                shared=entry.is_shared_with_psychologist,
            )
            messages.success(request, "Registro salvo.")
            return redirect("journal:patient_journal_list")
    else:
        form = JournalEntryForm()
    return render(request, "journal/patient_journal_form.html", {"form": form, "mode": "create"})


@login_required
def patient_journal_edit(request: HttpRequest, entry_id: int) -> HttpResponse:
    profile = _require_patient(request)
    entry = get_object_or_404(JournalEntry.objects.for_patient(profile), pk=entry_id)
    if request.method == "POST":
        form = JournalEntryForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            log_event(
                actor=request.user,
                action="journal_entry.edited",
                target=entry,
                fields=list(form.changed_data),
            )
            messages.success(request, "Registro atualizado.")
            return redirect("journal:patient_journal_list")
    else:
        form = JournalEntryForm(instance=entry)
    return render(
        request,
        "journal/patient_journal_form.html",
        {"form": form, "mode": "edit", "entry": entry},
    )


@login_required
@require_POST
def patient_journal_toggle_share(request: HttpRequest, entry_id: int) -> HttpResponse:
    profile = _require_patient(request)
    entry = get_object_or_404(JournalEntry.objects.for_patient(profile), pk=entry_id)
    entry.is_shared_with_psychologist = not entry.is_shared_with_psychologist
    entry.save(update_fields=["is_shared_with_psychologist", "updated_at"])
    log_event(
        actor=request.user,
        action="journal_entry.share_toggled",
        target=entry,
        shared=entry.is_shared_with_psychologist,
    )
    return redirect("journal:patient_journal_list")


# ===========================================================================
# Psicólogo — pacientes e timeline
# ===========================================================================


@login_required
def psychologist_patient_list(request: HttpRequest) -> HttpResponse:
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
    """Timeline do paciente para o psicólogo.

    Mostra:
    - MoodLogs shared (filtro duplo: bond ativo + flag)
    - JournalEntries shared (filtro duplo)
    - ClinicalNotes próprias do psicólogo (visibilidade unilateral)

    Acesso via URL direta a paciente não-bonded → 404.
    """
    profile = _require_psychologist(request)
    bond = _bond_or_404_for_psych(profile, patient_id)

    mood_logs = MoodLog.objects.shared_with_psychologist(profile).filter(
        patient_id=patient_id
    )
    journal_entries = JournalEntry.objects.shared_with_psychologist(profile).filter(
        patient_id=patient_id
    )
    clinical_notes = ClinicalNote.objects.for_bond(bond)

    log_event(
        actor=request.user,
        action="patient_timeline.viewed",
        target=bond.patient,
        mood_log_count=mood_logs.count(),
        journal_entry_count=journal_entries.count(),
        clinical_note_count=clinical_notes.count(),
    )

    return render(
        request,
        "journal/psychologist_patient_detail.html",
        {
            "bond": bond,
            "patient": bond.patient,
            "mood_logs": mood_logs,
            "journal_entries": journal_entries,
            "clinical_notes": clinical_notes,
        },
    )


# ===========================================================================
# Psicólogo — anotações clínicas
# ===========================================================================


@login_required
def clinical_note_create(request: HttpRequest, patient_id: int) -> HttpResponse:
    profile = _require_psychologist(request)
    bond = _bond_or_404_for_psych(profile, patient_id)

    if request.method == "POST":
        form = ClinicalNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.bond = bond
            note.save()
            log_event(
                actor=request.user,
                action="clinical_note.created",
                target=note,
                bond_id=bond.id,
            )
            messages.success(request, "Anotação salva.")
            return redirect("journal:psychologist_patient_detail", patient_id=patient_id)
    else:
        form = ClinicalNoteForm()

    return render(
        request,
        "journal/clinical_note_form.html",
        {"form": form, "bond": bond, "mode": "create"},
    )


@login_required
def clinical_note_edit(request: HttpRequest, note_id: int) -> HttpResponse:
    profile = _require_psychologist(request)
    note = get_object_or_404(
        ClinicalNote.objects.for_psychologist(profile),
        pk=note_id,
    )
    if request.method == "POST":
        form = ClinicalNoteForm(request.POST, instance=note)
        if form.is_valid():
            form.save()
            log_event(
                actor=request.user,
                action="clinical_note.edited",
                target=note,
                fields=list(form.changed_data),
            )
            messages.success(request, "Anotação atualizada.")
            return redirect(
                "journal:psychologist_patient_detail", patient_id=note.bond.patient_id
            )
    else:
        form = ClinicalNoteForm(instance=note)

    return render(
        request,
        "journal/clinical_note_form.html",
        {"form": form, "bond": note.bond, "mode": "edit", "note": note},
    )
