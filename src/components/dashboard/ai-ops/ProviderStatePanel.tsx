import { QuotaConfirmButton } from './QuotaConfirmButton'
import type { Provider, ProviderSignal } from '@/lib/ai-ops/types'
import { PROVIDER_SHORT } from '@/lib/ai-ops/types'

function HealthDot({ status }: { status: ProviderSignal['health'] }) {
  const color =
    status === 'healthy'  ? 'bg-emerald-500' :
    status === 'degraded' ? 'bg-yellow-500' :
    status === 'down'     ? 'bg-red-500' :
    'bg-zinc-600'
  const label =
    status === 'healthy'  ? 'Healthy' :
    status === 'degraded' ? 'Degraded' :
    status === 'down'     ? 'Down' :
    'Unknown'
  return (
    <span className="flex items-center gap-1.5 text-xs text-zinc-400">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {label}
    </span>
  )
}

function QuotaBar({ pct }: { pct: number | null }) {
  if (pct === null) {
    return <span className="text-xs text-zinc-600">—</span>
  }
  const filled = Math.round(pct / 10)
  return (
    <span className="flex items-center gap-1.5">
      <span className="flex gap-px">
        {Array.from({ length: 10 }, (_, i) => (
          <span
            key={i}
            className={`h-2 w-2 rounded-sm ${i < filled ? 'bg-zinc-400' : 'bg-zinc-700'}`}
          />
        ))}
      </span>
      <span className="text-xs text-zinc-400">~{Math.round(pct)}%</span>
    </span>
  )
}

function formatHours(h: number): string {
  if (h < 1)  return '<1h'
  if (h < 24) return `${Math.round(h)}h`
  return `${Math.round(h / 24)}d`
}

function sourceLabel(source: ProviderSignal['quota_source']): string {
  if (source === 'user_confirmed')    return 'User confirmed'
  if (source === 'browser_extension') return 'Extension read'
  if (source === 'api')               return 'API'
  if (source === 'estimated')         return 'Estimated'
  return 'Unknown'
}

function ageLabel(d: Date | null): string {
  if (!d) return ''
  const mins = Math.floor((Date.now() - d.getTime()) / 60000)
  if (mins < 2)  return 'just now'
  if (mins < 60) return `${mins}m ago`
  return `${Math.floor(mins / 60)}h ago`
}

interface Props {
  signals: ProviderSignal[]
}

export function ProviderStatePanel({ signals }: Props) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 overflow-hidden">
      <div className="px-4 py-3 border-b border-zinc-800">
        <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider">Provider State</h3>
      </div>
      <div className="divide-y divide-zinc-800">
        {signals.map((s) => (
          <div key={s.provider} className="px-4 py-3 space-y-2">
            {/* Main row */}
            <div className="flex items-center gap-4 flex-wrap">
              <span className="text-sm font-medium text-zinc-300 w-28 shrink-0">
                {PROVIDER_SHORT[s.provider as Provider]}
              </span>
              <div className="flex-1 min-w-0">
                <QuotaBar pct={s.quota_remaining_pct} />
              </div>
              <div className="shrink-0">
                {s.hours_until_reset !== null ? (
                  <span className="text-xs text-zinc-500">Reset in {formatHours(s.hours_until_reset)}</span>
                ) : (
                  <span className="text-xs text-zinc-700">Reset —</span>
                )}
              </div>
              <div className="shrink-0">
                <HealthDot status={s.health} />
              </div>
            </div>

            {/* Meta row */}
            <div className="flex items-center gap-3 flex-wrap">
              {s.quota_remaining_pct !== null ? (
                <span className="text-xs text-zinc-600">
                  {sourceLabel(s.quota_source)}
                  {s.quota_snapshotted_at ? ` · ${ageLabel(s.quota_snapshotted_at)}` : ''}
                </span>
              ) : (
                <span className="text-xs text-zinc-600">Quota unknown</span>
              )}
              {s.health_checked_at && (
                <span className="text-xs text-zinc-700">Health {ageLabel(s.health_checked_at)}</span>
              )}
              {s.cost_trend === 'elevated' && (
                <span className="text-xs text-yellow-600">API spend ↑ this week</span>
              )}
              {s.error_rate_24h !== null && s.error_rate_24h > 0.05 && (
                <span className="text-xs text-red-500/70">
                  {Math.round(s.error_rate_24h * 100)}% errors (24h)
                </span>
              )}
              <QuotaConfirmButton provider={s.provider as Provider} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
