"""Modelos de billing — log idempotente de eventos da Stripe.

`WebhookEvent` é a tabela que garante que cada evento da Stripe é processado
exatamente uma vez (ADR 0012). Stripe retransmite o mesmo `event_id` se não
receber 2xx em tempo hábil; sem essa tabela, um upgrade poderia ser aplicado
duas vezes em race condition.

Não armazena dados de cartão nem PII — apenas metadata do evento + payload
bruto pra debugging. Payload sob `JSONField` é o objeto que Stripe enviou;
não contém PAN nem CVV (Stripe nunca envia esses dados pelo webhook).
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class WebhookEvent(models.Model):
    """Evento recebido do webhook da Stripe — append-only, idempotente."""

    event_id = models.CharField(
        _("Stripe event id"),
        max_length=128,
        unique=True,
        db_index=True,
        help_text=_(
            "Identificador único do evento na Stripe (formato `evt_...`). "
            "Unique constraint garante processamento exatamente uma vez."
        ),
    )
    event_type = models.CharField(
        _("tipo do evento"),
        max_length=64,
        db_index=True,
    )
    payload = models.JSONField(
        _("payload"),
        help_text=_(
            "Objeto completo do evento conforme recebido da Stripe. Útil "
            "para debug e re-processamento manual. Não contém dados de "
            "cartão (Stripe não envia PAN/CVV por webhook)."
        ),
    )
    received_at = models.DateTimeField(_("recebido em"), auto_now_add=True)
    processed_at = models.DateTimeField(
        _("processado em"),
        null=True,
        blank=True,
        help_text=_("Quando o handler terminou sem erro. Vazio = falhou ou ignorado."),
    )
    error = models.TextField(
        _("erro"),
        blank=True,
        help_text=_("Traceback / mensagem se o handler falhou. Vazio = sucesso."),
    )

    class Meta:
        verbose_name = _("evento da Stripe")
        verbose_name_plural = _("eventos da Stripe")
        ordering = ("-received_at",)
        indexes = [
            models.Index(fields=["-received_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} ({self.event_id})"
