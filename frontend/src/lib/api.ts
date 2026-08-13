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
