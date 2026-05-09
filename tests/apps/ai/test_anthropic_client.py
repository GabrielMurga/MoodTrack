"""Testes do AnthropicClient — gates de segurança e fluxo de chamada.

Nunca chama a API real. Mocks o SDK.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.ai.anthropic_client import (
    AnthropicClient,
    AnthropicClientError,
    CompletionResult,
)


class TestSafetyGates:
    def test_no_api_key_raises(self):
        client = AnthropicClient(api_key="", zdr_confirmed=True)
        with pytest.raises(AnthropicClientError, match="API_KEY"):
            client.complete(system="x", user_message="y")

    def test_no_zdr_confirmation_raises(self):
        client = AnthropicClient(api_key="sk-test", zdr_confirmed=False)
        with pytest.raises(AnthropicClientError, match="ZDR"):
            client.complete(system="x", user_message="y")

    def test_both_set_does_not_raise_at_gate(self):
        """Com ambos OK, falha apenas pra falta de mock real (próximo teste)."""
        client = AnthropicClient(api_key="sk-test", zdr_confirmed=True)
        # Não vamos fazer chamada real — só validar que _ensure_ready passa.
        client._ensure_ready()  # não deve raise


class TestCompleteFlow:
    @patch("anthropic.Anthropic")
    def test_complete_returns_completion_result(self, mock_anthropic):
        # Setup mock SDK
        mock_message = MagicMock()
        mock_message.content = [MagicMock(type="text", text="Resposta da IA.")]
        mock_message.model = "claude-sonnet-4-6"
        mock_message.usage.input_tokens = 100
        mock_message.usage.output_tokens = 50

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message
        mock_anthropic.return_value = mock_client

        client = AnthropicClient(api_key="sk-test", zdr_confirmed=True)
        result = client.complete(
            system="System prompt aqui",
            user_message="Mensagem do usuário",
        )

        assert isinstance(result, CompletionResult)
        assert result.text == "Resposta da IA."
        assert result.input_tokens == 100
        assert result.output_tokens == 50

        # Verifica que chamada foi feita com cache_control no system
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}

    def test_metadata_excludes_content(self):
        result = CompletionResult(
            text="conteúdo sensível",
            model="claude-sonnet-4-6",
            input_tokens=10,
            output_tokens=20,
        )
        meta = result.to_metadata()
        # Regra 15: metadata não pode ter o conteúdo.
        assert "conteúdo sensível" not in str(meta)
        assert meta["model"] == "claude-sonnet-4-6"
        assert meta["input_tokens"] == 10
