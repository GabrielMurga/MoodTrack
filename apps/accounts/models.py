"""Custom user model.

MoodTrack autentica exclusivamente via OAuth social (CLAUDE.md regra 12).
Não há fluxo de cadastro com senha. O campo de password permanece no modelo
porque é parte do contrato do AbstractBaseUser do Django, mas é sempre
"unusable" — definido por set_unusable_password() na criação.

Perfis (Psychologist / Patient) não estão modelados aqui ainda; isso é
decisão de modelagem que merece discussão própria (OneToOne vs role flag,
campos profissionais, etc.) e será adicionada quando o app de auth real
for implementado.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager["User"]):
    """Manager sem fluxo de senha — OAuth-only."""

    use_in_migrations = True

    def _create_user(self, email: str, **extra_fields: Any) -> User:
        if not email:
            raise ValueError("Email é obrigatório.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, **extra_fields: Any) -> User:
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, **extra_fields)

    def create_superuser(self, email: str, **extra_fields: Any) -> User:
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser precisa ter is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser precisa ter is_superuser=True.")

        return self._create_user(email, **extra_fields)


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
