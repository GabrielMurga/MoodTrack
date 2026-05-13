"""Wrapper fino sobre o SDK `stripe` (ADR 0012).

Razões pra encapsular (espelha `apps/ai/anthropic_client.py`):

- Gate de configuração em runtime: `STRIPE_API_KEY` ausente → erro tratável,
  não 500 em produção.
- Encapsulamento facilita mock em testes (não dependemos do stripe-mock).
- Centraliza decisões: que campos vão no Checkout Session, como Customer é
  criado, como webhook é verificado.

Nunca chama a API em tempo de import — toda inicialização é lazy.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


class StripeBillingError(Exception):
    """Levantada quando o cliente não pode ser usado (chave ausente, erro Stripe)."""


class StripeClient:
    """Wrapper fino sobre o SDK `stripe`. Lazy init."""

    def __init__(
        self,
        api_key: str | None = None,
        webhook_secret: str | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.STRIPE_API_KEY
        self.webhook_secret = (
            webhook_secret if webhook_secret is not None else settings.STRIPE_WEBHOOK_SECRET
        )
        self._stripe = None  # módulo configurado, lazy

    def _ensure_ready(self) -> None:
        if not self.api_key:
            raise StripeBillingError(
                "STRIPE_API_KEY não configurada. Defina no .env antes de iniciar "
                "o fluxo de assinatura."
            )

    def _get_stripe(self):
        if self._stripe is None:
            import stripe

            stripe.api_key = self.api_key
            self._stripe = stripe
        return self._stripe

    # --------- Customer ---------

    def get_or_create_customer(self, provider) -> str:
        """Retorna o `stripe_customer_id` do provider, criando se necessário.

        Persiste em `provider.stripe_customer_id` na primeira criação.
        Idempotente: chamadas subsequentes apenas retornam o id existente.
        """
        self._ensure_ready()
        if provider.stripe_customer_id:
            return provider.stripe_customer_id

        stripe = self._get_stripe()
        customer = stripe.Customer.create(
            email=provider.user.email,
            name=provider.user.get_full_name(),
            metadata={"provider_id": str(provider.pk)},
        )
        provider.stripe_customer_id = customer.id
        provider.save(update_fields=["stripe_customer_id", "updated_at"])
        return customer.id

    # --------- Checkout ---------

    def create_checkout_session(
        self,
        *,
        provider,
        price_id: str,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """Cria uma Stripe Checkout Session pra assinatura mensal.

        Retorna a URL de redirect (hospedada na Stripe). Profissional vai pra
        checkout.stripe.com, paga, e volta pra `success_url` (que não promove
        plano — webhook é a fonte de verdade).
        """
        self._ensure_ready()
        stripe = self._get_stripe()
        customer_id = self.get_or_create_customer(provider)

        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"provider_id": str(provider.pk)},
            subscription_data={"metadata": {"provider_id": str(provider.pk)}},
        )
        return session.url

    # --------- Customer Portal ---------

    def create_portal_session(self, *, provider, return_url: str) -> str:
        """Cria uma Portal Session pra o profissional gerenciar a assinatura.

        Cancelar, trocar de plano, atualizar cartão, ver invoices — tudo
        no portal hospedado da Stripe.
        """
        self._ensure_ready()
        if not provider.stripe_customer_id:
            raise StripeBillingError(
                "Profissional ainda não tem assinatura — não há portal pra abrir."
            )
        stripe = self._get_stripe()
        session = stripe.billing_portal.Session.create(
            customer=provider.stripe_customer_id,
            return_url=return_url,
        )
        return session.url

    # --------- Webhook verification ---------

    def verify_webhook(self, payload: bytes, signature: str) -> dict[str, Any]:
        """Valida `Stripe-Signature` e retorna o evento como dict.

        Falha → levanta `StripeBillingError`. Quem chama precisa retornar
        400 sem processar nada (fail-closed; nunca confiar em payload sem
        assinatura válida).
        """
        if not self.webhook_secret:
            raise StripeBillingError(
                "STRIPE_WEBHOOK_SECRET não configurada — não é seguro processar "
                "webhook sem verificação de assinatura."
            )
        stripe = self._get_stripe()
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=signature,
                secret=self.webhook_secret,
            )
        except (ValueError, stripe.error.SignatureVerificationError) as exc:
            raise StripeBillingError(f"Assinatura do webhook inválida: {exc}") from exc
        return event


# Singleton padrão. Testes podem instanciar StripeClient com chaves mockadas.
default_client = StripeClient()
