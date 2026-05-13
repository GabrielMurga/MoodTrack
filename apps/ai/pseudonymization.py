"""Pseudonimização de dados antes de envio à LLM externa.

Implementa CLAUDE.md regra 1: nenhum dado de paciente vai à LLM sem
passar por aqui. Estratégia detalhada em ADR 0007.

Pipeline:
    text → forward(text) → (text_pseudonimizado, vault) → LLM
                                                            ↓
    text_final ← vault.reverse(response) ← response_pseudonimizada

O vault é efêmero: vive só pelo tempo da chamada, não persistido.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from spacy.language import Language


# ---------------------------------------------------------------------------
# Modelo spaCy — singleton lazy (carrega no primeiro uso)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_nlp() -> Language:
    """Carrega o modelo PT-BR uma vez por processo. ~540MB, ~5s pra carregar."""
    import spacy

    return spacy.load("pt_core_news_lg")


# ---------------------------------------------------------------------------
# Regex para identificadores estruturados que NER não pega bem
# ---------------------------------------------------------------------------

# CPF: 11 dígitos com ou sem pontuação. Aceita formatos: 12345678901, 123.456.789-01
_RE_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")

# Telefone BR: (XX) 9XXXX-XXXX, XXXXX-XXXX, +55 XX XXXXXXXXX, etc.
_RE_PHONE = re.compile(r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?9?\d{4}[-\s]?\d{4}\b")

# Email
_RE_EMAIL = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")

# Data DD/MM/YYYY ou DD-MM-YYYY (com 2 ou 4 dígitos no ano)
_RE_DATE = re.compile(r"\b\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b")


# ---------------------------------------------------------------------------
# Vault — mapping placeholder ↔ original
# ---------------------------------------------------------------------------


@dataclass
class Vault:
    """Mapeamento efêmero de placeholders para os textos originais.

    Existe apenas durante uma chamada (forward → LLM → reverse). Nunca
    persistido em DB.
    """

    _mapping: dict[str, str] = field(default_factory=dict)
    _counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def store(self, kind: str, original: str) -> str:
        """Cria placeholder pra `original`, retorna o placeholder.

        Se `original` já foi visto neste vault, reusa o mesmo placeholder
        (preserva consistência: "João Silva" → [PERSON_1] sempre, mesmo
        que apareça 5 vezes no texto).
        """
        existing = next(
            (ph for ph, val in self._mapping.items() if val == original),
            None,
        )
        if existing is not None:
            return existing

        self._counters[kind] += 1
        # Formato com angle brackets — não é capturado pelo NER do spaCy.
        placeholder = f"<<{kind}_{self._counters[kind]}>>"
        self._mapping[placeholder] = original
        return placeholder

    def reverse(self, text: str) -> str:
        """Substitui placeholders por seus originais.

        Aplicado no resultado da LLM antes de mostrar ao usuário.
        """
        result = text
        # Ordem decrescente de tamanho de placeholder pra evitar matches
        # parciais (ex.: [PERSON_1] vs [PERSON_10]).
        for placeholder in sorted(self._mapping.keys(), key=len, reverse=True):
            result = result.replace(placeholder, self._mapping[placeholder])
        return result

    @property
    def size(self) -> int:
        return len(self._mapping)


# ---------------------------------------------------------------------------
# Pseudonymizer — aplica forward
# ---------------------------------------------------------------------------


# Detecta placeholders já criados (de uma passada anterior do regex)
# para que o NER não tente "re-pseudonimizar" os marcadores.
_RE_PLACEHOLDER = re.compile(r"^<<[A-Z]+_\d+>>$")


# Mapeamento de labels do spaCy → kind de placeholder
_SPACY_LABEL_TO_KIND = {
    "PER": "PERSON",
    "PERSON": "PERSON",
    "LOC": "LOCATION",
    "GPE": "LOCATION",
    "ORG": "ORG",
    "MISC": "MISC",
}


class Pseudonymizer:
    """Aplica forward pseudonimization em texto livre.

    Use o singleton de módulo `pseudonymizer` em vez de instanciar manualmente.
    """

    def forward(self, text: str) -> tuple[str, Vault]:
        """Substitui entidades por placeholders, retorna (novo_texto, vault).

        Estratégia:
        1. Coleta matches de regex (identificadores estruturados: CPF,
           email, telefone, data). Estes são confiáveis e específicos.
        2. Coleta entidades do NER (PERSON, LOC, ORG, MISC).
        3. Resolve conflitos: se um match de NER se sobrepõe a uma regex,
           a regex vence (mais específica). Isso evita que `ana@x.com` seja
           classificado pelo NER como PERSON.
        4. Aplica substituições do fim pro começo (offsets preservados).
        """
        vault = Vault()

        regex_matches: list[tuple[int, int, str, str]] = []
        for pattern, kind in (
            (_RE_CPF, "CPF"),
            (_RE_EMAIL, "EMAIL"),
            (_RE_PHONE, "PHONE"),
            (_RE_DATE, "DATE"),
        ):
            for m in pattern.finditer(text):
                regex_matches.append((m.start(), m.end(), kind, m.group(0)))

        ner_matches: list[tuple[int, int, str, str]] = []
        nlp = _load_nlp()
        doc = nlp(text)
        for ent in doc.ents:
            kind = _SPACY_LABEL_TO_KIND.get(ent.label_)
            if kind is None:
                continue
            # Skip se overlap com qualquer match de regex.
            overlaps = any(
                ent.start_char < r_end and ent.end_char > r_start
                for r_start, r_end, _, _ in regex_matches
            )
            if overlaps:
                continue
            ner_matches.append((ent.start_char, ent.end_char, kind, ent.text))

        # Combina e aplica do fim pro começo.
        all_matches = sorted(regex_matches + ner_matches, key=lambda m: m[0], reverse=True)
        result = text
        for start, end, kind, original in all_matches:
            placeholder = vault.store(kind, original)
            result = result[:start] + placeholder + result[end:]

        return result, vault


# Singleton para uso na app — evita carregar o modelo a cada chamada.
pseudonymizer = Pseudonymizer()
