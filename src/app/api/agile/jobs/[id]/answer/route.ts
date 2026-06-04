import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

/**
 * POST /api/agile/jobs/[id]/answer
 * Body: { answers: [{ question, answer }] }
 * Enqueues a Pass B job (same intake + the human answers) that finalizes the brief.
 * The worker runs it; the original job stays as the audit record of the clarify round.
 */
export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const body = await req.json().catch(() => ({}))
  const answers = Array.isArray(body.answers) ? body.answers : []
  if (answers.length === 0) return Response.json({ error: 'answers are required' }, { status: 400 })

  const sb = createServiceRoleClient()
  const { data: parent, error } = await sb.from('agile_intake_jobs').select('*').eq('id', id).single()
  if (error || !parent) return Response.json({ error: 'parent job not found' }, { status: 404 })
  const p = parent as {
    company_id: string; product_key: string; workspace_id: string; intake: unknown
  }

  const { data, error: insErr } = await sb
    .from('agile_intake_jobs')
    .insert({
      company_id: p.company_id, product_key: p.product_key, workspace_id: p.workspace_id,
      pass: 'b', intake: p.intake, answers, parent_job_id: id, status: 'queued', created_by: 'dashboard',
    })
    .select('id')
    .single()
  if (insErr) return Response.json({ error: insErr.message }, { status: 500 })

  return Response.json({ job_id: (data as { id: string }).id })
}
