"""Modelos do prontuário clínico — overview do paciente + medicações.

Três entidades pra o bloco fixo "Resumo + Medicações" (memory project_patient_overview_field):

- **PatientOverview**: visão consolidada do paciente. 1:1 com PatientProfile.
  Conteúdo livre, criptografado. Editável por qualquer profissional vinculado
  ativamente. **Paciente NÃO vê** (decisão de produto: o paciente não precisa
  ler "resumo clínico de si mesmo" gerado por outros).

- **Medication**: medicação prescrita. **Apenas psiquiatra** (kind=psychiatrist)
  pode criar/editar — fail-closed via clean() + CheckConstraint indireta.
  Paciente vê (read-only). Outros profissionais (psicólogos) vêm read-only.

- **PatientReportedMedication**: medicação que o paciente disse que toma.
  Distinta da prescrição — campo separado para preservar rastreabilidade.
  Paciente edita; profissionais vêm.

Regras inegociáveis aplicadas:
- Regra 2 (criptografia): conteúdos sensíveis criptografados via django_cryptography.
- Regra 5 (fail-closed): validação de prescrição em 3 camadas (form, model.clean,
  manager-level filtering nas views).
- Regra 8 (audit): edições registradas em apps.audit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_cryptography.fields import encrypt

if TYPE_CHECKING:
    from apps.accounts.models import HealthcareProvider, PatientProfile


# ---------------------------------------------------------------------------
# PatientOverview — resumo consolidado (visível só para profissionais)
# ---------------------------------------------------------------------------


class PatientOverviewQuerySet(models.QuerySet):
    def for_patient(self, patient: PatientProfile) -> PatientOverviewQuerySet:
        return self.filter(patient=patient)

    def for_provider(self, provider: HealthcareProvider) -> PatientOverviewQuerySet:
        """Overviews de pacientes vinculados ATIVAMENTE a este profissional."""
        from apps.bonds.models import Bond, BondStatus

        bonded_patient_ids = Bond.objects.filter(
            provider=provider,
            status=BondStatus.ACTIVE,
        ).values_list("patient_id", flat=True)
        return self.filter(patient_id__in=bonded_patient_ids)


class PatientOverview(models.Model):
    """Resumo consolidado do paciente — visão rápida para o profissional.

    1:1 com PatientProfile. O conteúdo é texto livre, editado por profissionais
    vinculados. **Paciente não vê.**
    """

    patient = models.OneToOneField(
        "accounts.PatientProfile",
        on_delete=models.CASCADE,
        related_name="overview",
        verbose_name=_("paciente"),
    )
    summary = encrypt(models.TextField(_("resumo"), blank=True))

    last_edited_by = models.ForeignKey(
        "accounts.HealthcareProvider",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="overviews_edited",
        verbose_name=_("último editor"),
        help_text=_("Profissional que editou o resumo pela última vez."),
    )

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    objects = PatientOverviewQuerySet.as_manager()

    class Meta:
        verbose_name = _("resumo do paciente")
        verbose_name_plural = _("resumos do paciente")

    def __str__(self) -> str:
        return f"PatientOverview de {self.patient}"


# ---------------------------------------------------------------------------
# Medication — prescrição (psiquiatra apenas)
# ---------------------------------------------------------------------------


class MedicationQuerySet(models.QuerySet):
    def for_patient(self, patient: PatientProfile) -> MedicationQuerySet:
        return self.filter(patient=patient)

    def active(self) -> MedicationQuerySet:
        """Medicações em uso (sem `ended_at`)."""
        return self.filter(ended_at__isnull=True)

    def visible_to_provider(self, provider: HealthcareProvider) -> MedicationQuerySet:
        """Medicações dos pacientes vinculados ATIVAMENTE a este profissional.

        Tanto psicólogo quanto psiquiatra podem ver (psicólogo precisa do
        contexto medicamentoso — humor/sono/energia podem ter causa farmacológica).
        Apenas psiquiatra pode criar/editar — fail-closed em `clean()`.
        """
        from apps.bonds.models import Bond, BondStatus

        bonded_patient_ids = Bond.objects.filter(
            provider=provider,
            status=BondStatus.ACTIVE,
        ).values_list("patient_id", flat=True)
        return self.filter(patient_id__in=bonded_patient_ids)


class Medication(models.Model):
    """Medicação prescrita pelo psiquiatra.

    Persistente: continua existindo mesmo após o vínculo (Bond) terminar —
    é histórico clínico do paciente. Por isso FK direto a PatientProfile,
    não a Bond. Campo `prescribed_by` registra qual psiquiatra prescreveu
    (referência histórica).

    Validação fail-closed: `prescribed_by.kind` deve ser `psychiatrist`,
    verificado em `clean()`. Tentativa de criação por psicólogo levanta
    ValidationError em qualquer camada que use `full_clean()` — view,
    form ou save() chamando full_clean.
    """

    patient = models.ForeignKey(
        "accounts.PatientProfile",
        on_delete=models.CASCADE,
        related_name="medications",
        verbose_name=_("paciente"),
    )
    prescribed_by = models.ForeignKey(
        "accounts.HealthcareProvider",
        on_delete=models.PROTECT,
        related_name="prescriptions",
        verbose_name=_("prescrito por"),
        help_text=_("Psiquiatra que fez a prescrição."),
    )

    # Conteúdos clínicos sensíveis (regra 2).
    name = encrypt(models.CharField(_("medicamento"), max_length=200))
    dosage = encrypt(models.CharField(_("dosagem"), max_length=120, blank=True))
    frequency = encrypt(models.CharField(_("frequência"), max_length=120, blank=True))
    notes = encrypt(models.TextField(_("observações"), blank=True))

    started_at = models.DateField(_("iniciada em"), null=True, blank=True)
    ended_at = models.DateField(
        _("descontinuada em"),
        null=True,
        blank=True,
        help_text=_("Vazio = em uso. Preencher quando descontinuar."),
    )

    created_at = models.DateTimeField(_("registrada em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizada em"), auto_now=True)

    objects = MedicationQuerySet.as_manager()

    class Meta:
        verbose_name = _("medicação prescrita")
        verbose_name_plural = _("medicações prescritas")
        ordering = ("-started_at", "-created_at")
        indexes = [
            models.Index(fields=["patient", "-started_at"]),
        ]

    def __str__(self) -> str:
        return f"Medication#{self.id} → patient={self.patient_id}"

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    def clean(self) -> None:
        """Fail-closed: apenas psiquiatra pode prescrever (regra 5).

        Não confiamos em forms ou views — a validação roda no model. Qualquer
        caminho que chame `full_clean()` (forms, admin, save explícito) bloqueia
        prescrição por não-psiquiatra.
        """
        super().clean()
        if self.prescribed_by_id is None:
            raise ValidationError(
                {"prescribed_by": _("Prescritor é obrigatório.")}
            )
        # `can_prescribe` é derivado de `kind` em HealthcareProvider.
        if not self.prescribed_by.can_prescribe:
            raise ValidationError(
                {
                    "prescribed_by": _(
                        "Apenas psiquiatra pode prescrever medicação."
                    )
                }
            )

    def save(self, *args, **kwargs) -> None:
        """Força full_clean antes de salvar.

        Em geral evitamos chamar full_clean em save (CLAUDE.md), mas aqui é
        defesa em profundidade contra criação direta de Medication por código
        que esqueça de passar pelo form. Custo: pequeno overhead em saves.
        """
        self.full_clean()
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# PatientReportedMedication — auto-reporte (paciente)
# ---------------------------------------------------------------------------


class PatientReportedMedicationQuerySet(models.QuerySet):
    def for_patient(self, patient: PatientProfile) -> PatientReportedMedicationQuerySet:
        return self.filter(patient=patient)

    def visible_to_provider(
        self, provider: HealthcareProvider
    ) -> PatientReportedMedicationQuerySet:
        from apps.bonds.models import Bond, BondStatus

        bonded_patient_ids = Bond.objects.filter(
            provider=provider,
            status=BondStatus.ACTIVE,
        ).values_list("patient_id", flat=True)
        return self.filter(patient_id__in=bonded_patient_ids)


class PatientReportedMedication(models.Model):
    """Auto-reporte do paciente — "o que estou tomando".

    Distinto da prescrição (Medication) por design (memory:
    project_patient_overview_field): preserva rastreabilidade clínica entre
    "psiquiatra prescreveu X" e "paciente disse que está tomando Y" (que
    podem divergir — paciente esquece, decide cortar, toma OTC etc.).

    Profissionais vinculados vêm read-only.
    """

    patient = models.ForeignKey(
        "accounts.PatientProfile",
        on_delete=models.CASCADE,
        related_name="reported_medications",
        verbose_name=_("paciente"),
    )
    content = encrypt(
        models.TextField(
            _("medicações que estou tomando"),
            help_text=_(
                "Liste o que está tomando — receitas atuais, OTC, suplementos. "
                "É auto-reporte; o profissional usa como contexto clínico."
            ),
        )
    )

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    objects = PatientReportedMedicationQuerySet.as_manager()

    class Meta:
        verbose_name = _("medicação auto-reportada")
        verbose_name_plural = _("medicações auto-reportadas")

    def __str__(self) -> str:
        return f"PatientReportedMedication de {self.patient}"
