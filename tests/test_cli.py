"""Testy CLI end-to-end na plikach tymczasowych — bez modelu (--use-llm
wymaga Ollamy, więc zostaje poza CI; ścieżka regułowa jest w pełni testowalna
bez żadnej zewnętrznej usługi)."""

from __future__ import annotations

import csv
import json

from catalog_tools.cli import main

RULES = {"wymagane_konteksty": {}, "mapowanie": {"Dom > Oświetlenie": ["lampka choinkowa"]}}


def write_csv(path, rows, fieldnames, delimiter=","):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


class TestCategorize:
    def test_dopasowuje_i_zapisuje_wynik(self, tmp_path, capsys):
        rules_path = tmp_path / "rules.json"
        rules_path.write_text(json.dumps(RULES), encoding="utf-8")
        csv_path = tmp_path / "products.csv"
        write_csv(
            csv_path,
            [{"sku": "1", "kategoria": "Świąteczne / lampka choinkowa"}, {"sku": "2", "kategoria": "Coś innego"}],
            ["sku", "kategoria"],
            delimiter=";",
        )
        out_path = tmp_path / "out.csv"

        code = main(["categorize", "--csv", str(csv_path), "--rules", str(rules_path), "--out", str(out_path)])

        assert code == 0
        assert out_path.exists()
        content = out_path.read_text(encoding="utf-8")
        assert "Dom > Oświetlenie" in content
        assert "reguły: 1/2" in capsys.readouterr().out

    def test_brakujaca_kolumna_zwraca_kod_bledu(self, tmp_path):
        rules_path = tmp_path / "rules.json"
        rules_path.write_text(json.dumps(RULES), encoding="utf-8")
        csv_path = tmp_path / "products.csv"
        write_csv(csv_path, [{"sku": "1", "inna_kolumna": "x"}], ["sku", "inna_kolumna"], delimiter=";")

        code = main(["categorize", "--csv", str(csv_path), "--rules", str(rules_path), "--out", str(tmp_path / "o.csv")])
        assert code == 2


class TestConsolidate:
    def test_konsoliduje_i_zapisuje_wynik(self, tmp_path, capsys):
        csv_path = tmp_path / "listings.csv"
        write_csv(
            csv_path,
            [
                {"Handle": "h1", "Title": "Sukienka Midnight", "Variant SKU": "A", "Variant Price": "10", "Image Src": ""},
                {"Handle": "h2", "Title": "Sukienka Sand", "Variant SKU": "B", "Variant Price": "10", "Image Src": ""},
            ],
            ["Handle", "Title", "Variant SKU", "Variant Price", "Image Src"],
        )
        out_path = tmp_path / "out.csv"

        code = main(["consolidate", "--csv", str(csv_path), "--out", str(out_path)])

        assert code == 0
        rows = list(csv.DictReader(out_path.open(encoding="utf-8")))
        assert len(rows) == 2
        assert {r["Option1 Value"] for r in rows} == {"Granatowy", "Beżowy"}
        assert "skonsolidowano grup: 1" in capsys.readouterr().out
