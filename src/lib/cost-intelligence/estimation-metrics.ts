// Estimation Dashboard — Canonical Metric Definitions
//
// This module is the single source of truth for all TypeScript-derived
// estimation metrics. It exists to prevent dashboard logic drift:
//
//   SQL-derived metrics  → DB functions in migration 022 (public.get_*)
//   TS-derived metrics   → THIS FILE, and nowhere else
//   Artifact semantics   → RFC-002, types in ./types.ts
//
// Rule: if you add a derived metric to a dashboard component inline,
// move it here instead. Components import from here; they do not
// compute their own business logic.
//
// RFC references: RFC-002 §10 (ART-001, ART-002)

import type { EstimationFeatures } from './types'

// ---------------------------------------------------------------------------
// Raw artifact shapes (what the DB returns via get_estimation_run_detail)
// ---------------------------------------------------------------------------

export interface EstimateArtifact {
  id:                            string
  run_request_id:                string
  tenant_id:                     string
  schema_version:                string
  model:                         string
  provider:                      string
  model_selection_mode:          string
  model_selection_reason:        string
  pricing_table_version_id:      string
  pricing_snapshot:              {
    provider:    string
    model:       string
    rates: {
      input_per_1k_tokens_usd:        number
      output_per_1k_tokens_usd:       number
      cached_input_per_1k_tokens_usd: number
      reasoning_per_1k_tokens_usd:    number
      tool_call_per_invocation_usd:   number
    }
    captured_at: string
  }
  estimation_features_snapshot:  EstimationFeatures | null
  estimation_tier:               'calibrated' | 'cached_calibration' | 'deterministic' | 'embedded_fallback'
  cost_p50_usd:                  number
  cost_p75_usd:                  number
  cost_p95_usd:                  number
  tokens_in_p50:                 number | null
  tokens_out_p50:                number | null
  estimated_latency_ms_p50:      number | null
  confidence:                    'very_low' | 'low' | 'medium' | 'high' | 'very_high'
  warnings:                      string[]
  created_at:                    string
  calibration_version_id:        string | null
  calibration_source:            string | null
}

export interface EvaluationArtifact {
  id:                       string
  estimate_id:              string
  run_id:                   string
  tenant_id:                string
  schema_version:           string
  eval_algorithm_version:   string
  telemetry_status:         'complete' | 'incomplete' | 'provisional' | 'reconciled'
  actual_cost_usd:          number
  actual_cost_input_usd:    number | null
  actual_cost_output_usd:   number | null
  actual_cost_cached_usd:   number | null
  actual_cost_tools_usd:    number | null
  actual_cost_reasoning_usd:number | null
  tokens_in_actual:         number | null
  tokens_out_actual:        number | null
  tokens_cached_actual:     number | null
  tokens_reasoning_actual:  number | null
  wall_clock_ms:            number | null
  retry_count:              number
  failure_mode:             string | null
  actual_tool_calls:        number | null
  actual_child_runs:        number | null
  context_window_used_pct:  number | null
  absolute_error_usd:       number | null
  percentage_error:         number | null
  underestimated:           boolean | null
  calibration_bucket_id:    string | null
  calibration_bucket_key:   string | null
  is_outlier:               boolean
  outlier_reason:           string | null
  is_recomputable:          boolean
  derivation_manifest:      Record<string, unknown>
  created_at:               string
}

export interface RecommendationArtifact {
  id:                       string
  run_request_id:           string
  routing_mode:             string
  model_selection_mode:     string
  selected_model:           string
  selected_provider:        string
  selection_reason:         string
  task_type_id:             string | null
  task_complexity_bucket:   string | null
  budget_available_at_routing: number
  cold_start_model_selected:boolean
  routing_confidence:       string | null
  candidates_evaluated:     unknown[]
  created_at:               string
}

export interface BudgetReservation {
  id:                           string
  run_id:                       string
  estimate_id:                  string
  reservation_tier:             'p50' | 'p75' | 'p95'
  reserved_usd:                 number
  status:                       string
  budget_available_at_dispatch: number
  expires_at:                   string
  created_at:                   string
}

export interface SettlementRecord {
  id:               string
  reservation_id:   string
  settlement_type:  string
  actual_cost_usd:  number
  settlement_source:string
  is_provisional:   boolean
  created_at:       string
}

