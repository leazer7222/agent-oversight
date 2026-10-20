import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'
import { requireTenant, authErrorResponse } from '@/lib/auth/require-tenant'

export const runtime = 'nodejs'

/** GET /api/sourcing/operations - counters for the workspace header, plus the
 *  pipeline board and this tenant's recent agent runs and spend. */
export async function GET(request: NextRequest) {
  try {
    const url = new URL(request.url)
    const ctx = await requireTenant(url.searchParams.get('company'))
    const sb = createServiceRoleClient()

    const [summary, pipeline, runs] = await Promise.all([
      sb.rpc('swim_operations_summary', { p_company_id: ctx.companyId }),
      sb.rpc('swim_pipeline_summary', { p_company_id: ctx.companyId }),
      sb.from('runs')
        .select('id, agent_id, status, cost_usd, started_at, completed_at, error, agents!inner(company_id, name)')
        .eq('agents.company_id', ctx.companyId)
        .order('started_at', { ascending: false })
        .limit(20),
    ])

    const runRows = (runs.data ?? []) as Array<Record<string, unknown>>
    const spend = runRows.reduce(
      (acc, r) => acc + (typeof r.cost_usd === 'number' ? r.cost_usd : 0), 0)

    return Response.json({
      company_id: ctx.companyId,
      summary: summary.data ?? {},
      pipeline: pipeline.data ?? [],
      recent_runs: runRows,
      // Internal cost attribution. NOT the same thing as provider billing
      // isolation, which comes solely from the tenant owning the API key.
      recent_spend_usd: Number(spend.toFixed(6)),
      errors: runs.error ? [runs.error.message] : [],
    })
  } catch (err) {
    return authErrorResponse(err)
  }
}
