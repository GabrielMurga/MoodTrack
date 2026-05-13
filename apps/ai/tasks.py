"""Pipelines de geração de IA.

Sync por enquanto (ADR 0008). Cada função:

1. Coleta os dados (com filtros de visibilidade aplicados).
2. Pseudonimiza.
3. Chama Anthropic via wrapper.
4. De-pseudonimiza a saída.
5. Salva AISummary.
6. Audita (sem conteúdo — regra 15).
7. Retorna AISummary.

Audiência:
- `generate_weekly_summary(patient_profile, actor)` — paciente vê
  TODOS os próprios dados (privados + compartilhados).
- `generate_session_briefing(bond, actor)` — profissional (psicólogo
  ou psiquiatra) vê só dados shared do paciente + suas próprias notas
  clínicas.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.audit.models import log_event
from apps.bonds.models import Bond
from apps.journal.models import ClinicalNote, JournalEntry, MoodLevel, MoodLog

from .anthropic_client import AnthropicClient, default_client
from .models import AISummary, AISummaryKind
from .prompts import SESSION_BRIEFING_SYSTEM, WEEKLY_SUMMARY_SYSTEM
from .pseudonymization import Pseudonymizer, pseudonymizer

# ---------------------------------------------------------------------------
# Coleta de dados — formatadores
# ---------------------------------------------------------------------------


_COMPACT_MAX_ENTRIES = 10
_COMPACT_MAX_CHARS = 500


def _truncate(text: str, max_chars: int) -> str:
    return text[:max_chars] + "…" if len(text) > max_chars else text


def _format_mood_logs(qs, compact: bool = False) -> str:
    if not qs.exists():
        return "Sem registros de humor no período."
    if compact:
        qs = qs[:14]
    lines = []
    for log in qs:
        emoji = MoodLevel(log.mood).label
        lines.append(f"- {log.recorded_at:%d/%m %H:%M}: {emoji}")
    return "\n".join(lines)


def _format_journal_entries(qs, compact: bool = False) -> str:
    if not qs.exists():
        return "Sem entradas de diário no período."
    if compact:
        qs = qs[:_COMPACT_MAX_ENTRIES]
    lines = []
    for entry in qs:
        kind = entry.get_kind_display()
        mood = entry.get_mood_display() if entry.mood else "sem humor"
        title = f' — "{entry.title}"' if entry.title else ""
        content = _truncate(entry.content, _COMPACT_MAX_CHARS) if compact else entry.content
        lines.append(f"- [{entry.created_at:%d/%m}] {kind}{title} ({mood}):\n  {content}")
    return "\n\n".join(lines)


def _format_clinical_notes(qs) -> str:
    if not qs.exists():
        return "Sem anotações clínicas anteriores."
    lines = []
    for note in qs:
        date_label = (
            f"sessão {note.session_date:%d/%m}"
            if note.session_date
            else f"anotação {note.created_at:%d/%m}"
        )
        lines.append(f"- [{date_label}]:\n  {note.content}")
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Pipelines de alto nível
# ---------------------------------------------------------------------------


def generate_weekly_summary(
    patient_profile,
    *,
    actor,
    client: AnthropicClient | None = None,
    pseudo: Pseudonymizer | None = None,
    model: str | None = None,
    compact: bool = False,
) -> AISummary:
    """Resumo semanal pro paciente (autoconhecimento).

    Janela: últimos 7 dias. Vê TODOS os dados próprios do paciente
    (privados + compartilhados — é o resumo do próprio paciente).
    """
    client = client or default_client
    pseudo = pseudo or pseudonymizer

    period_end = timezone.now()
    period_start = period_end - timedelta(days=7)

    mood_logs = MoodLog.objects.for_patient(patient_profile).filter(
        recorded_at__gte=period_start, recorded_at__lte=period_end
    )
    journal_entries = JournalEntry.objects.for_patient(patient_profile).filter(
        created_at__gte=period_start, created_at__lte=period_end
    )

    raw_content = (
        "Janela: últimos 7 dias.\n\n"
        f"REGISTROS DE HUMOR:\n{_format_mood_logs(mood_logs, compact=compact)}\n\n"
        f"ENTRADAS DO DIÁRIO:\n{_format_journal_entries(journal_entries, compact=compact)}"
    )

    pseudonimized, vault = pseudo.forward(raw_content)

    log_event(
        actor=actor,
        action="ai.pseudonymization_applied",
        target=patient_profile,
        placeholder_count=vault.size,
        kind="weekly_summary",
    )

    result = client.complete(
        system=WEEKLY_SUMMARY_SYSTEM,
        user_message=pseudonimized,
        max_tokens=1500,
        model=model,
    )

    final_text = vault.reverse(result.text)

    summary = AISummary.objects.create(
        kind=AISummaryKind.WEEKLY_PATIENT,
        target_patient=patient_profile,
        content=final_text,
        period_start=period_start,
        period_end=period_end,
        model_used=result.model,
        token_metadata=result.to_metadata(),
        requested_by=actor,
    )

    log_event(
        actor=actor,
        action="ai.summary_generated",
        target=summary,
        kind="weekly_summary",
        **result.to_metadata(),
    )

    return summary


def generate_session_briefing(
    bond: Bond,
    *,
    actor,
    client: AnthropicClient | None = None,
    pseudo: Pseudonymizer | None = None,
    model: str | None = None,
    compact: bool = False,
) -> AISummary:
    """Briefing pré-sessão pro profissional.

    Janela: desde o último briefing gerado, ou desde
    `provider_confirmed_at` se for o primeiro.

    Vê: registros do paciente shared + anotações clínicas próprias do
    profissional. NÃO vê registros privados do paciente (regra 3).
    """
    client = client or default_client
    pseudo = pseudo or pseudonymizer

    period_end = timezone.now()

    # Janela: desde último briefing OU desde profissional confirmou bond.
    last = AISummary.objects.for_bond(bond).order_by("-generated_at").first()
    period_start = last.generated_at if last is not None else bond.provider_confirmed_at
    if period_start is None:
        # Bond ainda não confirmado, não deveria chegar aqui — mas fail-safe.
        period_start = period_end - timedelta(days=7)

    provider = bond.provider
    patient = bond.patient

    mood_logs = MoodLog.objects.shared_with_provider(provider).filter(
        patient=patient,
        recorded_at__gte=period_start,
        recorded_at__lte=period_end,
    )
    journal_entries = JournalEntry.objects.shared_with_provider(provider).filter(
        patient=patient,
        created_at__gte=period_start,
        created_at__lte=period_end,
    )
    clinical_notes = ClinicalNote.objects.for_bond(bond).filter(
        created_at__gte=period_start, created_at__lte=period_end
    )

    raw_content = (
        f"Janela: {period_start:%d/%m} até {period_end:%d/%m}.\n\n"
        f"REGISTROS DE HUMOR COMPARTILHADOS:\n{_format_mood_logs(mood_logs, compact=compact)}\n\n"
        f"ENTRADAS DO DIÁRIO COMPARTILHADAS:\n{_format_journal_entries(journal_entries, compact=compact)}\n\n"
        f"SUAS ANOTAÇÕES CLÍNICAS NO PERÍODO:\n{_format_clinical_notes(clinical_notes)}"
    )

    pseudonimized, vault = pseudo.forward(raw_content)

    log_event(
        actor=actor,
        action="ai.pseudonymization_applied",
        target=bond,
        placeholder_count=vault.size,
        kind="session_briefing",
    )

    result = client.complete(
        system=SESSION_BRIEFING_SYSTEM,
        user_message=pseudonimized,
        max_tokens=2000,
        model=model,
    )

    final_text = vault.reverse(result.text)

    summary = AISummary.objects.create(
        kind=AISummaryKind.SESSION_BRIEFING,
        target_bond=bond,
        content=final_text,
        period_start=period_start,
        period_end=period_end,
        model_used=result.model,
        token_metadata=result.to_metadata(),
        requested_by=actor,
    )

    log_event(
        actor=actor,
        action="ai.briefing_generated",
        target=summary,
        kind="session_briefing",
        bond_id=bond.id,
        **result.to_metadata(),
    )

    return summary
