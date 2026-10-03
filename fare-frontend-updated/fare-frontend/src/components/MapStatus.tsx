import { AlertCircle, Check, Loader2, MousePointerClick } from 'lucide-react'

export interface Status { kind: 'busy' | 'ok' | 'error' | 'hint'; text: string }

export default function MapStatus({ status }: { status: Status | null }) {
  return (
    <div className="pointer-events-none absolute inset-x-0 top-3 z-[1000] flex justify-center px-4 lg:top-5 lg:pl-[440px]" aria-live="polite">
      {status && (
        <div key={status.kind + status.text} className={`flex animate-pop items-center gap-2 rounded-full px-3.5 py-2 text-[13px] font-medium shadow-lg
          ${status.kind === 'error' ? 'bg-rose-600 text-white' : status.kind === 'hint' ? 'bg-white/95 text-slate-600' : 'bg-slate-900 text-white'}`}>
          {status.kind === 'busy' && <Loader2 size={14} className="animate-spin" />}
          {status.kind === 'ok' && <Check size={14} className="text-emerald-400" />}
          {status.kind === 'error' && <AlertCircle size={14} />}
          {status.kind === 'hint' && <MousePointerClick size={14} />}
          {status.text}
        </div>
      )}
    </div>
  )
}
