import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

/** GET /api/agile/jobs -> recent intake jobs (newest first). */
export async function GET() {
  const sb = createServiceRoleClient()
  const { data, error } = await sb
    .from('agile_intake_jobs')
    .select('id, status, decision, pass, product_key, brief_id, assessment_id, parent_job_id, intake, created_at')
    .order('created_at', { ascending: false })
    .limit(25)
  if (error) return Response.json({ error: error.message }, { status: 500 })
  return Response.json({ jobs: data ?? [] })
}
