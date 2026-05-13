import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'
import { parsePagination, paginationMeta } from '@/lib/api/pagination'

export const runtime = 'nodejs'

/**
 * GET /api/errors
 *
 * Failed runs with error details and taxonomy grouping.
 *
 * Query params:
 *   agent    - filter by agent_id (uuid)
 *   category - filter by error category prefix (e.g. "quota_exceeded", "auth_error")
 *   since    - ISO timestamp — only runs after this time
 *   limit    - page size (default 50, max 200)
 *   offset   - page offset (default 0)
 */
export async function GET(request: NextRequest) {
  const url = new URL(request.url)
  const { limit, offset } = parsePagination(url)
  const agentFilter    = url.searchParams.get('agent')
  const categoryFilter = url.searchParams.get('category')
  const since          = url.searchParams.get('since')

  const supabase = createServiceRoleClient()

  let query = supabase
    .from('runs')
    .select(
      'id, agent_id, status, error, started_at, completed_at, created_at, ' +
      'tokens_in, tokens_out, cost_usd, parent_run_id',
      { count: 'exact' }
    )
    .eq('status', 'failed')
    .order('started_at', { ascending: false })
    .range(offset, offset + limit - 1)

  if (agentFilter) query = query.eq('agent_id', agentFilter)
  if (since)       query = query.gte('started_at', since)

  // Category filter: error column starts with [category]
  if (categoryFilter) {
    query = query.like('error', `[${categoryFilter}]%`)
  }

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
    agent_name:     agentNames[run.agent_id] ?? null,
    duration_ms:    run.completed_at && run.started_at
      ? new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()
      : null,
    error_category: extractCategory(run.error as string | null),
  }))

  // Build category breakdown (frequency count)
  const categoryCounts: Record<string, number> = {}
  for (const run of enriched) {
    const cat = run.error_category ?? 'unknown'
    categoryCounts[cat] = (categoryCounts[cat] ?? 0) + 1
  }

  const breakdown = Object.entries(categoryCounts)
    .map(([category, count]) => ({ category, count }))
    .sort((a, b) => b.count - a.count)

  return Response.json({
    data:       enriched,
    count:      count ?? 0,
    pagination: paginationMeta({ limit, offset }, (runs ?? []).length),
    breakdown,
  })
}

/**
 * Extract the error category prefix written by the Python SDK.
 * E.g. "[quota_exceeded] Rate limit reached" → "quota_exceeded"
 * Falls back to null if no bracket prefix is present.
 */
function extractCategory(error: string | null): string | null {
  if (!error) return null
  const match = error.match(/^\[([^\]]+)\]/)
  return match ? match[1] : null
}
