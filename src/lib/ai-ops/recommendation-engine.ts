import type { Confidence, Provider, ProviderSignal, Recommendation, WorkloadType } from './types'
import { PROVIDER_SHORT } from './types'

// Workload fit per provider — used when user declares intent
const WORKLOAD_FIT: Record<Provider, Record<WorkloadType, number>> = {
  anthropic: { reasoning: 0.95, creative: 0.80, bulk: 0.50, code: 0.75, general: 0.80 },
  openai:    { reasoning: 0.80, creative: 0.75, bulk: 0.70, code: 0.90, general: 0.75 },
  google:    { reasoning: 0.70, creative: 0.70, bulk: 0.90, code: 0.70, general: 0.70 },
}

// Workload-specific notes for secondary recommendations
const WORKLOAD_NOTES: Record<Provider, Record<WorkloadType, string>> = {
  anthropic: {
    reasoning: 'strong for complex reasoning',
    creative:  'strong for long-form creative work',
    bulk:      'less optimal for high-volume batch tasks',
    code:      'solid for code with context',
    general:   'good all-around choice',
  },
  openai: {
    reasoning: 'solid for structured reasoning',
    creative:  'good for creative tasks',
    bulk:      'efficient for moderate batch work',
    code:      'best fit for coding tasks',
    general:   'reliable general-purpose option',
  },
  google: {
    reasoning: 'adequate for reasoning tasks',
    creative:  'good for creative tasks',
    bulk:      'best fit for high-volume batch work',
    code:      'adequate for code tasks',
    general:   'good for bulk or lower-cost work',
  },
}

function scoreProvider(signal: ProviderSignal, workload: WorkloadType): number {
  if (signal.health === 'down') return 0

  const healthScore =
    signal.health === 'healthy' ? 1.0 :
    signal.health === 'degraded' ? 0.35 :
    0.65 // unknown

  // Use-it-or-lose-it: the core allocation signal
  let quotaScore = 0.5 // neutral when unknown
  if (signal.quota_remaining_pct !== null && signal.hours_until_reset !== null) {
    const pct = signal.quota_remaining_pct
    const hrs = signal.hours_until_reset
    if (pct > 50 && hrs < 24)       quotaScore = 1.0   // strong: use today or lose it
    else if (pct < 15 && hrs > 48)  quotaScore = 0.05  // conserve: critically low, long wait
    else if (pct > 50)              quotaScore = 0.70
    else if (hrs < 24)              quotaScore = 0.60
    else                            quotaScore = 0.50
  }

  const errorPenalty = signal.error_rate_24h !== null
    ? Math.max(0, 1 - signal.error_rate_24h * 4) : 1.0

  const fitScore = WORKLOAD_FIT[signal.provider][workload]

  // Weights: quota signal slightly edges health — it's the unique value
  return healthScore * 0.35 + quotaScore * 0.40 + errorPenalty * 0.15 + fitScore * 0.10
}

function buildReasons(signal: ProviderSignal, workload: WorkloadType): string[] {
  const reasons: string[] = []

  // Quota + reset (highest signal — always first if present)
  if (signal.quota_remaining_pct !== null && signal.hours_until_reset !== null) {
    const pct = Math.round(signal.quota_remaining_pct)
    const hrs = Math.round(signal.hours_until_reset)
    if (pct > 50 && hrs < 24)
      reasons.push(`${pct}% quota remaining — resets in ${hrs}h (use it today)`)
    else if (pct < 15)
      reasons.push(`${pct}% quota remaining — conserve until reset in ${hrs}h`)
    else
      reasons.push(`${pct}% quota remaining, resets in ${hrs}h`)
  }

  // Health
  if (signal.health === 'healthy')   reasons.push('Currently healthy')
  if (signal.health === 'degraded')  reasons.push('Some degradation reported — suitable for non-critical work')

  // Workload fit note (if non-general and quota didn't dominate all slots)
  if (workload !== 'general' && reasons.length < 3) {
    const note = WORKLOAD_NOTES[signal.provider][workload]
    reasons.push(`Well-suited: ${note}`)
  }

  // Error trend (only if notable)
  if (signal.error_rate_24h !== null && signal.error_rate_24h > 0.1 && reasons.length < 3)
    reasons.push(`${Math.round(signal.error_rate_24h * 100)}% error rate in last 24h`)

  return reasons.slice(0, 3)
}

