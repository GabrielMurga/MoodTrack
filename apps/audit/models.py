"""Audit log append-only.

CLAUDE.md regra 8: toda operação sensível (leitura ou escrita) gera
registro em apps/audit. Tabela append-only — sem UPDATE/DELETE.

Enforcement em camadas:

1. **Aplicação** (este arquivo): `save()` recusa qualquer chamada com
   `pk` já definido (ou seja, qualquer UPDATE). `delete()` é overridden
   para levantar.
2. **Banco** (operacional, fora do MVP de código): em produção, executar
   `REVOKE UPDATE, DELETE ON audit_auditlog FROM moodtrack;` no Postgres.
   Isso garante que mesmo bug de aplicação ou acesso direto ao DB não
   consegue alterar o histórico. Documentado em ADR de hardening (futuro).
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AuditLogError(Exception):
    """Levantada em tentativas de UPDATE/DELETE em AuditLog."""


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="audit_logs",
        verbose_name=_("ator"),
        null=True,
        blank=True,
        help_text=_("Usuário que executou a operação. Nulo apenas em ações de sistema."),
    )
    action = models.CharField(
        _("ação"),
        max_length=64,
        db_index=True,
        help_text=_("Identificador da ação. Convenção: 'app.evento', ex.: 'bond.confirmed'."),
    )
    target_type = models.CharField(
        _("tipo do alvo"),
        max_length=64,
        blank=True,
        help_text=_("Nome do modelo do alvo (ex.: 'Bond', 'MoodEntry'). Vazio se ação não tem alvo."),
    )
    target_id = models.BigIntegerField(
        _("ID do alvo"),
        null=True,
        blank=True,
        help_text=_("PK do alvo. Não é FK pra preservar histórico após delete cascade."),
    )
    timestamp = models.DateTimeField(_("timestamp"), auto_now_add=True, db_index=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("registro de auditoria")
        verbose_name_plural = _("registros de auditoria")
        ordering = ("-timestamp",)
        indexes = [
            models.Index(fields=["target_type", "target_id"]),
            models.Index(fields=["actor", "-timestamp"]),
        ]

    def __str__(self) -> str:
        actor = self.actor.email if self.actor_id else "system"
        target = (
            f"{self.target_type}#{self.target_id}"
            if self.target_type
            else "(sem alvo)"
        )
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {actor} → {self.action} {target}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            raise AuditLogError(
                "AuditLog é append-only — UPDATE não permitido."
            )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> None:
        raise AuditLogError("AuditLog é append-only — DELETE não permitido.")


def log_event(
    *,
    actor: Any | None,
    action: str,
    target: models.Model | None = None,
    **metadata: Any,
) -> AuditLog:
    """Helper para criar uma entrada de auditoria.

    Uso:
        log_event(actor=user, action="bond.confirmed", target=bond, code=bond.invite_code)

    `actor=None` é permitido apenas para ações de sistema (jobs, signals).
    Em fluxos de view sempre passar request.user.
    """
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        target_type=target.__class__.__name__ if target is not None else "",
        target_id=target.pk if target is not None else None,
        metadata=metadata,
    )
