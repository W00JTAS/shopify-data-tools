"""Testy pipeline.categorize_frame — logika współdzielona przez CLI i panel."""

from __future__ import annotations

import pandas as pd

from catalog_tools.pipeline import categorize_frame

RULES = {"wymagane_konteksty": {}, "mapowanie": {"Audio": ["słuchawki bluetooth"]}}


class TestUnresolvedCategories:
    def test_zbiera_unikalne_nierozpoznane_zrodla_z_liczba_wystapien(self):
        frame = pd.DataFrame(
            {
                "kategoria": [
                    "słuchawki bluetooth",
                    "coś innego",
                    "coś innego",
                    "zupełnie inna rzecz",
                ]
            }
        )
        _, summary = categorize_frame(frame, "kategoria", RULES)
        assert summary["unresolved"] == 3
        assert summary["unresolved_categories"] == [
            {"source": "coś innego", "count": 2},
            {"source": "zupełnie inna rzecz", "count": 1},
        ]

    def test_pusta_lista_gdy_wszystko_dopasowane(self):
        frame = pd.DataFrame({"kategoria": ["słuchawki bluetooth"]})
        _, summary = categorize_frame(frame, "kategoria", RULES)
        assert summary["unresolved_categories"] == []

    def test_limit_100_pozycji(self):
        frame = pd.DataFrame({"kategoria": [f"nieznana kategoria {i}" for i in range(150)]})
        _, summary = categorize_frame(frame, "kategoria", RULES)
        assert summary["unresolved"] == 150
        assert len(summary["unresolved_categories"]) == 100
