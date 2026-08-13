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
