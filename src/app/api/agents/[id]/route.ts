import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

/**
 * GET /api/agents/[id]
 *
 * Returns full agent record enriched with run stats and recent runs.
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params
  const supabase = createServiceRoleClient()

  const [agentResult, costResult, runsResult] = await Promise.all([
    supabase
      .from('agents')
      .select('*')
      .eq('id', id)
      .single(),

    supabase
      .from('agent_cost_summary')
      .select('total_runs, total_cost_usd, total_tokens_in, total_tokens_out, last_event_at')
      .eq('agent_id', id)
      .single(),

    supabase
      .from('runs')
      .select('id, status, started_at, completed_at, cost_usd, cost_reported, tokens_in, tokens_out, error')
      .eq('agent_id', id)
      .order('started_at', { ascending: false })
      .limit(10),
  ])

  if (agentResult.error || !agentResult.data) {
    return Response.json({ error: 'Agent not found' }, { status: 404 })
  }

  return Response.json({
    agent: {
      ...agentResult.data,
      run_count:        costResult.data?.total_runs        ?? 0,
      total_cost_usd:   costResult.data?.total_cost_usd    ?? 0,
      total_tokens_in:  costResult.data?.total_tokens_in   ?? 0,
      total_tokens_out: costResult.data?.total_tokens_out  ?? 0,
      last_event_at:    costResult.data?.last_event_at     ?? null,
    },
    recent_runs: runsResult.data ?? [],
  })
}
