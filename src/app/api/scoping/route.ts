import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

async function resolveTenant(sb: ReturnType<typeof createServiceRoleClient>, name: string) {
  const { data } = await sb.from('companies').select('id').eq('name', name)
  return data && data.length === 1 ? (data[0] as { id: string }).id : null
}

/** GET /api/scoping?product=reformai-product&tenant=ReformAI -> features + ratification backlog */
export async function GET(req: NextRequest) {
  const url = new URL(req.url)
  const product = url.searchParams.get('product') ?? 'reformai-product'
  const tenantName = url.searchParams.get('tenant') ?? 'ReformAI'

  const sb = createServiceRoleClient()
  const tenant = await resolveTenant(sb, tenantName)
  if (!tenant) return Response.json({ error: `tenant '${tenantName}' not resolved` }, { status: 400 })

  const [features, backlog] = await Promise.all([
    sb.rpc('graph_list_features', { p_tenant: tenant, p_product: product }),
    sb.rpc('graph_backlog', { p_tenant: tenant, p_product: product }),
  ])
  if (features.error) return Response.json({ error: features.error.message }, { status: 500 })

  return Response.json({ tenant, product, features: features.data ?? [], backlog: backlog.data })
}
