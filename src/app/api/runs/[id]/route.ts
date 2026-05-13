import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

/**
 * GET /api/runs/[id]
 *
 * Full run detail: lifecycle summary + agent info + event trace + outputs.
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params
  const supabase = createServiceRoleClient()

  const [runResult, eventsResult, outputsResult] = await Promise.all([
    supabase
      .from('runs')
      .select('*')
      .eq('id', id)
      .single(),

    supabase
      .from('agent_events')
      .select(
        'id, event_type, occurred_at, message, severity, duration_ms, ' +
        'tokens_in, tokens_out, cost_usd, payload'
      )
      .eq('run_id', id)
      .order('occurred_at', { ascending: true }),

    supabase
      .from('agent_outputs')
      .select('id, output_type, content, created_at')
      .eq('run_id', id)
      .order('created_at', { ascending: true }),
  ])

  if (runResult.error || !runResult.data) {
    return Response.json({ error: 'Run not found' }, { status: 404 })
  }

  const run = runResult.data

  // Fetch agent info
  const { data: agent } = await supabase
    .from('agents')
    .select('id, name, agent_type, model, status')
    .eq('id', run.agent_id)
    .single()

  const duration_ms = run.completed_at && run.started_at
    ? new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()
    : null

  return Response.json({
    run: {
      ...run,
      duration_ms,
    },
    agent:   agent ?? null,
    events:  eventsResult.data  ?? [],
    outputs: outputsResult.data ?? [],
  })
}