function deriveConfidence(signals: ProviderSignal[], winner: ProviderSignal): Confidence {
  const hasConfirmedQuota = winner.quota_source === 'user_confirmed' || winner.quota_source === 'browser_extension' || winner.quota_source === 'api'
  const hasHealth = winner.health !== 'unknown'
  const quotaFresh = winner.quota_snapshotted_at
    ? (Date.now() - winner.quota_snapshotted_at.getTime()) < 4 * 60 * 60 * 1000
    : false
  const healthFresh = winner.health_checked_at
    ? (Date.now() - winner.health_checked_at.getTime()) < 10 * 60 * 1000
    : false

  if (hasHealth && healthFresh && hasConfirmedQuota && quotaFresh) return 'high'
  if (hasHealth && healthFresh) return 'moderate'
  return 'low'
}

function buildCautions(signals: ProviderSignal[], winner: Provider): string[] {
  const cautions: string[] = []
  for (const s of signals) {
    if (s.provider === winner) continue
    if (s.cost_trend === 'elevated' && cautions.length < 2)
      cautions.push(`${PROVIDER_SHORT[s.provider]} API spend above average this week`)
    if (s.health === 'degraded' && cautions.length < 2)
      cautions.push(`${PROVIDER_SHORT[s.provider]} showing degraded status`)
  }
  return cautions.slice(0, 2)
}

function buildSecondary(
  ranked: { signal: ProviderSignal; score: number }[],
  winner: Provider,
  workload: WorkloadType,
): { provider: Provider; note: string } | null {
  const second = ranked.find(r => r.signal.provider !== winner && r.score > 0)
  if (!second) return null
  const note = WORKLOAD_NOTES[second.signal.provider][workload]
  return { provider: second.signal.provider, note: `Good fallback — ${note}` }
}

export function generateRecommendation(
  signals: ProviderSignal[],
  workload: WorkloadType = 'general',
): Recommendation {
  const now = new Date()

  if (signals.length === 0) {
    return {
      recommended_provider: null,
      confidence: 'low',
      headline: 'No provider data available',
      reasons: ['Configure at least one provider to get a recommendation'],
      secondary: null,
      cautions: [],
      valid_until: new Date(now.getTime() + 30 * 60 * 1000),
      stale: false,
      generated_at: now,
    }
  }

  const ranked = signals
    .map(s => ({ signal: s, score: scoreProvider(s, workload) }))
    .sort((a, b) => b.score - a.score)

  const winner = ranked[0]

  // All providers are down
  if (winner.score === 0) {
    return {
      recommended_provider: null,
      confidence: 'low',
      headline: 'All providers currently unavailable',
      reasons: signals.map(s => `${PROVIDER_SHORT[s.provider]}: ${s.health}`),
      secondary: null,
      cautions: [],
      valid_until: new Date(now.getTime() + 10 * 60 * 1000),
      stale: false,
      generated_at: now,
    }
  }

  const winnerSignal = winner.signal
  const confidence = deriveConfidence(signals, winnerSignal)
  const reasons = buildReasons(winnerSignal, workload)
  const cautions = buildCautions(signals, winnerSignal.provider)
  const secondary = buildSecondary(ranked, winnerSignal.provider, workload)

  // Valid longer when confidence is higher
  const validMs = confidence === 'high' ? 4 * 60 * 60 * 1000
    : confidence === 'moderate' ? 60 * 60 * 1000
    : 30 * 60 * 1000
  const valid_until = new Date(now.getTime() + validMs)

  const workloadLabel = workload === 'general' ? '' : ` for ${workload} work`
  const headline = `Prioritize ${PROVIDER_SHORT[winnerSignal.provider]} today${workloadLabel}`

  return {
    recommended_provider: winnerSignal.provider,
    confidence,
    headline,
    reasons,
    secondary,
    cautions,
    valid_until,
    stale: false,
    generated_at: now,
  }
}
