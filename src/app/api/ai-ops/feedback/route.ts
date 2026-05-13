import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

/**
 * POST /api/ai-ops/feedback
 *
 * Record thumbs-up / thumbs-down on a recommendation.
 *
 * Body: { recommendation_id, was_accurate, actual_provider_used?, notes? }
 */
export async function POST(request: NextRequest) {
  let body: any
  try {
    body = await request.json()
  } catch {
    return Response.json({ error: 'invalid json' }, { status: 400 })
  }

  const { recommendation_id, was_accurate, actual_provider_used, notes } = body

  if (!recommendation_id || typeof was_accurate !== 'boolean') {
    return Response.json({ error: 'recommendation_id and was_accurate are required' }, { status: 400 })
  }

  const supabase = createServiceRoleClient()

  const { error } = await supabase.from('recommendation_feedback').insert({
    recommendation_id,
    was_accurate,
    actual_provider_used: actual_provider_used ?? null,
    notes: notes ?? null,
  })

  if (error) {
    return Response.json({ error: error.message }, { status: 500 })
  }

  return Response.json({ ok: true })
}
