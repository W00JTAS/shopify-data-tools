from io import BytesIO

from PIL import Image

from catalog_tools import colors


def solid_image_bytes(rgb: tuple[int, int, int], size: int = 30) -> bytes:
    """Prawdziwy obraz jednokolorowy — nie mock, realny plik PNG w pamięci."""
    img = Image.new("RGB", (size, size), rgb)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestFromDictionary:
    def test_angielskie_slowo(self):
        assert colors.from_dictionary("midnight") == "Granatowy"

    def test_polskie_slowo(self):
        assert colors.from_dictionary("czerwona") == "Czerwony"

    def test_wielkosc_liter_i_spacje_nie_maja_znaczenia(self):
        assert colors.from_dictionary("  BLACK  ") == "Czarny"

    def test_nieznane_slowo_zwraca_none(self):
        assert colors.from_dictionary("turkusowy") is None


class TestDominantColor:
    def test_jednolity_czerwony_obraz(self):
        rgb = colors.dominant_color(solid_image_bytes((200, 30, 30)))
        # kwantyzacja do kroku 16 — sprawdzamy przedział, nie dokładną wartość
        assert 192 <= rgb[0] <= 208 and rgb[1] < 48 and rgb[2] < 48

    def test_jednolity_niebieski_obraz(self):
        rgb = colors.dominant_color(solid_image_bytes((30, 80, 200)))
        assert rgb[2] > rgb[0] and rgb[2] > 176


class TestNearestNamedColor:
    def test_dokladny_kolor_z_palety(self):
        assert colors.nearest_named_color((200, 30, 30)) == "Czerwony"

    def test_bliski_ale_nie_dokladny_kolor(self):
        assert colors.nearest_named_color((205, 35, 25)) == "Czerwony"

    def test_kolory_przeciwlegle_nie_myla_sie(self):
        assert colors.nearest_named_color((245, 245, 245)) == "Biały"
        assert colors.nearest_named_color((20, 20, 20)) == "Czarny"


class TestResolve:
    def test_slownik_ma_pierwszenstwo_przed_zdjeciem(self):
        # Zdjęcie jest niebieskie, ale token jest znanym słowem-kolorem —
        # słownik wygrywa, zdjęcie nie jest nawet otwierane.
        result = colors.resolve("midnight", solid_image_bytes((30, 80, 200)))
        assert result == colors.ColorResult("Granatowy", "dictionary")

    def test_zdjecie_jako_fallback_gdy_slownik_zawodzi(self):
        result = colors.resolve("XYZ123", solid_image_bytes((200, 30, 30)))
        assert result == colors.ColorResult("Czerwony", "image")

    def test_bez_slownika_i_bez_zdjecia_jest_nierozpoznany(self):
        result = colors.resolve("XYZ123")
        assert result == colors.ColorResult(None, "unresolved")

    def test_uszkodzony_plik_nie_wywraca_rozwiazania(self):
        result = colors.resolve("XYZ123", image_bytes=b"to nie jest obraz")
        assert result == colors.ColorResult(None, "unresolved")
