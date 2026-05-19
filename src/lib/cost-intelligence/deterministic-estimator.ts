// Deterministic Estimation Service — Phase 1
//
// Produces cost estimates using pricing table rates + fixed token count heuristics.
// No calibration data is used. All estimates are at tier 'deterministic' when
// the model is found in the pricing table, or 'embedded_fallback' otherwise.
//
// Confidence is always 'low' in Phase 1 (no calibration to improve accuracy).
// Phase 2 will replace this with calibrated multipliers from calibration_snapshots.
//
// RFC references: RFC-002 §5 (estimation tier ladder), RFC-002 §10.1.1 (features),
//                RFC-003 §8 (hot path discipline + timeout fallback)

import type { SupabaseClient } from '@supabase/supabase-js'
import type { EstimationFeatures, EstimateResult, PricingEntry, PricingSnapshot } from './types'

// ---------------------------------------------------------------------------
// Embedded fallback rates — used when the pricing table is unavailable or the
// model isn't listed. These are conservative overestimates to avoid budget
// underruns. Never updated in code — add models to pricing_table_versions instead.
// ---------------------------------------------------------------------------
const EMBEDDED_FALLBACK_RATES = {
  input_per_1k_tokens_usd:        0.015,   // Opus-class pricing — conservative overestimate
  output_per_1k_tokens_usd:       0.075,
  cached_input_per_1k_tokens_usd: 0.0015,
  reasoning_per_1k_tokens_usd:    0.075,
  tool_call_per_invocation_usd:   0.0,
}

// ---------------------------------------------------------------------------
// Expected output token counts by task type × complexity bucket.
// Source: engineering judgment; will be replaced by calibration in Phase 2.
// Keys match the 8 task type codes seeded in taxonomy-v1 (migration 013).
// ---------------------------------------------------------------------------
const OUTPUT_TOKEN_ESTIMATES: Record<string, Record<string, number>> = {
  info_retrieval: { simple: 250,  medium: 700,  complex: 1800 },
  content_gen:    { simple: 600,  medium: 2200, complex: 5500 },
  code_gen:       { simple: 450,  medium: 1800, complex: 4500 },
  data_analysis:  { simple: 350,  medium: 1100, complex: 3200 },
  orchestration:  { simple: 250,  medium: 900,  complex: 3000 },
  classification: { simple: 80,   medium: 250,  complex: 600  },
  conversation:   { simple: 200,  medium: 600,  complex: 1600 },
  evaluation:     { simple: 350,  medium: 1000, complex: 2500 },
}

const FALLBACK_OUTPUT_TOKENS: Record<string, number> = { simple: 300, medium: 1000, complex: 3000 }

// ---------------------------------------------------------------------------
// Token estimation from feature vector
// ---------------------------------------------------------------------------

function estimateInputTokens(features: EstimationFeatures): number {
  const promptTokens   = Math.ceil(features.prompt_chars / 4)           // ~4 chars/token
  const contextTokens  = features.context_ref_count * 500               // 500 tokens per context ref
  const artifactTokens = features.artifact_ref_count * 300              // 300 tokens per artifact ref
  const toolDefTokens  = features.tools_enabled.length * 150            // 150 tokens per tool definition
  const systemOverhead = 250                                             // system prompt + formatting
  return promptTokens + contextTokens + artifactTokens + toolDefTokens + systemOverhead
}

function estimateOutputTokens(features: EstimationFeatures): number {
  const byType = OUTPUT_TOKEN_ESTIMATES[features.task_type_code] ?? FALLBACK_OUTPUT_TOKENS
  return byType[features.task_complexity_bucket] ?? byType['medium'] ?? 1000
}

// ---------------------------------------------------------------------------
// Latency heuristic (ms) — very rough; useful only for display, not governance
// ---------------------------------------------------------------------------
function estimateLatencyMs(tokensOut: number, provider: string): number {
  const tokenRateMs = provider === 'google' ? 8 : 12   // tokens/ms varies by provider
  return 300 + tokensOut * tokenRateMs
}

// ---------------------------------------------------------------------------
// Cost computation with p50 / p75 / p95 bands
// p75 = p50 × 1.35  (moderate overrun scenario)
// p95 = p50 × 2.10  (tail scenario — multi-retry or longer-than-expected output)
// These multipliers will be calibrated in Phase 2 per task type.
// ---------------------------------------------------------------------------
function computeCost(
  tokensIn: number,
  tokensOut: number,
  rates:    typeof EMBEDDED_FALLBACK_RATES,
  toolCalls: number,
): { p50: number; p75: number; p95: number } {
  const base =
    (tokensIn  / 1000) * rates.input_per_1k_tokens_usd +
    (tokensOut / 1000) * rates.output_per_1k_tokens_usd +
    toolCalls * rates.tool_call_per_invocation_usd

  return {
    p50: Math.max(base, 0.000001),            // floor at $0.000001 to avoid zero estimates
    p75: Math.max(base * 1.35, 0.000001),
    p95: Math.max(base * 2.10, 0.000001),
  }
}

