import { useEffect, useState } from 'react'
import { ApiError, searchLocations } from '../services/api'
import type { GeoResult } from '../types'

interface State { results: GeoResult[]; loading: boolean; error: string | null; settled: boolean }
const IDLE: State = { results: [], loading: false, error: null, settled: false }

/** Debounced, cancellable search. Idle until `enabled` and the query has 2+ characters. */
export function useLocationSearch(query: string, enabled: boolean): State {
  const [state, setState] = useState<State>(IDLE)
  useEffect(() => {
    const q = query.trim()
    if (!enabled || q.length < 2) { setState(IDLE); return }
    setState(s => ({ ...s, loading: true, error: null, settled: false }))
    const ctrl = new AbortController()
    const t = setTimeout(async () => {
      try {
        const results = await searchLocations(q, ctrl.signal)
        setState({ results, loading: false, error: null, settled: true })
      } catch (e) {
        if (ctrl.signal.aborted) return
        setState({ results: [], loading: false, error: e instanceof ApiError ? e.message : 'Unable to connect right now. Please try again.', settled: true })
      }
    }, 300)
    return () => { clearTimeout(t); ctrl.abort() }
  }, [query, enabled])
  return state
}
