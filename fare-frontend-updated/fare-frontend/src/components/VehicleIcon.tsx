import { Accessibility, Users } from 'lucide-react'
import type { RideKind } from '../types'

/** Clean, monochrome side-view vehicle drawings (no image assets needed). */
function Sedan({ premium }: { premium?: boolean }) {
  return (
    <>
      <path fill="currentColor" d="M6 38c0-4 2-6 6-7l16-3 12-13c2-2 4-3 7-3h28c3 0 5 1 7 3l10 13 14 3c4 1 6 3 6 7v4c0 2-2 3-4 3H10c-2 0-4-1-4-3z" />
      <path fill="#fff" fillOpacity=".88" d="M43 28l8-11h14v11zM69 28V17h9c1 0 2 .5 3 1.5L90 28z" />
      {premium && <path d="M12 36h96" stroke="#fff" strokeOpacity=".28" strokeWidth="1.5" strokeLinecap="round" />}
      <Wheel cx={32} /><Wheel cx={90} />
    </>
  )
}
function Suv({ premium }: { premium?: boolean }) {
  return (
    <>
      <path fill="currentColor" d="M6 40c0-4 2-7 6-8l8-2 8-16c1-2 3-3 5-3h56c3 0 5 1 6 3l6 16 8 2c3 1 5 3 5 6v5c0 2-2 3-4 3H10c-2 0-4-1-4-3z" />
      <path fill="#fff" fillOpacity=".88" d="M32 30l5-12h22v12zM63 30V18h22l6 12z" />
      <path d="M30 9h58" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity=".55" />
      {premium && <path d="M12 38h96" stroke="#fff" strokeOpacity=".28" strokeWidth="1.5" strokeLinecap="round" />}
      <Wheel cx={31} /><Wheel cx={91} />
    </>
  )
}
const Wheel = ({ cx }: { cx: number }) => (
  <g>
    <circle cx={cx} cy={46} r={8.5} fill="#0f172a" />
    <circle cx={cx} cy={46} r={3.4} fill="#cbd5e1" />
  </g>
)

export default function VehicleIcon({ kind, className = '' }: { kind: RideKind; className?: string }) {
  const suv = kind === 'suv' || kind === 'wav' || kind === 'premium-suv'
  const premium = kind === 'premium' || kind === 'premium-suv'
  const badge = kind === 'shared' ? <Users size={11} /> : kind === 'wav' ? <Accessibility size={12} /> : null
  return (
    <span className={`relative inline-block ${className}`} aria-hidden="true">
      <svg viewBox="0 0 120 58" className="h-full w-full">
        {suv ? <Suv premium={premium} /> : <Sedan premium={premium} />}
      </svg>
      {badge && <span className="absolute -right-1 -top-1 grid h-5 w-5 place-items-center rounded-full border border-slate-200 bg-white text-slate-700 shadow-sm">{badge}</span>}
    </span>
  )
}
