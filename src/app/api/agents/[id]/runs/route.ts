import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'
import { parsePagination, paginationMeta } from '@/lib/api/pagination'

export const runtime = 'nodejs'

/**
 * GET /api/agents/[id]/runs
 *
 * Run history for a specific agent.
 * Query params: status, limit, offset
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params
  const url = new URL(request.url)
  const { limit, offset } = parsePagination(url)
  const statusFilter = url.searchParams.get('status')

  const supabase = createServiceRoleClient()

  // Verify agent exists
  const { data: agent } = await supabase
    .from('agents')
    .select('id, name')
    .eq('id', id)
    .single()

  if (!agent) {
    return Response.json({ error: 'Agent not found' }, { status: 404 })
  }

  let query = supabase
    .from('runs')
    .select(
      'id, status, started_at, completed_at, created_at, timeout_at, ' +
      'tokens_in, tokens_out, cost_usd, cost_reported, error, metadata',
      { count: 'exact' }
    )
    .eq('agent_id', id)
    .order('started_at', { ascending: false })
    .range(offset, offset + limit - 1)

  if (statusFilter) query = query.eq('status', statusFilter)

  const { data: runs, error, count } = await query

  if (error) {
    return Response.json({ error: error.message }, { status: 500 })
  }

  // Compute duration_ms from timestamps
  const enriched = (runs as any[] ?? []).map((run: any) => ({
    ...run,
    duration_ms: run.completed_at && run.started_at
      ? new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()
      : null,
  }))

  return Response.json({
    agent:      { id: agent.id, name: agent.name },
    data:       enriched,
    count:      count ?? 0,
    pagination: paginationMeta({ limit, offset }, (runs ?? []).length),
  })
}
