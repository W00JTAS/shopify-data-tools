# Panel v2 (Vite + React + Tailwind) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the vanilla-JS panel frontend with a Vite + React + TypeScript + Tailwind v4 SPA styled like `ME/panel`, and fix categorize's missing "which categories are unresolved" feedback.

**Architecture:** FastAPI backend keeps its JSON API unchanged except one new field (`unresolved_categories`) on `/api/categorize/run`. A new `frontend/` Vite project consumes that API and, once built, is served by FastAPI via `StaticFiles` mounted at `/`, replacing today's `webapp/static/`.

**Tech Stack:** Python/FastAPI (existing) · Vite 8 · React 19 · TypeScript · Tailwind CSS v4 (`@tailwindcss/vite`) · `@fontsource/geist-mono`.

## Global Constraints

- No changes to categorization/consolidation business logic beyond the one additive field described in Task 1 — copied verbatim from the spec's "Poza zakresem" section.
- Frontend gets no separate test framework (Vitest) in this pass — verification is `npm run build` (type-check + bundle) plus a manual browser check; copied verbatim from the spec's "Świadome cięcie zakresu".
- Visual tokens (colors, font, `radius: 0`) are copied 1:1 from `ME/panel/src/app/globals.css` — this repo's own copy, no cross-project import.
- Existing 80 Python tests must stay green throughout every task.

---

### Task 1: `unresolved_categories` in `pipeline.categorize_frame`

**Files:**
- Modify: `src/catalog_tools/pipeline.py`
- Create: `tests/test_pipeline.py`
- Modify: `tests/test_webapp.py:56-66` (`TestCategorizeRun.test_kategoryzuje_bez_modelu`)

**Interfaces:**
- Produces: `categorize_frame(...)` summary dict gains key `unresolved_categories: list[{"source": str, "count": int}]`, sorted by `count` descending, capped at 100 entries. Every later task that touches `/api/categorize/run` or `CategorizeSummary` (Tasks 3, 4) relies on this exact shape.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pipeline.py`:

```python
"""Testy pipeline.categorize_frame — logika współdzielona przez CLI i panel."""

from __future__ import annotations

import pandas as pd

from catalog_tools.pipeline import categorize_frame

RULES = {"wymagane_konteksty": {}, "mapowanie": {"Audio": ["słuchawki bluetooth"]}}


class TestUnresolvedCategories:
    def test_zbiera_unikalne_nierozpoznane_zrodla_z_liczba_wystapien(self):
        frame = pd.DataFrame(
            {
                "kategoria": [
                    "słuchawki bluetooth",
                    "coś innego",
                    "coś innego",
                    "zupełnie inna rzecz",
                ]
            }
        )
        _, summary = categorize_frame(frame, "kategoria", RULES)
        assert summary["unresolved"] == 3
        assert summary["unresolved_categories"] == [
            {"source": "coś innego", "count": 2},
            {"source": "zupełnie inna rzecz", "count": 1},
        ]

    def test_pusta_lista_gdy_wszystko_dopasowane(self):
        frame = pd.DataFrame({"kategoria": ["słuchawki bluetooth"]})
        _, summary = categorize_frame(frame, "kategoria", RULES)
        assert summary["unresolved_categories"] == []

    def test_limit_100_pozycji(self):
        frame = pd.DataFrame({"kategoria": [f"nieznana kategoria {i}" for i in range(150)]})
        _, summary = categorize_frame(frame, "kategoria", RULES)
        assert summary["unresolved"] == 150
        assert len(summary["unresolved_categories"]) == 100
