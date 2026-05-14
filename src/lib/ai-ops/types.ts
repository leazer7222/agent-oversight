export type Provider = 'anthropic' | 'openai' | 'google'
export type HealthStatus = 'healthy' | 'degraded' | 'down' | 'unknown'
export type Confidence = 'high' | 'moderate' | 'low'
export type SnapshotSource = 'user_confirmed' | 'browser_extension' | 'api' | 'estimated'
export type WorkloadType = 'reasoning' | 'creative' | 'bulk' | 'code' | 'general'

export interface ProviderSignal {
  provider: Provider
  display_name: string
  health: HealthStatus
  health_checked_at: Date | null
  // null = no quota data at all
  quota_remaining_pct: number | null      // binding minimum — used by recommendation engine
  quota_remaining_pct_5h: number | null  // 5-hour rolling window
  quota_remaining_pct_7d: number | null  // 7-day weekly budget
  quota_is_stale: boolean               // true when last snapshot is expired
  quota_confidence: Confidence | null
  quota_source: SnapshotSource | null
  quota_snapshotted_at: Date | null
  hours_until_reset: number | null       // from the binding (most constrained) window
  // Whether a provider_account row exists (reset schedule configured)
  has_account: boolean
  reset_period: 'weekly' | 'monthly' | null
  reset_anchor: number | null
  // Derived from existing runs telemetry
  run_count_7d: number
  error_rate_24h: number | null
  cost_7d_usd: number
  cost_trend: 'normal' | 'elevated' | null
}

export interface Recommendation {
  recommended_provider: Provider | null  // null = insufficient signal
  confidence: Confidence
  headline: string
  reasons: string[]          // max 3, always specific and factual
  secondary: { provider: Provider; note: string } | null
  cautions: string[]         // max 2
  valid_until: Date
  stale: boolean
  generated_at: Date
}

export const PROVIDER_DISPLAY: Record<Provider, string> = {
  anthropic: 'Claude (Anthropic)',
  openai:    'ChatGPT / OpenAI',
  google:    'Gemini (Google)',
}

export const PROVIDER_SHORT: Record<Provider, string> = {
  anthropic: 'Claude',
  openai:    'OpenAI',
  google:    'Gemini',
}
