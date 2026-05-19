import type { NextRequest } from 'next/server'
import { z } from 'zod'
import { createServiceRoleClient } from '@/lib/supabase/server'
import { estimate, buildIngestFeatures } from '@/lib/cost-intelligence/deterministic-estimator'
import { createEvaluationArtifact } from '@/lib/cost-intelligence/evaluation-pipeline'
import { ensureBudgetPeriod, createReservation, settleReservation, currentPeriodKey } from '@/lib/runtime-governance/budget'

export const runtime = 'nodejs'

const IngestSchema = z.object({
  agent_id:      z.string().uuid(),
  event:         z.enum(['run_started', 'run_completed', 'run_failed', 'run_step']),
  run_id:        z.string().uuid(),
  timestamp:     z.string().datetime().optional(),
  tokens_in:     z.number().int().nonnegative().optional(),
  tokens_out:    z.number().int().nonnegative().optional(),
  cost_usd:      z.number().nonnegative().optional(),
  error:         z.string().optional(),
  metadata:      z.record(z.string(), z.unknown()).optional(),
  parent_run_id: z.string().uuid().optional(),
  // Phase 2 step event fields
  step_name:     z.string().optional(),
  message:       z.string().optional(),
  duration_ms:   z.number().int().nonnegative().optional(),
  severity:      z.enum(['info', 'warning', 'error']).optional(),
  // Agile Team / workspace attribution fields
  team_id:                 z.string().optional(),
  context_bundle_id:       z.string().optional(),
  context_bundle_version:  z.number().int().nonnegative().optional(),
  // Phase 1 Group 2 — task classification (RFC-005)
  // Agents supply the human-readable code; the ingest layer resolves to UUID.
  // If omitted, defaults to code_gen / medium (transitional until dispatch coordinator ships).
  task_type_code:           z.string().optional(),
  task_complexity_bucket:   z.enum(['simple', 'medium', 'complex']).optional(),
})

// How long a run is allowed to run before it is considered a zombie
const RUN_TIMEOUT_MS = 30 * 60 * 1000 // 30 minutes

// ---------------------------------------------------------------------------
// Phase 1 Group 3 — dark-launch artifact writes (RFC-002 ART-001 + ART-007)
// Called fire-and-forget after run INSERT commits. Errors are logged but never
// propagate to the caller — artifact creation must not block the run response.
// ---------------------------------------------------------------------------

// Writes recommendation_artifact, estimate_artifact, budget_period, and budget_reservation.
// Fire-and-forget on run_started. All writes are non-fatal.
async function writeGroupThreeArtifacts(opts: {
  runId:                 string
  tenantId:              string
  model:                 string
  provider:              string
  taskTypeId:            string | null
  taskTypeCode:          string
  taskComplexityBucket:  string
}) {
  const supabase = createServiceRoleClient()

  const features = buildIngestFeatures({
    task_type_code:         opts.taskTypeCode,
    task_complexity_bucket: opts.taskComplexityBucket,
    declared_max_steps:     5,   // default; agents will supply this in Phase 3+
    declared_child_runs:    0,
    tools_enabled:          [],
  })

  // 1. Recommendation artifact (passthrough stub — RFC-002 ART-007)
  const { data: recRow, error: recErr } = await supabase
    .schema('model_intelligence')
    .from('recommendation_artifacts')
    .insert({
      run_request_id:              opts.runId,
      tenant_id:                   opts.tenantId,
      schema_version:              '1.0.0',
      routing_mode:                'passthrough',
      model_selection_mode:        'user_specified',
      selected_model:              opts.model,
      selected_provider:           opts.provider,
      selection_reason:            'passthrough: routing engine not active in Phase 1',
      task_type_id:                opts.taskTypeId,
      task_complexity_bucket:      opts.taskComplexityBucket,
      budget_eligible_models:      [opts.model],
      budget_available_at_routing: 9999.9999,
      cold_start_model_selected:   false,
      routing_confidence:          'not_applicable',
      candidates_evaluated:        [],
    })
    .select('id')
    .single()

  if (recErr) {
    // Duplicate on re-delivery is fine; log everything else
    if (recErr.code !== '23505') {
      console.error('[ingest/artifacts] recommendation_artifact write failed:', recErr.message, { runId: opts.runId })
    }
    return  // no point estimating if the recommendation anchor didn't write
  }

  // 2. Estimate artifact (deterministic tier — RFC-002 ART-001)
  let estimateResult
  try {
    estimateResult = await estimate(supabase, opts.model, opts.provider, features)
  } catch (err) {
    console.error('[ingest/artifacts] estimate() failed:', err, { runId: opts.runId })
    return
  }

  const { data: estRow, error: estErr } = await supabase
    .schema('cost_intelligence')
    .from('estimate_artifacts')
    .insert({
      run_request_id:               opts.runId,
      tenant_id:                    opts.tenantId,
      schema_version:               '1.0.0',
      model:                        opts.model,
      provider:                     opts.provider,
      model_selection_mode:         'user_specified',
      model_selection_reason:       `passthrough via recommendation ${recRow.id}`,
      pricing_table_version_id:     estimateResult.pricing_table_version_id,
      pricing_snapshot:             estimateResult.pricing_snapshot,
      calibration_version_id:       null,
      calibration_source:           'deterministic',
      estimation_features_snapshot: features,
      estimation_tier:              estimateResult.estimation_tier,
      cost_p50_usd:                 estimateResult.cost_p50_usd,
      cost_p75_usd:                 estimateResult.cost_p75_usd,
      cost_p95_usd:                 estimateResult.cost_p95_usd,
      tokens_in_p50:                estimateResult.tokens_in_p50,
      tokens_out_p50:               estimateResult.tokens_out_p50,
      estimated_latency_ms_p50:     estimateResult.estimated_latency_ms_p50,
      confidence:                   estimateResult.confidence,
      warnings:                     estimateResult.warnings,
    })
    .select('id')
    .single()

  if (estErr && estErr.code !== '23505') {
    console.error('[ingest/artifacts] estimate_artifact write failed:', estErr.message, { runId: opts.runId })
    return
  }

  // 3. Budget period + reservation (Group 4)
  const periodKey = currentPeriodKey()
  const period    = await ensureBudgetPeriod(supabase, opts.tenantId, periodKey)
  if (!period) return

  const budgetAvailable = period.budget_usd - period.reserved_usd - period.consumed_usd

  await createReservation(supabase, {
    runId:            opts.runId,
    tenantId:         opts.tenantId,
    estimateId:       estRow!.id,
    recommendationId: recRow.id,
    periodKey,
    reservedUsd:      estimateResult.cost_p95_usd,
    budgetAvailable,
  })
}

