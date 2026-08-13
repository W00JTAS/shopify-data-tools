"""Interfejs wiersza poleceń.

    catalog-tools categorize --csv data/sample/products.csv --rules data/sample/rules.json
    catalog-tools consolidate --csv data/sample/listings.csv --out data/out/consolidated.csv
    catalog-tools benchmark --csv data/sample/products.csv --rules data/sample/rules.json --limit 50
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import requests

from . import consolidate
from .llm_fallback import OllamaClassifier, ResponseCache
from .rules import categories_from_rules, find_category


def _load_rules(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_categorize(args: argparse.Namespace) -> int:
    rules = _load_rules(args.rules)
    frame = pd.read_csv(args.csv, sep=args.sep, dtype=str)
    if args.column not in frame.columns:
        print(f"Brak kolumny {args.column!r}. Dostępne: {list(frame.columns)}", file=sys.stderr)
        return 2

    classifier = None
    if args.use_llm:
        classifier = OllamaClassifier(categories=categories_from_rules(rules), cache=ResponseCache())

    matched = via_llm = unresolved = 0
    out_categories: list[str | None] = []
    for source in frame[args.column].fillna(""):
        match = find_category(str(source), rules)
        if match:
            out_categories.append(match.target_category)
            matched += 1
            continue
        target = classifier.classify(str(source)) if classifier else None
        out_categories.append(target)
        if target:
            via_llm += 1
        else:
            unresolved += 1

    frame["kategoria_docelowa"] = out_categories
    frame.to_csv(args.out, index=False)
    total = len(frame)
    print(f"reguły: {matched}/{total}   model: {via_llm}/{total}   nierozpoznane: {unresolved}/{total}")
    print(f"zapisano: {args.out}")
    return 0


def cmd_consolidate(args: argparse.Namespace) -> int:
    with open(args.csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    fetcher = None
    if args.fetch_images:
        def fetcher(url: str) -> bytes | None:  # noqa: E306
            try:
                resp = requests.get(url, timeout=10)
                return resp.content if resp.ok else None
            except requests.RequestException:
                return None

    result = consolidate.consolidate(rows, image_fetcher=fetcher)

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Handle", "Title", "Option1 Name", "Option1 Value", "Variant SKU", "Variant Price", "Image Src"])
        for r in result.rows:
            writer.writerow([r.handle, r.title, r.option_name, r.option_value, r.sku, r.price, r.image_src])

    print(f"skonsolidowano grup: {result.groups_consolidated}   pojedynczych: {result.groups_passthrough}")
    if result.unresolved:
        print(f"nierozpoznane warianty ({len(result.unresolved)}):")
        for line in result.unresolved:
            print(f"  {line}")
    print(f"zapisano: {args.out}")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    rules = _load_rules(args.rules)
    categories = categories_from_rules(rules)
    print(f"Kategorii docelowych w regułach: {len(categories)}")

    frame = pd.read_csv(args.csv, sep=args.sep, dtype=str, engine="python", on_bad_lines="skip")
    unique = [c for c in frame[args.column].dropna().unique() if str(c).strip()]
    print(f"Unikalnych kategorii źródłowych: {len(unique)}")

    matched = {c: find_category(str(c), rules) for c in unique}
    by_rules = {c: m for c, m in matched.items() if m}
    unmatched = [c for c, m in matched.items() if not m]
    print(f"\nSILNIK REGUŁ: {len(by_rules)}/{len(unique)} ({100*len(by_rules)/len(unique):.1f}%)")

    if not unmatched:
        print("Reguły pokryły wszystko — model nie ma co robić.")
        return 0

    rng = random.Random(args.seed)
    sample = rng.sample(unmatched, min(args.limit, len(unmatched)))

    cache = None if args.no_cache else ResponseCache()
    classifier = OllamaClassifier(categories=categories, cache=cache)
    print(f"\nMODEL ({classifier.model}) na {len(sample)} nierozpoznanych kategoriach...")

    started = time.time()
    by_llm: dict[str, str] = {}
    for source in sample:
        target = classifier.classify(str(source))
        if target:
            by_llm[str(source)] = target
    elapsed = time.time() - started

    resolved = len(by_llm)
    print(f"MODEL: {resolved}/{len(sample)} ({100*resolved/len(sample):.1f}%) w {elapsed:.0f}s")
    if by_llm:
        print("\nRozkład kategorii wybranych przez model:")
        for target, count in Counter(by_llm.values()).most_common(5):
            print(f"  {count:3}x {target}")
    if cache:
        cache.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="catalog-tools", description="Kategoryzacja i konsolidacja katalogu produktowego")
    sub = parser.add_subparsers(dest="command", required=True)

    cat = sub.add_parser("categorize", help="dopasuj kategorie po regułach + model jako fallback")
    cat.add_argument("--csv", type=Path, required=True)
    cat.add_argument("--rules", type=Path, required=True)
    cat.add_argument("--column", default="kategoria")
    cat.add_argument("--sep", default=";")
    cat.add_argument("--out", type=Path, default=Path("data/out/categorized.csv"))
    cat.add_argument("--use-llm", action="store_true", help="dopytaj lokalny model o nierozpoznane kategorie")
    cat.set_defaults(func=cmd_categorize)

    con = sub.add_parser("consolidate", help="połącz osobne wpisy w produkt z wariantami")
    con.add_argument("--csv", type=Path, required=True)
    con.add_argument("--out", type=Path, default=Path("data/out/consolidated.csv"))
    con.add_argument("--fetch-images", action="store_true", help="pobierz zdjęcie, gdy słownik nie rozpozna koloru")
    con.set_defaults(func=cmd_consolidate)

    bench = sub.add_parser("benchmark", help="reguły vs. model na realnym pliku")
    bench.add_argument("--csv", type=Path, required=True)
    bench.add_argument("--rules", type=Path, required=True)
    bench.add_argument("--column", default="kategoria")
    bench.add_argument("--sep", default=";")
    bench.add_argument("--limit", type=int, default=150)
    bench.add_argument("--seed", type=int, default=42)
    bench.add_argument("--no-cache", action="store_true")
    bench.set_defaults(func=cmd_benchmark)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True) if hasattr(args, "out") else None
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
