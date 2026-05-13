"""AISummary — saídas da IA persistidas.

`content` é criptografado em nível de aplicação (CLAUDE.md regra 2)
porque é uma síntese feita a partir de dados sensíveis do paciente.

`token_metadata` contém apenas metadados (modelo, contagem de tokens)
— nunca o conteúdo da chamada (CLAUDE.md regra 15).
"""

from __future__ import annotations

from decimal import Decimal

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

    def for_provider(self, profile) -> AISummaryQuerySet:
        """Todos os briefings de bonds onde este profissional é dono."""
        return self.filter(
            kind=AISummaryKind.SESSION_BRIEFING,
            target_bond__provider=profile,
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
                    models.Q(
                        kind="weekly_patient",
                        target_patient__isnull=False,
                        target_bond__isnull=True,
                    )
                    | models.Q(
                        kind="session_briefing",
                        target_bond__isnull=False,
                        target_patient__isnull=True,
                    )
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


class AIUsageCounter(models.Model):
    """Contador mensal de uso de IA por profissional (ADR 0010).

    Uma linha por (provider, primeiro dia do mês). Incrementado a cada
    operação de IA bem-sucedida via `apps.ai.access.record_usage`.

    Coarse-grained por design: detalhamento por chamada já existe em
    `apps.audit` (CLAUDE.md regra 8/15). Este contador serve para
    comparação rápida contra o limite do plano sem fazer COUNT em audit.
    """

    provider = models.ForeignKey(
        "accounts.HealthcareProvider",
        on_delete=models.CASCADE,
        related_name="ai_usage_counters",
        verbose_name=_("profissional"),
    )
    period = models.DateField(
        _("período (1º dia do mês)"),
        db_index=True,
        help_text=_(
            "Primeiro dia do mês a que se refere a contagem. "
            "Reset implícito: novo mês = nova linha."
        ),
    )
    count = models.PositiveIntegerField(_("usos no período"), default=0)
    cost_brl = models.DecimalField(
        _("custo acumulado (R$)"),
        max_digits=10,
        decimal_places=6,
        default=Decimal("0"),
        help_text=_("Custo total de chamadas à LLM no período, em reais."),
    )

    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("contador de uso de IA")
        verbose_name_plural = _("contadores de uso de IA")
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "period"],
                name="unique_ai_usage_counter_per_period",
            ),
        ]
        indexes = [
            models.Index(fields=["provider", "-period"]),
        ]

    def __str__(self) -> str:
        return f"AIUsageCounter[{self.provider_id} @ {self.period:%Y-%m}] = {self.count}"