// ---------------------------------------------------------------------------
// EstimationFailureMode — derived from artifacts, NEVER stored in DB
// ---------------------------------------------------------------------------

export type EstimationFailureMode =
  | 'context_size_unknown'   // prompt_chars=0 at estimate time; estimator blind to actual input
  | 'output_expansion'       // token-out actual >> token-out p50; agent generated far more output
  | 'complexity_mismatch'    // classified simple/medium but ran as complex (>500% error)
  | 'pricing_table_stale'    // token error small, cost error large — rates are wrong
  | 'context_window_pressure'// context_window_used_pct > 85%
  | 'within_tolerance'       // |error| < 50% — acceptable
  | 'insufficient_data'      // evaluation missing or telemetry incomplete
  | 'unknown'

/**
 * Classify the root cause of an estimation miss.
 *
 * Called at API response time — never stored as a DB column.
 * This is the canonical failure mode logic. Do not re-implement
 * this in dashboard components.
 */
export function classifyFailureMode(
  estimate:   EstimateArtifact   | null,
  evaluation: EvaluationArtifact | null,
): EstimationFailureMode {
  if (!estimate || !evaluation) return 'insufficient_data'
  if (evaluation.telemetry_status !== 'complete') return 'insufficient_data'
  if (evaluation.percentage_error === null) return 'insufficient_data'

  const features = estimate.estimation_features_snapshot

  const tokenInError = (estimate.tokens_in_p50 && evaluation.tokens_in_actual)
    ? (evaluation.tokens_in_actual - estimate.tokens_in_p50) / estimate.tokens_in_p50
    : null

  const tokenOutError = (estimate.tokens_out_p50 && evaluation.tokens_out_actual)
    ? (evaluation.tokens_out_actual - estimate.tokens_out_p50) / estimate.tokens_out_p50
    : null

  // Acceptable: error within ±50%
  if (Math.abs(evaluation.percentage_error) < 50) {
    return 'within_tolerance'
  }

  // context_size_unknown: prompt_chars=0 AND massive token-in error
  // This is the Phase 1 dark-launch blind spot: the ingest endpoint
  // cannot see the actual prompt content at run_started time.
  if (
    features?.prompt_chars === 0 &&
    tokenInError !== null &&
    tokenInError > 5.0
  ) {
    return 'context_size_unknown'
  }

  // output_expansion: token-out blew up, token-in was roughly accurate
  if (
    tokenOutError !== null &&
    tokenOutError > 3.0 &&
    (tokenInError === null || Math.abs(tokenInError) < 1.0)
  ) {
    return 'output_expansion'
  }

  // pricing_table_stale: token prediction accurate but cost error large
  if (
    tokenInError !== null && Math.abs(tokenInError) < 0.25 &&
    tokenOutError !== null && Math.abs(tokenOutError) < 0.25
  ) {
    const costError = (evaluation.actual_cost_usd - estimate.cost_p50_usd) / estimate.cost_p50_usd
    if (costError > 0.5) return 'pricing_table_stale'
  }

  // context_window_pressure
  if ((evaluation.context_window_used_pct ?? 0) > 85) {
    return 'context_window_pressure'
  }

  // complexity_mismatch: classified as simple/medium, behaved as complex
  if (
    features?.task_complexity_bucket !== 'complex' &&
    Math.abs(evaluation.percentage_error) > 500
  ) {
    return 'complexity_mismatch'
  }

  return 'unknown'
}

// ---------------------------------------------------------------------------
// Derived scalar metrics — computed from artifacts, never stored
// ---------------------------------------------------------------------------

/** Signed error in dollars. Positive = actual exceeded estimate (underestimated). */
export function signedErrorUsd(
  estimate:   EstimateArtifact,
  evaluation: EvaluationArtifact,
): number {
  return evaluation.actual_cost_usd - estimate.cost_p50_usd
}

/** Did the actual cost fall within the p95 estimate band? */
export function isWithinP95Band(
  estimate:   EstimateArtifact,
  evaluation: EvaluationArtifact,
): boolean {
  return evaluation.actual_cost_usd <= estimate.cost_p95_usd
}

/** Token-in prediction error as a percentage. Null if either value missing. */
export function tokenInErrorPct(
  estimate:   EstimateArtifact,
  evaluation: EvaluationArtifact,
): number | null {
  if (!estimate.tokens_in_p50 || !evaluation.tokens_in_actual) return null
  return ((evaluation.tokens_in_actual - estimate.tokens_in_p50) / estimate.tokens_in_p50) * 100
}

