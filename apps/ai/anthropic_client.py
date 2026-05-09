"""Cliente da Anthropic API com gates de segurança.

Encapsula toda interação com `anthropic` SDK. Razões em ADR 0008:

- Gate de ZDR em runtime: chamada é bloqueada se
  `ANTHROPIC_ZDR_CONFIRMED=false` (CLAUDE.md regra 14).
- API key opcional: ausente → erro tratável (não 500).
- Encapsulamento permite mock em testes e troca de provedor futuro.

Importante: este cliente NÃO faz pseudonimização — quem chama deve
ter passado o texto por `pseudonymizer.forward(...)` antes (CLAUDE.md
regra 1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings


class AnthropicClientError(Exception):
    """Levantada quando o cliente não pode ser usado (config ausente, ZDR off)."""


@dataclass
class CompletionResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int

    def to_metadata(self) -> dict[str, Any]:
        """Metadata sem conteúdo (CLAUDE.md regra 15)."""
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


class AnthropicClient:
    """Wrapper fino sobre `anthropic.Anthropic`."""

    def __init__(
        self,
        api_key: str | None = None,
        zdr_confirmed: bool | None = None,
        default_model: str | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.ANTHROPIC_API_KEY
        self.zdr_confirmed = (
            zdr_confirmed if zdr_confirmed is not None else settings.ANTHROPIC_ZDR_CONFIRMED
        )
        self.default_model = default_model or settings.ANTHROPIC_DEFAULT_MODEL
        self._client = None  # lazy

    def _ensure_ready(self) -> None:
        if not self.api_key:
            raise AnthropicClientError(
                "ANTHROPIC_API_KEY não configurada. Defina no .env antes de "
                "chamar a IA."
            )
        if not self.zdr_confirmed:
            raise AnthropicClientError(
                "ANTHROPIC_ZDR_CONFIRMED=false. Confirme Zero Data Retention "
                "em console.anthropic.com e defina a env var como true antes "
                "de habilitar a IA (CLAUDE.md regra 14)."
            )

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def complete(
        self,
        *,
        system: str,
        user_message: str,
        model: str | None = None,
        max_tokens: int = 1024,
        cache_system: bool = True,
    ) -> CompletionResult:
        """Faz uma chamada de completion. Retorna CompletionResult.

        - `system` é o system prompt (instruções de papel/comportamento).
        - `user_message` é o conteúdo (idealmente já pseudonimizado).
        - `cache_system=True` aplica prompt caching ao system prompt
          (corte de custo/latência em chamadas repetidas).
        """
        self._ensure_ready()
        client = self._get_client()
        model = model or self.default_model

        system_param: list[dict[str, Any]] | str
        if cache_system:
            system_param = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            system_param = system

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_param,
            messages=[{"role": "user", "content": user_message}],
        )

        # SDK retorna content como lista de blocks; pegamos o texto.
        text_parts = [
            block.text for block in response.content if getattr(block, "type", None) == "text"
        ]
        text = "".join(text_parts)

        return CompletionResult(
            text=text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )


# Singleton padrão da app. Tests podem instanciar AnthropicClient com mock.
default_client = AnthropicClient()
