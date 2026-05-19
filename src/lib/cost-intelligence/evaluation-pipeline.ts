// Cost Intelligence — Evaluation Pipeline (Phase 1)
//
// Creates evaluation_artifacts after a run reaches terminal state.
// Idempotent: checks for existing evaluation via UNIQUE index on run_id
// before writing. Duplicate attempts are silently ignored (23505).
//
// Phase 1 algorithm version: 'eval-v1-deterministic'
//   - Compares actual_cost_usd (from runs.cost_usd) to estimate cost_p50_usd
//   - Sets telemetry_status = 'incomplete' when cost is missing
//   - No calibration bucket assignment (Phase 2)
//   - No outlier detection (Phase 2)
//
// RFC references: RFC-002 §10 (ART-002), RFC-003 §6 (idempotency)

import type { SupabaseClient } from '@supabase/supabase-js'

const EVAL_ALGORITHM_VERSION = 'eval-v1-deterministic'

interface RunRecord {
  id:           string
  cost_usd:     number | null
  tokens_in:    number | null
  tokens_out:   number | null
  started_at:   string
  completed_at: string | null
  error:        string | null
}

// ---------------------------------------------------------------------------
// createEvaluationArtifact
//
// Called on run_completed or run_failed. Looks up the estimate_artifact for
// this run, then writes an evaluation_artifact comparing actuals to estimates.
//
// Returns: 'created' | 'duplicate' | 'no_estimate' | 'error'
// ---------------------------------------------------------------------------

export async function createEvaluationArtifact(
  supabase: SupabaseClient,
  run:      RunRecord,
  tenantId: string,
): Promise<'created' | 'duplicate' | 'no_estimate' | 'error'> {
  // 1. Look up the estimate for this run (run_request_id = run_id in Phase 1)
  const { data: est } = await supabase
    .schema('cost_intelligence')
    .from('estimate_artifacts')
    .select('id, cost_p50_usd, tokens_in_p50, tokens_out_p50, estimated_latency_ms_p50')
    .eq('run_request_id', run.id)
    .maybeSingle()

  if (!est) return 'no_estimate'   // pre-Group-3 run; skip silently

  // 2. Determine telemetry completeness
  const hasActualCost = run.cost_usd !== null && run.cost_usd !== undefined
  const telemetryStatus = hasActualCost ? 'complete' : 'incomplete'
  const actualCostUsd   = hasActualCost ? run.cost_usd! : 0.0

  // 3. Error metrics — only computed when telemetry is complete
  let absoluteErrorUsd: number | null = null
  let percentageError:  number | null = null
  let underestimated:   boolean | null = null

  if (hasActualCost) {
    const p50 = est.cost_p50_usd as number
    absoluteErrorUsd = Math.abs(actualCostUsd - p50)
    percentageError  = p50 > 0 ? parseFloat(((absoluteErrorUsd / p50) * 100).toFixed(4)) : null
    underestimated   = actualCostUsd > p50
  }

  // 4. Wall-clock time
  let wallClockMs: number | null = null
  if (run.started_at && run.completed_at) {
    wallClockMs = new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()
  }

  // 5. Failure mode from error string (best-effort parse for Phase 1)
  let failureMode: string | null = null
  if (run.error) {
    if (run.error.includes('rate_limit') || run.error.includes('429'))  failureMode = 'rate_limit'
    else if (run.error.includes('context'))                              failureMode = 'context_overflow'
    else if (run.error.includes('timeout'))                              failureMode = 'timeout'
    else                                                                 failureMode = 'api_error'
  }

  // 6. Derivation manifest — required, documents input sources
  const derivationManifest = {
    algorithm_version:     EVAL_ALGORITHM_VERSION,
    computed_at:           new Date().toISOString(),
    inputs: {
      estimate_artifact_id:  est.id,
      run_id:                run.id,
      actual_cost_usd_source: hasActualCost ? 'runs.cost_usd' : 'missing',
      tokens_source:          (run.tokens_in !== null) ? 'runs.tokens_in/out' : 'missing',
    },
    notes: telemetryStatus === 'incomplete'
      ? 'actual_cost_usd missing at evaluation time; artifact excluded from calibration'
      : null,
  }

  // 7. Write evaluation_artifact (idempotent via UNIQUE on run_id)
  const { error } = await supabase
    .schema('cost_intelligence')
    .from('evaluation_artifacts')
    .insert({
      estimate_id:             est.id,
      run_id:                  run.id,
      tenant_id:               tenantId,
      schema_version:          '1.0.0',
      eval_algorithm_version:  EVAL_ALGORITHM_VERSION,
      telemetry_status:        telemetryStatus,
      actual_cost_usd:         actualCostUsd,
      tokens_in_actual:        run.tokens_in  ?? null,
      tokens_out_actual:       run.tokens_out ?? null,
      wall_clock_ms:           wallClockMs,
      failure_mode:            failureMode,
      absolute_error_usd:      absoluteErrorUsd,
      percentage_error:        percentageError,
      underestimated:          underestimated,
      is_outlier:              false,
      is_recomputable:         true,
      derivation_manifest:     derivationManifest,
    })

  if (error) {
    if (error.code === '23505') return 'duplicate'
    console.error('[eval-pipeline] evaluation_artifact write failed:', error.message, { runId: run.id })
    return 'error'
  }

  return 'created'
}
