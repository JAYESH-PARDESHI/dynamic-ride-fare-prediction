/**
 * Adapts the /api/v2/fare/predict response to what the UI needs.
 *
 * FIELD-NAME CONFIRMATION NEEDED: the exact property names of the v2 response were not
 * provided (only that it contains fare, route geometry, distance, duration, weather, surge).
 * Names below follow the earlier schema (estimated_fare, distance, duration, surge_multiplier,
 * weather.*) and the route geometry is located by searching likely keys and accepting the
 * common shapes. If something is missing, a console warning lists the keys that were received.
 * Once the real names are confirmed, tighten this one file – nothing else depends on them.
 */
import type { FareQuote, FareResponse, LatLng, WeatherInfo } from '../types'

type Obj = Record<string, unknown>
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v)
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const pickNum = (o: Obj | undefined, keys: string[]): number | null => {
  if (!o) return null
  for (const k of keys) { const v = o[k]; if (isNum(v)) return v; if (typeof v === 'string' && v.trim() !== '' && isNum(Number(v))) return Number(v) }
  return null
}

/* ----------------------------- route geometry ----------------------------- */

export function decodePolyline(str: string, precision = 5): LatLng[] {
  const f = 10 ** precision
  const out: LatLng[] = []
  let i = 0, lat = 0, lng = 0
  const next = (): number | null => {
    let shift = 0, result = 0, b: number
    do {
      if (i >= str.length) return null
      b = str.charCodeAt(i++) - 63
      result |= (b & 31) << shift
      shift += 5
    } while (b >= 32)
    return result & 1 ? ~(result >> 1) : result >> 1
  }
  while (i < str.length) {
    const dLat = next(); const dLng = next()
    if (dLat === null || dLng === null) break
    lat += dLat; lng += dLng
    out.push([lat / f, lng / f])
  }
  return out
}

const pairOf = (p: unknown): [number, number] | null => {
  if (Array.isArray(p) && p.length >= 2 && isNum(p[0]) && isNum(p[1])) return [p[0], p[1]]
  if (isObj(p)) {
    const a = p.latitude ?? p.lat, b = p.longitude ?? p.lng ?? p.lon
    if (isNum(a) && isNum(b)) return [a, b]
  }
  return null
}

const dist = (a: [number, number], b: [number, number]) => Math.hypot(a[0] - b[0], a[1] - b[1])

/** Raw candidate -> list of [a, b] pairs (orientation not yet decided). */
function pairsFrom(v: unknown, depth = 0): [number, number][] | null {
  if (depth > 3 || v == null) return null
  if (typeof v === 'string') return v.length > 8 ? decodePolyline(v, 5) : null
  if (Array.isArray(v)) {
    const pts = v.map(pairOf)
    return pts.length >= 2 && pts.every(Boolean) ? (pts as [number, number][]) : null
  }
  if (isObj(v)) {
    for (const k of ['coordinates', 'points', 'geometry', 'polyline', 'path', 'route']) {
      const r = pairsFrom(v[k], depth + 1); if (r) return r
    }
  }
  return null
}

const ROUTE_KEYS = ['route_geometry', 'route', 'geometry', 'route_polyline', 'polyline', 'route_points', 'path']

export function extractRoute(root: Obj, pickup: LatLng, destination: LatLng): LatLng[] | null {
  const candidates: unknown[] = ROUTE_KEYS.map(k => root[k])
  for (const k of Object.keys(root)) if (/route|geometry|polyline/i.test(k) && !ROUTE_KEYS.includes(k)) candidates.push(root[k])
  for (const c of candidates) {
    let pairs = pairsFrom(c)
    // Encoded polylines may use 6-digit precision: choose the precision that lands near the pickup.
    if (typeof c === 'string' && pairs && dist(pairs[0] ?? [0, 0], pickup) > 0.5) pairs = decodePolyline(c, 6)
    if (!pairs || pairs.length < 2) continue
    // Decide [lat,lng] vs [lng,lat] by whichever orientation sits closest to the trip's endpoints.
    const first = pairs[0], last = pairs[pairs.length - 1]
    const asLatLng = dist(first, pickup) + dist(last, destination)
    const swapped = dist([first[1], first[0]], pickup) + dist([last[1], last[0]], destination)
    const out = (swapped < asLatLng ? pairs.map(([a, b]) => [b, a] as LatLng) : pairs.map(([a, b]) => [a, b] as LatLng))
    if (Math.min(swapped, asLatLng) < 0.5) return out
  }
  return null
}

/* --------------------------------- weather -------------------------------- */

function weatherOf(root: Obj): WeatherInfo | null {
  const w = isObj(root.weather) ? root.weather : null
  if (!w) return null
  const temp = pickNum(w, ['temperature_f', 'temperature', 'temp_f'])
  if (temp === null) return null
  const rainRaw = w.raining ?? w.rain
  const raining = rainRaw === true || (isNum(rainRaw) && rainRaw > 0)
  let cloud = pickNum(w, ['cloud_cover_pct', 'clouds', 'cloud_cover']) ?? 0
  if (cloud <= 1) cloud *= 100 // tolerate fraction or percent
  const summary = raining ? 'Rain' : cloud < 30 ? 'Clear' : cloud < 70 ? 'Partly cloudy' : 'Cloudy'
  return { tempF: temp, summary, raining }
}

/* ---------------------------------- main ---------------------------------- */

export function parseFare(raw: unknown, pickup: LatLng, destination: LatLng): FareResponse | null {
  if (!isObj(raw)) return null
  const nested = isObj(raw.route) ? raw.route : undefined
  const fare = pickNum(raw, ['estimated_fare', 'fare', 'predicted_fare', 'price'])
  if (fare === null) { warn('fare amount', raw); return null }

  let duration = pickNum(raw, ['duration', 'duration_minutes', 'duration_min']) ?? pickNum(nested, ['duration', 'duration_minutes'])
  if (duration !== null && raw.duration_unit === 'seconds') duration /= 60
  const distance = pickNum(raw, ['distance', 'distance_miles', 'distance_mi']) ?? pickNum(nested, ['distance', 'distance_miles'])

  const quote: FareQuote = {
    fare,
    currency: typeof raw.currency === 'string' ? raw.currency : 'USD',
    distanceMi: distance,
    durationMin: duration,
    surge: pickNum(raw, ['surge_multiplier', 'surge']),
    weather: weatherOf(raw),
  }
  const route = extractRoute(raw, pickup, destination)
  if (!route) warn('route geometry', raw)
  return { quote, route }
}

function warn(what: string, raw: Obj) {
  if (import.meta.env.DEV) console.warn(`[fare] Could not find ${what} in response. Keys received:`, Object.keys(raw))
}
