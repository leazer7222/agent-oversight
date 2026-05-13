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
})

// How long a run is allowed to run before it is considered a zombie
const RUN_TIMEOUT_MS = 30 * 60 * 1000 // 30 minutes

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

    const { error: insertErr } = await supabase.from('runs').insert({
      id:           run_id,
      agent_id,
      status:       'started',
      started_at:   now,
      timeout_at,
      parent_run_id: parent_run_id ?? null,
      metadata:     metadata ?? null,
    })

    if (insertErr) {
      return Response.json({ error: insertErr.message }, { status: 500 })
    }
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
