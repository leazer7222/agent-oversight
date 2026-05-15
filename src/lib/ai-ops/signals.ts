import { createServiceRoleClient } from '@/lib/supabase/server'
import { getProviderHealth } from './provider-health'
import type { Provider, ProviderSignal, SnapshotSource, Confidence } from './types'
import { PROVIDER_DISPLAY } from './types'

const PROVIDERS: Provider[] = ['anthropic', 'openai', 'google']

// Map model name prefix → provider
function modelToProvider(model: string | null): Provider | null {
  if (!model) return null
  const m = model.toLowerCase()
  if (m.startsWith('claude'))  return 'anthropic'
  if (m.startsWith('gpt') || m.startsWith('o1') || m.startsWith('o3') || m.startsWith('o4')) return 'openai'
  if (m.startsWith('gemini')) return 'google'
  return null
}

interface RunsStats {
  run_count_7d: number
  error_rate_24h: number | null
  cost_7d_usd: number
  cost_trend: 'normal' | 'elevated' | null
}

async function deriveRunsStats(supabase: ReturnType<typeof createServiceRoleClient>): Promise<Record<Provider, RunsStats>> {
  const defaults: RunsStats = { run_count_7d: 0, error_rate_24h: null, cost_7d_usd: 0, cost_trend: null }
  const stats: Record<Provider, RunsStats> = {
    anthropic: { ...defaults },
    openai:    { ...defaults },
    google:    { ...defaults },
  }

  // 7-day runs with model info for cost + run count
  const { data: runs7d } = await supabase
    .from('runs')
    .select('status, cost_usd, started_at, agents(model)')
    .gte('started_at', new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString())

  // 24h runs for error rate
  const { data: runs24h } = await supabase
    .from('runs')
    .select('status, agents(model)')
    .gte('started_at', new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString())

  // 7-day prior period for cost trend comparison
  const { data: runsPrior } = await supabase
    .from('runs')
    .select('cost_usd, agents(model)')
    .gte('started_at', new Date(Date.now() - 14 * 24 * 60 * 60 * 1000).toISOString())
    .lt('started_at', new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString())

  // Tally 7d stats
  const priorCost: Record<Provider, number> = { anthropic: 0, openai: 0, google: 0 }

  for (const r of runs7d ?? []) {
    const agent = Array.isArray(r.agents) ? r.agents[0] : r.agents
    const p = modelToProvider(agent?.model ?? null)
    if (!p) continue
    stats[p].run_count_7d++
    stats[p].cost_7d_usd += r.cost_usd ?? 0
  }

  for (const r of runsPrior ?? []) {
    const agent = Array.isArray(r.agents) ? r.agents[0] : r.agents
    const p = modelToProvider(agent?.model ?? null)
    if (p) priorCost[p] += r.cost_usd ?? 0
  }

  // 24h error rates
  const counts24h: Record<Provider, { total: number; failed: number }> = {
    anthropic: { total: 0, failed: 0 },
    openai:    { total: 0, failed: 0 },
    google:    { total: 0, failed: 0 },
  }
  for (const r of runs24h ?? []) {
    const agent = Array.isArray(r.agents) ? r.agents[0] : r.agents
    const p = modelToProvider(agent?.model ?? null)
    if (!p) continue
    counts24h[p].total++
    if (r.status === 'failed') counts24h[p].failed++
  }

  for (const p of PROVIDERS) {
    const { total, failed } = counts24h[p]
    stats[p].error_rate_24h = total > 0 ? failed / total : null

    // Cost trend: >30% above prior period → elevated
    const prior = priorCost[p]
    const current = stats[p].cost_7d_usd
    if (prior > 0 && current > prior * 1.3) stats[p].cost_trend = 'elevated'
    else if (prior > 0 || current > 0) stats[p].cost_trend = 'normal'
  }

  return stats
}

