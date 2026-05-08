"""Vínculo paciente-psicólogo.

O Bond é o relacionamento terapêutico autorizado dentro do MoodTrack.
Conforme CLAUDE.md regra 4, o vínculo exige confirmação dos dois lados:

    1. Psicólogo gera convite (Bond criado em estado INVITED, com invite_code).
    2. Paciente recebe o código fora da plataforma e o insere no app
       (INVITED → PENDING_CONFIRMATION; patient é preenchido).
    3. Psicólogo confirma a conexão (PENDING_CONFIRMATION → ACTIVE).
    4. Qualquer lado pode encerrar a qualquer momento (* → ENDED).

Querysets do manager seguem CLAUDE.md regra 6 — fail-closed: filtragem por
psicólogo/paciente acontece em camada de manager, não em view.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from apps.accounts.models import PatientProfile, PsychologistProfile, User


# Alfabeto Crockford-like sem caracteres ambíguos (0/O, 1/I/L).
_INVITE_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_INVITE_CODE_LENGTH = 8


def generate_invite_code() -> str:
    """Gera código de convite único, fácil de digitar.

    Espaço de 31^8 ~= 8.5e11 combinações. Unicidade é garantida em DB
    (UniqueConstraint), mas a probabilidade de colisão é desprezível
    no horizonte do MVP.
    """
    return "".join(secrets.choice(_INVITE_CODE_ALPHABET) for _ in range(_INVITE_CODE_LENGTH))


class InvalidBondTransition(Exception):
    """Levantada quando uma transição de estado do Bond é inválida."""


class BondStatus(models.TextChoices):
    INVITED = "invited", _("Convite gerado")
    PENDING_CONFIRMATION = "pending", _("Aguardando confirmação do psicólogo")
    ACTIVE = "active", _("Ativo")
    ENDED = "ended", _("Encerrado")


# Estados em que o vínculo é considerado "vivo" — usado em constraints e querysets.
ALIVE_STATUSES = (
    BondStatus.INVITED,
    BondStatus.PENDING_CONFIRMATION,
    BondStatus.ACTIVE,
)


class BondQuerySet(models.QuerySet):
    def alive(self) -> BondQuerySet:
        return self.filter(status__in=ALIVE_STATUSES)

    def active(self) -> BondQuerySet:
        return self.filter(status=BondStatus.ACTIVE)

    def for_psychologist(self, profile: PsychologistProfile) -> BondQuerySet:
        return self.filter(psychologist=profile)

    def for_patient(self, profile: PatientProfile) -> BondQuerySet:
        return self.filter(patient=profile)

    def for_user(self, user: User) -> BondQuerySet:
        """Bonds visíveis ao usuário pelo perfil que ele tiver.

        Fail-closed: usuário sem perfil retorna queryset vazio (não erra,
        não levanta — apenas não vê nada). Isso garante que view que esquecer
        checagem de perfil não exponha bonds.
        """
        from django.db.models import Q

        filters = Q(pk__in=[])  # vazio por default
        if hasattr(user, "psychologist_profile"):
            filters |= Q(psychologist=user.psychologist_profile)
        if hasattr(user, "patient_profile"):
            filters |= Q(patient=user.patient_profile)
        return self.filter(filters)


class Bond(models.Model):
    psychologist = models.ForeignKey(
        "accounts.PsychologistProfile",
        on_delete=models.PROTECT,
        related_name="bonds",
        verbose_name=_("psicólogo"),
    )
    patient = models.ForeignKey(
        "accounts.PatientProfile",
        on_delete=models.PROTECT,
        related_name="bonds",
        null=True,
        blank=True,
        verbose_name=_("paciente"),
        help_text=_("Nulo enquanto o paciente ainda não inseriu o código de convite."),
    )

    invite_code = models.CharField(
        _("código de convite"),
        max_length=12,
        unique=True,
        db_index=True,
        default=generate_invite_code,
    )
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=BondStatus.choices,
        default=BondStatus.INVITED,
    )

    invited_at = models.DateTimeField(_("convite criado em"), auto_now_add=True)
    patient_entered_at = models.DateTimeField(
        _("paciente entrou em"), null=True, blank=True
    )
    psychologist_confirmed_at = models.DateTimeField(
        _("psicólogo confirmou em"), null=True, blank=True
    )
    ended_at = models.DateTimeField(_("encerrado em"), null=True, blank=True)
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ended_bonds",
        null=True,
        blank=True,
        verbose_name=_("encerrado por"),
    )

    objects = BondQuerySet.as_manager()

    class Meta:
        verbose_name = _("vínculo")
        verbose_name_plural = _("vínculos")
        ordering = ("-invited_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["psychologist", "patient"],
                condition=models.Q(status__in=("invited", "pending", "active")),
                name="unique_alive_bond_per_pair",
            ),
            models.CheckConstraint(
                condition=models.Q(status="invited") | models.Q(patient__isnull=False),
                name="bond_patient_required_after_invite",
            ),
        ]

    def __str__(self) -> str:
        return f"Bond {self.invite_code} ({self.get_status_display()})"

    # ----- transições de estado -----

    def accept_invite(self, patient: PatientProfile) -> None:
        """Paciente insere o código de convite — INVITED → PENDING_CONFIRMATION.

        Se o paciente é o mesmo User do psicólogo do convite (caso dual:
        psicóloga que também faz terapia), recusa: ninguém pode ser próprio
        paciente.
        """
        if self.status != BondStatus.INVITED:
            raise InvalidBondTransition(
                f"accept_invite só é válido em INVITED (status atual: {self.status})."
            )
        if patient.user_id == self.psychologist.user_id:
            raise InvalidBondTransition(
                "Você não pode usar seu próprio código de convite — "
                "psicólogo e paciente devem ser pessoas diferentes."
            )
        self.patient = patient
        self.status = BondStatus.PENDING_CONFIRMATION
        self.patient_entered_at = timezone.now()
        self.save(update_fields=["patient", "status", "patient_entered_at"])

    def confirm(self) -> None:
        """Psicólogo confirma o vínculo — PENDING_CONFIRMATION → ACTIVE."""
        if self.status != BondStatus.PENDING_CONFIRMATION:
            raise InvalidBondTransition(
                f"confirm só é válido em PENDING (status atual: {self.status})."
            )
        self.status = BondStatus.ACTIVE
        self.psychologist_confirmed_at = timezone.now()
        self.save(update_fields=["status", "psychologist_confirmed_at"])

    def end(self, by_user: User) -> None:
        """Encerra o vínculo — qualquer estado vivo → ENDED."""
        if self.status == BondStatus.ENDED:
            raise InvalidBondTransition("Bond já está encerrado.")
        self.status = BondStatus.ENDED
        self.ended_at = timezone.now()
        self.ended_by = by_user
        self.save(update_fields=["status", "ended_at", "ended_by"])

    # ----- helpers -----

    @property
    def is_alive(self) -> bool:
        return self.status in ALIVE_STATUSES

    @property
    def is_active(self) -> bool:
        return self.status == BondStatus.ACTIVE
