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