// ---------------------------------------------------------------------------
// Main estimation function
// ---------------------------------------------------------------------------

export async function estimate(
  supabase: SupabaseClient,
  model:    string,
  provider: string,
  features: EstimationFeatures,
): Promise<EstimateResult> {
  const warnings: string[] = []
  const capturedAt = new Date().toISOString()

  // --- Phase 1 feature quality warnings ---
  if (features.prompt_chars === 0) {
    warnings.push('prompt_chars=0: token estimate uses output heuristics only (Phase 1 dark launch)')
  }
  if (features.tools_definition_hash === 'unknown' || features.system_prompt_hash === 'unknown') {
    warnings.push('feature_snapshot_partial: prompt/tool hashes not available at ingest time')
  }

  // --- Pricing table lookup ---
  let pricingVersionId: string
  let matchedEntry: PricingEntry | undefined
  let tier: EstimateResult['estimation_tier'] = 'embedded_fallback'
  let pricingSnapshot: PricingSnapshot

  const { data: pricingRow } = await supabase
    .schema('cost_intelligence')
    .from('pricing_table_versions')
    .select('id, entries')
    .eq('status', 'active')
    .maybeSingle()

  if (pricingRow) {
    const entries = pricingRow.entries as PricingEntry[]
    matchedEntry = entries.find(e => e.provider === provider && e.model === model)

    if (matchedEntry) {
      tier = 'deterministic'
      pricingVersionId = pricingRow.id as string
      pricingSnapshot = { ...matchedEntry, captured_at: capturedAt }
    } else {
      warnings.push(`model '${provider}/${model}' not in pricing table — using embedded fallback rates`)
      pricingVersionId = pricingRow.id as string
      pricingSnapshot = {
        provider, model,
        rates: EMBEDDED_FALLBACK_RATES,
        captured_at: capturedAt,
      }
    }
  } else {
    // No active pricing table — true embedded fallback
    warnings.push('no active pricing table found — using embedded fallback rates')
    // Use a sentinel version id; will be overwritten once pricing table is seeded
    pricingVersionId = '00000000-0000-0000-0000-000000000000'
    pricingSnapshot = {
      provider, model,
      rates: EMBEDDED_FALLBACK_RATES,
      captured_at: capturedAt,
    }
  }

  // --- Token + cost estimation ---
  const rates = matchedEntry?.rates ?? EMBEDDED_FALLBACK_RATES
  const tokensIn  = estimateInputTokens(features)
  const tokensOut = estimateOutputTokens(features)
  const toolCalls = features.tools_enabled.length * Math.max(1, features.declared_max_steps)
  const costs     = computeCost(tokensIn, tokensOut, rates, toolCalls)

  return {
    cost_p50_usd:             parseFloat(costs.p50.toFixed(6)),
    cost_p75_usd:             parseFloat(costs.p75.toFixed(6)),
    cost_p95_usd:             parseFloat(costs.p95.toFixed(6)),
    tokens_in_p50:            tokensIn,
    tokens_out_p50:           tokensOut,
    estimated_latency_ms_p50: estimateLatencyMs(tokensOut, provider),
    confidence:               'low',   // no calibration data in Phase 1
    estimation_tier:          tier,
    pricing_table_version_id: pricingVersionId,
    pricing_snapshot:         pricingSnapshot,
    warnings,
  }
}

// ---------------------------------------------------------------------------
// Build a Phase 1 feature snapshot from the limited data available at ingest
// time. Fields the ingest endpoint cannot supply are zeroed/unknown and flagged.
// ---------------------------------------------------------------------------

export function buildIngestFeatures(opts: {
  task_type_code:         string
  task_complexity_bucket: string
  declared_max_steps:     number
  declared_child_runs:    number
  tools_enabled:          string[]
}): EstimationFeatures {
  return {
    feature_schema_version:       'features-v1',
    captured_at:                  new Date().toISOString(),
    prompt_chars:                 0,     // not available from /api/ingest
    context_ref_count:            0,     // not available from /api/ingest
    artifact_ref_count:           0,     // not available from /api/ingest
    tools_enabled:                opts.tools_enabled,
    tools_definition_hash:        'unknown',
    system_prompt_hash:           'unknown',
    declared_max_steps:           opts.declared_max_steps,
    declared_child_runs:          opts.declared_child_runs,
    task_type_code:               opts.task_type_code,
    task_complexity_bucket:       opts.task_complexity_bucket,
    context_window_requested_pct: 0,
  }
}
