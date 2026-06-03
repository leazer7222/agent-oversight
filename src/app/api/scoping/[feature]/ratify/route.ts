import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

async function resolveTenant(sb: ReturnType<typeof createServiceRoleClient>, name: string) {
  const { data } = await sb.from('companies').select('id').eq('name', name)
  return data && data.length === 1 ? (data[0] as { id: string }).id : null
}

/**
 * POST /api/scoping/[feature]/ratify
 * Body: { node_key, new_status, ratified_by?, product?, tenant? }
 *
 * Flips a knowledge-plane node's lifecycle state (e.g. concept/decision proposed -> accepted | rejected).
 * The DB immutability trigger guards illegal transitions (accepted nodes are content-frozen).
 */
export async function POST(req: NextRequest, { params }: { params: Promise<{ feature: string }> }) {
  await params
  const body = await req.json().catch(() => ({}))
  const product = body.product ?? 'reformai-product'
  const tenantName = body.tenant ?? 'ReformAI'
  if (!body.node_key || !body.new_status) {
    return Response.json({ error: 'node_key and new_status are required' }, { status: 400 })
  }

  const sb = createServiceRoleClient()
  const tenant = await resolveTenant(sb, tenantName)
  if (!tenant) return Response.json({ error: `tenant '${tenantName}' not resolved` }, { status: 400 })

  const res = await sb.rpc('graph_ratify_node', {
    p_tenant: tenant, p_product: product, p_node_key: body.node_key,
    p_new_status: body.new_status, p_ratified_by: body.ratified_by || 'human',
  })
  if (res.error) return Response.json({ error: res.error.message }, { status: 500 })
  return Response.json({ ok: true })
}
