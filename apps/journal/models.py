"""Registros do diário do paciente.

CLAUDE.md regras críticas que se aplicam aqui:

- **Regra 2**: `content` é criptografado em nível de aplicação via
  django-cryptography-5 (ADR 0006). Mesmo administrador do banco
  ou backup vazado não consegue ler sem a chave.
- **Regra 3**: cada registro tem flag `is_shared_with_psychologist`,
  default `False` (privado). Compartilhamento é decisão consciente do
  paciente.
- **Regra 6/7**: queryset `shared_with_psychologist` filtra duplo —
  Bond ATIVO E flag de compartilhamento — e é fail-closed: ausência
  de bond ativo retorna queryset vazio.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.utils.translation import gettext_lazy as _
from django_cryptography.fields import encrypt

if TYPE_CHECKING:
    from apps.accounts.models import PatientProfile, PsychologistProfile


class MoodLevel(models.IntegerChoices):
    """Escala emocional do MVP — 5 níveis (vision.md: 'representações emocionais')."""

    VERY_SAD = 1, _("Muito triste 😢")
    SAD = 2, _("Triste ☹")
    NEUTRAL = 3, _("Neutro 😐")
    GOOD = 4, _("Bem 🙂")
    GREAT = 5, _("Muito bem 😊")


class MoodEntryQuerySet(models.QuerySet):
    def for_patient(self, profile: PatientProfile) -> MoodEntryQuerySet:
        return self.filter(patient=profile)

    def shared_with_psychologist(
        self, psychologist: PsychologistProfile
    ) -> MoodEntryQuerySet:
        """Entries visíveis ao psicólogo: dupla checagem.

        - Paciente precisa ter Bond ATIVO com este psicólogo.
        - Entry precisa estar marcada como `is_shared_with_psychologist`.

        Fail-closed: se o psicólogo não tem nenhum bond ativo, o
        queryset retorna vazio mesmo que existam entries shared.
        """
        from apps.bonds.models import Bond, BondStatus

        bonded_patient_ids = Bond.objects.filter(
            psychologist=psychologist,
            status=BondStatus.ACTIVE,
        ).values_list("patient_id", flat=True)

        return self.filter(
            patient_id__in=bonded_patient_ids,
            is_shared_with_psychologist=True,
        )


class MoodEntry(models.Model):
    patient = models.ForeignKey(
        "accounts.PatientProfile",
        on_delete=models.PROTECT,
        related_name="mood_entries",
        verbose_name=_("paciente"),
    )

    mood = models.IntegerField(
        _("humor"),
        choices=MoodLevel.choices,
    )

    # `content` armazenado criptografado em DB; transparent ao app.
    # blank=True permite registro só com escala emocional, sem texto.
    content = encrypt(models.TextField(_("conteúdo"), blank=True))

    is_shared_with_psychologist = models.BooleanField(
        _("compartilhar com psicólogo"),
        default=False,
        help_text=_(
            "Default privado — compartilhamento é decisão consciente do paciente."
        ),
    )

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    objects = MoodEntryQuerySet.as_manager()

    class Meta:
        verbose_name = _("registro de humor")
        verbose_name_plural = _("registros de humor")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["patient", "-created_at"]),
        ]

    def __str__(self) -> str:
        shared = "compartilhado" if self.is_shared_with_psychologist else "privado"
        return f"MoodEntry {self.id} ({self.get_mood_display()}, {shared})"
