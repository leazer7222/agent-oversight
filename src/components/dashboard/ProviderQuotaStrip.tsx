import Link from 'next/link'
import type { ProviderSignal, Provider } from '@/lib/ai-ops/types'
import { PROVIDER_SHORT } from '@/lib/ai-ops/types'

function QuotaBar({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-xs text-zinc-600">No data</span>
  const filled = Math.round(pct / 10)
  const color = pct > 50 ? 'bg-emerald-500' : pct > 20 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <span className="flex items-center gap-1.5">
      <span className="flex gap-px">
        {Array.from({ length: 10 }, (_, i) => (
          <span key={i} className={`h-1.5 w-2 rounded-sm ${i < filled ? color : 'bg-zinc-700'}`} />
        ))}
      </span>
      <span className="text-xs text-zinc-400">{Math.round(pct)}%</span>
    </span>
  )
}

function HealthDot({ status }: { status: ProviderSignal['health'] }) {
  const color =
    status === 'healthy'  ? 'bg-emerald-500' :
    status === 'degraded' ? 'bg-yellow-500' :
    status === 'down'     ? 'bg-red-500' :
    'bg-zinc-600'
  return <span className={`h-2 w-2 rounded-full shrink-0 ${color}`} />
}

function formatReset(h: number | null): string {
  if (h === null) return '—'
  if (h < 1) return '<1h'
  if (h < 24) return `${Math.round(h)}h`
  return `${Math.round(h / 24)}d`
}

interface Props {
  signals: ProviderSignal[]
}

export function ProviderQuotaStrip({ signals }: Props) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 overflow-hidden">
      <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
        <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider">Provider Quota</h3>
        <Link href="/dashboard/ai-ops" className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
          AI Ops →
        </Link>
      </div>
      <div className="divide-y divide-zinc-800">
        {signals.map((s) => (
          <div key={s.provider} className="px-4 py-2.5 flex items-center gap-4">
            {/* Name */}
            <span className="text-xs font-medium text-zinc-400 w-24 shrink-0">
              {PROVIDER_SHORT[s.provider as Provider]}
            </span>

            {/* Quota bar */}
            <div className="flex-1 min-w-0">
              <QuotaBar pct={s.quota_remaining_pct} />
            </div>

            {/* Reset countdown */}
            <span className="text-xs text-zinc-500 w-16 text-right shrink-0">
              {s.hours_until_reset !== null
                ? `resets ${formatReset(s.hours_until_reset)}`
                : s.quota_remaining_pct !== null ? 'no schedule' : ''}
            </span>

            {/* Health dot */}
            <HealthDot status={s.health} />
          </div>
        ))}
      </div>
    </div>
  )
}
