import urllib.error

import pytest

from catalog_tools.llm_fallback import OllamaClassifier
from catalog_tools.rule_proposer import (
    ProposalError,
    parse_category_names,
    propose_category_names,
    propose_rules,
)

CATEGORIES = [
    "Elektronika / Audio / słuchawki bluetooth",
    "Akcesoria mobilne / słuchawki bezprzewodowe TWS",
    "GSM / etui na telefon",
]


class TestParseCategoryNames:
    def test_jedna_nazwa_na_linie(self):
        raw = "Elektronika > Audio\nGSM > Etui"
        assert parse_category_names(raw) == ["Elektronika > Audio", "GSM > Etui"]

    def test_usuwa_numeracje_i_wypunktowanie(self):
        raw = "1. Elektronika > Audio\n- GSM > Etui\n• Dom > Kuchnia"
        assert parse_category_names(raw) == ["Elektronika > Audio", "GSM > Etui", "Dom > Kuchnia"]

    def test_usuwa_cudzyslowy_i_puste_linie(self):
        raw = '"Elektronika > Audio"\n\n   \nGSM > Etui'
        assert parse_category_names(raw) == ["Elektronika > Audio", "GSM > Etui"]

    def test_duplikaty_scalone_z_zachowaniem_pierwszej_formy(self):
        raw = "Elektronika > Audio\nelektronika > audio\nGSM > Etui"
        assert parse_category_names(raw) == ["Elektronika > Audio", "GSM > Etui"]

    def test_pusta_odpowiedz_daje_pusta_liste(self):
        assert parse_category_names("") == []


class TestProposeCategoryNames:
    def test_niedostepny_model_podnosi_jasny_blad(self, monkeypatch):
        import catalog_tools.rule_proposer as mod

        def boom(*a, **k):
            raise urllib.error.URLError("refused")

        monkeypatch.setattr(mod, "_call_model", boom)
        with pytest.raises(ProposalError, match="niedostępny"):
            propose_category_names(CATEGORIES)

    def test_pusta_odpowiedz_modelu_podnosi_blad(self, monkeypatch):
        import catalog_tools.rule_proposer as mod

        monkeypatch.setattr(mod, "_call_model", lambda *a, **k: "   ")
        with pytest.raises(ProposalError, match="ani jednej"):
            propose_category_names(CATEGORIES)

    def test_szczesliwa_sciezka(self, monkeypatch):
        import catalog_tools.rule_proposer as mod

        monkeypatch.setattr(mod, "_call_model", lambda *a, **k: "Elektronika > Audio\nGSM > Etui")
        assert propose_category_names(CATEGORIES) == ["Elektronika > Audio", "GSM > Etui"]


class TestProposeRules:
    def test_pusta_lista_podnosi_blad(self):
        with pytest.raises(ProposalError):
            propose_rules([])

    def test_zbyt_duzo_kategorii_podnosi_blad(self):
        with pytest.raises(ProposalError, match="Za dużo"):
            propose_rules([f"kat {i}" for i in range(400)])

    def _patch_two_steps(self, monkeypatch, name_response: str, classify_responses: list[str]):
        """Podmienia obie granice sieciowe: nazywanie kategorii (`_call_model` w
        rule_proposer) i klasyfikację per kategoria (`OllamaClassifier._call`,
        wołane wewnątrz `propose_rules` na świeżo tworzonej instancji — trzeba
        podmienić na poziomie klasy, żeby złapać ją mimo to)."""
        import catalog_tools.rule_proposer as mod

        monkeypatch.setattr(mod, "_call_model", lambda *a, **k: name_response)
        responses = iter(classify_responses)
        monkeypatch.setattr(OllamaClassifier, "_call", lambda self, prompt: next(responses))

    def test_grupuje_przez_klasyfikacje_do_wspolnej_listy(self, monkeypatch):
        # Krok 1: model proponuje jedną wspólną nazwę dla obu kategorii słuchawkowych.
        self._patch_two_steps(
            monkeypatch,
            name_response="Elektronika > Audio\nGSM > Etui",
            classify_responses=["Elektronika > Audio", "Elektronika > Audio", "GSM > Etui"],
        )

        proposal = propose_rules(CATEGORIES)

        assert set(proposal.rules["mapowanie"]) == {"Elektronika > Audio", "GSM > Etui"}
        assert len(proposal.rules["mapowanie"]["Elektronika > Audio"]) == 2
        assert proposal.unmapped == []

    def test_kategorie_bez_dopasowania_trafiaja_do_unmapped(self, monkeypatch):
        self._patch_two_steps(
            monkeypatch,
            name_response="Elektronika > Audio",
            classify_responses=["Elektronika > Audio", "coś spoza listy", "coś spoza listy"],
        )

        proposal = propose_rules(CATEGORIES)

        assert proposal.unmapped == CATEGORIES[1:]

    def test_zaproponowana_fraza_zawsze_pasuje_do_zrodla(self, monkeypatch):
        """Gwarancja, nie tylko test: reguła zbudowana z dosłownego tekstu
        źródłowego musi dopasować się do pliku, z którego powstała."""
        from catalog_tools.rules import find_category

        self._patch_two_steps(
            monkeypatch, name_response="Elektronika > Audio", classify_responses=["Elektronika > Audio"]
        )

        proposal = propose_rules([CATEGORIES[0]])
        match = find_category(CATEGORIES[0], proposal.rules)
        assert match is not None and match.target_category == "Elektronika > Audio"
