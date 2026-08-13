"""Deterministyczny silnik kategoryzacji: dopasowuje kategorię dostawcy do
kategorii docelowej po zamkniętej liście reguł. Bez sieci, bez LLM — pierwszy,
tani krok w pipeline'ie; drugi krok (model jako fallback) jest w
``llm_fallback.py`` i wchodzi tylko tam, gdzie ten silnik zwróci ``None``.

Format reguł (JSON):
    {
      "wymagane_konteksty": {"<prefiks kategorii docelowej>": "<słowo wymagane w źródle>"},
      "mapowanie": {"<kategoria docelowa>": ["<fraza źródłowa>", ...]}
    }
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Match:
    target_category: str
    matched_phrase: str


def find_category(source_category: str, rules: dict) -> Match | None:
    """Dopasowuje kategorię źródłową do kategorii docelowej z reguł.

    Dopasowanie jest po SUFIKSIE: fraza z reguły musi kończyć znormalizowaną
    (małe litery, bez białych znaków na brzegach) kategorię źródłową. To
    pozwala jednej regule obsłużyć różne prefiksy ("Elektronika > Etui",
    "Akcesoria / Etui" — obie kończą się na "etui").

    Gdy dla kategorii docelowej zdefiniowano wymagany kontekst (np. reguła dla
    "Akcesoria GSM" wymaga słowa "telefon" w źródle), dopasowanie bez tego
    słowa jest odrzucane — zapobiega to fałszywym trafieniom w niepowiązanych
    kategoriach o podobnej końcówce.
    """
    if not source_category:
        return None

    normalized = source_category.lower().strip()
    required_contexts: dict[str, str] = rules.get("wymagane_konteksty", {})
    mapping: dict[str, list[str] | str] = rules.get("mapowanie", {})
    context_check_enabled = bool(required_contexts)

    for target_category, phrases in mapping.items():
        phrase_list = phrases if isinstance(phrases, list) else [phrases]

        matched_phrase = next(
            (p for p in phrase_list if normalized.endswith(p.lower().strip())), None
        )
        if matched_phrase is None:
            continue

        if not context_check_enabled:
            return Match(target_category, matched_phrase)

        required_word = next(
            (word for prefix, word in required_contexts.items() if target_category.startswith(prefix)),
            None,
        )
        if required_word is None or required_word.lower() in normalized:
            return Match(target_category, matched_phrase)
        # Fraza pasuje, ale brak wymaganego kontekstu — reguła nie dotyczy tej
        # kategorii docelowej; próbujemy dalej, inna reguła może pasować lepiej.

    return None


def categories_from_rules(rules: dict) -> list[str]:
    """Zamknięta lista kategorii docelowych — używana też przez fallback LLM,
    żeby model nigdy nie mógł wymyślić kategorii spoza tego, co obsługuje silnik."""
    return sorted(rules.get("mapowanie", {}).keys())