function buildEventMessage(event: string, data: { error?: string; step_name?: string; message?: string }): string {
  if (data.message) return data.message
  if (event === 'run_started')   return 'Run started'
  if (event === 'run_completed') return 'Run completed successfully'
  if (event === 'run_failed')    return data.error ? `Run failed: ${data.error}` : 'Run failed'
  return event
}

export async function POST(request: NextRequest) {
  // Auth
  const secret = request.headers.get('x-agent-secret')
  if (!secret || secret !== process.env.INGEST_SECRET) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 })
  }

  // Parse & validate
  let body: unknown
  try {
    body = await request.json()
  } catch {
    return Response.json({ error: 'Invalid JSON' }, { status: 400 })
  }

  const parsed = IngestSchema.safeParse(body)
  if (!parsed.success) {
    return Response.json(
      { error: 'Validation failed', issues: parsed.error.issues },
      { status: 422 }
    )
  }

  const {
    agent_id, event, run_id, timestamp,
    tokens_in, tokens_out, cost_usd, error, metadata,
    parent_run_id, step_name, message, duration_ms, severity,
    team_id, context_bundle_id, context_bundle_version,
    task_type_code, task_complexity_bucket,
  } = parsed.data

  const supabase = createServiceRoleClient()
  const now = timestamp ?? new Date().toISOString()

  // Verify agent exists — fetch fields needed for agent_events write
  const { data: agent, error: agentErr } = await supabase
    .from('agents')
    .select('id, status, company_id, depth, agent_type, project_id')
    .eq('id', agent_id)
    .single()

  if (agentErr || !agent) {
    return Response.json({ error: 'Agent not found' }, { status: 404 })
  }

  if (agent.status !== 'active') {
    return Response.json({ error: 'Agent is not active' }, { status: 403 })
  }

  // run_step: write directly to agent_events, skip runs table entirely
  if (event === 'run_step') {
    if (agent.company_id) {
      const { error: stepErr } = await supabase.from('agent_events').insert({
        agent_id,
        company_id:   agent.company_id,
        project_id:   agent.project_id ?? null,
        run_id,
        event_type:   'run_step',
        occurred_at:  now,
        message:      message || step_name || 'step',
        payload:      metadata ?? {},
        severity:     severity ?? 'info',
        depth:        agent.depth ?? 0,
        duration_ms:  duration_ms ?? null,
        tokens_in:    tokens_in  ?? null,
        tokens_out:   tokens_out ?? null,
        cost_usd:     cost_usd   ?? null,
      })
      if (stepErr) console.error('[ingest] run_step write failed:', stepErr.message)
    }
    return Response.json({ ok: true, run_id }, { status: 200 })
  }

  // Write run record
  if (event === 'run_started') {
    const timeout_at = new Date(Date.now() + RUN_TIMEOUT_MS).toISOString()

    // Resolve task type UUID from the human-readable code (RFC-005).
    // Falls back to code_gen if the caller omits the field or supplies an unknown code.
    // Transitional: once the dispatch coordinator ships (Group 3+), task_type will be
    // resolved upstream before reaching ingest.
    const resolvedCode = task_type_code ?? 'code_gen'
    const { data: taskTypeRow } = await supabase
      .schema('cost_intelligence')
      .from('task_types')
      .select('id')
      .eq('code', resolvedCode)
      .maybeSingle()

    let taskTypeId: string | null = taskTypeRow?.id ?? null

    if (!taskTypeId && task_type_code) {
      // Caller supplied a code that doesn't exist — fall back to code_gen and warn
      console.warn('[ingest] unknown task_type_code, falling back to code_gen:', task_type_code)
      const { data: fallback } = await supabase
        .schema('cost_intelligence')
        .from('task_types')
        .select('id')
        .eq('code', 'code_gen')
        .maybeSingle()
      taskTypeId = fallback?.id ?? null
    }

    const { error: insertErr } = await supabase.from('runs').insert({
      id:           run_id,
      agent_id,
      status:       'started',
      started_at:   now,
      timeout_at,
      parent_run_id:           parent_run_id           ?? null,
      metadata:                metadata                ?? null,
      team_id:                 team_id                 ?? null,
      context_bundle_id:       context_bundle_id       ?? null,
      context_bundle_version:  context_bundle_version  ?? null,
      task_type_id:            taskTypeId,
      task_complexity_bucket:  task_complexity_bucket  ?? 'medium',
      task_classifier_version: 'complexity-v1',
    })

    if (insertErr) {
      return Response.json({ error: insertErr.message }, { status: 500 })
    }

    // Fire-and-forget: write recommendation + estimate artifacts (Group 3 dark launch).
    // Runs asynchronously after the run INSERT commits. Never blocks the response.
    // Uses the agent's model/company as tenant proxy until a real tenant table exists.
    void writeGroupThreeArtifacts({
      runId:                run_id,
      tenantId:             agent.company_id ?? '00000000-0000-0000-0000-000000000000',
      model:                'claude-sonnet-4-6',    // TODO: read from agent.model in Phase 3
      provider:             'anthropic',            // TODO: infer from model name in Phase 3
      taskTypeId:           taskTypeId,
      taskTypeCode:         resolvedCode,
      taskComplexityBucket: task_complexity_bucket ?? 'medium',
    })
  } else {
    const hasCostData = cost_usd !== undefined && cost_usd !== null

    const update: Record<string, unknown> = {
      status:       event === 'run_completed' ? 'completed' : 'failed',
      completed_at: now,
      cost_reported: hasCostData,
    }
    if (tokens_in  !== undefined) update.tokens_in  = tokens_in
    if (tokens_out !== undefined) update.tokens_out = tokens_out
    if (cost_usd   !== undefined) update.cost_usd   = cost_usd
    if (error      !== undefined) update.error      = error
    if (metadata   !== undefined) update.metadata   = metadata

    const { error: updateErr } = await supabase
      .from('runs')
      .update(update)
      .eq('id', run_id)
      .eq('agent_id', agent_id)

    if (updateErr) {
      return Response.json({ error: updateErr.message }, { status: 500 })
    }

    // Fire-and-forget: evaluation artifact + reservation settlement (Groups 4 + 5).
    // Non-blocking — errors must never affect the run_completed response.
    const tenantId = agent.company_id ?? '00000000-0000-0000-0000-000000000000'
    void (async () => {
      await createEvaluationArtifact(
        createServiceRoleClient(),
        {
          id:           run_id,
          cost_usd:     cost_usd    ?? null,
          tokens_in:    tokens_in   ?? null,
          tokens_out:   tokens_out  ?? null,
          started_at:   now,         // approximate — actual started_at is on the runs row
          completed_at: now,
          error:        error        ?? null,
        },
        tenantId,
      )
      await settleReservation(
        createServiceRoleClient(),
        {
          runId:         run_id,
          tenantId,
          actualCostUsd: cost_usd    ?? 0,
          isProvisional: cost_usd === null || cost_usd === undefined,
          source:        (cost_usd !== null && cost_usd !== undefined) ? 'telemetry' : 'estimated',
        },
      )
    })().catch(err => console.error('[ingest/terminal] evaluation/settlement failed:', err, { run_id }))
  }

  // Write agent_events trace row (non-fatal — run record already committed above)
  // Requires company_id; skip silently if agent has no company association.
  if (agent.company_id) {
    try {
      await supabase.from('agent_events').insert({
        agent_id,
        company_id:   agent.company_id,
        project_id:   agent.project_id ?? null,
        run_id,
        event_type:   event,
        occurred_at:  now,
        message:      buildEventMessage(event, { error, step_name, message }),
        payload:      metadata ?? {},
        severity:     event === 'run_failed' ? 'error' : 'info',
        depth:        agent.depth ?? 0,
        duration_ms:  duration_ms ?? null,
        tokens_in:    tokens_in  ?? null,
        tokens_out:   tokens_out ?? null,
        cost_usd:     cost_usd   ?? null,
      })
    } catch {
      // Telemetry failure must never break the run record response
      console.error('[ingest] agent_events write failed for run', run_id)
    }
  }

  return Response.json({ ok: true, run_id }, { status: 200 })
}
