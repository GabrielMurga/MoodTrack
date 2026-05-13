"""Modelos de identidade.

MoodTrack autentica usuários finais (profissionais de saúde e pacientes)
exclusivamente via OAuth social (CLAUDE.md regra 12). O campo `password`
permanece no modelo porque é parte do contrato do AbstractBaseUser do Django,
mas para usuários criados pelo fluxo OAuth ele é sempre "unusable" —
`set_unusable_password()` é chamado.

Senha utilizável só é definida via `createsuperuser` (uso de ops/dev) ou pelo
seed de desenvolvimento. Nenhum endpoint público aceita senha.

Um mesmo User pode ter `HealthcareProvider` E `PatientProfile` simultaneamente
(profissional que também faz terapia, por exemplo). Os perfis são OneToOne
opcionais; o User permanece neutro quanto ao papel.

`HealthcareProvider` (ADR 0009) cobre tanto psicólogo quanto psiquiatra,
diferenciados pelo campo `kind`. Detalhes que divergem entre os dois (CRP/CRM,
capacidade de prescrição) ficam no próprio model, condicionais ao `kind`.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager["User"]):
    """Manager que não requer senha — OAuth-only para usuários finais.

    `password` é aceito apenas para suportar `createsuperuser` (Django passa
    a senha digitada no prompt) e seed de desenvolvimento. Quando ausente,
    o usuário é criado com senha unusable.
    """

    use_in_migrations = True

    def _create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> User:
        if not email:
            raise ValueError("Email é obrigatório.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> User:
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> User:
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser precisa ter is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser precisa ter is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(_("email"), unique=True)
    full_name = models.CharField(_("nome completo"), max_length=255, blank=True)

    is_staff = models.BooleanField(_("staff"), default=False)
    is_active = models.BooleanField(_("ativo"), default=True)

    date_joined = models.DateTimeField(_("data de cadastro"), default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        verbose_name = _("usuário")
        verbose_name_plural = _("usuários")

    def __str__(self) -> str:
        return self.email

    def get_full_name(self) -> str:
        return self.full_name or self.email

    def get_short_name(self) -> str:
        return self.full_name.split()[0] if self.full_name else self.email

    @property
    def is_provider(self) -> bool:
        return hasattr(self, "provider_profile")

    @property
    def is_psychologist(self) -> bool:
        return self.is_provider and self.provider_profile.kind == ProviderKind.PSYCHOLOGIST

    @property
    def is_psychiatrist(self) -> bool:
        return self.is_provider and self.provider_profile.kind == ProviderKind.PSYCHIATRIST

    @property
    def is_patient(self) -> bool:
        return hasattr(self, "patient_profile")


class ProviderKind(models.TextChoices):
    PSYCHOLOGIST = "psychologist", _("Psicólogo")
    PSYCHIATRIST = "psychiatrist", _("Psiquiatra")


class ProviderPlan(models.TextChoices):
    """Tier de assinatura do profissional (ADR 0010).

    - BASIC: sem acesso a IA. Plataforma + timeline + anotações clínicas.
    - PRO: IA com cota dimensionada para o uso típico.
    - PREMIUM: IA praticamente ilimitada (limites apenas anti-abuse).

    Default em criação é BASIC. Promoção para PRO/PREMIUM acontece via
    side-effect de pagamento confirmado (futuro). No MVP, alteração manual
    pelo admin Django.
    """

    BASIC = "basic", _("Básico")
    PRO = "pro", _("Pro")
    PREMIUM = "premium", _("Premium")


class HealthcareProvider(models.Model):
    """Perfil profissional unificado (psicólogo ou psiquiatra).

    Ver ADR 0009. O campo `kind` define se é psicólogo ou psiquiatra; CRP é
    preenchido apenas para psicólogo, CRM apenas para psiquiatra. Capacidade
    de prescrição é derivada de `kind` (psiquiatra prescreve, psicólogo não)
    e usada em validação fail-closed nos models que tratam medicação.

    Validação real de CRP/CRM contra base oficial do CFP/CFM fica para
    iteração futura; nesta fatia ambos são free-text com restrição de
    consistência (CheckConstraint + clean()).
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="provider_profile",
        verbose_name=_("usuário"),
    )
    kind = models.CharField(
        _("tipo de profissional"),
        max_length=20,
        choices=ProviderKind.choices,
    )
    crp_number = models.CharField(
        _("CRP"),
        max_length=20,
        blank=True,
        help_text=_(
            "Número do CRP (Conselho Regional de Psicologia). Preenchido "
            "apenas quando o tipo é psicólogo. Validação de formato é futura."
        ),
    )
    crm_number = models.CharField(
        _("CRM"),
        max_length=20,
        blank=True,
        help_text=_(
            "Número do CRM (Conselho Regional de Medicina). Preenchido apenas "
            "quando o tipo é psiquiatra. Validação de formato é futura."
        ),
    )
    bio = models.TextField(_("biografia profissional"), blank=True)

    plan = models.CharField(
        _("plano"),
        max_length=10,
        choices=ProviderPlan.choices,
        default=ProviderPlan.BASIC,
        help_text=_(
            "Tier de assinatura. Define acesso a IA e cota — ver ADR 0010. "
            "Profissional novo nasce em Básico (sem IA) por default."
        ),
    )

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("perfil de profissional")
        verbose_name_plural = _("perfis de profissional")
        constraints = [
            # Garante que o número de registro corresponde ao tipo: psicólogo
            # não pode ter CRM preenchido, psiquiatra não pode ter CRP. Free-
            # text continua possível dentro do tipo correto.
            models.CheckConstraint(
                condition=(
                    models.Q(kind="psychologist", crm_number="")
                    | models.Q(kind="psychiatrist", crp_number="")
                ),
                name="provider_register_number_matches_kind",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.user.email}"

    @property
    def can_prescribe(self) -> bool:
        return self.kind == ProviderKind.PSYCHIATRIST

    @property
    def has_ai_access(self) -> bool:
        """Plano dá direito a usar IA? Cota é decisão separada (ver apps/ai/access)."""
        return self.plan != ProviderPlan.BASIC

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        super().clean()
        if self.kind == ProviderKind.PSYCHOLOGIST and self.crm_number:
            raise ValidationError({"crm_number": _("Psicólogo não preenche CRM.")})
        if self.kind == ProviderKind.PSYCHIATRIST and self.crp_number:
            raise ValidationError({"crp_number": _("Psiquiatra não preenche CRP.")})


class PatientProfile(models.Model):
    """Perfil de paciente.

    Modo "individual" do produto = paciente sem Bond ativo. Não há campo
    `mode` separando — a presença de Bond ATIVO é o que define a relação
    terapêutica em vigor.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="patient_profile",
        verbose_name=_("usuário"),
    )
    preferred_name = models.CharField(
        _("nome preferido"),
        max_length=120,
        blank=True,
        help_text=_(
            "Como o paciente prefere ser chamado. Usado em devolutivas e pelo profissional."
        ),
    )
    birth_date = models.DateField(_("data de nascimento"), null=True, blank=True)

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("perfil de paciente")
        verbose_name_plural = _("perfis de paciente")

    def __str__(self) -> str:
        return f"Paciente: {self.user.email}"

    @property
    def has_ai_via_bond(self) -> bool:
        """Tem bond ativo a um profissional cujo plano inclui IA?

        Usado para esconder/mostrar pontos de entrada de IA na UI do paciente.
        Modo individual (sem bond) ou bond a profissional Básico → False.
        """
        from apps.bonds.models import Bond, BondStatus

        return (
            Bond.objects.filter(patient=self, status=BondStatus.ACTIVE)
            .exclude(provider__plan=ProviderPlan.BASIC)
            .exists()
        )
