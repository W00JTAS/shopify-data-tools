from io import BytesIO

from PIL import Image

from catalog_tools import consolidate


def row(handle, title, sku="", price="", image=""):
    return {"Handle": handle, "Title": title, "Variant SKU": sku, "Variant Price": price, "Image Src": image}


def solid_png(rgb):
    buf = BytesIO()
    Image.new("RGB", (20, 20), rgb).save(buf, format="PNG")
    return buf.getvalue()


class TestSplitVariantToken:
    def test_dwa_slowa(self):
        assert consolidate.split_variant_token("Sukienka Midnight") == ("Sukienka", "Midnight")

    def test_wiele_slow_bierze_ostatnie(self):
        assert consolidate.split_variant_token("Letnia Sukienka Midnight") == ("Letnia Sukienka", "Midnight")

    def test_jedno_slowo_nie_ma_wariantu(self):
        assert consolidate.split_variant_token("Sukienka") == ("Sukienka", "")


class TestSlugify:
    def test_male_litery_i_myslniki(self):
        assert consolidate.slugify("Letnia Sukienka") == "letnia-sukienka"

    def test_polskie_znaki_zachowane(self):
        assert consolidate.slugify("Żółta Sukienka") == "żółta-sukienka"

    def test_wielokrotne_separatory_scalone(self):
        assert consolidate.slugify("A   /  B") == "a-b"


class TestGroupByBaseTitle:
    def test_grupuje_warianty_tego_samego_produktu(self):
        rows = [row("h1", "Sukienka Midnight"), row("h2", "Sukienka Sand")]
        groups = consolidate.group_by_base_title(rows)
        assert list(groups.keys()) == ["Sukienka"]
        assert len(groups["Sukienka"]) == 2

    def test_rozne_produkty_nie_lacza_sie(self):
        rows = [row("h1", "Sukienka Midnight"), row("h2", "Koszula Midnight")]
        groups = consolidate.group_by_base_title(rows)
        assert set(groups.keys()) == {"Sukienka", "Koszula"}


class TestConsolidate:
    def test_dwa_warianty_ze_znanych_slow_koloru(self):
        rows = [row("h1", "Sukienka Midnight", sku="SKU-1"), row("h2", "Sukienka Sand", sku="SKU-2")]
        result = consolidate.consolidate(rows)

        assert result.groups_consolidated == 1
        assert result.groups_passthrough == 0
        assert len(result.rows) == 2
        assert {r.option_value for r in result.rows} == {"Granatowy", "Beżowy"}
        # Wszystkie wiersze grupy dzielą jeden, nowy Handle.
        assert len({r.handle for r in result.rows}) == 1
        # Konwencja Shopify: tylko pierwszy wiersz grupy niesie tytuł.
        titles = [r.title for r in result.rows]
        assert titles.count("Sukienka") == 1 and titles.count("") == 1

    def test_pojedynczy_produkt_przechodzi_bez_zmian(self):
        rows = [row("h1", "Sukienka Midnight")]
        result = consolidate.consolidate(rows)
        assert result.groups_passthrough == 1
        assert result.groups_consolidated == 0
        assert result.rows[0].option_name == ""

    def test_nierozpoznany_token_trafia_do_raportu(self):
        rows = [row("h1", "Sukienka Zeta"), row("h2", "Sukienka Omega")]
        result = consolidate.consolidate(rows)
        assert len(result.unresolved) == 2
        assert "Zeta" in result.unresolved[0]
        # Nierozpoznany token zostaje wpisany jako wartość opcji wprost —
        # widoczny błąd, nie cichy default.
        assert {r.option_value for r in result.rows} == {"Zeta", "Omega"}

    def test_zdjecie_uzywane_tylko_gdy_slownik_zawodzi(self):
        calls = []

        def fetcher(url):
            calls.append(url)
            return solid_png((200, 30, 30))

        rows = [
            row("h1", "Sukienka Midnight", image="http://example.test/1.png"),
            row("h2", "Sukienka Zeta", image="http://example.test/2.png"),
        ]
        result = consolidate.consolidate(rows, image_fetcher=fetcher)

        # "Midnight" jest w słowniku — obraz dla niego nie powinien być pobrany.
        assert calls == ["http://example.test/2.png"]
        values = {r.source_handle: r.option_value for r in result.rows}
        assert values["h1"] == "Granatowy"
        assert values["h2"] == "Czerwony"
        assert result.unresolved == []

    def test_brak_obrazu_i_slownika_zostaje_nierozpoznany(self):
        rows = [row("h1", "Sukienka Zeta"), row("h2", "Sukienka Omega")]
        result = consolidate.consolidate(rows, image_fetcher=lambda url: None)
        assert len(result.unresolved) == 2

    def test_trzy_warianty_w_jednej_grupie(self):
        rows = [row("h1", "Torba Black"), row("h2", "Torba White"), row("h3", "Torba Red")]
        result = consolidate.consolidate(rows)
        assert result.groups_consolidated == 1
        assert len(result.rows) == 3
        assert {r.option_value for r in result.rows} == {"Czarny", "Biały", "Czerwony"}
