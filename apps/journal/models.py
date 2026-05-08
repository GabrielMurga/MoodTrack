"""Modelos do diário e da clínica.

Três entidades, três audiências, três regras de visibilidade:

- **MoodLog** (paciente): toque rápido na cara — humor 1-5, momento.
  Sem texto. Calendário de humor. Default privado, paciente toggle compartilhamento.

- **JournalEntry** (paciente): acontecimento, pensamento, sonho, reflexão.
  Texto criptografado. Humor opcional (FK / null). Default privado.

- **ClinicalNote** (psicólogo): anotação clínica sobre o paciente.
  Sempre criptografada. **Visibilidade unilateral**: só o psicólogo dono
  enxerga. Paciente nunca vê. Padrão clínico real.

CLAUDE.md regras críticas que se aplicam:
- Regra 2: content sempre criptografado em nível de aplicação.
- Regra 3: cada registro tem flag `is_shared_with_psychologist` (default False)
  exceto ClinicalNote, que tem regra de visibilidade própria.
- Regras 6/7: querysets filtram por dono antes da view tocar.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.utils.translation import gettext_lazy as _
from django_cryptography.fields import encrypt

if TYPE_CHECKING:
    from apps.accounts.models import PatientProfile, PsychologistProfile
    from apps.bonds.models import Bond


class MoodLevel(models.IntegerChoices):
    """Escala emocional 1-5 com emojis (vision.md: 'representações emocionais')."""

    VERY_SAD = 1, _("Muito triste 😢")
    SAD = 2, _("Triste ☹")
    NEUTRAL = 3, _("Neutro 😐")
    GOOD = 4, _("Bem 🙂")
    GREAT = 5, _("Muito bem 😊")


# ---------------------------------------------------------------------------
# MoodLog — calendário de humor, sem texto
# ---------------------------------------------------------------------------


class MoodLogQuerySet(models.QuerySet):
    def for_patient(self, profile: PatientProfile) -> MoodLogQuerySet:
        return self.filter(patient=profile)

    def shared_with_psychologist(
        self, psychologist: PsychologistProfile
    ) -> MoodLogQuerySet:
        from apps.bonds.models import Bond, BondStatus

        bonded_patient_ids = Bond.objects.filter(
            psychologist=psychologist,
            status=BondStatus.ACTIVE,
        ).values_list("patient_id", flat=True)
        return self.filter(
            patient_id__in=bonded_patient_ids,
            is_shared_with_psychologist=True,
        )


class MoodLog(models.Model):
    patient = models.ForeignKey(
        "accounts.PatientProfile",
        on_delete=models.PROTECT,
        related_name="mood_logs",
        verbose_name=_("paciente"),
    )
    mood = models.IntegerField(_("humor"), choices=MoodLevel.choices)
    is_shared_with_psychologist = models.BooleanField(
        _("compartilhar com psicólogo"),
        default=False,
    )
    recorded_at = models.DateTimeField(_("registrado em"), auto_now_add=True, db_index=True)

    objects = MoodLogQuerySet.as_manager()

    class Meta:
        verbose_name = _("registro de humor")
        verbose_name_plural = _("registros de humor")
        ordering = ("-recorded_at",)
        indexes = [
            models.Index(fields=["patient", "-recorded_at"]),
        ]

    def __str__(self) -> str:
        return f"MoodLog#{self.id} {self.get_mood_display()} @ {self.recorded_at:%Y-%m-%d %H:%M}"


# ---------------------------------------------------------------------------
# JournalEntry — acontecimento / pensamento / sonho / reflexão
# ---------------------------------------------------------------------------


class JournalEntryKind(models.TextChoices):
    SITUATION = "situation", _("Situação vivida")
    THOUGHT = "thought", _("Pensamento")
    DREAM = "dream", _("Sonho")
    REFLECTION = "reflection", _("Reflexão")


class JournalEntryQuerySet(models.QuerySet):
    def for_patient(self, profile: PatientProfile) -> JournalEntryQuerySet:
        return self.filter(patient=profile)

    def shared_with_psychologist(
        self, psychologist: PsychologistProfile
    ) -> JournalEntryQuerySet:
        from apps.bonds.models import Bond, BondStatus

        bonded_patient_ids = Bond.objects.filter(
            psychologist=psychologist,
            status=BondStatus.ACTIVE,
        ).values_list("patient_id", flat=True)
        return self.filter(
            patient_id__in=bonded_patient_ids,
            is_shared_with_psychologist=True,
        )


class JournalEntry(models.Model):
    patient = models.ForeignKey(
        "accounts.PatientProfile",
        on_delete=models.PROTECT,
        related_name="journal_entries",
        verbose_name=_("paciente"),
    )
    kind = models.CharField(
        _("tipo"),
        max_length=16,
        choices=JournalEntryKind.choices,
        default=JournalEntryKind.SITUATION,
    )
    title = models.CharField(
        _("título"),
        max_length=200,
        blank=True,
        help_text=_("Opcional. Ajuda a localizar o registro depois."),
    )
    # Conteúdo textual sempre criptografado (CLAUDE.md regra 2).
    content = encrypt(models.TextField(_("conteúdo")))

    # Humor opcional — paciente pode (não) atribuir um humor ao acontecimento.
    mood = models.IntegerField(
        _("humor associado"),
        choices=MoodLevel.choices,
        null=True,
        blank=True,
    )

    is_shared_with_psychologist = models.BooleanField(
        _("compartilhar com psicólogo"),
        default=False,
    )

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    objects = JournalEntryQuerySet.as_manager()

    class Meta:
        verbose_name = _("entrada do diário")
        verbose_name_plural = _("entradas do diário")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["patient", "-created_at"]),
        ]

    def __str__(self) -> str:
        kind = self.get_kind_display()
        date = self.created_at.strftime("%Y-%m-%d") if self.created_at else "?"
        return f"{kind} [{date}]"


# ---------------------------------------------------------------------------
# ClinicalNote — anotação clínica do psicólogo
# ---------------------------------------------------------------------------


class ClinicalNoteQuerySet(models.QuerySet):
    def for_psychologist(
        self, psychologist: PsychologistProfile
    ) -> ClinicalNoteQuerySet:
        """Notas escritas POR este psicólogo. Visibilidade unilateral.

        ClinicalNote é privada do psicólogo: o paciente nunca vê.
        Outros psicólogos nunca veem (mesmo que houvesse vínculo histórico).
        """
        return self.filter(bond__psychologist=psychologist)

    def for_bond(self, bond: Bond) -> ClinicalNoteQuerySet:
        return self.filter(bond=bond)


class ClinicalNote(models.Model):
    bond = models.ForeignKey(
        "bonds.Bond",
        on_delete=models.PROTECT,
        related_name="clinical_notes",
        verbose_name=_("vínculo"),
        help_text=_("Define implicitamente o psicólogo (autor) e o paciente (sujeito)."),
    )
    content = encrypt(models.TextField(_("conteúdo")))
    session_date = models.DateField(
        _("data da sessão"),
        null=True,
        blank=True,
        help_text=_("Opcional. Data da sessão à qual a nota se refere."),
    )

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    objects = ClinicalNoteQuerySet.as_manager()

    class Meta:
        verbose_name = _("anotação clínica")
        verbose_name_plural = _("anotações clínicas")
        ordering = ("-session_date", "-created_at")
        indexes = [
            models.Index(fields=["bond", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"ClinicalNote#{self.id} bond={self.bond_id}"
