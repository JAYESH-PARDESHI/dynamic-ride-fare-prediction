import { useCallback, useState } from 'react'
import { AlertCircle, Check, CloudRain, Loader2, Sun } from 'lucide-react'
import LocationFields from './LocationFields'
import RideList from './RideList'
import TripDetails from './TripDetails'
import type { Field, FareQuote, GeoResult, Place } from '../types'
import { demandLabel, formatDistance, formatMinutes, formatMoney } from '../utils/format'

interface Props {
  pickup: Place | null; destination: Place | null
  errors: Partial<Record<Field, string>>; note: string | null
  target: Field; onTarget: (f: Field) => void
  onPick: (f: Field, r: GeoResult) => void; onClear: (f: Field) => void; onSwap: () => void
  cab: string; ride: string; onCab: (c: string) => void; onRide: (n: string) => void
  quotes: Record<string, FareQuote>; pending: Record<string, boolean>
  quote: FareQuote | null; loading: boolean; failure: string | null
  canQuote: boolean; booked: boolean; onGetFare: () => void; onBook: () => void
}

const Logo = () => (
  <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">
    <rect width="32" height="32" rx="9" fill="#0f172a" />
    <circle cx="9.5" cy="22.5" r="2.6" fill="none" stroke="#34d399" strokeWidth="2" />
    <rect x="19.5" y="7.5" width="5" height="5" rx="1.2" fill="#fff" />
    <path d="M12 22.5h6a4 4 0 0 0 4-4v-4" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
  </svg>
)

export default function BookingPanel(p: Props) {
  const [searching, setSearching] = useState(false)
  const onOpenChange = useCallback((o: boolean) => setSearching(o), [])
  const demand = p.quote ? demandLabel(p.quote.surge) : null
  const w = p.quote?.weather

  return (
    <>
      <header className="flex items-center gap-2.5 px-5 pb-1 pt-4 lg:pt-5">
        <Logo />
        <div className="leading-tight"><div className="text-[15px] font-semibold tracking-tight text-slate-900">RideFlow</div><div className="text-[11px] text-slate-400">Move smarter.</div></div>
      </header>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto overscroll-contain px-5 pb-4 pt-3">
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">Book a ride</h1>
        <LocationFields pickup={p.pickup} destination={p.destination} errors={p.errors} note={p.note}
          target={p.target} onTarget={p.onTarget} onPick={p.onPick} onClear={p.onClear} onSwap={p.onSwap} onOpenChange={onOpenChange} />
        {!searching && <>
          <RideList cab={p.cab} ride={p.ride} quotes={p.quotes} pending={p.pending} onCab={p.onCab} onRide={p.onRide} />
          {p.quote && p.pickup && p.destination && <TripDetails pickup={p.pickup} destination={p.destination} quote={p.quote} />}
        </>}
      </div>

      <footer className="border-t border-slate-200 bg-white px-5 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 lg:rounded-b-2xl">
        {p.quote && (
          <div className="mb-3 animate-fade">
            <div className="flex items-end justify-between gap-3">
              <div>
                <div className="text-xs text-slate-500">Estimated fare</div>
                <div className="text-[13px] text-slate-600">
                  {[p.quote.distanceMi != null && formatDistance(p.quote.distanceMi), p.quote.durationMin != null && formatMinutes(p.quote.durationMin)].filter(Boolean).join(' · ')}
                </div>
              </div>
              <div className="text-[28px] font-semibold leading-none tabular-nums text-slate-900">{formatMoney(p.quote.fare, p.quote.currency)}</div>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
              {demand && <span className={`rounded-full px-2 py-0.5 font-medium ${demand.high ? 'bg-amber-100 text-amber-800' : 'bg-slate-100 text-slate-600'}`}>{demand.label}</span>}
              {w && <span className="flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">{w.raining ? <CloudRain size={12} /> : <Sun size={12} />}{Math.round(w.tempF)}°F · {w.summary}</span>}
            </div>
          </div>
        )}
        {p.failure && <p role="alert" className="mb-2 flex animate-fade items-start gap-1.5 text-[13px] text-rose-600"><AlertCircle size={14} className="mt-[2px] shrink-0" />{p.failure}</p>}
        {!p.quote && !p.failure && !p.canQuote && !p.loading && <p className="mb-2 text-[13px] text-slate-500">Choose a pickup and destination to see your fare.</p>}

        {p.quote ? (
          <>
            <button onClick={p.onBook} disabled={p.booked || p.loading}
              className={`flex h-[52px] w-full items-center justify-center gap-2 rounded-xl text-[15px] font-semibold transition active:scale-[.99] ${p.booked ? 'bg-emerald-600 text-white' : 'bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-60'}`}>
              {p.loading ? <><Loader2 size={18} className="animate-spin" />Calculating fare...</> : p.booked ? <><Check size={18} />Ride selected</> : 'Book ride'}
            </button>
            {p.booked && <p className="mt-2 animate-fade text-center text-xs text-slate-500">Booking preview. No ride has been requested.</p>}
          </>
        ) : (
          <button onClick={p.onGetFare} disabled={!p.canQuote || p.loading}
            className="flex h-[52px] w-full items-center justify-center gap-2 rounded-xl bg-slate-900 text-[15px] font-semibold text-white transition hover:bg-slate-800 active:scale-[.99] disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400">
            {p.loading ? <><Loader2 size={18} className="animate-spin" />Calculating fare...</> : 'Get fare'}
          </button>
        )}
      </footer>
    </>
  )
}
