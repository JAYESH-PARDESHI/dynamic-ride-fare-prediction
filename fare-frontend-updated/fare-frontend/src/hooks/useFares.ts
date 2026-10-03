import { useCallback, useRef, useState } from 'react'
import { ApiError, MSG, predictFare } from '../services/api'
import { rideKey } from '../config/rides'
import type { FareQuote, LatLng, Place } from '../types'

const pairOf = (p: Place, d: Place) => `${p.lat},${p.lng}>${d.lat},${d.lng}`

/** Fare quotes for the current pickup/destination pair, cached per ride option. */
export function useFares() {
  const [quotes, setQuotes] = useState<Record<string, FareQuote>>({})
  const [route, setRoute] = useState<LatLng[] | null>(null)
  const [pending, setPending] = useState<Record<string, boolean>>({})
  const [error, setError] = useState<ApiError | null>(null)
  const pair = useRef('')

  const reset = useCallback(() => { pair.current = ''; setQuotes({}); setRoute(null); setPending({}); setError(null) }, [])

  /** Resolves to the ApiError (if any) so the caller can attach it to the right field. */
  const request = useCallback(async (p: Place, d: Place, cab: string, name: string): Promise<ApiError | null> => {
    const mine = pairOf(p, d), key = rideKey(cab, name)
    pair.current = mine
    setPending(s => ({ ...s, [key]: true })); setError(null)
    try {
      const res = await predictFare(
        { pickup: { latitude: p.lat, longitude: p.lng, display_name: p.label },
          destination: { latitude: d.lat, longitude: d.lng, display_name: d.label }, cab_type: cab, name },
        [p.lat, p.lng], [d.lat, d.lng])
      if (pair.current !== mine) return null
      setQuotes(s => ({ ...s, [key]: res.quote }))
      if (res.route) setRoute(res.route)
      return null
    } catch (e) {
      if (pair.current !== mine) return null
      const err = e instanceof ApiError ? e : new ApiError('fare', MSG.fare)
      setError(err)
      return err
    } finally {
      if (pair.current === mine) setPending(s => { const n = { ...s }; delete n[key]; return n })
    }
  }, [])

  return { quotes, route, pending, error, request, reset, clearError: () => setError(null) }
}
