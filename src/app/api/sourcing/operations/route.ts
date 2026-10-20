import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'
import { requireTenant, authErrorResponse } from '@/lib/auth/require-tenant'

export const runtime = 'nodejs'

/** GET /api/sourcing/operations - counters for the workspace header, the
 *  pipeline board, this tenant's recent agent runs and spend, and (migration
 *  053) the research worksheet, drafts, reply threads, next actions and
 *  objective progress.
 *
 *  Every domain read goes through a public RPC: PostgREST does not expose the
 *  swim_sourcing schema (verified live 2026-10-20, PGRST106). */
export async function GET(request: NextRequest) {
  try {
    const url = new URL(request.url)
    const ctx = await requireTenant(url.searchParams.get('company'))
    const sb = createServiceRoleClient()
    const company = { p_company_id: ctx.companyId }

    const [summary, pipeline, runs, research, drafts, threads, actions, objective] = await Promise.all([
      sb.rpc('swim_operations_summary', company),
      sb.rpc('swim_pipeline_summary', company),
      sb.from('runs')
        .select('id, agent_id, status, cost_usd, tokens_in, tokens_out, started_at, completed_at, error, metadata, agents!inner(company_id, name)')
        .eq('agents.company_id', ctx.companyId)
        .order('started_at', { ascending: false })
        .limit(20),
      sb.rpc('swim_list_research', { ...company, p_limit: 200 }),
      sb.rpc('swim_list_drafts', { ...company, p_limit: 50 }),
      sb.rpc('swim_list_threads', { ...company, p_limit: 50 }),
      sb.rpc('swim_next_actions', company),
      sb.rpc('swim_objective_progress', company),
    ])

    const runRows = (runs.data ?? []) as Array<Record<string, unknown>>
    const spend = runRows.reduce(
      (acc, r) => acc + (typeof r.cost_usd === 'number' ? r.cost_usd : Number(r.cost_usd ?? 0)), 0)

    const errors = [summary, pipeline, runs, research, drafts, threads, actions, objective]
      .map((r) => r.error?.message)
      .filter((m): m is string => Boolean(m))

    return Response.json({
      company_id: ctx.companyId,
      summary: summary.data ?? {},
      pipeline: pipeline.data ?? [],
      recent_runs: runRows,
      // Internal cost attribution. NOT the same thing as provider billing
      // isolation, which comes solely from the tenant owning the API key.
      recent_spend_usd: Number(spend.toFixed(6)),
      research: research.data ?? [],
      drafts: drafts.data ?? [],
      threads: threads.data ?? [],
      next_actions: actions.data ?? [],
      objective: objective.data ?? {},
      errors,
    })
  } catch (err) {
    return authErrorResponse(err)
  }
}
