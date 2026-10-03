import { API_BASE_URL } from '../config/env'
import type { Field, GeoResult, LatLng, PredictRequest, FareResponse } from '../types'
import { parseFare } from './normalize'

export const MSG = {
  connect: 'Unable to connect right now. Please try again.',
  route: 'Unable to calculate this route. Please try again.',
  fare: 'Unable to calculate the fare. Please try again.',
  noResults: 'No locations found. Try a different search.',
  unavailable: "That location isn't available yet. Please choose another location.",
  pickup: "Pickup location isn't available. Try another location.",
  destination: "Destination isn't available. Try another location.",
  sameArea: 'Please choose a different pickup or destination.',
}

export type ErrorKind = 'connect' | 'route' | 'fare' | 'unsupported' | 'same_area'
/** Always carries a message that is safe to show to riders. */
export class ApiError extends Error {
  constructor(public kind: ErrorKind, message: string, public field?: Field) { super(message) }
}

type Obj = Record<string, unknown>
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v)

async function request<T>(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<{ status: number; ok: boolean; data: T | null }> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 30000)
  const onAbort = () => ctrl.abort()
  signal?.addEventListener('abort', onAbort)
  try {
    const headers = init.body ? { 'Content-Type': 'application/json' } : undefined
    const res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, signal: ctrl.signal })
    const data = (await res.json().catch(() => null)) as T | null
    return { status: res.status, ok: res.ok, data }
  } catch (e) {
    if (signal?.aborted) throw e // caller cancelled: let it ignore
    throw new ApiError('connect', MSG.connect)
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', onAbort)
  }
}

const geoList = (v: unknown): GeoResult[] =>
  (Array.isArray(v) ? v : []).filter((x): x is GeoResult =>
    isObj(x) && typeof x.latitude === 'number' && typeof x.longitude === 'number' && typeof x.name === 'string')
    .map(x => ({ ...x, supported: x.supported === true }))

export async function searchLocations(q: string, signal?: AbortSignal): Promise<GeoResult[]> {
  const r = await request<Obj>(`/api/v1/locations/search?q=${encodeURIComponent(q)}`, {}, signal)
  if (!r.ok || !isObj(r.data)) throw new ApiError('connect', MSG.connect)
  return geoList(r.data.results)
}

export async function reverseGeocode(lat: number, lng: number, signal?: AbortSignal): Promise<GeoResult | null> {
  const r = await request<Obj>(`/api/v1/locations/reverse?latitude=${lat.toFixed(6)}&longitude=${lng.toFixed(6)}`, {}, signal)
  // The service answers 4xx when it cannot place a point: treat as "not available".
  if (r.status >= 400 && r.status < 500) return null
  if (!r.ok || !isObj(r.data)) throw new ApiError('connect', MSG.connect)
  return geoList([r.data])[0] ?? null
}

/** Pulls { code, message } out of the service's error body without trusting its shape. */
function errInfo(body: unknown): { code: string; message: string } {
  const b = isObj(body) ? body : {}
  const e = isObj(b.error) ? b.error : isObj(b.detail) ? (isObj(b.detail.error) ? b.detail.error : b.detail) : b
  const code = typeof e.code === 'string' ? e.code : ''
  const message = typeof e.message === 'string' ? e.message : typeof b.detail === 'string' ? b.detail : ''
  return { code, message }
}

function failure(status: number, body: unknown): ApiError {
  if (status === 422) {
    const { code, message } = errInfo(body)
    const text = `${code} ${message}`.toLowerCase()
    if (text.includes('same_model_area')) return new ApiError('same_area', MSG.sameArea)
    if (text.includes('location_not_mapped')) {
      const field: Field | undefined = /\b(pickup|source)\b/.test(message.toLowerCase()) ? 'pickup'
        : /\bdestination\b/.test(message.toLowerCase()) ? 'destination' : undefined
      return new ApiError('unsupported', field ? MSG[field] : MSG.unavailable, field)
    }
    return new ApiError('fare', MSG.fare)
  }
  if (status === 502) return new ApiError('route', MSG.route)
  if (status === 503 || status === 504) return new ApiError('connect', MSG.connect)
  return new ApiError('fare', MSG.fare)
}

export async function predictFare(body: PredictRequest, pickup: LatLng, destination: LatLng): Promise<FareResponse> {
  const r = await request<unknown>('/api/v2/fare/predict', { method: 'POST', body: JSON.stringify(body) })
  if (!r.ok) throw failure(r.status, r.data)
  const parsed = parseFare(r.data, pickup, destination)
  if (!parsed) throw new ApiError('fare', MSG.fare)
  return parsed
}
