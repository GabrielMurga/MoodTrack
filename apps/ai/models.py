"""AISummary — saídas da IA persistidas.

`content` é criptografado em nível de aplicação (CLAUDE.md regra 2)
porque é uma síntese feita a partir de dados sensíveis do paciente.

`token_metadata` contém apenas metadados (modelo, contagem de tokens)
— nunca o conteúdo da chamada (CLAUDE.md regra 15).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_cryptography.fields import encrypt


class AISummaryKind(models.TextChoices):
    WEEKLY_PATIENT = "weekly_patient", _("Resumo semanal (paciente)")
    SESSION_BRIEFING = "session_briefing", _("Briefing pré-sessão (psicólogo)")


class AISummaryQuerySet(models.QuerySet):
    def for_patient(self, profile) -> AISummaryQuerySet:
        """Resumos cuja audiência é o paciente (kind=WEEKLY_PATIENT)."""
        return self.filter(
            kind=AISummaryKind.WEEKLY_PATIENT,
            target_patient=profile,
        )

    def for_bond(self, bond) -> AISummaryQuerySet:
        """Briefings desse vínculo específico (kind=SESSION_BRIEFING)."""
        return self.filter(
            kind=AISummaryKind.SESSION_BRIEFING,
            target_bond=bond,
        )

    def for_psychologist(self, profile) -> AISummaryQuerySet:
        """Todos os briefings de bonds onde este psicólogo é dono."""
        return self.filter(
            kind=AISummaryKind.SESSION_BRIEFING,
            target_bond__psychologist=profile,
        )


class AISummary(models.Model):
    kind = models.CharField(
        _("tipo"),
        max_length=24,
        choices=AISummaryKind.choices,
    )

    # Apenas UM dos dois targets é usado por kind (validamos via clean()).
    target_patient = models.ForeignKey(
        "accounts.PatientProfile",
        on_delete=models.PROTECT,
        related_name="ai_summaries",
        null=True,
        blank=True,
        verbose_name=_("paciente alvo"),
    )
    target_bond = models.ForeignKey(
        "bonds.Bond",
        on_delete=models.PROTECT,
        related_name="ai_summaries",
        null=True,
        blank=True,
        verbose_name=_("vínculo alvo"),
    )

    content = encrypt(models.TextField(_("conteúdo")))
    period_start = models.DateTimeField(_("janela início"))
    period_end = models.DateTimeField(_("janela fim"))

    model_used = models.CharField(_("modelo"), max_length=64)
    token_metadata = models.JSONField(_("metadata de tokens"), default=dict)

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ai_summaries_requested",
        verbose_name=_("solicitado por"),
    )

    generated_at = models.DateTimeField(_("gerado em"), auto_now_add=True, db_index=True)

    objects = AISummaryQuerySet.as_manager()

    class Meta:
        verbose_name = _("resumo de IA")
        verbose_name_plural = _("resumos de IA")
        ordering = ("-generated_at",)
        constraints = [
            # Garante consistência: WEEKLY_PATIENT precisa de target_patient,
            # SESSION_BRIEFING precisa de target_bond.
            models.CheckConstraint(
                condition=(
                    models.Q(kind="weekly_patient", target_patient__isnull=False, target_bond__isnull=True)
                    | models.Q(kind="session_briefing", target_bond__isnull=False, target_patient__isnull=True)
                ),
                name="aisummary_kind_target_consistency",
            ),
        ]
        indexes = [
            models.Index(fields=["kind", "-generated_at"]),
        ]

    def __str__(self) -> str:
        target = self.target_patient or self.target_bond
        return f"AISummary#{self.id} [{self.get_kind_display()}] → {target}"