export async function assembleSignals(): Promise<ProviderSignal[]> {
  const supabase = createServiceRoleClient()

  const [health, runsStats] = await Promise.all([
    getProviderHealth(PROVIDERS),
    deriveRunsStats(supabase),
  ])

  // Load latest quota snapshot per provider (via provider_accounts join)
  const { data: accounts } = await supabase
    .from('provider_accounts')
    .select('id, provider, quota_reset_period, quota_reset_anchor')
    .eq('is_active', true)

  const accountMap: Record<string, { id: string; provider: string; quota_reset_period: string | null; quota_reset_anchor: number | null }> = {}
  for (const a of accounts ?? []) accountMap[a.provider] = a

  // Latest quota snapshot per account per window_type
  const accountIds = (accounts ?? []).map(a => a.id)
  // snapsByWindow[accountId][windowType] = most recent snapshot
  let snapsByWindow: Record<string, Record<string, any>> = {}

  if (accountIds.length > 0) {
    const { data: snaps } = await supabase
      .from('provider_quota_snapshots')
      .select('provider_account_id, quota_remaining_pct, confidence, snapshot_source, snapshotted_at, expires_at, window_type')
      .in('provider_account_id', accountIds)
      .order('snapshotted_at', { ascending: false })

    for (const s of snaps ?? []) {
      const wt = s.window_type ?? 'primary'
      if (!snapsByWindow[s.provider_account_id]) snapsByWindow[s.provider_account_id] = {}
      if (!snapsByWindow[s.provider_account_id][wt]) snapsByWindow[s.provider_account_id][wt] = s
    }
  }

  return PROVIDERS.map((p): ProviderSignal => {
    const h = health[p]
    const account = accountMap[p]
    const windows = account ? (snapsByWindow[account.id] ?? {}) : {}

    // Prefer fresh specific window; fall back to fresh primary; last resort: any expired data
    function getSnap(wt: string) {
      const specific = windows[wt]
      const primary  = windows['primary']
      if (specific && !isExpired(specific)) return specific
      if (primary  && !isExpired(primary))  return primary
      return specific ?? primary ?? null
    }

    function isExpired(s: any): boolean {
      return !!(s?.expires_at && new Date(s.expires_at) < new Date())
    }

    const snap5h = getSnap('five_hour')
    const snap7d = getSnap('seven_day')
    const snapAny = snap5h ?? snap7d ?? getSnap('primary')

    const quota_remaining_pct_5h: number | null = snap5h?.quota_remaining_pct ?? null
    const quota_remaining_pct_7d: number | null = snap7d?.quota_remaining_pct ?? null
    const quota_is_stale: boolean = !!(snapAny && isExpired(snapAny))

    // Binding = minimum of available windows (most constrained)
    const available = [quota_remaining_pct_5h, quota_remaining_pct_7d].filter((v): v is number => v !== null)
    const quota_remaining_pct: number | null = available.length > 0 ? Math.min(...available) : null

    // Compute hours until reset — prefer the binding window's reset_at if stored,
    // otherwise fall back to account schedule config
    let hours_until_reset: number | null = null
    if (account?.quota_reset_period && account?.quota_reset_anchor != null) {
      const now = new Date()
      if (account.quota_reset_period === 'weekly') {
        const targetDay = account.quota_reset_anchor
        const currentDay = now.getDay()
        let daysUntil = (targetDay - currentDay + 7) % 7
        if (daysUntil === 0) daysUntil = 7
        hours_until_reset = daysUntil * 24 - now.getHours()
      } else if (account.quota_reset_period === 'monthly') {
        const targetDay = account.quota_reset_anchor
        const nextReset = new Date(now.getFullYear(), now.getMonth(), targetDay)
        if (nextReset <= now) nextReset.setMonth(nextReset.getMonth() + 1)
        hours_until_reset = (nextReset.getTime() - now.getTime()) / (1000 * 60 * 60)
      }
    }

    // Metadata from any available snapshot
    const quota_confidence: Confidence | null = snapAny ? snapAny.confidence as Confidence : null
    const quota_source: SnapshotSource | null = snapAny ? snapAny.snapshot_source as SnapshotSource : null
    const quota_snapshotted_at: Date | null = snapAny ? new Date(snapAny.snapshotted_at) : null

    const rs = runsStats[p]

    return {
      provider: p,
      display_name: PROVIDER_DISPLAY[p],
      health: h.status,
      health_checked_at: h.checked_at,
      quota_remaining_pct,
      quota_remaining_pct_5h,
      quota_remaining_pct_7d,
      quota_is_stale,
      quota_confidence,
      quota_source,
      quota_snapshotted_at,
      hours_until_reset,
      has_account: !!account,
      reset_period: (account?.quota_reset_period as 'weekly' | 'monthly' | null) ?? null,
      reset_anchor: account?.quota_reset_anchor ?? null,
      run_count_7d: rs.run_count_7d,
      error_rate_24h: rs.error_rate_24h,
      cost_7d_usd: rs.cost_7d_usd,
      cost_trend: rs.cost_trend,
    }
  })
}