/** Token-out prediction error as a percentage. Null if either value missing. */
export function tokenOutErrorPct(
  estimate:   EstimateArtifact,
  evaluation: EvaluationArtifact,
): number | null {
  if (!estimate.tokens_out_p50 || !evaluation.tokens_out_actual) return null
  return ((evaluation.tokens_out_actual - estimate.tokens_out_p50) / estimate.tokens_out_p50) * 100
}

/**
 * Is this run eligible to be a calibration training point?
 * Three conditions: features snapshot present, pricing table resolvable,
 * and evaluation is_recomputable.
 */
export function isReplayable(
  estimate:   EstimateArtifact,
  evaluation: EvaluationArtifact,
): boolean {
  return Boolean(
    estimate.estimation_features_snapshot !== null &&
    estimate.pricing_table_version_id &&
    evaluation.is_recomputable
  )
}

// ---------------------------------------------------------------------------
// Feature snapshot interpretation helpers
// ---------------------------------------------------------------------------

/**
 * Human-readable label for a failure mode.
 * Canonical label map — components must use this, not define their own.
 */
export const FAILURE_MODE_LABELS: Record<EstimationFailureMode, string> = {
  context_size_unknown:    'Context size unknown at estimate time',
  output_expansion:        'Output expansion — agent generated far more tokens than expected',
  complexity_mismatch:     'Complexity mismatch — classified lower than actual behavior',
  pricing_table_stale:     'Pricing table stale — token prediction accurate, cost wrong',
  context_window_pressure: 'Context window pressure — >85% utilization',
  within_tolerance:        'Within tolerance — error < 50%',
  insufficient_data:       'Insufficient data — telemetry incomplete',
  unknown:                 'Unknown — no dominant root cause identified',
}

/**
 * Explanation sentences for the "Why this estimate?" section.
 * Phase 1: derived from warnings in estimate_artifacts.warnings[].
 * Phase 2: will be enriched with feature importance scores from calibration.
 */
export function estimateExplanation(estimate: EstimateArtifact): string[] {
  const lines: string[] = []
  const f = estimate.estimation_features_snapshot

  if (!f) {
    lines.push('Feature snapshot unavailable — estimate cannot be explained.')
    return lines
  }

  if (f.prompt_chars === 0) {
    lines.push('prompt_chars = 0: prompt size was not available at run_started time. Input token estimate used system overhead only (250 tokens).')
  } else {
    lines.push(`prompt_chars = ${f.prompt_chars.toLocaleString()} → ~${Math.ceil(f.prompt_chars / 4).toLocaleString()} input tokens from prompt`)
  }

  if (f.context_ref_count > 0) {
    lines.push(`context_ref_count = ${f.context_ref_count} → ~${(f.context_ref_count * 500).toLocaleString()} additional input tokens`)
  }

  if (f.tools_enabled.length > 0) {
    lines.push(`tools_enabled = [${f.tools_enabled.join(', ')}] → ~${(f.tools_enabled.length * 150).toLocaleString()} tokens for tool definitions`)
  }

  lines.push(`Output tokens estimated by task type / complexity heuristic: ${f.task_type_code} / ${f.task_complexity_bucket}`)

  if (estimate.warnings.length > 0) {
    for (const w of estimate.warnings) {
      lines.push(`⚠ ${w}`)
    }
  }

  return lines
}

// ---------------------------------------------------------------------------
// Formatting helpers — used consistently across all estimation UI
// ---------------------------------------------------------------------------

export function formatErrorPct(pct: number | null | undefined): string {
  if (pct == null) return '—'
  const sign = pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(1)}%`
}

export function formatUsd(usd: number | null | undefined, decimals = 4): string {
  if (usd == null) return '—'
  return `$${usd.toFixed(decimals)}`
}

export function formatTokens(n: number | null | undefined): string {
  if (n == null) return '—'
  return n.toLocaleString()
}

/** Error severity for color-coding. Matches SQL calibration_status thresholds. */
export function errorSeverity(pctError: number | null): 'ok' | 'warn' | 'severe' {
  if (pctError == null) return 'ok'
  const abs = Math.abs(pctError)
  if (abs < 50)  return 'ok'
  if (abs < 200) return 'warn'
  return 'severe'
}
