"""Wspólna logika kategoryzacji i eksportu — jedno miejsce prawdy dla CLI
i panelu webowego, żeby oba działały identycznie zamiast dwóch osobnych
implementacji, które mogłyby się rozjechać."""

from __future__ import annotations

import csv
import io
from collections import Counter

import pandas as pd

from .consolidate import ConsolidatedRow
from .llm_fallback import DEFAULT_HOST, DEFAULT_MODEL, OllamaClassifier, ResponseCache
from .rules import categories_from_rules, find_category


def categorize_frame(
    frame: pd.DataFrame,
    column: str,
    rules: dict,
    use_llm: bool = False,
    model: str = DEFAULT_MODEL,
    host: str = DEFAULT_HOST,
    cache: ResponseCache | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Dopasowuje kategorie: reguły najpierw, model tylko tam, gdzie reguły
    nie złapały. Zwraca ramkę z nową kolumną i podsumowanie liczbowe."""
    classifier = None
    if use_llm:
        classifier = OllamaClassifier(
            categories=categories_from_rules(rules), model=model, host=host, cache=cache
        )

    matched = via_llm = unresolved = 0
    unresolved_counts: Counter[str] = Counter()
    out: list[str | None] = []
    for source in frame[column].fillna(""):
        source = str(source)
        match = find_category(source, rules)
        if match:
            out.append(match.target_category)
            matched += 1
            continue
        target = classifier.classify(source) if classifier else None
        out.append(target)
        if target:
            via_llm += 1
        else:
            unresolved += 1
            unresolved_counts[source] += 1

    result = frame.copy()
    result["kategoria_docelowa"] = out
    unresolved_categories = [
        {"source": source, "count": count} for source, count in unresolved_counts.most_common(100)
    ]
    summary = {
        "total": len(frame),
        "matched_by_rules": matched,
        "matched_by_llm": via_llm,
        "unresolved": unresolved,
        "unresolved_categories": unresolved_categories,
    }
    return result, summary


def consolidated_rows_to_csv(rows: list[ConsolidatedRow]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Handle", "Title", "Option1 Name", "Option1 Value", "Variant SKU", "Variant Price", "Image Src"])
    for r in rows:
        writer.writerow([r.handle, r.title, r.option_name, r.option_value, r.sku, r.price, r.image_src])
    return buf.getvalue()