```

Modify `tests/test_webapp.py`, in `TestCategorizeRun.test_kategoryzuje_bez_modelu`, add after the existing asserts (after `assert "Audio" in data["csv"]`):

```python
        assert data["summary"]["unresolved_categories"] == [{"source": "coś innego", "count": 1}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_pipeline.py tests/test_webapp.py -q`
Expected: FAIL — `KeyError: 'unresolved_categories'`.

- [ ] **Step 3: Implement**

In `src/catalog_tools/pipeline.py`, add the import at the top:

```python
from collections import Counter
```

Replace the body of `categorize_frame` (the loop and summary construction) with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest -q`
Expected: all tests pass (83 total: 80 existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/catalog_tools/pipeline.py tests/test_pipeline.py tests/test_webapp.py
git commit -m "pipeline: zwracaj listę nierozpoznanych kategorii źródłowych z liczbą wystąpień"
```

---

### Task 2: Scaffold Vite + React + TypeScript + Tailwind frontend

**Files:**
- Create: `frontend/` (Vite `react-ts` template + deps)
- Modify: `frontend/index.html`, `frontend/vite.config.ts`
- Create: `frontend/src/index.css`
- Modify: `frontend/src/main.tsx` (import `./index.css`)
- Modify: `.gitignore` (repo root)

**Interfaces:**
- Produces: a buildable Vite project (`npm run build` → `frontend/dist/`) with Tailwind v4 available via `@import "tailwindcss"` and theme tokens `--color-bg`, `--color-surface`, `--color-muted`, `--color-fg`, `--color-mutedfg`, `--color-line`, `--color-success`, `--color-warning`, `--color-danger` (consumed as Tailwind utilities `bg-bg`, `text-fg`, `border-line`, etc. in Tasks 3–6). Dev server proxies `/api/*` to `http://localhost:8000`.

- [ ] **Step 1: Scaffold the project**

```bash
cd /home/antek/Documents/Workspace/PROJECTS/SHOPIFY_CATALOG_TOOLS
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install tailwindcss @tailwindcss/vite @fontsource/geist-mono
```

- [ ] **Step 2: Configure Vite (Tailwind plugin + dev proxy)**

Replace `frontend/vite.config.ts` with:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

- [ ] **Step 3: Set the page title**

In `frontend/index.html`, change `<title>Vite + React + TS</title>` to `<title>Catalog Tools</title>` (keeps `tests/test_webapp.py::test_strona_glowna_sie_laduje`, which asserts `"Catalog Tools" in res.text`, green once Task 7 serves this build).

- [ ] **Step 4: Add design tokens**

Create `frontend/src/index.css` — colors and font copied 1:1 from `ME/panel/src/app/globals.css` (light values in `:root`, dark values under `prefers-color-scheme` — no manual toggle button in this pass, system preference only):

```css
@import "tailwindcss";
@import "@fontsource/geist-mono/400.css";
@import "@fontsource/geist-mono/500.css";
@import "@fontsource/geist-mono/700.css";

:root {
  --bg: #ffffff;
  --surface: #ffffff;
  --muted: #f5f5f5;
  --fg: #0a0a0a;
  --mutedfg: #717171;
  --line: #e5e5e5;
  --success: #0d8f4f;
  --warning: #a3760a;
  --danger: #e7000b;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0a0a0a;
    --surface: #191919;
    --muted: #262626;
    --fg: #fafafa;
    --mutedfg: #a1a1a1;
    --line: #383838;
    --success: #39d98a;
    --warning: #e0b84d;
    --danger: #ff6467;
  }
}

@theme inline {
  --color-bg: var(--bg);
  --color-surface: var(--surface);
  --color-muted: var(--muted);
  --color-fg: var(--fg);
  --color-mutedfg: var(--mutedfg);
  --color-line: var(--line);
  --color-success: var(--success);
  --color-warning: var(--warning);
  --color-danger: var(--danger);
  --font-sans: "Geist Mono", ui-monospace, monospace;
  --font-mono: "Geist Mono", ui-monospace, monospace;
  --radius: 0px;
}

html {
  background: var(--bg);
  color: var(--fg);
}
body {
  background: var(--bg);
  color: var(--fg);
  font-family: var(--font-mono);
  -webkit-font-smoothing: antialiased;
}
```

In `frontend/src/main.tsx`, add `import './index.css'` (remove any existing `import './index.css'` / `import App.css` lines left by the template if they conflict — keep only this one stylesheet import).

- [ ] **Step 5: Ignore build artifacts**

Append to the repo-root `.gitignore`:

```
frontend/node_modules/
frontend/dist/
```

- [ ] **Step 6: Verify it builds**

Run: `cd frontend && npm run build`
Expected: exits 0, creates `frontend/dist/index.html` and `frontend/dist/assets/`.

- [ ] **Step 7: Commit**

```bash
cd /home/antek/Documents/Workspace/PROJECTS/SHOPIFY_CATALOG_TOOLS
git add frontend/package.json frontend/package-lock.json frontend/index.html frontend/vite.config.ts \
        frontend/src frontend/public frontend/tsconfig*.json frontend/eslint.config.js .gitignore
git commit -m "frontend: scaffold Vite + React + TS + Tailwind v4, tokeny z ME/panel"
```

---

### Task 3: API client + shared UI primitives

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/components/Button.tsx`
- Create: `frontend/src/components/Card.tsx`
- Create: `frontend/src/components/StatPill.tsx`
- Create: `frontend/src/components/FileField.tsx`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure new files); mirrors the backend response shape from Task 1 (`unresolved_categories`).
- Produces: `fetchHealth`, `fetchPreview`, `proposeRules`, `runCategorize`, `runConsolidate`, `downloadCsv` functions and `HealthResponse`, `PreviewResponse`, `CategorizeSummary`, `CategorizeRunResponse`, `ProposeRulesResponse`, `ConsolidateSummary`, `ConsolidateRunResponse` types from `lib/api.ts`; `Button`, `Card`, `StatPill`, `FileField` components — all consumed by Tasks 4 and 5.

- [ ] **Step 1: Write the API client**

Create `frontend/src/lib/api.ts`:

```ts
export interface PreviewResponse {
  columns: string[]
  row_count: number
}

export interface UnresolvedCategory {
  source: string
  count: number
}

export interface CategorizeSummary {
  total: number
  matched_by_rules: number
  matched_by_llm: number
  unresolved: number
  unresolved_categories: UnresolvedCategory[]
}

export interface CategorizeRunResponse {
  summary: CategorizeSummary
  csv: string
}

export interface ProposeRulesResponse {
  rules: { wymagane_konteksty: Record<string, unknown>; mapowanie: Record<string, string[]> }
  unmapped: string[]
  unique_categories: number
  target_categories: number
}

export interface ConsolidateSummary {
  groups_consolidated: number
  groups_passthrough: number
  rows_out: number
}

export interface ConsolidateRunResponse {
  summary: ConsolidateSummary
  unresolved: string[]
  csv: string
}

export interface HealthResponse {
  ollama: boolean
  model: string
}

async function parseJsonOrThrow<T>(res: Response): Promise<T> {
  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.detail ?? 'Żądanie się nie powiodło.')
  }
  return data as T
}

export async function fetchHealth(): Promise<HealthResponse> {
  return parseJsonOrThrow<HealthResponse>(await fetch('/api/health'))
}

export async function fetchPreview(file: File, sep: string): Promise<PreviewResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('sep', sep)
  return parseJsonOrThrow<PreviewResponse>(await fetch('/api/preview', { method: 'POST', body: form }))
}

export async function proposeRules(
  file: File,
  column: string,
  sep: string,
  targetCount: number,
): Promise<ProposeRulesResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('column', column)
  form.append('sep', sep)
  form.append('target_count', String(targetCount))
  return parseJsonOrThrow<ProposeRulesResponse>(
    await fetch('/api/categorize/propose-rules', { method: 'POST', body: form }),
  )
}

export async function runCategorize(
  file: File,
  column: string,
  sep: string,
  rulesJson: string,
  useLlm: boolean,
): Promise<CategorizeRunResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('column', column)
  form.append('sep', sep)
  form.append('rules', rulesJson)
  form.append('use_llm', String(useLlm))
  return parseJsonOrThrow<CategorizeRunResponse>(
    await fetch('/api/categorize/run', { method: 'POST', body: form }),
  )
}

export async function runConsolidate(file: File, fetchImages: boolean): Promise<ConsolidateRunResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('fetch_images', String(fetchImages))
  return parseJsonOrThrow<ConsolidateRunResponse>(
    await fetch('/api/consolidate/run', { method: 'POST', body: form }),
  )
}

export function downloadCsv(text: string, filename: string): void {
  const blob = new Blob([text], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
```

- [ ] **Step 2: Write the shared primitives**

Create `frontend/src/components/Button.tsx`:

```tsx
import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary'

export function Button({
  variant = 'primary',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  const base = 'px-4 py-2 text-sm font-medium border disabled:opacity-50 disabled:cursor-not-allowed'
  const styles =
    variant === 'primary'
      ? 'bg-fg text-bg border-fg hover:opacity-90'
      : 'bg-surface text-fg border-line hover:bg-muted'
  return <button className={`${base} ${styles} ${className}`} {...props} />
}
```

Create `frontend/src/components/Card.tsx`:

```tsx
import type { PropsWithChildren, ReactNode } from 'react'

export function Card({ title, children }: PropsWithChildren<{ title: ReactNode }>) {
  return (
    <div className="border border-line bg-surface p-5 mb-4">
      <h2 className="text-base font-semibold mb-4">{title}</h2>
      {children}
    </div>
  )
}
```

Create `frontend/src/components/StatPill.tsx`:

```tsx
type Tone = 'neutral' | 'ok' | 'err'

export function StatPill({ value, label, tone = 'neutral' }: { value: number; label: string; tone?: Tone }) {
  const toneClass = tone === 'ok' ? 'text-success' : tone === 'err' ? 'text-danger' : 'text-fg'
  return (
    <div className="border border-line px-4 py-3 text-center">
      <div className={`text-2xl font-semibold ${toneClass}`}>{value}</div>
      <div className="text-xs text-mutedfg uppercase tracking-wide">{label}</div>
    </div>
  )
}
```

Create `frontend/src/components/FileField.tsx`:

```tsx
export function FileField({
  label,
  accept,
  onChange,
}: {
  label: string
  accept: string
  onChange: (file: File | null) => void
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-mutedfg">{label}</span>
      <input
        type="file"
        accept={accept}
        className="border border-line bg-bg px-2 py-1.5 text-sm file:mr-3 file:border-0 file:bg-muted file:px-3 file:py-1"
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
    </label>
  )
}
```

- [ ] **Step 3: Verify it type-checks and builds**

Run: `cd frontend && npm run build`
Expected: exits 0 (unused-file warnings are fine — nothing imports these yet; that happens in Tasks 4–6).

- [ ] **Step 4: Commit**

```bash
cd /home/antek/Documents/Workspace/PROJECTS/SHOPIFY_CATALOG_TOOLS
git add frontend/src/lib frontend/src/components
git commit -m "frontend: klient API i wspólne prymitywy UI"
```

---

### Task 4: `CategorizeTab` component

**Files:**
- Create: `frontend/src/components/CategorizeTab.tsx`

**Interfaces:**
- Consumes: `fetchPreview`, `proposeRules`, `runCategorize`, `downloadCsv`, `CategorizeRunResponse` from `frontend/src/lib/api.ts` (Task 3); `Card`, `Button`, `StatPill`, `FileField` from `frontend/src/components/` (Task 3).
- Produces: `CategorizeTab` default-exported React component, no props — consumed by `App.tsx` in Task 6.

- [ ] **Step 1: Write the component**

Create `frontend/src/components/CategorizeTab.tsx`:

```tsx
import { useState } from 'react'
import { Card } from './Card'
import { Button } from './Button'
import { StatPill } from './StatPill'
import { FileField } from './FileField'
import { downloadCsv, fetchPreview, proposeRules, runCategorize, type CategorizeRunResponse } from '../lib/api'

const DEFAULT_RULES = JSON.stringify({ wymagane_konteksty: {}, mapowanie: {} }, null, 2)

export function CategorizeTab() {
  const [file, setFile] = useState<File | null>(null)
  const [sep, setSep] = useState(';')
  const [columns, setColumns] = useState<string[]>([])
  const [column, setColumn] = useState('kategoria')
  const [previewHint, setPreviewHint] = useState('')
  const [mode, setMode] = useState<'manual' | 'ai'>('manual')
  const [targetCount, setTargetCount] = useState(12)
  const [rulesJson, setRulesJson] = useState(DEFAULT_RULES)
  const [useLlm, setUseLlm] = useState(false)
  const [busy, setBusy] = useState<'preview' | 'propose' | 'run' | null>(null)
  const [error, setError] = useState('')
  const [result, setResult] = useState<CategorizeRunResponse | null>(null)

  async function handleFile(f: File | null) {
    setFile(f)
    setResult(null)
    if (!f) return
    setBusy('preview')
    setError('')
    try {
      const data = await fetchPreview(f, sep)
      setColumns(data.columns)
      if (data.columns.includes('kategoria')) setColumn('kategoria')
      else if (data.columns.length) setColumn(data.columns[0])
      setPreviewHint(`${data.row_count} wierszy, ${data.columns.length} kolumn.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Nie udało się odczytać pliku.')
    } finally {
      setBusy(null)
    }
  }

  async function handlePropose() {
    if (!file) return setError('Wybierz najpierw plik CSV.')
    setBusy('propose')
    setError('')
    try {
      const data = await proposeRules(file, column, sep, targetCount)
      setRulesJson(JSON.stringify(data.rules, null, 2))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Nie udało się zaproponować reguł.')
    } finally {
      setBusy(null)
    }
  }

  async function handleRun() {
    if (!file) return setError('Wybierz plik CSV.')
    try {
      JSON.parse(rulesJson)
    } catch (e) {
      return setError(`Reguły nie są poprawnym JSON-em: ${e instanceof Error ? e.message : String(e)}`)
    }
    setBusy('run')
    setError('')
    setResult(null)
    try {
      const data = await runCategorize(file, column, sep, rulesJson, useLlm)
      setResult(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Kategoryzacja nie powiodła się.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div>
      <Card title="1. Plik">
        <div className="flex flex-wrap gap-4">
          <FileField label="CSV z katalogiem" accept=".csv" onChange={handleFile} />
          <label className="flex flex-col gap-1 text-sm w-24">
            <span className="text-mutedfg">Separator</span>
            <input
              className="border border-line bg-bg px-2 py-1.5 text-sm"
              value={sep}
              onChange={(e) => setSep(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-mutedfg">Kolumna kategorii</span>
            <select
              className="border border-line bg-bg px-2 py-1.5 text-sm"
              value={column}
              onChange={(e) => setColumn(e.target.value)}
            >
              {columns.length ? columns.map((c) => <option key={c}>{c}</option>) : <option>{column}</option>}
            </select>
          </label>
        </div>
        {previewHint && <p className="text-xs text-mutedfg mt-3">{previewHint}</p>}
      </Card>

      <Card title="2. Reguły">
        <div className="flex gap-2 mb-4">
          <Button variant={mode === 'manual' ? 'primary' : 'secondary'} onClick={() => setMode('manual')}>
            Własne reguły
          </Button>
          <Button variant={mode === 'ai' ? 'primary' : 'secondary'} onClick={() => setMode('ai')}>
            AI proponuje reguły
          </Button>
        </div>

        {mode === 'ai' && (
          <div className="mb-4 flex items-end gap-3">
            <label className="flex flex-col gap-1 text-sm w-28">
              <span className="text-mutedfg">Ile grup</span>
              <input
                type="number"
                min={2}
                max={60}
                className="border border-line bg-bg px-2 py-1.5 text-sm"
                value={targetCount}
                onChange={(e) => setTargetCount(Number(e.target.value))}
              />
            </label>
            <Button variant="secondary" disabled={busy === 'propose'} onClick={handlePropose}>
              {busy === 'propose' ? 'Proponuję…' : 'Zaproponuj reguły'}
            </Button>
          </div>
        )}

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-mutedfg">JSON reguł (edytowalny)</span>
          <textarea
            className="border border-line bg-bg px-2 py-1.5 text-sm font-mono h-40"
            value={rulesJson}
            onChange={(e) => setRulesJson(e.target.value)}
          />
        </label>

        <label className="flex items-center gap-2 text-sm mt-3">
          <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} />
          Dopytaj model o kategorie, których reguły nie złapały
        </label>

        <div className="mt-4">
          <Button disabled={busy === 'run'} onClick={handleRun}>
            {busy === 'run' ? 'Kategoryzuję…' : 'Uruchom kategoryzację'}
          </Button>
        </div>

        {error && <div className="mt-3 border border-danger text-danger px-3 py-2 text-sm">{error}</div>}

        {result && (
          <div className="mt-5">
            <div className="grid grid-cols-3 gap-3">
              <StatPill value={result.summary.matched_by_rules} label="reguły" tone="ok" />
              <StatPill value={result.summary.matched_by_llm} label="model" />
              <StatPill value={result.summary.unresolved} label="nierozpoznane" tone="err" />
            </div>

            {result.summary.unresolved_categories.length > 0 && (
              <div className="mt-4 border border-line p-3">
                <p className="text-xs text-mutedfg mb-2">
                  Nierozpoznane kategorie źródłowe — dopisz je do <code>mapowanie</code> w JSON-ie powyżej:
                </p>
                <ul className="text-sm font-mono max-h-48 overflow-y-auto">
                  {result.summary.unresolved_categories.map((u) => (
                    <li key={u.source} className="flex justify-between border-b border-line py-1 last:border-0">
                      <span>{u.source}</span>
                      <span className="text-mutedfg">{u.count}×</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <Button variant="secondary" className="mt-4" onClick={() => downloadCsv(result.csv, 'skategoryzowane.csv')}>
              Zapisz CSV lokalnie
            </Button>
          </div>
        )}
      </Card>
    </div>
  )
}
```

- [ ] **Step 2: Verify it type-checks and builds**

Run: `cd frontend && npm run build`
Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
cd /home/antek/Documents/Workspace/PROJECTS/SHOPIFY_CATALOG_TOOLS
git add frontend/src/components/CategorizeTab.tsx
git commit -m "frontend: zakładka kategoryzacji, z listą nierozpoznanych kategorii"
```

---

### Task 5: `ConsolidateTab` component

**Files:**
- Create: `frontend/src/components/ConsolidateTab.tsx`

**Interfaces:**
- Consumes: `runConsolidate`, `downloadCsv`, `ConsolidateRunResponse` from `frontend/src/lib/api.ts` (Task 3); `Card`, `Button`, `StatPill`, `FileField` from `frontend/src/components/` (Task 3).
- Produces: `ConsolidateTab` default-exported React component, no props — consumed by `App.tsx` in Task 6.

- [ ] **Step 1: Write the component**

Create `frontend/src/components/ConsolidateTab.tsx`:

```tsx
import { useState } from 'react'
import { Card } from './Card'
import { Button } from './Button'
import { StatPill } from './StatPill'
import { FileField } from './FileField'
import { downloadCsv, runConsolidate, type ConsolidateRunResponse } from '../lib/api'

export function ConsolidateTab() {
  const [file, setFile] = useState<File | null>(null)
  const [fetchImages, setFetchImages] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<ConsolidateRunResponse | null>(null)

  async function handleRun() {
    if (!file) return setError('Wybierz plik CSV.')
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const data = await runConsolidate(file, fetchImages)
      setResult(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Konsolidacja nie powiodła się.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Plik">
      <FileField
        label="CSV z osobnymi wpisami wariantów (Handle, Title, …)"
        accept=".csv"
        onChange={(f) => {
          setFile(f)
          setResult(null)
        }}
      />

      <label className="flex items-center gap-2 text-sm mt-3">
        <input type="checkbox" checked={fetchImages} onChange={(e) => setFetchImages(e.target.checked)} />
        Pobierz zdjęcie jako fallback, gdy słownik nie rozpozna koloru
      </label>

      <div className="mt-4">
        <Button disabled={busy} onClick={handleRun}>
          {busy ? 'Konsoliduję…' : 'Uruchom konsolidację'}
        </Button>
      </div>

      {error && <div className="mt-3 border border-danger text-danger px-3 py-2 text-sm">{error}</div>}

      {result && (
        <div className="mt-5">
          <div className="grid grid-cols-3 gap-3">
            <StatPill value={result.summary.groups_consolidated} label="skonsolidowane grupy" tone="ok" />
            <StatPill value={result.summary.groups_passthrough} label="pojedyncze" />
            <StatPill value={result.unresolved.length} label="nierozpoznane warianty" tone="err" />
          </div>

          {result.unresolved.length > 0 && (
            <ul className="mt-4 text-sm font-mono border border-line p-3 max-h-48 overflow-y-auto">
              {result.unresolved.map((u) => (
                <li key={u} className="border-b border-line py-1 last:border-0">
                  {u}
                </li>
              ))}
            </ul>
          )}

          <Button variant="secondary" className="mt-4" onClick={() => downloadCsv(result.csv, 'skonsolidowane.csv')}>
            Zapisz CSV lokalnie
          </Button>
        </div>
      )}
    </Card>
  )
}
```

- [ ] **Step 2: Verify it type-checks and builds**

Run: `cd frontend && npm run build`
Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
cd /home/antek/Documents/Workspace/PROJECTS/SHOPIFY_CATALOG_TOOLS
git add frontend/src/components/ConsolidateTab.tsx
git commit -m "frontend: zakładka konsolidacji wariantów"
```

---

### Task 6: App shell — Ollama status + tabs, wired together

**Files:**
- Create: `frontend/src/hooks/useOllamaStatus.ts`
- Modify: `frontend/src/App.tsx` (replace template contents entirely)
- Delete: `frontend/src/App.css` (template leftover, no longer used)

**Interfaces:**
- Consumes: `fetchHealth`, `HealthResponse` from `frontend/src/lib/api.ts` (Task 3); `CategorizeTab` (Task 4); `ConsolidateTab` (Task 5).
- Produces: rendered app tree mounted by `frontend/src/main.tsx` (unchanged from Task 2) — this is the final consumer, nothing later depends on `App`'s internals.

- [ ] **Step 1: Write the Ollama status hook**

Create `frontend/src/hooks/useOllamaStatus.ts`:

```ts
import { useEffect, useState } from 'react'
import { fetchHealth } from '../lib/api'

type Status = { state: 'loading' } | { state: 'ok'; model: string } | { state: 'down' } | { state: 'error' }

export function useOllamaStatus(): Status {
  const [status, setStatus] = useState<Status>({ state: 'loading' })

  useEffect(() => {
    let cancelled = false
    fetchHealth()
      .then((data) => {
        if (cancelled) return
        setStatus(data.ollama ? { state: 'ok', model: data.model } : { state: 'down' })
      })
      .catch(() => {
        if (!cancelled) setStatus({ state: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [])

  return status
}
```

- [ ] **Step 2: Write the App shell**

Replace `frontend/src/App.tsx` entirely with:

```tsx
import { useState } from 'react'
import { useOllamaStatus } from './hooks/useOllamaStatus'
import { CategorizeTab } from './components/CategorizeTab'
import { ConsolidateTab } from './components/ConsolidateTab'

function OllamaStatusBadge() {
  const status = useOllamaStatus()
  const label =
    status.state === 'loading'
      ? 'sprawdzam Ollamę…'
      : status.state === 'ok'
        ? `Ollama gotowa (${status.model})`
        : status.state === 'down'
          ? 'Ollama niedostępna — działa tylko ścieżka regułowa'
          : 'brak połączenia z panelem'
  const dotClass = status.state === 'ok' ? 'bg-success' : status.state === 'loading' ? 'bg-mutedfg' : 'bg-danger'
  return (
    <div className="flex items-center gap-2 text-xs text-mutedfg">
      <span className={`inline-block w-2 h-2 rounded-full ${dotClass}`} />
      <span>{label}</span>
    </div>
  )
}

export default function App() {
  const [tab, setTab] = useState<'categorize' | 'consolidate'>('categorize')

  return (
    <div className="min-h-screen">
      <header className="flex items-center justify-between border-b border-line px-7 py-4">
        <div>
          <h1 className="text-lg font-semibold">Catalog Tools</h1>
          <p className="text-xs text-mutedfg">Kategoryzacja i konsolidacja wariantów katalogu — lokalnie, bez wysyłania danych</p>
        </div>
        <OllamaStatusBadge />
      </header>

      <main className="max-w-3xl mx-auto px-6 py-8">
        <div className="flex gap-2 mb-6">
          <button
            className={`px-4 py-2 text-sm border-b-2 ${tab === 'categorize' ? 'border-fg font-semibold' : 'border-transparent text-mutedfg'}`}
            onClick={() => setTab('categorize')}
          >
            Kategoryzacja
          </button>
          <button
            className={`px-4 py-2 text-sm border-b-2 ${tab === 'consolidate' ? 'border-fg font-semibold' : 'border-transparent text-mutedfg'}`}
            onClick={() => setTab('consolidate')}
          >
            Konsolidacja wariantów
          </button>
        </div>

        {tab === 'categorize' ? <CategorizeTab /> : <ConsolidateTab />}
      </main>
    </div>
  )
}
```

Delete `frontend/src/App.css` and remove any leftover `import './App.css'` line (there should be none left, since `App.tsx` was fully replaced above).

- [ ] **Step 3: Verify it builds**

Run: `cd frontend && npm run build`
Expected: exits 0.

- [ ] **Step 4: Manual smoke check**

Run: `cd frontend && npm run dev` (Vite on :5173) and, in a separate terminal, `cd .. && ./.venv/bin/uvicorn catalog_tools.webapp.main:app --reload` (FastAPI on :8000). Open `http://localhost:5173`, confirm both tabs render, switching tabs works, and the Ollama status badge settles to either "gotowa" or "niedostępna" (not stuck on "sprawdzam"). Stop both servers after checking.

- [ ] **Step 5: Commit**

```bash
cd /home/antek/Documents/Workspace/PROJECTS/SHOPIFY_CATALOG_TOOLS
git add frontend/src/hooks frontend/src/App.tsx
git rm frontend/src/App.css
git commit -m "frontend: spinamy status Ollamy i obie zakładki w App"
```

---

### Task 7: Backend serves the built frontend

**Files:**
- Modify: `src/catalog_tools/webapp/main.py`
- Delete: `src/catalog_tools/webapp/static/app.js`, `src/catalog_tools/webapp/static/index.html`, `src/catalog_tools/webapp/static/style.css`

**Interfaces:**
- Consumes: `frontend/dist/` produced by Task 6's build (must exist on disk when the "happy path" is checked — the fallback path in Step 1 covers the case where it doesn't).
- Produces: `GET /` serves `frontend/dist/index.html` (and `/assets/*` etc.) when `frontend/dist` exists; otherwise returns a 200 JSON hint to build it. No change to any `/api/*` route signature.

- [ ] **Step 1: Update `main.py`**

In `src/catalog_tools/webapp/main.py`:

1. Change the import line `from fastapi.responses import FileResponse, JSONResponse` to `from fastapi.responses import JSONResponse` (drop the now-unused `FileResponse`).
2. Replace `STATIC_DIR = Path(__file__).resolve().parent / "static"` with:

```python
FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"
```

3. Replace the trailing block:

```python
@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
```

with:

```python
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:

    @app.get("/")
    async def frontend_missing():
        return JSONResponse(
            {
                "detail": (
                    "Catalog Tools — frontend nie jest zbudowany. Uruchom "
                    "`cd frontend && npm install && npm run build`, potem odśwież."
                )
            },
        )
```

- [ ] **Step 2: Remove the now-dead vanilla-JS static files**

```bash
git rm src/catalog_tools/webapp/static/app.js src/catalog_tools/webapp/static/index.html src/catalog_tools/webapp/static/style.css
rmdir src/catalog_tools/webapp/static 2>/dev/null || true
```

- [ ] **Step 3: Run the test suite (covers both branches)**

Run: `./.venv/bin/python -m pytest tests/test_webapp.py -q` twice — once with `frontend/dist/` present (from Task 6's build) and once after temporarily renaming it away (`mv frontend/dist frontend/dist.bak && pytest tests/test_webapp.py -q ; mv frontend/dist.bak frontend/dist`).
Expected: `test_strona_glowna_sie_laduje` passes in both cases (asserts `"Catalog Tools" in res.text`, present in the built `index.html`'s `<title>` and in the fallback JSON message).

- [ ] **Step 4: Run the full suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: all 83 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/catalog_tools/webapp/main.py
git commit -m "webapp: serwuj zbudowany frontend React zamiast statycznego JS"
```

---

### Task 8: CI builds the frontend before the smoke test

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:** none (CI-only change).

- [ ] **Step 1: Add a Node setup + frontend build step**

In `.github/workflows/ci.yml`, insert a new step after `Kategoryzacja demo …` and before `Panel wstaje i odpowiada`:

```yaml
      - uses: actions/setup-node@v4
        with:
          node-version: "24"
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Frontend: instalacja i build
        run: |
          cd frontend
          npm ci
          npm run build
```

Leave the existing `Panel wstaje i odpowiada` step (`curl -sf http://localhost:8420/`) unchanged — it now exercises the real built frontend instead of the fallback message.

- [ ] **Step 2: Verify locally that the sequence works end to end**

Run:

```bash
cd frontend && rm -rf dist node_modules && npm ci && npm run build && cd ..
./.venv/bin/uvicorn catalog_tools.webapp.main:app --app-dir src --port 8420 &
sleep 2
curl -sf http://localhost:8420/ > /dev/null && echo OK
curl -sf http://localhost:8420/api/health > /dev/null && echo OK
kill %1
```

Expected: both `curl` calls print `OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: buduj frontend przed smoke-testem panelu"
```

---

### Task 9: README — updated panel instructions

**Files:**
- Modify: `README.md` (repo root), section "Panel webowy" (currently lines 92–103)

**Interfaces:** none (docs-only change).

- [ ] **Step 1: Update the install/run instructions**

Replace the current install/run snippet in the "Panel webowy" section:

```bash
./.venv/bin/pip install -e ".[web]"
./.venv/bin/uvicorn catalog_tools.webapp.main:app --reload
# → http://localhost:8000
```

with:

```bash
./.venv/bin/pip install -e ".[web]"
cd frontend && npm install && npm run build && cd ..
./.venv/bin/uvicorn catalog_tools.webapp.main:app --reload
# → http://localhost:8000
```

Add one sentence above the snippet noting the frontend is now Vite + React + TypeScript + Tailwind (styled to match the same token system as the author's other panels), replacing the earlier "Lekki FastAPI + vanilla JS, bez frameworka frontendowego" line — that line becomes stale with this change and should be removed or updated to say the frontend now uses React/Tailwind for the UI while the backend stays a stateless FastAPI JSON API.

**Note for whoever runs this task:** the three screenshots (`docs/panel_propose.png`, `docs/panel_categorize.png`, `docs/panel_consolidate.png`) referenced later in this section will look stale (old vanilla-JS UI) once this ships. Re-taking them requires a running browser against the new UI — do this step **inline in the orchestrating session** after Task 6 is merged, not as a delegated subagent task (subagents in this plan don't have browser tooling). Leave a `<!-- TODO: re-take screenshots after React panel ships -->` HTML comment right above the screenshots if you reach this task before that's done.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "README: instrukcje uruchomienia panelu po przejściu na React"
```

---

## Final Integration Check (orchestrator, not a subagent task)

After Task 9, in the main session (not a dispatched subagent, since this needs the browser preview tools):

1. `./.venv/bin/python -m pytest -q` — expect all tests green.
2. `cd frontend && npm run build` — expect exit 0.
3. Start `uvicorn catalog_tools.webapp.main:app --reload` and open it in the browser preview tool.
4. Click through both tabs with `data/sample/products.csv` / `data/sample/listings.csv`, confirm the categorize tab now shows the unresolved-categories list, take a screenshot.
5. Re-take the three README screenshots against the new UI and update `docs/panel_*.png` + remove the `TODO` comment from Task 9.
6. Only after this passes, consider the panel work for today done and move to the Hekla Energy manual submission step from the earlier session plan.
