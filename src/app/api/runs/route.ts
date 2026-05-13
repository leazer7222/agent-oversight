import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'
import { parsePagination, paginationMeta } from '@/lib/api/pagination'

export const runtime = 'nodejs'

/**
 * GET /api/runs
 *
 * Execution history across all agents.
 *
 * Query params:
 *   status      - filter: started | completed | failed
 *   agent       - filter by agent_id (uuid)
 *   errors_only - "true" to return only failed runs
 *   limit       - page size (default 50, max 200)
 *   offset      - page offset (default 0)
 */
export async function GET(request: NextRequest) {
  const url = new URL(request.url)
  const { limit, offset } = parsePagination(url)
  const statusFilter    = url.searchParams.get('status')
  const agentFilter     = url.searchParams.get('agent')
  const errorsOnly      = url.searchParams.get('errors_only') === 'true'

  const supabase = createServiceRoleClient()

  let query = supabase
    .from('runs')
    .select(
      'id, agent_id, status, started_at, completed_at, created_at, ' +
      'tokens_in, tokens_out, cost_usd, cost_reported, error, timeout_at, parent_run_id',
      { count: 'exact' }
    )
    .order('started_at', { ascending: false })
    .range(offset, offset + limit - 1)

  if (errorsOnly)    query = query.eq('status', 'failed')
  else if (statusFilter) query = query.eq('status', statusFilter)
  if (agentFilter)   query = query.eq('agent_id', agentFilter)

  const { data: runs, error, count } = await query

  if (error) {
    return Response.json({ error: error.message }, { status: 500 })
  }

  // Enrich with agent names
  const agentIds = [...new Set((runs as any[] ?? []).map((r: any) => r.agent_id))]
  let agentNames: Record<string, string> = {}

  if (agentIds.length > 0) {
    const { data: agentRows } = await supabase
      .from('agents')
      .select('id, name')
      .in('id', agentIds)
    for (const a of agentRows ?? []) agentNames[a.id] = a.name
  }

  const enriched = (runs as any[] ?? []).map((run: any) => ({
    ...run,
    agent_name:  agentNames[run.agent_id] ?? null,
    duration_ms: run.completed_at && run.started_at
      ? new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()
      : null,
  }))

  return Response.json({
    data:       enriched,
    count:      count ?? 0,
    pagination: paginationMeta({ limit, offset }, (runs ?? []).length),
  })
}
