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
