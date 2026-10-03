import { useEffect, useMemo } from 'react'
import { MapContainer, Marker, Polyline, TileLayer, Tooltip, ZoomControl, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import type { LatLng, Place } from '../types'

const dot = (cls: string) => L.divIcon({ className: 'rf-marker', html: `<span class="rf-pin ${cls}"></span>`, iconSize: [26, 26], iconAnchor: [13, 13] })
const PICKUP_ICON = dot('rf-pin-pickup')
const DEST_ICON = dot('rf-pin-dest')

const prefersReducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
const isDesktop = () => window.matchMedia('(min-width: 1024px)').matches

function FitTo({ points }: { points: LatLng[] }) {
  const map = useMap()
  const key = useMemo(() => points.map(p => p.join(',')).join('|'), [points])
  useEffect(() => {
    if (!points.length) return
    // On desktop the floating panel covers the left side: keep the route clear of it.
    const desktop = isDesktop()
    map.fitBounds(L.latLngBounds(points), {
      paddingTopLeft: desktop ? [452, 56] : [36, 48],
      paddingBottomRight: [48, desktop ? 56 : 36],
      maxZoom: 16, animate: !prefersReducedMotion(),
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, map])
  return null
}

function Clicks({ onPick }: { onPick: (p: LatLng) => void }) {
  useMapEvents({ click: e => onPick([e.latlng.lat, e.latlng.lng]) })
  return null
}

interface Props { pickup: Place | null; destination: Place | null; route: LatLng[] | null; onMapClick: (p: LatLng) => void }

export default function MapView({ pickup, destination, route, onMapClick }: Props) {
  const fit: LatLng[] = route && route.length > 1 ? route : [pickup, destination].filter(Boolean).map(p => [p!.lat, p!.lng] as LatLng)
  return (
    <MapContainer center={[42.3555, -71.0765]} zoom={13} zoomControl={false} className="rf-map h-full w-full">
      {/* OpenStreetMap tiles: no API key required. Styled neutral in CSS. */}
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} />
      <ZoomControl position="bottomright" />
      <Clicks onPick={onMapClick} />

      {route && route.length > 1 && (
        <>
          <Polyline positions={route} pathOptions={{ color: '#fff', weight: 10, opacity: 0.9, lineCap: 'round', lineJoin: 'round' }} />
          <Polyline positions={route} pathOptions={{ color: '#0f172a', weight: 5, opacity: 1, lineCap: 'round', lineJoin: 'round' }} />
        </>
      )}

      {pickup && (
        <Marker key={`p${pickup.lat},${pickup.lng}`} position={[pickup.lat, pickup.lng]} icon={PICKUP_ICON} interactive={false}>
          <Tooltip permanent direction="top" offset={[0, -14]} className="rf-tip">{pickup.name}</Tooltip>
        </Marker>
      )}
      {destination && (
        <Marker key={`d${destination.lat},${destination.lng}`} position={[destination.lat, destination.lng]} icon={DEST_ICON} interactive={false}>
          <Tooltip permanent direction="top" offset={[0, -14]} className="rf-tip">{destination.name}</Tooltip>
        </Marker>
      )}
      <FitTo points={fit} />
    </MapContainer>
  )
}
