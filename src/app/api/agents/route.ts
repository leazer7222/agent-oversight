import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'
import { parsePagination, paginationMeta } from '@/lib/api/pagination'

export const runtime = 'nodejs'

/**
 * GET /api/agents
 *
 * Query params:
 *   status   - filter by agent status (active | paused | retired)
 *   company  - filter by company_id (uuid)
 *   limit    - page size (default 50, max 200)
 *   offset   - page offset (default 0)
 */
export async function GET(request: NextRequest) {
  const url = new URL(request.url)
  const { limit, offset } = parsePagination(url)
  const statusFilter  = url.searchParams.get('status')
  const companyFilter = url.searchParams.get('company')

  const supabase = createServiceRoleClient()

  let query = supabase
    .from('agents')
    .select(`
      id, name, agent_type, status, model, platform,
      company_id, project_id, definition_id,
      registered_at, last_run_at, paused_at, paused_reason,
      depth, tags, metadata
    `, { count: 'exact' })
    .order('registered_at', { ascending: false })
    .range(offset, offset + limit - 1)

  if (statusFilter)  query = query.eq('status', statusFilter)
  if (companyFilter) query = query.eq('company_id', companyFilter)

  const { data: agents, error, count } = await query

  if (error) {
    return Response.json({ error: error.message }, { status: 500 })
  }

  // Enrich with run stats from agent_cost_summary view
  const agentIds = (agents ?? []).map(a => a.id)
  let costByAgent: Record<string, { total_runs: number; total_cost_usd: number; total_tokens_in: number; total_tokens_out: number; last_event_at: string | null }> = {}

  if (agentIds.length > 0) {
    const { data: costRows } = await supabase
      .from('agent_cost_summary')
      .select('agent_id, total_runs, total_cost_usd, total_tokens_in, total_tokens_out, last_event_at')
      .in('agent_id', agentIds)

    for (const row of costRows ?? []) {
      costByAgent[row.agent_id] = row
    }
  }

  const enriched = (agents ?? []).map(agent => ({
    ...agent,
    run_count:       costByAgent[agent.id]?.total_runs       ?? 0,
    total_cost_usd:  costByAgent[agent.id]?.total_cost_usd   ?? 0,
    total_tokens_in: costByAgent[agent.id]?.total_tokens_in  ?? 0,
    total_tokens_out:costByAgent[agent.id]?.total_tokens_out ?? 0,
    last_event_at:   costByAgent[agent.id]?.last_event_at    ?? null,
  }))

  return Response.json({
    data:       enriched,
    count:      count ?? 0,
    pagination: paginationMeta({ limit, offset }, (agents ?? []).length),
  })
}
