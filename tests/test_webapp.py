"""Testy panelu webowego — bez sieci i bez Ollamy.

`propose_rules` jest podmieniony na poziomie modułu; reszta endpointów jest
czysto deterministyczna (reguły, konsolidacja), więc testuje się tak samo jak
CLI, tylko przez klienta HTTP zamiast wywołania funkcji wprost.
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

from catalog_tools.rule_proposer import Proposal
from catalog_tools.webapp.main import app

client = TestClient(app)

CSV = "sku;kategoria\n1;słuchawki bluetooth\n2;coś innego\n"
RULES = {"wymagane_konteksty": {}, "mapowanie": {"Audio": ["słuchawki bluetooth"]}}


def csv_file(content: str = CSV) -> tuple[str, io.BytesIO, str]:
    return ("products.csv", io.BytesIO(content.encode("utf-8")), "text/csv")


class TestIndexAndHealth:
    def test_strona_glowna_sie_laduje(self):
        res = client.get("/")
        assert res.status_code == 200
        assert "Catalog Tools" in res.text

    def test_health_zwraca_status_ollamy(self):
        res = client.get("/api/health")
        assert res.status_code == 200
        assert "ollama" in res.json()


class TestPreview:
    def test_zwraca_kolumny_i_liczbe_wierszy(self):
        res = client.post("/api/preview", files={"file": csv_file()}, data={"sep": ";"})
        assert res.status_code == 200
        data = res.json()
        assert data["columns"] == ["sku", "kategoria"]
        assert data["row_count"] == 2

    def test_zly_separator_daje_czytelny_blad(self):
        res = client.post("/api/preview", files={"file": csv_file()}, data={"sep": "|"})
        # Pandas z jednym-kolumnowym wynikiem nie rzuca wyjątku — sprawdzamy,
        # że po prostu nie znajdzie oczekiwanych kolumn (kontrakt z frontendem).
        assert res.status_code == 200
        assert res.json()["columns"] == ["sku;kategoria"]


class TestCategorizeRun:
    def test_kategoryzuje_bez_modelu(self):
        res = client.post(
            "/api/categorize/run",
            files={"file": csv_file()},
            data={"column": "kategoria", "sep": ";", "rules": '{"wymagane_konteksty":{},"mapowanie":{"Audio":["słuchawki bluetooth"]}}', "use_llm": "false"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["summary"]["matched_by_rules"] == 1
        assert data["summary"]["unresolved"] == 1
        assert "Audio" in data["csv"]

    def test_brakujaca_kolumna_daje_400(self):
        res = client.post(
            "/api/categorize/run",
            files={"file": csv_file()},
            data={"column": "nie_ma_takiej", "sep": ";", "rules": "{}", "use_llm": "false"},
        )
        assert res.status_code == 400

    def test_zly_json_regul_daje_400(self):
        res = client.post(
            "/api/categorize/run",
            files={"file": csv_file()},
            data={"column": "kategoria", "sep": ";", "rules": "{niepoprawny", "use_llm": "false"},
        )
        assert res.status_code == 400


class TestCategorizeProposeRules:
    def test_zwraca_propozycje_z_podmienionego_modelu(self, monkeypatch):
        import catalog_tools.webapp.main as mod

        monkeypatch.setattr(
            mod,
            "propose_rules",
            lambda categories, target_count: Proposal(
                rules={"wymagane_konteksty": {}, "mapowanie": {"Audio": categories}}, unmapped=[]
            ),
        )
        res = client.post(
            "/api/categorize/propose-rules",
            files={"file": csv_file()},
            data={"column": "kategoria", "sep": ";", "target_count": "5"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["target_categories"] == 1
        assert data["unique_categories"] == 2

    def test_blad_modelu_daje_502(self, monkeypatch):
        import catalog_tools.webapp.main as mod
        from catalog_tools.rule_proposer import ProposalError

        def boom(categories, target_count):
            raise ProposalError("model niedostępny")

        monkeypatch.setattr(mod, "propose_rules", boom)
        res = client.post(
            "/api/categorize/propose-rules",
            files={"file": csv_file()},
            data={"column": "kategoria", "sep": ";", "target_count": "5"},
        )
        assert res.status_code == 502


class TestConsolidateRun:
    def test_konsoliduje_i_zwraca_csv(self):
        csv = "Handle,Title,Variant SKU,Variant Price,Image Src\nh1,Sukienka Midnight,A,10,\nh2,Sukienka Sand,B,10,\n"
        res = client.post("/api/consolidate/run", files={"file": ("listings.csv", io.BytesIO(csv.encode()), "text/csv")}, data={"fetch_images": "false"})
        assert res.status_code == 200
        data = res.json()
        assert data["summary"]["groups_consolidated"] == 1
        assert "Granatowy" in data["csv"]

    def test_pusty_plik_daje_400(self):
        res = client.post("/api/consolidate/run", files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")}, data={"fetch_images": "false"})
        assert res.status_code == 400
