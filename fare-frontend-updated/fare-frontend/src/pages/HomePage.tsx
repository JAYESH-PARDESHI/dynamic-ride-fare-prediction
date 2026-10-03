import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import MapView from '../components/MapView'
import MapStatus, { type Status } from '../components/MapStatus'
import BookingPanel from '../components/BookingPanel'
import { useFares } from '../hooks/useFares'
import { DEFAULT_RIDE, rideKey } from '../config/rides'
import { ApiError, MSG, reverseGeocode } from '../services/api'
import type { Field, GeoResult, LatLng, Place } from '../types'
import { samePlaceArea, toPlace } from '../utils/place'

const LABEL: Record<Field, string> = { pickup: 'Pickup', destination: 'Destination' }

export default function HomePage() {
  const [pickup, setPickup] = useState<Place | null>(null)
  const [destination, setDestination] = useState<Place | null>(null)
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({})
  const [target, setTarget] = useState<Field>('pickup')
  const [cab, setCab] = useState('Uber')
  const [ride, setRide] = useState(DEFAULT_RIDE.Uber)
  const [booked, setBooked] = useState(false)
  const [toast, setToast] = useState<Status | null>(null)
  const [busy, setBusy] = useState(false)
  const fares = useFares()
  const reverseId = useRef(0)
  const toastTimer = useRef<number>()

  const flash = useCallback((s: Status, ms = 2200) => {
    window.clearTimeout(toastTimer.current); setToast(s)
    toastTimer.current = window.setTimeout(() => setToast(null), ms)
  }, [])
  useEffect(() => () => window.clearTimeout(toastTimer.current), [])

  const setError = (f: Field, msg?: string) => setErrors(e => ({ ...e, [f]: msg }))
  const changed = () => { fares.reset(); setBooked(false) }

  const accept = (f: Field, place: Place) => {
    ;(f === 'pickup' ? setPickup : setDestination)(place)
    setError(f); changed()
    flash({ kind: 'ok', text: `${LABEL[f]} selected` })
    const other = f === 'pickup' ? destination : pickup
    if (!other) setTarget(f === 'pickup' ? 'destination' : 'pickup')
  }

  const onPick = (f: Field, r: GeoResult) => {
    if (!r.supported) return setError(f, MSG[f])
    accept(f, toPlace(r))
  }

  const onClear = (f: Field) => { (f === 'pickup' ? setPickup : setDestination)(null); setError(f); changed(); setTarget(f) }
  const onSwap = () => { setPickup(destination); setDestination(pickup); setErrors({}); changed() }

  const onMapClick = async ([lat, lng]: LatLng) => {
    const f = target, id = ++reverseId.current
    setBusy(true); setToast(null); setError(f)
    try {
      const r = await reverseGeocode(lat, lng)
      if (id !== reverseId.current) return
      if (!r || !r.supported) setError(f, MSG[f])
      else accept(f, toPlace(r, [lat, lng])) // keep the exact point the rider tapped
    } catch (e) {
      if (id !== reverseId.current) return
      flash({ kind: 'error', text: e instanceof ApiError ? e.message : MSG.connect }, 3200)
    } finally { if (id === reverseId.current) setBusy(false) }
  }

  const sameArea = samePlaceArea(pickup, destination)
  const canQuote = !!pickup && !!destination && !sameArea
  const key = rideKey(cab, ride)
  const quote = fares.quotes[key] ?? null
  const hasAny = Object.keys(fares.quotes).length > 0

  const quoteFor = async (c: string, r: string) => {
    if (!pickup || !destination) return
    const err = await fares.request(pickup, destination, c, r)
    if (err?.kind === 'unsupported' && err.field) setError(err.field, err.message)
  }

  const onCab = (c: string) => {
    const r = DEFAULT_RIDE[c]; setCab(c); setRide(r); setBooked(false)
    if (hasAny && canQuote && !fares.quotes[rideKey(c, r)]) void quoteFor(c, r)
  }
  const onRide = (r: string) => {
    setRide(r); setBooked(false)
    if (hasAny && canQuote && !fares.quotes[rideKey(cab, r)]) void quoteFor(cab, r)
  }

  const failure = fares.error && !(fares.error.kind === 'unsupported' && fares.error.field) ? fares.error.message : null
  const status: Status | null = busy ? { kind: 'busy', text: 'Finding this location...' }
    : toast ?? (!pickup && !destination ? { kind: 'hint', text: 'Search above or tap the map to set your pickup' } : null)

  const note = useMemo(() => (sameArea ? MSG.sameArea : null), [sameArea])

  return (
    <main className="relative flex h-dvh w-full flex-col overflow-hidden bg-slate-200 lg:block">
      <div className="relative h-[34dvh] min-h-[210px] shrink-0 lg:absolute lg:inset-0 lg:h-full">
        <MapView pickup={pickup} destination={destination} route={fares.route} onMapClick={onMapClick} />
        <MapStatus status={status} />
      </div>
      <section aria-label="Book a ride"
        className="relative z-[1100] -mt-5 flex min-h-0 flex-1 flex-col rounded-t-3xl bg-white shadow-sheet lg:absolute lg:bottom-4 lg:left-4 lg:top-4 lg:mt-0 lg:w-[408px] lg:flex-none lg:rounded-2xl lg:shadow-panel">
        <BookingPanel pickup={pickup} destination={destination} errors={errors} note={note}
          target={target} onTarget={setTarget} onPick={onPick} onClear={onClear} onSwap={onSwap}
          cab={cab} ride={ride} onCab={onCab} onRide={onRide} quotes={fares.quotes} pending={fares.pending}
          quote={quote} loading={!!fares.pending[key]} failure={failure} canQuote={canQuote} booked={booked}
          onGetFare={() => quoteFor(cab, ride)} onBook={() => setBooked(true)} />
      </section>
    </main>
  )
}
