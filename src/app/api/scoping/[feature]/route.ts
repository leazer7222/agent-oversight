import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

async function resolveTenant(sb: ReturnType<typeof createServiceRoleClient>, name: string) {
  const { data } = await sb.from('companies').select('id').eq('name', name)
  return data && data.length === 1 ? (data[0] as { id: string }).id : null
}

/**
 * GET /api/scoping/[feature]?product=reformai-product&tenant=ReformAI
 * Returns the full feature subgraph (nodes + edges), the derived readiness gate,
 * and the ratification backlog. All via SECURITY DEFINER graph_* RPCs.
 */
export async function GET(req: NextRequest, { params }: { params: Promise<{ feature: string }> }) {
  const { feature } = await params
  const url = new URL(req.url)
  const product = url.searchParams.get('product') ?? 'reformai-product'
  const tenantName = url.searchParams.get('tenant') ?? 'ReformAI'

  const sb = createServiceRoleClient()
  const tenant = await resolveTenant(sb, tenantName)
  if (!tenant) return Response.json({ error: `tenant '${tenantName}' not resolved` }, { status: 400 })

  const [detail, readiness, backlog] = await Promise.all([
    sb.rpc('graph_feature_graph', { p_tenant: tenant, p_product: product, p_feature_key: feature }),
    sb.rpc('graph_feature_readiness', { p_tenant: tenant, p_product: product, p_feature_key: feature }),
    sb.rpc('graph_backlog', { p_tenant: tenant, p_product: product }),
  ])
  if (detail.error) return Response.json({ error: detail.error.message }, { status: 500 })

  const upstream = await loadUpstream(sb, feature, detail.data)

  return Response.json({
    tenant, product, feature,
    detail: detail.data,
    readiness: readiness.data,
    backlog: backlog.data,
    upstream,
  })
}

/**
 * Upstream lifecycle artifacts for a feature:
 *   - codebase_context (CCA): the IS-state artifact this feature was scoped against, linked via the
 *     BA scope artifact's scoped_against.codebase_context_artifact_id (fallback: latest for product).
 *   - clarification (PCA): linked via feature.node_attributes.clarification_brief_artifact_id when present.
 *     Returns null when no brief is attached (the feature was scoped from a raw intent).
 */
async function loadUpstream(
  sb: ReturnType<typeof createServiceRoleClient>,
  feature: string,
  detail: any,
) {
  // The BA scope artifact records the exact CCA artifact it consumed.
  const scopeRes = await sb
    .from('agent_outputs')
    .select('content, created_at')
    .eq('output_type', 'product_graph_scope')
    .filter('content->>feature_key', 'eq', feature)
    .order('created_at', { ascending: false })
    .limit(1)
  const scope = scopeRes.data?.[0]?.content as any | undefined
  const ccaId: string | undefined = scope?.scoped_against?.codebase_context_artifact_id

  let codebase_context: any = null
  if (ccaId) {
    const ccaRes = await sb.from('agent_outputs').select('content, created_at').eq('id', ccaId).limit(1)
    const c = ccaRes.data?.[0]?.content as any | undefined
    if (c) {
      codebase_context = {
        artifact_id: ccaId,
        commit_sha: c.commit_sha,
        generated_at: c.generated_at,
        counts: {
          entities: (c.entities ?? []).length,
          actors: (c.actors ?? []).length,
          capabilities: (c.capabilities ?? []).length,
          domain_signals: (c.domain_signals ?? []).length,
        },
        concept_resolution: (c.concept_resolution ?? []).map((r: any) => ({
          requested_noun: r.requested_noun, exists: r.exists, cbc_ids: r.cbc_ids ?? [], note: r.note ?? '',
        })),
        domain_signals: (c.domain_signals ?? []).map((s: any) => ({
          signal: s.signal, implication_hint: s.implication_hint, confidence: s.confidence,
        })),
        actors: (c.actors ?? []).map((a: any) => ({ name: a.name, exists: a.exists })),
      }
    }
  }

  // PCA clarification brief, if one is ever linked to this feature.
  let clarification: any = null
  const clarId: string | undefined = detail?.feature?.node_attributes?.clarification_brief_artifact_id
  if (clarId) {
    const clRes = await sb.from('agent_outputs').select('content, created_at').eq('id', clarId).limit(1)
    const cl = clRes.data?.[0]?.content as any | undefined
    if (cl) clarification = { artifact_id: clarId, ...cl }
  }

  return { clarification, codebase_context }
}
