"""Modelos de identidade.

MoodTrack autentica usuários finais (psicólogos e pacientes) exclusivamente via
OAuth social (CLAUDE.md regra 12). O campo `password` permanece no modelo porque
é parte do contrato do AbstractBaseUser do Django, mas para usuários criados
pelo fluxo OAuth ele é sempre "unusable" — `set_unusable_password()` é chamado.

Senha utilizável só é definida via `createsuperuser` (uso de ops/dev) ou pelo
seed de desenvolvimento. Nenhum endpoint público aceita senha.

Um mesmo User pode ter `PsychologistProfile` E `PatientProfile` simultaneamente
(psicóloga que também faz terapia, por exemplo). Os perfis são OneToOne
opcionais; o User permanece neutro quanto ao papel.
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
    def is_psychologist(self) -> bool:
        return hasattr(self, "psychologist_profile")

    @property
    def is_patient(self) -> bool:
        return hasattr(self, "patient_profile")


class PsychologistProfile(models.Model):
    """Perfil profissional do psicólogo.

    Validação real do CRP contra base do CFP fica para iteração futura;
    nesta fatia o campo é free-text. Bio e especialidade são placeholders
    para evolução do perfil público profissional.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="psychologist_profile",
        verbose_name=_("usuário"),
    )
    crp_number = models.CharField(
        _("CRP"),
        max_length=20,
        blank=True,
        help_text=_("Número do CRP (Conselho Regional de Psicologia). Validação de formato é futura."),
    )
    bio = models.TextField(_("biografia profissional"), blank=True)

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("perfil de psicólogo")
        verbose_name_plural = _("perfis de psicólogo")

    def __str__(self) -> str:
        return f"Psicólogo: {self.user.email}"


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
        help_text=_("Como o paciente prefere ser chamado. Usado em devolutivas e pelo psicólogo."),
    )
    birth_date = models.DateField(_("data de nascimento"), null=True, blank=True)

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("perfil de paciente")
        verbose_name_plural = _("perfis de paciente")

    def __str__(self) -> str:
        return f"Paciente: {self.user.email}"
