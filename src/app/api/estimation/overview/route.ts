import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

/**
 * GET /api/estimation/overview
 *
 * Returns headline accuracy metrics and biggest misses for the estimation
 * overview dashboard. Two DB functions are called in parallel:
 *   - public.get_estimation_accuracy_overview()
 *   - public.get_biggest_misses(20)
 */
export async function GET() {
  const supabase = createServiceRoleClient()

  const [overviewRes, missesRes] = await Promise.all([
    supabase.rpc('get_estimation_accuracy_overview'),
    supabase.rpc('get_biggest_misses', { p_limit: 20 }),
  ])

  if (overviewRes.error) {
    return Response.json(
      { error: `Overview query failed: ${overviewRes.error.message}` },
      { status: 500 }
    )
  }
  if (missesRes.error) {
    return Response.json(
      { error: `Biggest misses query failed: ${missesRes.error.message}` },
      { status: 500 }
    )
  }

  const overview = overviewRes.data as Record<string, unknown>
  const misses   = missesRes.data  as unknown[]

  if (overview?.error) {
    return Response.json({ error: overview.error }, { status: 500 })
  }

  return Response.json({ overview, misses })
}
