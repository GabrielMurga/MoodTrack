"""Testes de pseudonimização — regex e vault.

NER do spaCy é testado em apenas um caso (custo de loading do modelo é alto).
Os outros casos focam em regex (CPF, telefone, email, data) e no comportamento
do Vault, que são determinísticos e rápidos.
"""

from __future__ import annotations

import pytest

from apps.ai.pseudonymization import (
    Vault,
    pseudonymizer,
)


class TestVault:
    def test_store_returns_placeholder(self):
        v = Vault()
        ph = v.store("PERSON", "João Silva")
        assert ph == "<<PERSON_1>>"

    def test_store_increments_counter_per_kind(self):
        v = Vault()
        v.store("PERSON", "Ana")
        ph2 = v.store("PERSON", "Bruno")
        assert ph2 == "<<PERSON_2>>"

    def test_store_reuses_placeholder_for_repeated_value(self):
        """Mesma entidade aparecendo 2x no texto → mesmo placeholder."""
        v = Vault()
        ph1 = v.store("PERSON", "Carla")
        ph2 = v.store("PERSON", "Carla")
        assert ph1 == ph2

    def test_reverse_replaces_placeholders(self):
        v = Vault()
        v.store("PERSON", "Daniel")
        v.store("LOCATION", "Belo Horizonte")
        text = "Falei com <<PERSON_1>> em <<LOCATION_1>>."
        assert v.reverse(text) == "Falei com Daniel em Belo Horizonte."

    def test_reverse_handles_overlapping_placeholder_numbers(self):
        """<<PERSON_1>> e <<PERSON_10>> não devem se sobrepor."""
        v = Vault()
        for i in range(10):
            v.store("PERSON", f"Pessoa {i}")
        text = "<<PERSON_10>> e <<PERSON_1>> são diferentes."
        result = v.reverse(text)
        assert "Pessoa 9" in result
        assert "Pessoa 0" in result


class TestRegexDetection:
    """Pseudonimização via regex pra identificadores estruturados.

    Não exige carregar o modelo spaCy — entidades não-nomeadas devem
    ser pegas pelas regex antes do NER rodar.
    """

    def test_cpf_replaced(self):
        text = "Meu CPF é 123.456.789-01, anote aí."
        result, vault = pseudonymizer.forward(text)
        assert "123.456.789-01" not in result
        assert "<<CPF_1>>" in result

    def test_email_replaced(self):
        text = "Pode me mandar email em ana.silva@example.com."
        result, vault = pseudonymizer.forward(text)
        assert "ana.silva@example.com" not in result
        assert "<<EMAIL_1>>" in result

    def test_date_replaced(self):
        text = "Foi no dia 12/03/2026 que aconteceu."
        result, vault = pseudonymizer.forward(text)
        assert "12/03/2026" not in result

    def test_reverse_after_forward_recovers_original(self):
        original = "Meu email é teste@example.com e CPF é 999.888.777-66."
        pseudonimized, vault = pseudonymizer.forward(original)
        assert vault.reverse(pseudonimized) == original


class TestNER:
    """Teste do NER spaCy — single case porque carregar o modelo é caro (~5s).

    Marcado pra rodar em CI mas pode ser pulado em iteração local com
    `pytest -k 'not ner'`.
    """

    @pytest.mark.slow
    def test_person_name_replaced_by_ner(self):
        """Nome próprio capitalizado deve ser pego pelo NER."""
        # Texto curto e direto pra evitar falsos positivos.
        text = "Ana Beatriz contou que estava cansada."
        result, vault = pseudonymizer.forward(text)
        # NER deve substituir "Ana Beatriz" por placeholder PERSON.
        assert "Ana Beatriz" not in result
        assert any("PERSON" in ph for ph in vault._mapping)
