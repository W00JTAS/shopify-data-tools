"""Testy fallbacku LLM — bez wywoływania modelu.

Najważniejsze jest tu to, że odpowiedź spoza zamkniętej listy NIE przechodzi.
Model, który wymyśli własną kategorię, jest gorszy od modelu, który milczy —
bo cicho zanieczyszcza katalog.
"""

from __future__ import annotations

import urllib.error

import pytest

from catalog_tools.llm_fallback import NO_MATCH, OllamaClassifier, ResponseCache

CATEGORIES = [
    "Akcesoria GSM > Etui i Ochrona > Etui i Pokrowce",
    "Akcesoria GSM > Audio > Słuchawki Bluetooth",
    "Akcesoria IT > Zasilanie > Powerbanki",
]


def classifier(response: str, **kwargs) -> OllamaClassifier:
    """Klasyfikator z podmienionym wywołaniem modelu."""
    instance = OllamaClassifier(categories=CATEGORIES, **kwargs)
    instance._call = lambda prompt: response  # type: ignore[method-assign]
    return instance


class TestParse:
    def test_dokladne_dopasowanie(self):
        assert classifier("").parse(CATEGORIES[0]) == CATEGORIES[0]

    def test_ignoruje_wielkosc_liter_i_spacje(self):
        assert classifier("").parse("  akcesoria gsm > audio > słuchawki bluetooth  ") == CATEGORIES[1]

    def test_znosi_cudzyslowy_i_kropke(self):
        assert classifier("").parse(f'"{CATEGORIES[2]}".') == CATEGORIES[2]

    def test_bierze_pierwsza_niepusta_linie(self):
        assert classifier("").parse(f"\n\n{CATEGORIES[0]}\njakiś komentarz") == CATEGORIES[0]

    def test_kategoria_spoza_listy_jest_odrzucana(self):
        assert classifier("").parse("Elektronika > Wymyślona Kategoria") is None

    def test_jawny_brak_dopasowania(self):
        assert classifier("").parse(NO_MATCH) is None

    def test_pusta_odpowiedz(self):
        assert classifier("").parse("") is None
        assert classifier("").parse("   \n  ") is None


class TestClassify:
    def test_zwraca_kategorie_z_listy(self):
        assert classifier(CATEGORIES[1]).classify("Słuchawki bezprzewodowe") == CATEGORIES[1]

    def test_pusty_input_nie_woła_modelu(self):
        instance = OllamaClassifier(categories=CATEGORIES)
        instance._call = lambda prompt: pytest.fail("model nie powinien być wołany")
        assert instance.classify("   ") is None

    def test_niedostepny_model_nie_wywraca_przetwarzania(self):
        instance = OllamaClassifier(categories=CATEGORIES)

        def boom(prompt):
            raise urllib.error.URLError("connection refused")

        instance._call = boom  # type: ignore[method-assign]
        assert instance.classify("cokolwiek") is None

    def test_pusta_lista_kategorii_to_blad(self):
        with pytest.raises(ValueError):
            OllamaClassifier(categories=[])


class TestCache:
    @pytest.fixture
    def cache(self, tmp_path):
        instance = ResponseCache(tmp_path / "cache.sqlite")
        yield instance
        instance.close()

    def test_drugie_wywolanie_nie_pyta_modelu(self, cache):
        calls = []
        instance = OllamaClassifier(categories=CATEGORIES, cache=cache)
        instance._call = lambda prompt: (calls.append(1), CATEGORIES[0])[1]  # type: ignore

        assert instance.classify("Etui") == CATEGORIES[0]
        assert instance.classify("Etui") == CATEGORIES[0]
        assert len(calls) == 1, "druga klasyfikacja powinna iść z cache'u"

    def test_brak_dopasowania_tez_jest_cachowany(self, cache):
        calls = []
        instance = OllamaClassifier(categories=CATEGORIES, cache=cache)
        instance._call = lambda prompt: (calls.append(1), "coś spoza listy")[1]  # type: ignore

        assert instance.classify("Dziwny produkt") is None
        assert instance.classify("Dziwny produkt") is None
        assert len(calls) == 1, "zapamiętany brak wyniku też oszczędza wywołanie"

    def test_cache_przezywa_ponowne_otwarcie(self, tmp_path):
        path = tmp_path / "c.sqlite"
        first = ResponseCache(path)
        first.set("Etui", "m", CATEGORIES[0])
        first.close()

        second = ResponseCache(path)
        assert second.get("Etui", "m") == (True, CATEGORIES[0])
        second.close()

    def test_inny_model_ma_osobny_wpis(self, cache):
        cache.set("Etui", "model-a", CATEGORIES[0])
        assert cache.get("Etui", "model-b") == (False, None)

    def test_tworzy_brakujace_katalogi_nadrzedne(self, tmp_path):
        path = tmp_path / "zagniezdzony" / "cache.sqlite"
        instance = ResponseCache(path)
        instance.set("x", "m", "y")
        instance.close()
        assert path.exists()
