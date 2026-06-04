import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

/**
 * GET /api/agile/jobs/[id] -> the job + its linked intake_assessment and clarification_brief
 * artifact bodies (from agent_outputs), so the console can render the full result.
 */
export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const sb = createServiceRoleClient()

  const { data: job, error } = await sb.from('agile_intake_jobs').select('*').eq('id', id).single()
  if (error || !job) return Response.json({ error: 'job not found' }, { status: 404 })

  const out: { job: unknown; assessment: unknown; brief: unknown; scope: unknown } =
    { job, assessment: null, brief: null, scope: null }
  const j = job as { assessment_id?: string; brief_id?: string; scope_artifact_id?: string }

  if (j.assessment_id) {
    const { data } = await sb.from('agent_outputs').select('content').eq('id', j.assessment_id).single()
    out.assessment = (data as { content: unknown } | null)?.content ?? null
  }
  if (j.brief_id) {
    const { data } = await sb.from('agent_outputs').select('content').eq('id', j.brief_id).single()
    out.brief = (data as { content: unknown } | null)?.content ?? null
  }
  if (j.scope_artifact_id) {
    const { data } = await sb.from('agent_outputs').select('content').eq('id', j.scope_artifact_id).single()
    out.scope = (data as { content: unknown } | null)?.content ?? null
  }
  return Response.json(out)
}
