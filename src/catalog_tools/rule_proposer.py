"""AI proponuje reguły kategoryzacji na podstawie surowych kategorii z pliku.

Wynik jest **zawsze szkicem do przejrzenia** — panel pokazuje go w edytorze
przed uruchomieniem kategoryzacji; ten moduł nigdy nie uruchamia kategoryzacji
sam.

Dwuetapowo, celowo — pierwsza wersja pytała model o cały szkic reguł
w jednym wywołaniu i to się nie sprawdziło: przy słabszym prompcie model
prawie nie grupował (33 kategorie źródłowe → 33 grupy), a przy prompcie
naciskającym na grupowanie zaczynał wklejać komentarze w środek odpowiedzi
("(połączenie z 20)"), psując format. Rozbicie na dwa kroki naprawia oba
problemy naraz:

1. **Nazwij kategorie docelowe** — jedno wywołanie, model proponuje krótką
   listę nazw pokrywającą cały katalog. Prosty format (jedna nazwa na linię),
   niski koszt błędu.
2. **Klasyfikuj do tej listy** — dokładnie ``OllamaClassifier`` z
   ``llm_fallback.py``, ten sam, który w kategoryzacji odrzuca odpowiedzi
   spoza zamkniętej listy zamiast je naprawiać. Grupowanie wychodzi tu za
   darmo: różne sformułowania tego samego produktu trafiają do tej samej,
   już istniejącej nazwy, bo model wybiera z ustalonej listy, nie wymyśla
   za każdym razem od nowa.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from .llm_fallback import DEFAULT_HOST, DEFAULT_MODEL, OllamaClassifier

NAME_PROMPT = """Jesteś analitykiem katalogu produktowego. Dostajesz listę unikalnych
kategorii dostawcy ze sklepu internetowego. Zaproponuj listę kategorii
docelowych, które razem pokryją WSZYSTKIE poniższe pozycje — kategorie
oznaczające ten sam typ produktu (nawet różnie nazwane) mają być pokryte
JEDNĄ wspólną nazwą, nie osobnymi.

Zasady:
- Format nazwy: "Dział > Temat" (2-3 poziomy, po polsku).
- Celuj w około {target_count} kategorii docelowych — nie więcej niż
  {max_count}.
- Odpowiedz WYŁĄCZNIE listą nazw, jedna na linię, bez numeracji,
  bez wstępu i bez podsumowania.

KATEGORIE ŹRÓDŁOWE:
{items}

LISTA KATEGORII DOCELOWYCH:"""

MAX_INPUT_CATEGORIES = 300  # bezpiecznik: powyżej tego jedno wywołanie na kategorię trwałoby zbyt długo


class ProposalError(RuntimeError):
    """Model nie zwrócił odpowiedzi w oczekiwanym kształcie."""


@dataclass(frozen=True)
class Proposal:
    rules: dict
    unmapped: list[str]  # kategorie, których model nie przypisał do żadnej z zaproponowanych nazw


def _call_model(prompt: str, model: str, host: str, timeout: int) -> str:
    payload = json.dumps(
        {"model": model, "prompt": prompt, "stream": False, "think": False, "options": {"temperature": 0}}
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{host}/api/generate", data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read()).get("response", "")


def parse_category_names(raw: str) -> list[str]:
    """Czyści odpowiedź modelu do listy nazw: usuwa numerację, cudzysłowy,
    puste linie i duplikaty (przy zachowaniu kolejności)."""
    seen: dict[str, str] = {}
    for line in raw.strip().splitlines():
        name = re.sub(r"^\s*[\d.\-•]+\s*", "", line).strip("\"'` .")
        name = re.sub(r"\s+", " ", name).strip()
        if name and name.lower() not in seen:
            seen[name.lower()] = name
    return list(seen.values())


def propose_category_names(
    categories: list[str],
    target_count: int = 12,
    model: str = DEFAULT_MODEL,
    host: str = DEFAULT_HOST,
    timeout: int = 120,
) -> list[str]:
    prompt = NAME_PROMPT.format(
        target_count=target_count,
        max_count=target_count * 2,
        items="\n".join(f"- {c}" for c in categories),
    )
    try:
        raw = _call_model(prompt, model, host, timeout)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ProposalError(f"Model niedostępny: {exc}") from exc

    names = parse_category_names(raw)
    if not names:
        raise ProposalError("Model nie zaproponował ani jednej nazwy kategorii.")
    return names


def propose_rules(
    categories: list[str],
    target_count: int = 12,
    model: str = DEFAULT_MODEL,
    host: str = DEFAULT_HOST,
    timeout: int = 120,
) -> Proposal:
    """Pełna dwuetapowa ścieżka: nazwij kategorie, potem sklasyfikuj do nich."""
    if not categories:
        raise ProposalError("Brak kategorii do zaproponowania.")
    if len(categories) > MAX_INPUT_CATEGORIES:
        raise ProposalError(
            f"Za dużo unikalnych kategorii ({len(categories)}) na jedno żądanie — "
            f"limit to {MAX_INPUT_CATEGORIES}. Podziel plik albo napisz reguły ręcznie."
        )

    target_names = propose_category_names(categories, target_count, model, host, timeout)
    classifier = OllamaClassifier(categories=target_names, model=model, host=host, timeout=timeout)

    mapping: dict[str, list[str]] = {}
    unmapped: list[str] = []
    for source in categories:
        target = classifier.classify(source)
        if not target:
            unmapped.append(source)
            continue
        phrase = source.strip().lower()
        bucket = mapping.setdefault(target, [])
        if phrase not in bucket:
            bucket.append(phrase)

    return Proposal(rules={"wymagane_konteksty": {}, "mapowanie": mapping}, unmapped=unmapped)
