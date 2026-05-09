"""Testes das pipelines generate_weekly_summary e generate_session_briefing.

Mock o AnthropicClient. Mock parcialmente o Pseudonymizer para evitar
loading do modelo spaCy nos testes (rápido).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.ai.anthropic_client import CompletionResult
from apps.ai.models import AISummary, AISummaryKind
from apps.ai.pseudonymization import Vault
from apps.ai.tasks import generate_session_briefing, generate_weekly_summary
from apps.audit.models import AuditLog
from apps.journal.models import JournalEntryKind, MoodLevel
from tests.factories import (
    BondFactory,
    JournalEntryFactory,
    MoodLogFactory,
    PatientProfileFactory,
)

pytestmark = pytest.mark.django_db


def _make_mock_client(response_text: str = "Resposta gerada."):
    client = MagicMock()
    client.complete.return_value = CompletionResult(
        text=response_text,
        model="claude-sonnet-4-6",
        input_tokens=120,
        output_tokens=80,
    )
    return client


def _make_mock_pseudo():
    """Pseudonymizer dummy que não carrega spaCy — passthrough."""
    pseudo = MagicMock()

    def forward(text):
        v = Vault()
        return text, v  # passa direto, vault vazio

    pseudo.forward.side_effect = forward
    return pseudo


class TestWeeklySummary:
    def test_generates_and_persists_summary(self):
        patient = PatientProfileFactory()
        MoodLogFactory(patient=patient, mood=MoodLevel.GOOD)
        JournalEntryFactory(
            patient=patient,
            kind=JournalEntryKind.SITUATION,
            content="Algo aconteceu.",
        )

        result = generate_weekly_summary(
            patient,
            actor=patient.user,
            client=_make_mock_client("Sua semana foi de altos e baixos."),
            pseudo=_make_mock_pseudo(),
        )

        assert isinstance(result, AISummary)
        assert result.kind == AISummaryKind.WEEKLY_PATIENT
        assert result.target_patient == patient
        assert result.target_bond is None
        assert result.content == "Sua semana foi de altos e baixos."
        assert result.requested_by == patient.user
        assert result.token_metadata["input_tokens"] == 120

    def test_audit_event_created(self):
        patient = PatientProfileFactory()
        generate_weekly_summary(
            patient,
            actor=patient.user,
            client=_make_mock_client(),
            pseudo=_make_mock_pseudo(),
        )

        # Pelo menos: pseudonymization_applied + summary_generated.
        actions = set(AuditLog.objects.values_list("action", flat=True))
        assert "ai.pseudonymization_applied" in actions
        assert "ai.summary_generated" in actions


class TestSessionBriefing:
    def test_generates_and_persists_briefing(self):
        bond = BondFactory(active=True)
        # Algumas entries shared do paciente
        JournalEntryFactory(
            patient=bond.patient,
            content="Compartilhado.",
            is_shared_with_psychologist=True,
        )
        # Uma privada — NÃO deve aparecer na geração
        JournalEntryFactory(
            patient=bond.patient,
            content="PRIVADO_NAO_VAZA",
            is_shared_with_psychologist=False,
        )

        client = _make_mock_client("Briefing gerado.")
        result = generate_session_briefing(
            bond,
            actor=bond.psychologist.user,
            client=client,
            pseudo=_make_mock_pseudo(),
        )

        assert result.kind == AISummaryKind.SESSION_BRIEFING
        assert result.target_bond == bond
        assert result.target_patient is None

        # Verifica que privada NÃO foi para o LLM
        sent_user_message = client.complete.call_args.kwargs["user_message"]
        assert "PRIVADO_NAO_VAZA" not in sent_user_message
        assert "Compartilhado." in sent_user_message

    def test_audit_includes_pseudonymization_and_briefing(self):
        bond = BondFactory(active=True)
        generate_session_briefing(
            bond,
            actor=bond.psychologist.user,
            client=_make_mock_client(),
            pseudo=_make_mock_pseudo(),
        )

        actions = set(AuditLog.objects.values_list("action", flat=True))
        assert "ai.pseudonymization_applied" in actions
        assert "ai.briefing_generated" in actions
