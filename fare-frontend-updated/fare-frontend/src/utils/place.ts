import type { GeoResult, LatLng, Place } from '../types'

const subtitleOf = (g: GeoResult): string => {
  if (g.neighborhood) return `${g.neighborhood}, Boston`
  const parts = g.display_name.split(',').map(s => s.trim()).filter(Boolean)
  return parts.slice(1, 3).join(', ') || 'Boston'
}

/** Compact label for fare requests (kept short; coordinates are what matter). */
const labelOf = (g: GeoResult): string =>
  [g.name, g.neighborhood, 'Boston, MA'].filter(Boolean).join(', ').slice(0, 100)

/** `at` overrides the coordinates (used for map clicks so the exact clicked point is kept). */
export function toPlace(g: GeoResult, at?: LatLng): Place {
  const fallback = g.display_name.split(',')[0]?.trim() || 'Selected location'
  return {
    name: g.name?.trim() || fallback,
    subtitle: subtitleOf(g),
    label: labelOf(g),
    lat: at ? at[0] : g.latitude,
    lng: at ? at[1] : g.longitude,
    area: g.model_area ?? null,
  }
}

export const samePlaceArea = (a: Place | null, b: Place | null) =>
  !!a && !!b && ((!!a.area && a.area === b.area) || (a.lat === b.lat && a.lng === b.lng))
