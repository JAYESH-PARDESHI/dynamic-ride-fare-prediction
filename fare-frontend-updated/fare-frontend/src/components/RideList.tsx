import { Check, Loader2, User } from 'lucide-react'
import VehicleIcon from './VehicleIcon'
import { RIDES, rideKey } from '../config/rides'
import type { FareQuote } from '../types'
import { formatMinutes, formatMoney } from '../utils/format'

interface Props {
  cab: string; ride: string
  quotes: Record<string, FareQuote>; pending: Record<string, boolean>
  onCab: (c: string) => void; onRide: (name: string) => void
}

export default function RideList({ cab, ride, quotes, pending, onCab, onRide }: Props) {
  return (
    <section aria-labelledby="rf-choose">
      <div className="mb-3 flex items-center justify-between">
        <h2 id="rf-choose" className="text-[15px] font-semibold text-slate-900">Choose a ride</h2>
        <div role="tablist" aria-label="Ride provider" className="flex rounded-full bg-slate-100 p-0.5">
          {Object.keys(RIDES).map(c => (
            <button key={c} role="tab" aria-selected={c === cab} onClick={() => onCab(c)}
              className={`rounded-full px-3.5 py-1 text-[13px] font-medium transition-colors ${c === cab ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}>{c}</button>
          ))}
        </div>
      </div>

      <div role="radiogroup" aria-label="Ride type" className="space-y-2">
        {RIDES[cab].map(r => {
          const key = rideKey(cab, r.name), selected = r.name === ride, q = quotes[key], busy = pending[key]
          return (
            <button key={r.name} role="radio" aria-checked={selected} onClick={() => onRide(r.name)}
              className={`group flex w-full items-center gap-3 rounded-2xl border-2 px-3 py-2.5 text-left transition-[border-color,background-color,transform] duration-150 active:scale-[.99]
                ${selected ? 'border-slate-900 bg-slate-50' : 'border-transparent hover:bg-slate-50'}`}>
              <VehicleIcon kind={r.kind} className={`h-10 w-[72px] shrink-0 transition-colors ${selected ? 'text-slate-800' : 'text-slate-400 group-hover:text-slate-500'}`} />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className="text-[15px] font-semibold text-slate-900">{r.name}</span>
                  <span className="flex items-center gap-0.5 text-xs text-slate-500"><User size={12} />{r.seats}</span>
                </span>
                <span className="block truncate text-[13px] text-slate-500">{r.desc}</span>
              </span>
              <span className="flex min-w-[56px] shrink-0 flex-col items-end">
                {busy ? <Loader2 size={16} className="animate-spin text-slate-400" aria-label="Calculating fare..." />
                  : q ? <>
                    <span className="animate-fade text-[15px] font-semibold tabular-nums text-slate-900">{formatMoney(q.fare, q.currency)}</span>
                    {q.durationMin != null && <span className="text-xs text-slate-500">{formatMinutes(q.durationMin)}</span>}
                  </> : null}
              </span>
              <span aria-hidden="true" className={`grid h-5 w-5 shrink-0 place-items-center rounded-full transition-all duration-150 ${selected ? 'scale-100 bg-slate-900 text-white' : 'scale-75 bg-transparent text-transparent'}`}>
                <Check size={12} strokeWidth={3} />
              </span>
            </button>
          )
        })}
      </div>
    </section>
  )
}
