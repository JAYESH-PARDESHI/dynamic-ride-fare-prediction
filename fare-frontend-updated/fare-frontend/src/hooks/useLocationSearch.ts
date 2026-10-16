import { useEffect, useState } from 'react'
import { ApiError, searchLocations } from '../services/api'
import type { GeoResult } from '../types'

interface State { results: GeoResult[]; loading: boolean; error: string | null; settled: boolean }
const IDLE: State = { results: [], loading: false, error: null, settled: false }

// Public geocoders ask clients not to search on every keystroke.
const DEBOUNCE_MS = 900
const MIN_CHARS = 3
const MAX_CACHED = 200

// Remembers successful searches for this browser session, so repeating a
// query (or backspacing to an earlier one) sends no request at all.
const cache = new Map<string, GeoResult[]>()

/** Debounced, cancellable search. Idle until `enabled` and the query has 3+ characters. */
export function useLocationSearch(query: string, enabled: boolean): State {
  const [state, setState] = useState<State>(IDLE)
  useEffect(() => {
    const q = query.trim()
    if (!enabled || q.length < MIN_CHARS) { setState(IDLE); return }

    const key = q.toLowerCase().replace(/\s+/g, ' ')
    const hit = cache.get(key)
    if (hit) {
      setState({ results: hit, loading: false, error: null, settled: true })
      return
    }

    setState(s => ({ ...s, loading: true, error: null, settled: false }))
    const ctrl = new AbortController()
    const t = setTimeout(async () => {
      try {
        const results = await searchLocations(q, ctrl.signal)
        if (cache.size >= MAX_CACHED) cache.delete(cache.keys().next().value as string)
        cache.set(key, results)
        setState({ results, loading: false, error: null, settled: true })
      } catch (e) {
        if (ctrl.signal.aborted) return
        setState({ results: [], loading: false, error: e instanceof ApiError ? e.message : 'Unable to connect right now. Please try again.', settled: true })
      }
    }, DEBOUNCE_MS)
    return () => { clearTimeout(t); ctrl.abort() }
  }, [query, enabled])
  return state
}
