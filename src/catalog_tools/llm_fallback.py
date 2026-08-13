"""Klasyfikacja kategorii lokalnym modelem — fallback dla silnika reguł.

Silnik reguł (``rules.find_category``) jest deterministyczny, darmowy i szybki,
więc zostaje pierwszym krokiem. Model wchodzi dopiero tam, gdzie reguły
zwróciły ``None`` — czyli dla kategorii źródłowych, których nikt jeszcze nie
zmapował.

Trzy rzeczy trzymają to w ryzach:

* **zamknięta lista** — model dostaje pełny wykaz kategorii docelowych i może
  zwrócić wyłącznie jedną z nich; cokolwiek innego odrzucamy jako brak odpowiedzi,
* **cache** — ta sama kategoria źródłowa nie idzie do modelu dwa razy, także między
  uruchomieniami,
* **tryb bez rozumowania** — ``think: false``, bo przy zamkniętej liście łańcuch myśli
  nic nie wnosi, a wydłuża odpowiedź z ~0,5 s do kilkunastu sekund.

Model działa lokalnie przez Ollamę: bez klucza, bez wysyłania danych produktowych
na zewnątrz. To jest tu wymaganie, nie wygoda — katalogi są cudzą własnością.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen3.5:9b"
DEFAULT_CACHE_PATH = Path("data") / "llm_cache.sqlite"
NO_MATCH = "BRAK"

PROMPT = """Jesteś klasyfikatorem kategorii produktowych w sklepie internetowym.

Dostajesz nazwę kategorii z pliku dostawcy. Przypisz ją do JEDNEJ kategorii z listy poniżej.

ZASADY:
- Odpowiedz WYŁĄCZNIE pełną nazwą kategorii, skopiowaną dokładnie z listy.
- Nie dodawaj wyjaśnień, cudzysłowów ani znaków interpunkcyjnych.
- Jeśli żadna kategoria nie pasuje sensownie, odpowiedz: {no_match}

LISTA KATEGORII:
{categories}

KATEGORIA DOSTAWCY: {source}

ODPOWIEDŹ:"""


def _normalize(text: str) -> str:
    """Do porównań: bez wielkości liter, bez nadmiarowych spacji wokół separatora."""
    return " > ".join(part.strip().lower() for part in text.replace(">", " > ").split(" > ") if part.strip())


class ResponseCache:
    """Trwały cache odpowiedzi modelu, kluczowany kategorią źródłową i modelem."""

    def __init__(self, path: Path = DEFAULT_CACHE_PATH):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_category (
                source_category TEXT NOT NULL,
                model           TEXT NOT NULL,
                target_category TEXT,
                created_at      REAL NOT NULL,
                PRIMARY KEY (source_category, model)
            )
            """
        )
        self._conn.commit()

    def get(self, source: str, model: str) -> tuple[bool, str | None]:
        """Zwraca ``(trafienie, wartość)``. Zapamiętany brak dopasowania to też trafienie."""
        row = self._conn.execute(
            "SELECT target_category FROM llm_category WHERE source_category = ? AND model = ?",
            (source, model),
        ).fetchone()
        return (True, row[0]) if row else (False, None)

    def set(self, source: str, model: str, target: str | None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO llm_category (source_category, model, target_category, created_at) "
            "VALUES (?, ?, ?, ?)",
            (source, model, target, time.time()),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


@dataclass
class OllamaClassifier:
    """Klasyfikator oparty o lokalny model, ograniczony do zamkniętej listy kategorii."""

    categories: list[str]
    model: str = DEFAULT_MODEL
    host: str = DEFAULT_HOST
    timeout: int = 60
    cache: ResponseCache | None = None
    _by_normalized: dict[str, str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.categories:
            raise ValueError("lista kategorii nie może być pusta")
        self._by_normalized = {_normalize(c): c for c in self.categories}

    # --- wywołanie modelu -------------------------------------------------

    def _call(self, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "options": {"temperature": 0, "num_predict": 60},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.host}/api/generate", data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read()).get("response", "")

    # --- walidacja --------------------------------------------------------

    def parse(self, raw: str) -> str | None:
        """Zamienia odpowiedź modelu na kategorię z listy albo ``None``.

        Model bywa gadatliwy mimo instrukcji, więc bierzemy pierwszą niepustą
        linię i porównujemy po normalizacji. Cokolwiek spoza listy = brak wyniku.
        """
        if not raw:
            return None
        line = next((ln.strip() for ln in raw.strip().splitlines() if ln.strip()), "")
        line = line.strip("\"'` .")
        if not line or line.upper() == NO_MATCH:
            return None
        return self._by_normalized.get(_normalize(line))

    # --- API publiczne ----------------------------------------------------

    def classify(self, source_category: str) -> str | None:
        """Kategoria docelowa dla nazwy od dostawcy albo ``None``."""
        source = (source_category or "").strip()
        if not source:
            return None

        if self.cache:
            hit, value = self.cache.get(source, self.model)
            if hit:
                log.debug("cache: %s -> %s", source, value)
                return value

        prompt = PROMPT.format(
            no_match=NO_MATCH, categories="\n".join(self.categories), source=source
        )
        try:
            result = self.parse(self._call(prompt))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            # Niedostępny model nie może wywrócić całego przetwarzania — reguły
            # już zrobiły swoje, a brak fallbacku to po prostu brak fallbacku.
            log.warning("Model niedostępny (%s) — pomijam fallback dla %r", exc, source)
            return None

        if self.cache:
            self.cache.set(source, self.model, result)
        return result
