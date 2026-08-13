"""Rozpoznawanie nazwy koloru — z tekstu, a gdy tekst zawodzi, ze zdjęcia.

Dwa etapy, w tej kolejności:

1. **Słownik** — deterministyczne dopasowanie słowa (EN/PL) do nazwy koloru.
   Tanie, bez sieci, pokrywa większość przypadków w praktyce.
2. **Zdjęcie** — gdy token nie jest znanym słowem-kolorem, pobieramy obraz,
   liczymy dominujący kolor (rzeczywista ekstrakcja pikseli, nie zgadywanie)
   i mapujemy go na najbliższą nazwę z małej, nazwanej palety.

Nierozpoznany token nigdy nie jest zgadywany na siłę — wraca jako ``None`` ze
źródłem ``"unresolved"``, zgodnie z tą samą zasadą co w ``llm_fallback.py``:
brak wyniku jest lepszy niż wynik zmyślony.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from io import BytesIO

from PIL import Image

# Słownik EN/PL. Świadomie mały i jawny — łatwiej go zweryfikować niż
# zaufać automatycznemu tłumaczeniu, którego jakości nikt nie sprawdza.
COLOR_DICTIONARY: dict[str, str] = {
    "black": "Czarny", "czarny": "Czarny", "czarna": "Czarny", "czarne": "Czarny",
    "white": "Biały", "bialy": "Biały", "biały": "Biały", "biala": "Biały", "biała": "Biały",
    "red": "Czerwony", "czerwony": "Czerwony", "czerwona": "Czerwony",
    "blue": "Niebieski", "niebieski": "Niebieski", "niebieska": "Niebieski",
    "navy": "Granatowy", "granatowy": "Granatowy", "granatowa": "Granatowy",
    "midnight": "Granatowy",
    "green": "Zielony", "zielony": "Zielony", "zielona": "Zielony",
    "pink": "Różowy", "rozowy": "Różowy", "różowy": "Różowy",
    "grey": "Szary", "gray": "Szary", "szary": "Szary", "szara": "Szary",
    "beige": "Beżowy", "bezowy": "Beżowy", "beżowy": "Beżowy",
    "sand": "Beżowy",
    "brown": "Brązowy", "brazowy": "Brązowy", "brązowy": "Brązowy",
    "yellow": "Żółty", "zolty": "Żółty", "żółty": "Żółty",
    "orange": "Pomarańczowy", "pomaranczowy": "Pomarańczowy", "pomarańczowy": "Pomarańczowy",
    "purple": "Fioletowy", "fioletowy": "Fioletowy",
}

# Paleta do dopasowania po odcieniu ze zdjęcia — nazwy muszą pokrywać się
# z tymi w COLOR_DICTIONARY, żeby wynik obu ścieżek był spójny.
NAMED_PALETTE: dict[str, tuple[int, int, int]] = {
    "Czarny": (20, 20, 20),
    "Biały": (245, 245, 245),
    "Czerwony": (200, 30, 30),
    "Niebieski": (30, 80, 200),
    "Granatowy": (20, 30, 80),
    "Zielony": (40, 140, 60),
    "Różowy": (230, 130, 180),
    "Szary": (130, 130, 130),
    "Beżowy": (220, 200, 170),
    "Brązowy": (110, 70, 40),
    "Żółty": (230, 210, 40),
    "Pomarańczowy": (230, 130, 30),
    "Fioletowy": (120, 60, 160),
}


@dataclass(frozen=True)
class ColorResult:
    name: str | None
    source: str  # "dictionary" | "image" | "unresolved"


def from_dictionary(token: str) -> str | None:
    """Dopasowanie po dokładnym słowie — czyszczone z diakrytyków celowo nie jest,
    słownik ma warianty z i bez ogonków wprost, żeby dopasowanie zostało jawne."""
    key = token.strip().lower()
    return COLOR_DICTIONARY.get(key)


def dominant_color(image_bytes: bytes, sample_size: int = 40) -> tuple[int, int, int]:
    """Prawdziwa ekstrakcja dominującego koloru: zmniejsza obraz i liczy,
    który (skwantowany) kolor pikseli występuje najczęściej.

    Kwantyzacja do kroku 16 na kanał redukuje szum kompresji JPEG, który przy
    liczeniu surowych wartości RGB rozbiłby jeden wizualny kolor na setki
    prawie identycznych — i dominanta wyszłaby przypadkowa.
    """
    img = Image.open(BytesIO(image_bytes)).convert("RGB").resize((sample_size, sample_size))
    get_pixels = getattr(img, "get_flattened_data", img.getdata)  # Pillow <12 fallback
    pixels = list(get_pixels())

    def quantize(px: tuple[int, int, int]) -> tuple[int, int, int]:
        return tuple((c // 16) * 16 for c in px)

    counts = Counter(quantize(p) for p in pixels)
    most_common, _ = counts.most_common(1)[0]
    return most_common


def nearest_named_color(rgb: tuple[int, int, int]) -> str:
    """Najbliższy kolor z nazwanej palety, odległość euklidesowa w RGB.

    To nie jest percepcyjnie doskonałe (RGB nie jest przestrzenią jednorodną
    dla ludzkiego oka), ale jest proste, deterministyczne i wystarczające przy
    małej, kilkunastoelementowej palecie — dokładnie taki kompromis, jaki ma
    sens dla narzędzia do katalogu, nie do profesjonalnej kolorymetrii.
    """
    def dist2(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
        return sum((x - y) ** 2 for x, y in zip(a, b))

    return min(NAMED_PALETTE, key=lambda name: dist2(rgb, NAMED_PALETTE[name]))


def resolve(token: str, image_bytes: bytes | None = None) -> ColorResult:
    """Pełna ścieżka: słownik, a dopiero gdy zawiedzie i jest zdjęcie — obraz."""
    by_dict = from_dictionary(token)
    if by_dict:
        return ColorResult(by_dict, "dictionary")

    if image_bytes:
        try:
            name = nearest_named_color(dominant_color(image_bytes))
            return ColorResult(name, "image")
        except Exception:
            # Uszkodzony/nieobsługiwany plik nie może wywrócić całego przebiegu —
            # token po prostu zostaje nierozpoznany, tak jak bez zdjęcia.
            pass

    return ColorResult(None, "unresolved")
