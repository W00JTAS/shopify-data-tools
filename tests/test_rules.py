from catalog_tools.rules import Match, categories_from_rules, find_category

RULES = {
    "wymagane_konteksty": {"Akcesoria GSM": "telefon"},
    "mapowanie": {
        "Akcesoria GSM > Etui": ["etui na telefon", "pokrowiec na telefon"],
        "Akcesoria IT > Etui": ["etui", "pokrowiec"],
        "Dom > Oświetlenie": ["lampka choinkowa"],
    },
}


class TestFindCategory:
    def test_dopasowanie_po_sufiksie(self):
        m = find_category("Elektronika / Akcesoria / etui na telefon", RULES)
        assert m == Match("Akcesoria GSM > Etui", "etui na telefon")

    def test_case_insensitive_i_bez_bialych_znakow(self):
        m = find_category("  ETUI NA TELEFON  ", RULES)
        assert m.target_category == "Akcesoria GSM > Etui"

    def test_brak_dopasowania_zwraca_none(self):
        assert find_category("Narzędzia ogrodowe / Szpadel", RULES) is None

    def test_pusty_string_zwraca_none(self):
        assert find_category("", RULES) is None

    def test_wymagany_kontekst_blokuje_falszywe_trafienie(self):
        # "etui" samo pasuje do reguły IT (bez wymogu kontekstu), ale reguła
        # GSM wymaga słowa "telefon" — to sprawdza, że silnik nie miesza reguł.
        m = find_category("Torby / etui", RULES)
        assert m.target_category == "Akcesoria IT > Etui"

    def test_kontekst_gdy_spelniony_pozwala_dopasowac_gsm(self):
        m = find_category("etui na telefon", RULES)
        assert m.target_category == "Akcesoria GSM > Etui"

    def test_pierwsza_pasujaca_regula_wygrywa(self):
        m = find_category("lampka choinkowa", RULES)
        assert m.target_category == "Dom > Oświetlenie"

    def test_brak_wymaganych_kontekstow_wylacza_sprawdzanie(self):
        rules = {"mapowanie": {"X": ["y"]}}
        assert find_category("to jest y", rules).target_category == "X"


class TestCategoriesFromRules:
    def test_zwraca_posortowane_klucze(self):
        assert categories_from_rules(RULES) == [
            "Akcesoria GSM > Etui",
            "Akcesoria IT > Etui",
            "Dom > Oświetlenie",
        ]

    def test_brak_mapowania_daje_pusta_liste(self):
        assert categories_from_rules({}) == []
