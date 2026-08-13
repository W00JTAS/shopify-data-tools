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
              {result.unresolved.map((u, i) => (
                <li key={`${u}-${i}`} className="border-b border-line py-1 last:border-0">
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
