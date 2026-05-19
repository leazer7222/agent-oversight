import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'
import {
  classifyFailureMode,
  signedErrorUsd,
  isWithinP95Band,
  tokenInErrorPct,
  tokenOutErrorPct,
  isReplayable,
  estimateExplanation,
  type EstimateArtifact,
  type EvaluationArtifact,
} from '@/lib/cost-intelligence/estimation-metrics'

export const runtime = 'nodejs'

/**
 * GET /api/estimation/runs/[id]
 *
 * Returns all four estimation artifacts for a single run, plus
 * TypeScript-derived metrics (failure mode, replayability, band containment).
 *
 * Derived fields are computed here at response time — never stored in the DB.
 * This is the canonical source for run-level estimation analysis.
 *
 * Data sources:
 *   DB artifacts  → public.get_estimation_run_detail(run_id)
 *   Raw events    → agent_events (public schema, direct query)
 *   Derived       → estimation-metrics.ts (this file imports + computes)
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params
  const supabase = createServiceRoleClient()

  // All cross-schema artifact fetches go through the SECURITY DEFINER function.
  // Direct .schema().from() calls on non-public schemas silently return null
  // at runtime (PostgREST only exposes public). See LESSONS_LEARNED.
  const [artifactsRes, eventsRes] = await Promise.all([
    supabase.rpc('get_estimation_run_detail', { p_run_id: id }),
    supabase
      .from('agent_events')
      .select('id, event_type, occurred_at, message, severity, duration_ms, tokens_in, tokens_out, cost_usd, payload')
      .eq('run_id', id)
      .order('occurred_at', { ascending: true }),
  ])

  if (artifactsRes.error) {
    return Response.json(
      { error: `DB function error: ${artifactsRes.error.message}` },
      { status: 500 }
    )
  }

  const artifacts = artifactsRes.data as {
    run:             Record<string, unknown> | null
    estimate:        EstimateArtifact        | null
    evaluation:      EvaluationArtifact      | null
    recommendation:  Record<string, unknown> | null
    reservation:     Record<string, unknown> | null
    settlement:      Record<string, unknown> | null
    pricing_version: Record<string, unknown> | null
    task_type:       Record<string, unknown> | null
    error?:          string
  }

  if (artifacts.error) {
    return Response.json({ error: artifacts.error }, { status: 500 })
  }

  if (!artifacts.run) {
    return Response.json({ error: 'Run not found' }, { status: 404 })
  }

  const { estimate, evaluation } = artifacts

  // ---------------------------------------------------------------------------
  // TypeScript-derived fields — computed here, not stored in DB.
  // All logic lives in estimation-metrics.ts to prevent drift.
  // ---------------------------------------------------------------------------
  const derived = estimate && evaluation ? {
    failureMode:     classifyFailureMode(estimate, evaluation),
    signedErrorUsd:  signedErrorUsd(estimate, evaluation),
    withinP95Band:   isWithinP95Band(estimate, evaluation),
    tokenInErrorPct: tokenInErrorPct(estimate, evaluation),
    tokenOutErrorPct:tokenOutErrorPct(estimate, evaluation),
    replayable:      isReplayable(estimate, evaluation),
    explanation:     estimateExplanation(estimate),
  } : null

  return Response.json({
    run:             artifacts.run,
    estimate:        artifacts.estimate,
    evaluation:      artifacts.evaluation,
    recommendation:  artifacts.recommendation,
    reservation:     artifacts.reservation,
    settlement:      artifacts.settlement,
    pricing_version: artifacts.pricing_version,
    task_type:       artifacts.task_type,
    events:          eventsRes.data ?? [],
    derived,
  })
}
