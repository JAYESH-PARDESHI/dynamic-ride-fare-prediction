import { useEffect, useState } from 'react'
import { AlertCircle, ArrowUpDown, Loader2, MapPin, X } from 'lucide-react'
import { useLocationSearch } from '../hooks/useLocationSearch'
import { MSG } from '../services/api'
import type { Field, GeoResult, Place } from '../types'
import { toPlace } from '../utils/place'

interface Props {
  pickup: Place | null; destination: Place | null
  errors: Partial<Record<Field, string>>; note: string | null
  target: Field; onTarget: (f: Field) => void
  onPick: (f: Field, r: GeoResult) => void; onClear: (f: Field) => void; onSwap: () => void
  onOpenChange: (open: boolean) => void
}

const CONFIG = {
  pickup: { label: 'Pickup', placeholder: 'Pickup location' },
  destination: { label: 'Destination', placeholder: 'Where are you going?' },
} as const

export default function LocationFields({ pickup, destination, errors, note, target, onTarget, onPick, onClear, onSwap, onOpenChange }: Props) {
  const values = { pickup, destination }
  const [focus, setFocus] = useState<Field | null>(null)
  const [dirty, setDirty] = useState(false)
  const [cursor, setCursor] = useState(0)
  const [texts, setTexts] = useState({ pickup: pickup?.name ?? '', destination: destination?.name ?? '' })

  // Keep the text in step with the chosen place (search pick, map click, swap, clear).
  useEffect(() => setTexts(t => ({ ...t, pickup: pickup?.name ?? '' })), [pickup])
  useEffect(() => setTexts(t => ({ ...t, destination: destination?.name ?? '' })), [destination])

  const query = focus ? texts[focus] : ''
  const open = !!focus && dirty && query.trim().length >= 2
  const search = useLocationSearch(query, open)
  useEffect(() => onOpenChange(open), [open, onOpenChange])
  useEffect(() => setCursor(0), [search.results])

  const choose = (r: GeoResult) => {
    if (!focus) return
    onPick(focus, r)
    setDirty(false)
    ;(document.activeElement as HTMLElement | null)?.blur()
  }

  const row = (f: Field) => {
    const c = CONFIG[f], place = values[f], focused = focus === f, active = focused || (!focus && target === f)
    return (
      <div key={f} className={`flex h-[60px] items-center gap-3 rounded-xl pl-3 pr-11 transition-[background-color,box-shadow] duration-150 ${active ? 'bg-white shadow-sm ring-1 ring-slate-900' : 'hover:bg-white/60'}`}>
        <span className="grid w-[18px] shrink-0 place-items-center" aria-hidden="true">
          {f === 'pickup'
            ? <span className="h-3 w-3 rounded-full border-[3px] border-emerald-500 bg-white" />
            : <span className="h-3 w-3 rounded-[3px] bg-slate-900" />}
        </span>
        <div className="min-w-0 flex-1">
          <input
            aria-label={c.label} placeholder={c.placeholder} autoComplete="off" spellCheck={false}
            role="combobox" aria-expanded={focused && open} aria-autocomplete="list" aria-controls="rf-suggestions"
            aria-activedescendant={focused && open ? `rf-opt-${cursor}` : undefined}
            value={texts[f]}
            className="w-full truncate bg-transparent text-[15px] font-medium text-slate-900 outline-none placeholder:font-normal placeholder:text-slate-400"
            onFocus={e => { setFocus(f); onTarget(f); e.currentTarget.select() }}
            onBlur={() => { setFocus(null); setDirty(false); setTexts({ pickup: pickup?.name ?? '', destination: destination?.name ?? '' }) }}
            onChange={e => { setTexts(t => ({ ...t, [f]: e.target.value })); setDirty(true) }}
            onKeyDown={e => {
              if (e.key === 'ArrowDown' && open) { e.preventDefault(); setCursor(i => Math.min(i + 1, Math.max(search.results.length - 1, 0))) }
              else if (e.key === 'ArrowUp' && open) { e.preventDefault(); setCursor(i => Math.max(i - 1, 0)) }
              else if (e.key === 'Enter' && open && search.results[cursor]) { e.preventDefault(); choose(search.results[cursor]) }
              else if (e.key === 'Escape') (e.target as HTMLElement).blur()
            }} />
          {place && !focused && <div className="truncate text-xs text-slate-500">{place.subtitle}</div>}
        </div>
        {(texts[f] || place) && (
          <button type="button" aria-label={`Clear ${c.label.toLowerCase()}`} onPointerDown={e => e.preventDefault()}
            onClick={() => { setTexts(t => ({ ...t, [f]: '' })); onClear(f) }}
            className="grid h-6 w-6 shrink-0 place-items-center rounded-full text-slate-400 transition hover:bg-slate-200 hover:text-slate-700"><X size={14} /></button>
        )}
      </div>
    )
  }

  return (
    <div>
      <div className="relative rounded-2xl bg-slate-100 p-1">
        <span aria-hidden="true" className="absolute left-[22px] top-[44px] h-[36px] w-px bg-slate-300" />
        {row('pickup')}
        {row('destination')}
        <button type="button" aria-label="Swap pickup and destination" onClick={onSwap} onPointerDown={e => e.preventDefault()}
          className="absolute right-2 top-1/2 z-10 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-full border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:text-slate-900 active:scale-95">
          <ArrowUpDown size={14} />
        </button>
      </div>

      {(['pickup', 'destination'] as Field[]).map(f => errors[f] && (
        <p key={f} role="alert" className="mt-2 flex animate-fade items-start gap-1.5 text-[13px] text-rose-600"><AlertCircle size={14} className="mt-[2px] shrink-0" />{errors[f]}</p>
      ))}
      {note && <p role="alert" className="mt-2 flex animate-fade items-start gap-1.5 text-[13px] text-amber-700"><AlertCircle size={14} className="mt-[2px] shrink-0" />{note}</p>}

      {open && (
        <ul id="rf-suggestions" role="listbox" aria-label="Suggested locations" className="mt-3 animate-fade divide-y divide-slate-100">
          {search.loading && <li className="flex items-center gap-2 px-1 py-3 text-sm text-slate-500"><Loader2 size={15} className="animate-spin" />Searching locations...</li>}
          {!search.loading && search.error && <li className="px-1 py-3 text-sm text-rose-600">{search.error}</li>}
          {!search.loading && !search.error && search.settled && search.results.length === 0 && <li className="px-1 py-3 text-sm text-slate-500">{MSG.noResults}</li>}
          {!search.loading && search.results.map((r, i) => {
            const p = toPlace(r)
            return (
              <li key={`${r.latitude},${r.longitude},${i}`} id={`rf-opt-${i}`} role="option" aria-selected={i === cursor}
                onPointerDown={e => e.preventDefault()} onClick={() => choose(r)} onMouseEnter={() => setCursor(i)}
                className={`flex cursor-pointer items-center gap-3 rounded-lg px-2 py-2.5 transition-colors ${i === cursor ? 'bg-slate-100' : ''} ${r.supported ? '' : 'opacity-60'}`}>
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-slate-100 text-slate-600"><MapPin size={16} /></span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[15px] font-medium text-slate-900">{p.name}</span>
                  <span className="block truncate text-xs text-slate-500">{p.subtitle}</span>
                </span>
                {!r.supported && <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500">Unavailable</span>}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
