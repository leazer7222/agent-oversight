import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

async function resolveTenant(sb: ReturnType<typeof createServiceRoleClient>, name: string) {
  const { data } = await sb.from('companies').select('id').eq('name', name)
  return data && data.length === 1 ? (data[0] as { id: string }).id : null
}

/**
 * POST /api/scoping/[feature]/answer
 * Body: { question_key, statement, rationale?, references:[CON-*], implies_rules?, implies_attributes?,
 *         ratified_by?, product?, tenant? }
 *
 * Captures a human answer as a PROPOSED Decision: mints DEC-*, links resolves -> question and
 * references -> concept(s), and marks the question 'answered'. The Decision remains 'proposed'
 * until separately ratified (Pass B touchpoint 1: answer; touchpoint 2: ratify).
 *
 * Citation rule: at least one concept reference is required (an uncited decision is an opinion).
 */
export async function POST(req: NextRequest, { params }: { params: Promise<{ feature: string }> }) {
  await params
  const body = await req.json().catch(() => ({}))
  const product = body.product ?? 'reformai-product'
  const tenantName = body.tenant ?? 'ReformAI'
  const by = body.ratified_by || 'human'
  const refs: string[] = Array.isArray(body.references) ? body.references : []

  if (!body.question_key || !body.statement || refs.length === 0) {
    return Response.json(
      { error: 'question_key, statement, and at least one concept reference are required' },
      { status: 400 }
    )
  }

  const sb = createServiceRoleClient()
  const tenant = await resolveTenant(sb, tenantName)
  if (!tenant) return Response.json({ error: `tenant '${tenantName}' not resolved` }, { status: 400 })

  const keyRes = await sb.rpc('graph_next_key', { p_product: product, p_node_type: 'decision' })
  if (keyRes.error) return Response.json({ error: keyRes.error.message }, { status: 500 })
  const dk = keyRes.data as string

  const upsert = await sb.rpc('graph_upsert_node', {
    p_tenant: tenant, p_product: product, p_node_type: 'decision', p_node_key: dk,
    p_title: body.statement, p_status: 'proposed', p_created_by: by,
    p_node_attributes: {
      rationale: body.rationale ?? '',
      implies_rules: Array.isArray(body.implies_rules) ? body.implies_rules : [],
      implies_attributes: Array.isArray(body.implies_attributes) ? body.implies_attributes : [],
    },
  })
  if (upsert.error) return Response.json({ error: upsert.error.message }, { status: 500 })

  const edges = [
    sb.rpc('graph_add_edge', { p_tenant: tenant, p_product: product, p_edge_type: 'resolves',
      p_src_key: dk, p_dst_key: body.question_key, p_created_by: by, p_edge_attributes: {} }),
    ...refs.map((r) => sb.rpc('graph_add_edge', { p_tenant: tenant, p_product: product,
      p_edge_type: 'references', p_src_key: dk, p_dst_key: r, p_created_by: by, p_edge_attributes: {} })),
  ]
  const edgeRes = await Promise.all(edges)
  const edgeErr = edgeRes.find((e) => e.error)
  if (edgeErr?.error) return Response.json({ error: edgeErr.error.message }, { status: 500 })

  const ans = await sb.rpc('graph_ratify_node', { p_tenant: tenant, p_product: product,
    p_node_key: body.question_key, p_new_status: 'answered', p_ratified_by: by })
  if (ans.error) return Response.json({ error: ans.error.message }, { status: 500 })

  return Response.json({ ok: true, decision: dk })
}
