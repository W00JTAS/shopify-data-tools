"""Konsolidacja osobnych ofert w jeden produkt z wariantami.

Wejściowy katalog bywa eksportowany tak, że każdy kolor osobnego produktu jest
osobnym wpisem — „Sukienka Midnight”, „Sukienka Sand” — zamiast jednego
produktu „Sukienka” z wariantem koloru. To narzędzie je grupuje.

Heurystyka jest celowo prosta i jawnie ograniczona: **wariant to ostatnie
słowo tytułu**. Działa dobrze dla „Sukienka Midnight”, nie złapie
dwuwyrazowego wariantu w stylu „Sukienka Midnight Blue” — to udokumentowane
ograniczenie w README, nie ukryty błąd. Kolor każdego wariantu rozwiązuje
``colors.resolve()``: najpierw słownik, potem zdjęcie, a gdy i to zawiedzie —
wiersz trafia do raportu jako nierozpoznany, zamiast dostać zgadywaną wartość.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import colors

OPTION_NAME = "Kolor"


@dataclass
class ConsolidatedRow:
    handle: str
    title: str  # puste dla wszystkich wierszy grupy poza pierwszym — konwencja Shopify
    option_name: str
    option_value: str
    sku: str
    price: str
    image_src: str
    source_handle: str  # oryginalny Handle, do audytu


@dataclass
class ConsolidationResult:
    rows: list[ConsolidatedRow] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)  # "Handle: token"
    groups_consolidated: int = 0
    groups_passthrough: int = 0  # pojedyncze produkty, nic do konsolidacji


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9ąćęłńóśźż]+", "-", text)
    return re.sub(r"-{2,}", "-", text).strip("-")


def split_variant_token(title: str) -> tuple[str, str]:
    """(baza, ostatnie słowo). Tytuł jednowyrazowy nie ma z czego wydzielić
    wariantu — baza to cały tytuł, token pusty."""
    words = title.strip().split()
    if len(words) < 2:
        return title.strip(), ""
    return " ".join(words[:-1]), words[-1]


def group_by_base_title(rows: list[dict]) -> dict[str, list[dict]]:
    """Grupuje wiersze po bazowym tytule (tytuł bez ostatniego słowa)."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        base, _ = split_variant_token(row.get("Title", ""))
        groups.setdefault(base, []).append(row)
    return groups


ImageFetcher = "Callable[[str], bytes | None] | None"


def consolidate(rows: list[dict], image_fetcher=None) -> ConsolidationResult:
    """Grupuje i rozwiązuje kolory. ``image_fetcher(url) -> bytes | None`` jest
    wstrzykiwany — testy nie robią zapytań sieciowych, CLI podaje prawdziwy
    ``requests.get``."""
    result = ConsolidationResult()
    groups = group_by_base_title(rows)

    for base_title, group_rows in groups.items():
        if len(group_rows) < 2:
            # Nic do konsolidacji — pojedynczy produkt zostaje bez zmian,
            # z pustą wartością opcji (nie ma z czego jej wydzielić).
            row = group_rows[0]
            result.rows.append(
                ConsolidatedRow(
                    handle=slugify(row.get("Title", "")),
                    title=row.get("Title", ""),
                    option_name="",
                    option_value="",
                    sku=row.get("Variant SKU", ""),
                    price=row.get("Variant Price", ""),
                    image_src=row.get("Image Src", ""),
                    source_handle=row.get("Handle", ""),
                )
            )
            result.groups_passthrough += 1
            continue

        result.groups_consolidated += 1
        handle = slugify(base_title)
        for i, row in enumerate(group_rows):
            _, token = split_variant_token(row.get("Title", ""))
            image_bytes = None
            image_url = row.get("Image Src", "")
            resolved = colors.resolve(token)
            if resolved.name is None and image_url and image_fetcher:
                image_bytes = image_fetcher(image_url)
                resolved = colors.resolve(token, image_bytes)

            option_value = resolved.name or token
            if resolved.name is None:
                result.unresolved.append(f"{row.get('Handle', '')}: „{token}”")

            result.rows.append(
                ConsolidatedRow(
                    handle=handle,
                    title=base_title if i == 0 else "",
                    option_name=OPTION_NAME,
                    option_value=option_value,
                    sku=row.get("Variant SKU", ""),
                    price=row.get("Variant Price", ""),
                    image_src=image_url,
                    source_handle=row.get("Handle", ""),
                )
            )

    return result
