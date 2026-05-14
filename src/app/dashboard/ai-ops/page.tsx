import Link from 'next/link'
import { createServiceRoleClient } from '@/lib/supabase/server'
import { assembleSignals } from '@/lib/ai-ops/signals'
import { generateRecommendation } from '@/lib/ai-ops/recommendation-engine'
import { RecommendationCard } from '@/components/dashboard/ai-ops/RecommendationCard'
import { ProviderStatePanel } from '@/components/dashboard/ai-ops/ProviderStatePanel'
import type { WorkloadType } from '@/lib/ai-ops/types'

const WORKLOADS: { value: WorkloadType; label: string }[] = [
  { value: 'general',   label: 'General' },
  { value: 'reasoning', label: 'Reasoning' },
  { value: 'code',      label: 'Code' },
  { value: 'creative',  label: 'Creative' },
  { value: 'bulk',      label: 'Bulk' },
]

export default async function AiOpsPage({
  searchParams,
}: {
  searchParams: Promise<{ workload?: string }>
}) {
  const sp = await searchParams
  const workload = (WORKLOADS.some(w => w.value === sp.workload)
    ? sp.workload
    : 'general') as WorkloadType

  const signals = await assembleSignals()
  const rec = generateRecommendation(signals, workload)

  // Persist recommendation for feedback linkage
  const supabase = createServiceRoleClient()
  const { data: company } = await supabase.from('companies').select('id').limit(1).single()

  let recId: string | null = null
  if (company) {
    const { data: saved } = await supabase
      .from('recommendation_events')
      .insert({
        company_id: company.id,
        recommended_provider: rec.recommended_provider,
        confidence: rec.confidence,
        headline: rec.headline,
        reasons: rec.reasons,
        secondary_provider: rec.secondary?.provider ?? null,
        secondary_note: rec.secondary?.note ?? null,
        cautions: rec.cautions,
        input_signals: signals.map(s => ({
          provider: s.provider,
          health: s.health,
          quota_remaining_pct: s.quota_remaining_pct,
          quota_source: s.quota_source,
          hours_until_reset: s.hours_until_reset,
          error_rate_24h: s.error_rate_24h,
          cost_trend: s.cost_trend,
        })),
        valid_until: rec.valid_until.toISOString(),
      })
      .select('id')
      .single()
    recId = saved?.id ?? null
  }

  // Freshness: oldest health check
  const healthChecks = signals.map(s => s.health_checked_at).filter(Boolean) as Date[]
  const oldestHealth = healthChecks.length
    ? new Date(Math.min(...healthChecks.map(d => d.getTime())))
    : null
  const healthAgeMin = oldestHealth
    ? Math.floor((Date.now() - oldestHealth.getTime()) / 60000)
    : null

  const hasExtension = signals.some(s => s.quota_source === 'browser_extension')

  return (
    <div className="p-6 space-y-5 max-w-2xl">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">AI Ops</h1>
          <p className="text-sm text-zinc-500 mt-0.5">
            Operational guidance for model and provider selection
          </p>
        </div>
        {healthAgeMin !== null && (
          <span className="text-xs text-zinc-600 mt-1 shrink-0">
            Updated {healthAgeMin < 2 ? 'just now' : `${healthAgeMin}m ago`}
          </span>
        )}
      </div>

      {/* Workload selector */}
      <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded-lg p-1 w-fit">
        {WORKLOADS.map(({ value, label }) => (
          <Link
            key={value}
            href={`/dashboard/ai-ops?workload=${value}`}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              workload === value
                ? 'bg-zinc-700 text-zinc-100'
                : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
            }`}
          >
            {label}
          </Link>
        ))}
      </div>

      {/* Recommendation */}
      <RecommendationCard recommendation={rec} recommendationId={recId} />

      {/* Provider state */}
      <ProviderStatePanel signals={signals} />

      {/* Signal freshness footer */}
      <div className="flex items-center gap-3 flex-wrap text-xs text-zinc-600">
        {healthAgeMin !== null && (
          <span>Health checks: {healthAgeMin < 2 ? 'just now' : `${healthAgeMin}m ago`}</span>
        )}
        <span>·</span>
        <span>
          Quota:{' '}
          {signals.some(s => s.quota_source === 'user_confirmed') ? 'user confirmed' :
           signals.some(s => s.quota_source === 'browser_extension') ? 'extension' :
           'not configured'}
        </span>
        {!hasExtension && (
          <>
            <span>·</span>
            <span className="text-zinc-500">
              Install the browser extension for live quota tracking
            </span>
          </>
        )}
      </div>
    </div>
  )
}
