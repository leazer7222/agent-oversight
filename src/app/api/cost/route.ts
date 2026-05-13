import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

/**
 * GET /api/cost
 *
 * Aggregate cost and token usage across all agents and projects.
 *
 * Query params:
 *   group_by - "agent" (default) | "project"
 *   company  - filter by company_id (uuid)
 *   limit    - max rows (default 50, max 200)
 */
export async function GET(request: NextRequest) {
  const url = new URL(request.url)
  const groupBy      = url.searchParams.get('group_by') ?? 'agent'
  const companyFilter = url.searchParams.get('company')
  const limit        = Math.min(parseInt(url.searchParams.get('limit') ?? '50', 10), 200)

  const supabase = createServiceRoleClient()

  if (groupBy === 'project') {
    // Project-level aggregates from project_cost_summary view
    let query = supabase
      .from('project_cost_summary')
      .select('*')
      .order('total_cost_usd', { ascending: false })
      .limit(limit)

    if (companyFilter) query = query.eq('company_id', companyFilter)

    const { data: rows, error } = await query

    if (error) {
      return Response.json({ error: error.message }, { status: 500 })
    }

    const overall = (rows ?? []).reduce(
      (acc, r) => ({
        total_cost_usd:   acc.total_cost_usd   + (r.total_cost_usd   ?? 0),
        total_tokens_in:  acc.total_tokens_in  + (r.total_tokens_in  ?? 0),
        total_tokens_out: acc.total_tokens_out + (r.total_tokens_out ?? 0),
        total_runs:       acc.total_runs       + (r.total_runs       ?? 0),
      }),
      { total_cost_usd: 0, total_tokens_in: 0, total_tokens_out: 0, total_runs: 0 }
    )

    return Response.json({
      group_by: 'project',
      data:     rows ?? [],
      count:    (rows ?? []).length,
      overall,
    })
  }

  // Default: agent-level aggregates from agent_cost_summary view
  let query = supabase
    .from('agent_cost_summary')
    .select('*')
    .order('total_cost_usd', { ascending: false })
    .limit(limit)

  if (companyFilter) query = query.eq('company_id', companyFilter)

  const { data: rows, error } = await query

  if (error) {
    return Response.json({ error: error.message }, { status: 500 })
  }

  // Enrich with agent names
  const agentIds = (rows ?? []).map(r => r.agent_id).filter(Boolean)
  let agentNames: Record<string, string> = {}

  if (agentIds.length > 0) {
    const { data: agentRows } = await supabase
      .from('agents')
      .select('id, name')
      .in('id', agentIds)
    for (const a of agentRows ?? []) agentNames[a.id] = a.name
  }

  const enriched = (rows ?? []).map(r => ({
    ...r,
    agent_name: agentNames[r.agent_id] ?? null,
  }))

  const overall = enriched.reduce(
    (acc, r) => ({
      total_cost_usd:   acc.total_cost_usd   + (r.total_cost_usd   ?? 0),
      total_tokens_in:  acc.total_tokens_in  + (r.total_tokens_in  ?? 0),
      total_tokens_out: acc.total_tokens_out + (r.total_tokens_out ?? 0),
      total_runs:       acc.total_runs       + (r.total_runs       ?? 0),
    }),
    { total_cost_usd: 0, total_tokens_in: 0, total_tokens_out: 0, total_runs: 0 }
  )

  return Response.json({
    group_by: 'agent',
    data:     enriched,
    count:    enriched.length,
    overall,
  })
}
