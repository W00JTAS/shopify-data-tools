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
  const [proposeSummary, setProposeSummary] = useState('')

  async function loadPreview(f: File, sepValue: string) {
    setBusy('preview')
    setError('')
    try {
      const data = await fetchPreview(f, sepValue)
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

  async function handleFile(f: File | null) {
    setFile(f)
    setResult(null)
    if (!f) return
    await loadPreview(f, sep)
  }

  function handleSepChange(value: string) {
    setSep(value)
    if (file) loadPreview(file, value)
  }

  async function handlePropose() {
    if (!file) return setError('Wybierz najpierw plik CSV.')
    setBusy('propose')
    setError('')
    try {
      const data = await proposeRules(file, column, sep, targetCount)
      setRulesJson(JSON.stringify(data.rules, null, 2))
      setProposeSummary(
        `${data.unique_categories} unikalnych kategorii → ${data.target_categories} grup. ` +
          (data.unmapped.length
            ? `Bez propozycji (${data.unmapped.length}): ${data.unmapped.slice(0, 5).join(', ')}${data.unmapped.length > 5 ? '…' : ''}`
            : 'wszystkie przypisane.'),
      )
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
              onChange={(e) => handleSepChange(e.target.value)}
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
          <div className="mb-4">
            <div className="flex items-end gap-3">
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
            <p className="text-xs text-mutedfg mb-2 mt-2">
              Model proponuje szkic — przejrzyj i popraw w polu niżej przed uruchomieniem. Może potrwać do kilku minut
              przy dużych katalogach.
            </p>
            {proposeSummary && <p className="text-xs text-mutedfg mt-2">{proposeSummary}</p>}
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

        <div className="mt-3">
          <FileField
            label="…albo wczytaj plik reguł"
            accept=".json"
            onChange={(f) => {
              if (!f) return
              f.text().then((text) => setRulesJson(text))
            }}
          />
        </div>

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
                      <span>{u.source || '(pusta wartość)'}</span>
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
