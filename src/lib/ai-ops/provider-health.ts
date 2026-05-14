import { createServiceRoleClient } from '@/lib/supabase/server'
import type { HealthStatus, Provider } from './types'

const STALE_AFTER_MS = 5 * 60 * 1000 // 5 minutes

interface StatusPageSummary {
  status: { indicator: 'none' | 'minor' | 'major' | 'critical' }
}

const STATUS_URLS: Record<Provider, string> = {
  anthropic: 'https://status.anthropic.com/api/v2/summary.json',
  openai:    'https://status.openai.com/api/v2/summary.json',
  google:    'https://status.cloud.google.com/incidents.json',
}

function indicatorToHealth(indicator: string): HealthStatus {
  if (indicator === 'none')     return 'healthy'
  if (indicator === 'minor')    return 'degraded'
  if (indicator === 'major')    return 'down'
  if (indicator === 'critical') return 'down'
  return 'unknown'
}

async function pollProvider(provider: Provider): Promise<{ status: HealthStatus; latency_ms: number }> {
  const url = STATUS_URLS[provider]
  const t0 = Date.now()
  try {
    const res = await fetch(url, { next: { revalidate: 0 } })
    const latency_ms = Date.now() - t0
    if (!res.ok) return { status: 'unknown', latency_ms }

    if (provider === 'google') {
      // Google returns an array of incidents; check for any unresolved
      const incidents: any[] = await res.json()
      const active = incidents.some((i: any) => !i.end)
      return { status: active ? 'degraded' : 'healthy', latency_ms }
    }

    const data: StatusPageSummary = await res.json()
    return { status: indicatorToHealth(data?.status?.indicator ?? 'none'), latency_ms }
  } catch {
    return { status: 'unknown', latency_ms: Date.now() - t0 }
  }
}

export interface HealthResult {
  provider: Provider
  status: HealthStatus
  latency_ms: number
  checked_at: Date
}

export async function getProviderHealth(providers: Provider[]): Promise<Record<Provider, HealthResult>> {
  const supabase = createServiceRoleClient()
  const now = Date.now()

  // Load latest snapshot per provider
  const { data: rows } = await supabase
    .from('provider_health_snapshots')
    .select('provider, status, latency_ms, checked_at')
    .in('provider', providers)
    .order('checked_at', { ascending: false })

  // Group: keep only the most recent per provider
  const latest: Record<string, { provider: string; status: string; latency_ms: number | null; checked_at: string }> = {}
  for (const r of rows ?? []) {
    if (!latest[r.provider]) latest[r.provider] = r
  }

  const results: Record<string, HealthResult> = {}
  const toRefresh: Provider[] = []

  for (const p of providers) {
    const snap = latest[p]
    const age = snap ? now - new Date(snap.checked_at).getTime() : Infinity
    if (age < STALE_AFTER_MS && snap) {
      results[p] = {
        provider: p,
        status: snap.status as HealthStatus,
        latency_ms: snap.latency_ms ?? 0,
        checked_at: new Date(snap.checked_at),
      }
    } else {
      toRefresh.push(p)
    }
  }

  if (toRefresh.length > 0) {
    const fresh = await Promise.all(toRefresh.map(async (p) => {
      const { status, latency_ms } = await pollProvider(p)
      return { provider: p, status, latency_ms }
    }))

    // Persist new snapshots
    await supabase.from('provider_health_snapshots').insert(
      fresh.map(f => ({
        provider: f.provider,
        status: f.status,
        latency_ms: f.latency_ms,
        source_url: STATUS_URLS[f.provider],
      }))
    )

    for (const f of fresh) {
      results[f.provider] = {
        provider: f.provider,
        status: f.status,
        latency_ms: f.latency_ms,
        checked_at: new Date(),
      }
    }
  }

  return results as Record<Provider, HealthResult>
}
