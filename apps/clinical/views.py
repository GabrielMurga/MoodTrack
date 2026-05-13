"""Views do prontuário clínico — medicações prescritas e auto-relatadas.

Regras aplicadas:
- Regra 5 (fail-closed): psicólogo tentando prescrever → 404.
- Regra 6: queryset filtrado por bond ativo antes de qualquer lógica.
- Regra 8: toda operação gera audit log.
- Regra 9: toda entrada passa por ModelForm antes de tocar o banco.
"""

from __future__ import annotations

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.audit.models import log_event
from apps.bonds.models import Bond, BondStatus

from .forms import MedicationForm, PatientReportedMedicationForm
from .models import Medication, PatientReportedMedication


def _require_provider(request: HttpRequest):
    if not request.user.is_provider:
        raise Http404("Perfil de profissional não encontrado.")
    return request.user.provider_profile


def _require_patient(request: HttpRequest):
    if not request.user.is_patient:
        raise Http404("Perfil de paciente não encontrado.")
    return request.user.patient_profile


def _require_psychiatrist(request: HttpRequest):
    provider = _require_provider(request)
    if not provider.can_prescribe:
        raise Http404("Apenas psiquiatra pode gerenciar prescrições.")
    return provider


def _bond_or_404(provider, patient_id: int) -> Bond:
    bond = (
        Bond.objects.filter(
            provider=provider,
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
# Psiquiatra — gerenciar prescrições
# ===========================================================================


@login_required
def medication_create(request: HttpRequest, patient_id: int) -> HttpResponse:
    provider = _require_psychiatrist(request)
    bond = _bond_or_404(provider, patient_id)
    patient = bond.patient

    # Instância pré-preenchida para que Medication.clean() valide can_prescribe
    # corretamente durante form._post_clean() — prescribed_by precisa estar
    # definido antes de is_valid() rodar.
    stub = Medication(patient=patient, prescribed_by=provider)
    if request.method == "POST":
        form = MedicationForm(request.POST, instance=stub)
        if form.is_valid():
            med = form.save()
            log_event(
                actor=request.user,
                action="medication.created",
                target=med,
                patient_id=patient.pk,
                provider_id=provider.pk,
            )
            messages.success(request, "Medicação registrada.")
            return redirect("journal:provider_patient_detail", patient_id=patient_id)
    else:
        form = MedicationForm(instance=stub)

    return render(
        request,
        "clinical/medication_form.html",
        {"form": form, "patient": patient, "mode": "create"},
    )


@login_required
def medication_edit(request: HttpRequest, medication_id: int) -> HttpResponse:
    provider = _require_psychiatrist(request)
    med = get_object_or_404(
        Medication.objects.filter(prescribed_by=provider),
        pk=medication_id,
    )

    if request.method == "POST":
        form = MedicationForm(request.POST, instance=med)
        if form.is_valid():
            form.save()
            log_event(
                actor=request.user,
                action="medication.edited",
                target=med,
                fields=list(form.changed_data),
            )
            messages.success(request, "Medicação atualizada.")
            return redirect("journal:provider_patient_detail", patient_id=med.patient_id)
    else:
        form = MedicationForm(instance=med)

    return render(
        request,
        "clinical/medication_form.html",
        {"form": form, "patient": med.patient, "mode": "edit", "med": med},
    )


@login_required
@require_POST
def medication_discontinue(request: HttpRequest, medication_id: int) -> HttpResponse:
    provider = _require_psychiatrist(request)
    med = get_object_or_404(
        Medication.objects.filter(prescribed_by=provider, ended_at__isnull=True),
        pk=medication_id,
    )
    med.ended_at = date.today()
    med.save(update_fields=["ended_at", "updated_at"])
    log_event(
        actor=request.user,
        action="medication.discontinued",
        target=med,
        patient_id=med.patient_id,
    )
    messages.success(request, "Medicação descontinuada.")
    return redirect("journal:provider_patient_detail", patient_id=med.patient_id)


# ===========================================================================
# Paciente — auto-reporte de medicações
# ===========================================================================


@login_required
def patient_reported_medication(request: HttpRequest) -> HttpResponse:
    """Paciente adiciona/consulta suas medicações auto-relatadas."""
    profile = _require_patient(request)
    reports = PatientReportedMedication.objects.for_patient(profile).order_by("-updated_at")

    if request.method == "POST":
        form = PatientReportedMedicationForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.patient = profile
            report.save()
            log_event(
                actor=request.user,
                action="patient_reported_medication.created",
                target=report,
            )
            messages.success(request, "Registro salvo.")
            return redirect("bonds:patient_dashboard")
    else:
        form = PatientReportedMedicationForm()

    return render(
        request,
        "clinical/patient_reported_medication_form.html",
        {"form": form, "reports": reports},
    )
