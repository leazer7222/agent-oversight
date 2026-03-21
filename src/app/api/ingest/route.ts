import type { NextRequest } from 'next/server'
import { z } from 'zod'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

const IngestSchema = z.object({
  agent_id: z.string().uuid(),
  event: z.enum(['run_started', 'run_completed', 'run_failed']),
  run_id: z.string().uuid(),
  timestamp: z.string().datetime().optional(),
  tokens_in: z.number().int().nonnegative().optional(),
  tokens_out: z.number().int().nonnegative().optional(),
  cost_usd: z.number().nonnegative().optional(),
  error: z.string().optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
})

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

  const { agent_id, event, run_id, timestamp, tokens_in, tokens_out, cost_usd, error, metadata } =
    parsed.data

  const supabase = createServiceRoleClient()
  const now = timestamp ?? new Date().toISOString()

  // Verify agent exists
  const { data: agent, error: agentErr } = await supabase
    .from('agents')
    .select('id, status')
    .eq('id', agent_id)
    .single()

  if (agentErr || !agent) {
    return Response.json({ error: 'Agent not found' }, { status: 404 })
  }

  if (agent.status !== 'active') {
    return Response.json({ error: 'Agent is not active' }, { status: 403 })
  }

  // Upsert run record based on event
  if (event === 'run_started') {
    const { error: insertErr } = await supabase.from('runs').insert({
      id: run_id,
      agent_id,
      status: 'started',
      started_at: now,
      metadata: metadata ?? null,
    })

    if (insertErr) {
      return Response.json({ error: insertErr.message }, { status: 500 })
    }
  } else {
    const update: Record<string, unknown> = {
      status: event === 'run_completed' ? 'completed' : 'failed',
      completed_at: now,
    }
    if (tokens_in !== undefined) update.tokens_in = tokens_in
    if (tokens_out !== undefined) update.tokens_out = tokens_out
    if (cost_usd !== undefined) update.cost_usd = cost_usd
    if (error !== undefined) update.error = error
    if (metadata !== undefined) update.metadata = metadata

    const { error: updateErr } = await supabase
      .from('runs')
      .update(update)
      .eq('id', run_id)
      .eq('agent_id', agent_id)

    if (updateErr) {
      return Response.json({ error: updateErr.message }, { status: 500 })
    }
  }

  return Response.json({ ok: true, run_id }, { status: 200 })
}
