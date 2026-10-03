import { Clock, Route, TrendingUp } from 'lucide-react'
import type { FareQuote, Place } from '../types'
import { demandLabel, formatDistance, formatMinutes } from '../utils/format'

export default function TripDetails({ pickup, destination, quote }: { pickup: Place; destination: Place; quote: FareQuote }) {
  const demand = demandLabel(quote.surge)
  return (
    <section aria-labelledby="rf-trip" className="animate-rise rounded-2xl border border-slate-200 p-4">
      <h2 id="rf-trip" className="mb-3 text-[15px] font-semibold text-slate-900">Trip details</h2>
      <ol className="relative space-y-3">
        <span aria-hidden="true" className="absolute left-[5px] top-4 h-[calc(100%-32px)] w-px bg-slate-200" />
        <li className="flex items-start gap-3"><span className="mt-1.5 h-[11px] w-[11px] shrink-0 rounded-full border-[3px] border-emerald-500 bg-white" />
          <span className="min-w-0"><span className="block text-xs text-slate-500">Pickup</span><span className="block truncate text-sm font-medium text-slate-900">{pickup.name}</span></span></li>
        <li className="flex items-start gap-3"><span className="mt-1.5 h-[11px] w-[11px] shrink-0 rounded-[3px] bg-slate-900" />
          <span className="min-w-0"><span className="block text-xs text-slate-500">Destination</span><span className="block truncate text-sm font-medium text-slate-900">{destination.name}</span></span></li>
      </ol>
      <div className="mt-4 grid grid-cols-3 gap-2 border-t border-slate-100 pt-3 text-sm">
        <div><div className="flex items-center gap-1 text-xs text-slate-500"><Route size={12} />Distance</div><div className="mt-0.5 font-semibold text-slate-900">{quote.distanceMi != null ? formatDistance(quote.distanceMi) : '—'}</div></div>
        <div><div className="flex items-center gap-1 text-xs text-slate-500"><Clock size={12} />Travel time</div><div className="mt-0.5 font-semibold text-slate-900">{quote.durationMin != null ? formatMinutes(quote.durationMin) : '—'}</div></div>
        <div><div className="flex items-center gap-1 text-xs text-slate-500"><TrendingUp size={12} />Demand</div><div className={`mt-0.5 font-semibold ${demand.high ? 'text-amber-700' : 'text-slate-900'}`}>{demand.high ? 'Higher' : 'Normal'}</div></div>
      </div>
    </section>
  )
}
