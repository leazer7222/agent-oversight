import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

/**
 * GET /api/runs/[id]/events
 *
 * Event trace for a specific run, ordered chronologically.
 * Useful for timeline views and step-level drill-down.
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params
  const supabase = createServiceRoleClient()

  const { data: events, error } = await supabase
    .from('agent_events')
    .select(
      'id, event_type, occurred_at, message, severity, duration_ms, ' +
      'tokens_in, tokens_out, cost_usd, payload, triggered_by_agent_id'
    )
    .eq('run_id', id)
    .order('occurred_at', { ascending: true })

  if (error) {
    return Response.json({ error: error.message }, { status: 500 })
  }

  // Compute cumulative cost/tokens across the trace
  const summary = (events as any[] ?? []).reduce(
    (acc: any, e: any) => ({
      total_tokens_in:   acc.total_tokens_in   + (e.tokens_in   ?? 0),
      total_tokens_out:  acc.total_tokens_out  + (e.tokens_out  ?? 0),
      total_cost_usd:    acc.total_cost_usd    + (e.cost_usd    ?? 0),
      total_duration_ms: acc.total_duration_ms + (e.duration_ms ?? 0),
    }),
    { total_tokens_in: 0, total_tokens_out: 0, total_cost_usd: 0, total_duration_ms: 0 }
  )

  return Response.json({
    run_id: id,
    events: (events as any[]) ?? [],
    count:  (events ?? []).length,
    summary,
  })
}
