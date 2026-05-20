import type { NextRequest } from 'next/server'
import { z } from 'zod'
import { createServiceRoleClient } from '@/lib/supabase/server'

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
  // Agents supply the human-readable code; the ingest layer resolves to UUID via RPC.
  // If omitted, defaults to code_gen / medium (transitional until dispatch coordinator ships).
  task_type_code:           z.string().optional(),
  task_complexity_bucket:   z.enum(['simple', 'medium', 'complex']).optional(),
  // Estimation accuracy fields (run_started only)
  // model/provider: the actual model the agent is about to call. Defaults to claude-sonnet-4-6
  //   if omitted for backward compatibility, but agents should always supply these.
  // tokens_in_hint: caller's pre-call estimate of input tokens (chars/4 approximation).
  //   When provided, used instead of the complexity-bucket heuristic (2000 tokens default).
  //   Also widens p95 band from 15x to 2.1x since context size is now known.
  model:            z.string().optional(),
  provider:         z.string().optional(),
  tokens_in_hint:   z.number().int().nonnegative().optional(),
})

const RUN_TIMEOUT_MS = 30 * 60 * 1000

function buildEventMessage(event: string, data: { error?: string; step_name?: string; message?: string }): string {
  if (data.message) return data.message
  if (event === 'run_started')   return 'Run started'
  if (event === 'run_completed') return 'Run completed successfully'
  if (event === 'run_failed')    return data.error ? `Run failed: ${data.error}` : 'Run failed'
  return event
}

