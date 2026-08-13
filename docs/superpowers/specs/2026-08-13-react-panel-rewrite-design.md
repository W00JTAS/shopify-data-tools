# Panel v2: przepisanie na Vite + React + Tailwind, naprawa widoczności nierozpoznanych kategorii

## Kontekst

Panel webowy (`src/catalog_tools/webapp/`) działa dziś jako FastAPI + vanilla JS bez frameworka
(`static/app.js`, 217 linii). Ma naśladować wizualnie `ME/panel/` — prywatny panel kariery
(Next.js/React, motyw "financial-terminal": Geist Mono, ostre rogi, jasny/ciemny motyw przez
zmienne CSS) — oraz zyskać React w stosie jako dodatkowy dowód kompetencji w portfolio (dziś
dowody są głównie Pythonowe).

Równolegle: zakładka "Kategoryzacja" pokazuje tylko *liczbę* nierozpoznanych wpisów
(`summary.unresolved`), nie *które* kategorie źródłowe nie trafiły w reguły — w efekcie nie widać,
co dopisać do `rules.json`, żeby pokrycie rosło. Zakładka "Konsolidacja" już dziś pokazuje listę
nierozpoznanych wariantów (`con-unresolved`); kategoryzacja ma dostać ten sam mechanizm.

Praca dzieje się w ramach ograniczonego okna czasowego (część dnia przed wysyłką aplikacji o
pracę) — zakres celowo minimalny, bez nowych funkcji ponad to, co opisano niżej.

## Architektura

- **Backend bez zmian architektonicznych.** FastAPI (`webapp/main.py`) zostaje jedynym API,
  logika kategoryzacji/konsolidacji (`pipeline.py`, `rules.py`, `consolidate.py`,
  `llm_fallback.py`, `rule_proposer.py`) nietknięta poza jedną zmianą w `pipeline.py` (patrz
  „Naprawa" niżej).
- **Nowy frontend** w `frontend/`: Vite + React + TypeScript + Tailwind v4, ten sam mechanizm
  tokenów co `ME/panel/src/app/globals.css` (`@theme` + zmienne CSS w `:root`/`.dark`, bez
  `tailwind.config.js`), Geist Mono, `radius: 0`. **Własna kopia tokenów w tym repo** — bez
  importu z `ME/panel` (prywatny vs. publiczne repo, nie mieszamy).
- **Dev workflow:** `npm run dev` w `frontend/` (Vite na 5173) z proxy `/api/*` → FastAPI
  (`localhost:8000`).
- **Build/produkcja:** `npm run build` → `frontend/dist` zastępuje dzisiejszy
  `webapp/static/` jako katalog serwowany przez `StaticFiles`; `uvicorn ... --reload` zostaje
  jedyną komendą do uruchomienia całości, jak dziś.
- README dostaje zaktualizowaną sekcję "Panel webowy" z nowymi krokami instalacji/uruchomienia
  (`npm install` + `npm run build` w `frontend/`, potem `uvicorn`) i nowymi zrzutami ekranu.

## Komponenty

Mirror dzisiejszych dwóch zakładek, jako React (funkcjonalność 1:1 z dzisiejszą + naprawa
widoczności opisana niżej):

- `App.tsx` — header, status Ollamy, przełącznik zakładek.
- `useOllamaStatus.ts` — hook pollujący `/api/health`.
- `CategorizeTab.tsx` — upload CSV, pole separatora, wybór kolumny (z `/api/preview`), tryb reguł
  (własne / AI proponuje — `/api/categorize/propose-rules`), edytowalny JSON reguł, checkbox
  „dopytaj model", uruchomienie (`/api/categorize/run`), wynik: statystyki + **nowa lista
  nierozpoznanych kategorii źródłowych** (patrz niżej).
- `ConsolidateTab.tsx` — upload CSV, checkbox „pobierz zdjęcie", uruchomienie
  (`/api/consolidate/run`), wynik: statystyki + istniejąca lista nierozpoznanych wariantów.
- Prymitywy współdzielone: `Card`, `StatPill`, `FileField`, `Button` — cienkie, same klasy
  Tailwind, bez biblioteki komponentów (zgodnie z dotychczasową filozofią minimalizmu tego
  narzędzia).

## Naprawa: widoczność nierozpoznanych kategorii przy kategoryzacji

`pipeline.categorize_frame` dziś zwraca w `summary` tylko `unresolved: int`. Zmiana:

- Podczas iteracji zbierany jest `collections.Counter` unikalnych wartości źródłowych
  (`source`), które nie trafiły ani w reguły, ani w model.
- `summary["unresolved_categories"]` = lista `{"source": str, "count": int}`, posortowana malejąco
  po `count`, ograniczona do **100** pozycji (duże katalogi nie rozdymają odpowiedzi JSON bez
  potrzeby — reszta i tak widoczna po pobraniu CSV).
- `/api/categorize/run` przekazuje to pole bez zmian dalej.
- `CategorizeTab` renderuje listę pod rzędem statystyk, analogicznie do istniejącej listy w
  konsolidacji — użytkownik widzi wprost, jakie źródłowe kategorie dopisać do `mapowanie` w
  JSON-ie reguł.

## Obsługa błędów

Bez zmian względem dziś: backend zwraca czyste `400`/`502` z polem `detail`; frontend pokazuje je
w banerze błędu per zakładka, tak jak obecny `app.js`.

## Testy

- Rozszerzenie istniejących testów Pythona (`tests/test_cli.py` i/lub nowy test w
  `tests/test_webapp.py` / test pipeline'u) o asercję na `unresolved_categories`: poprawność
  zawartości, sortowanie malejące, limit 100, brak duplikatów. Baza 80 zielonych testów zostaje
  utrzymana przez cały czas pracy.
- **Świadome cięcie zakresu:** frontend nie dostaje osobnego frameworka testowego (Vitest) w tym
  oknie czasowym — weryfikacja przez uruchomienie w przeglądarce (preview) zamiast automatycznych
  testów UI. Jeśli czasu zabraknie, pierwsze do ścięcia jest dalszy polish wizualny ponad
  działające MVC obu zakładek — nie naprawa widoczności nierozpoznanych kategorii, która jest tu
  głównym celem.

## Poza zakresem (świadomie)

- Structured rule-builder UI (dodawanie/usuwanie wpisów `mapowanie` przez formularz zamiast
  surowego JSON-a) — YAGNI na dziś, lista nierozpoznanych kategorii wystarcza jako podpowiedź do
  ręcznej edycji istniejącego pola JSON.
- Jakakolwiek zmiana logiki kategoryzacji/konsolidacji poza dodaniem `unresolved_categories`.
- Deploy panelu publicznie (live demo) — osobny temat, nieporuszany w tej sesji.
