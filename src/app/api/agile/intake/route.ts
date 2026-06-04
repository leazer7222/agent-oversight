import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

const SOURCE_TYPES = new Set([
  'idea', 'paragraph', 'prd', 'jira_text', 'customer_feedback', 'bug_enhancement', 'text_workflow',
])

/**
 * POST /api/agile/intake
 * Body: { text, source_type?, product?, tenant?, workspace? }
 * Enqueues an intake job for the agile worker (worker.py) to execute via PCA run_intake.
 */
export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}))
  const text = (body.text ?? '').toString().trim()
  const sourceType = (body.source_type ?? 'paragraph').toString()
  const product = (body.product ?? 'reformai-product').toString()
  const tenantName = (body.tenant ?? 'ReformAI').toString()
  const workspace = (body.workspace ?? 'reformai-product').toString()

  if (!text) return Response.json({ error: 'intake text is required' }, { status: 400 })
  if (!SOURCE_TYPES.has(sourceType)) {
    return Response.json({ error: `unsupported source_type '${sourceType}'` }, { status: 400 })
  }

  const sb = createServiceRoleClient()
  const { data: companies } = await sb.from('companies').select('id').eq('name', tenantName)
  const company = companies && companies.length === 1 ? (companies[0] as { id: string }).id : null
  if (!company) return Response.json({ error: `tenant '${tenantName}' not resolved` }, { status: 400 })

  const { data, error } = await sb
    .from('agile_intake_jobs')
    .insert({
      company_id: company, product_key: product, workspace_id: workspace, pass: 'a',
      intake: [{ source_type: sourceType, text }], status: 'queued', created_by: 'dashboard',
    })
    .select('id')
    .single()
  if (error) return Response.json({ error: error.message }, { status: 500 })

  return Response.json({ job_id: (data as { id: string }).id })
}