export async function POST(request: NextRequest) {
  const secret = request.headers.get('x-agent-secret')
  if (!secret || secret !== process.env.INGEST_SECRET) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 })
  }

  let body: unknown
  try {
    body = await request.json()
  } catch {
    return Response.json({ error: 'Invalid JSON' }, { status: 400 })
  }

  const parsed = IngestSchema.safeParse(body)
  if (!parsed.success) {
    return Response.json({ error: 'Validation failed', issues: parsed.error.issues }, { status: 422 })
  }

  const {
    agent_id, event, run_id, timestamp,
    tokens_in, tokens_out, cost_usd, error, metadata,
    parent_run_id, step_name, message, duration_ms, severity,
    team_id, context_bundle_id, context_bundle_version,
    task_type_code, task_complexity_bucket,
    model, provider, tokens_in_hint,
  } = parsed.data

  const supabase = createServiceRoleClient()
  const now = timestamp ?? new Date().toISOString()

  const { data: agent, error: agentErr } = await supabase
    .from('agents')
    .select('id, status, company_id, depth, agent_type, project_id')
    .eq('id', agent_id)
    .single()

  if (agentErr || !agent) return Response.json({ error: 'Agent not found' }, { status: 404 })
  if (agent.status !== 'active') return Response.json({ error: 'Agent is not active' }, { status: 403 })

  if (event === 'run_step') {
    if (agent.company_id) {
      const { error: stepErr } = await supabase.from('agent_events').insert({
        agent_id, company_id: agent.company_id, project_id: agent.project_id ?? null,
        run_id, event_type: 'run_step', occurred_at: now,
        message: message || step_name || 'step', payload: metadata ?? {},
        severity: severity ?? 'info', depth: agent.depth ?? 0,
        duration_ms: duration_ms ?? null, tokens_in: tokens_in ?? null,
        tokens_out: tokens_out ?? null, cost_usd: cost_usd ?? null,
      })
      if (stepErr) console.error('[ingest] run_step write failed:', stepErr.message)
    }
    return Response.json({ ok: true, run_id }, { status: 200 })
  }

  if (event === 'run_started') {
    const timeout_at = new Date(Date.now() + RUN_TIMEOUT_MS).toISOString()
    const resolvedCode = task_type_code ?? 'code_gen'

    // Resolve task_type_id via public RPC (SECURITY DEFINER — accesses cost_intelligence schema)
    const { data: taskTypeId } = await supabase.rpc('get_task_type_id', { p_code: resolvedCode })
    const finalTaskTypeId = taskTypeId as string | null

    if (!finalTaskTypeId) {
      console.warn('[ingest] get_task_type_id returned null for code:', resolvedCode)
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
      task_type_id:            finalTaskTypeId,
      task_complexity_bucket:  task_complexity_bucket  ?? 'medium',
      task_classifier_version: 'complexity-v1',
    })

    if (insertErr) return Response.json({ error: insertErr.message }, { status: 500 })

    // Only write artifacts when the agent has a real company association.
    // A sentinel/null tenant_id would contaminate artifact tables with invalid data (finding #3).
    if (agent.company_id) {
      void supabase.rpc('write_run_started_artifacts', {
        p_run_id:                 run_id,
        p_tenant_id:              agent.company_id,
        p_model:                  model    ?? 'claude-sonnet-4-6',
        p_provider:               provider ?? 'anthropic',
        p_task_type_code:         resolvedCode,
        p_task_complexity_bucket: task_complexity_bucket ?? 'medium',
        p_tokens_in_hint:         tokens_in_hint ?? null,
      }).then(({ data, error: rpcErr }: { data: { error?: string } | null; error: { message: string } | null }) => {
        if (rpcErr) console.error('[ingest/artifacts] write_run_started_artifacts failed:', rpcErr.message)
        else if (data?.error) console.error('[ingest/artifacts] run_started artifacts error:', data.error)
      })
    }

  } else {
    const hasCostData = cost_usd !== undefined && cost_usd !== null

    const update: Record<string, unknown> = {
      status:        event === 'run_completed' ? 'completed' : 'failed',
      completed_at:  now,
      cost_reported: hasCostData,
    }
    if (tokens_in  !== undefined) update.tokens_in  = tokens_in
    if (tokens_out !== undefined) update.tokens_out = tokens_out
    if (cost_usd   !== undefined) update.cost_usd   = cost_usd
    if (error      !== undefined) update.error      = error
    if (metadata   !== undefined) update.metadata   = metadata

    const { error: updateErr } = await supabase
      .from('runs').update(update).eq('id', run_id).eq('agent_id', agent_id)

    if (updateErr) return Response.json({ error: updateErr.message }, { status: 500 })

    // Only write artifacts when the agent has a real company association (finding #3).
    if (agent.company_id) {
      void supabase.rpc('write_run_completed_artifacts', {
        p_run_id:           run_id,
        p_tenant_id:        agent.company_id,
        p_actual_cost_usd:  cost_usd   ?? null,
        p_tokens_in:        tokens_in  ?? null,
        p_tokens_out:       tokens_out ?? null,
        p_started_at:       now,
        p_completed_at:     now,
        p_error_text:       error      ?? null,
      }).then(({ data, error: rpcErr }: { data: { error?: string } | null; error: { message: string } | null }) => {
        if (rpcErr) console.error('[ingest/artifacts] write_run_completed_artifacts failed:', rpcErr.message)
        else if (data?.error) console.error('[ingest/artifacts] run_completed artifacts error:', data.error)
      })
    }
  }

  if (agent.company_id) {
    try {
      await supabase.from('agent_events').insert({
        agent_id, company_id: agent.company_id, project_id: agent.project_id ?? null,
        run_id, event_type: event, occurred_at: now,
        message: buildEventMessage(event, { error, step_name, message }),
        payload: metadata ?? {}, severity: event === 'run_failed' ? 'error' : 'info',
        depth: agent.depth ?? 0, duration_ms: duration_ms ?? null,
        tokens_in: tokens_in ?? null, tokens_out: tokens_out ?? null, cost_usd: cost_usd ?? null,
      })
    } catch {
      console.error('[ingest] agent_events write failed for run', run_id)
    }
  }

  return Response.json({ ok: true, run_id }, { status: 200 })
}
