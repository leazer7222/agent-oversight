import type { NextRequest } from 'next/server'
import { createHash } from 'node:crypto'
import { createServiceRoleClient } from '@/lib/supabase/server'
import { renderFeatureSpec } from '@/lib/scoping/render-feature-spec'

export const runtime = 'nodejs'

async function resolveTenant(sb: ReturnType<typeof createServiceRoleClient>, name: string) {
  const { data } = await sb.from('companies').select('id').eq('name', name)
  return data && data.length === 1 ? (data[0] as { id: string }).id : null
}

/**
 * POST /api/scoping/[feature]/gate-a
 * Body: { ratified_by, pm_layer?, product?, tenant? }
 *
 * Approves Gate A: validates internal graph consistency (graph_gate_a_readiness, H1-H7), then freezes
 * an immutable gate_a_feature_spec snapshot into agent_outputs (manifest of node UUIDs + content hash +
 * rendered markdown + provenance + human PM layer), supersedes any prior snapshot, and flips the
 * feature to 'ready'. The graph stays the source of truth; this is a pinned, auditable baseline.
 *
 * Option B: self-contained in agent_outputs (no feature_lifecycle spine yet).
 */
export async function POST(req: NextRequest, { params }: { params: Promise<{ feature: string }> }) {
  const { feature } = await params
  const body = await req.json().catch(() => ({}))
  const product = body.product ?? 'reformai-product'
  const tenantName = body.tenant ?? 'ReformAI'
  const ratifiedBy = body.ratified_by
  if (!ratifiedBy) return Response.json({ error: 'ratified_by is required (D3)' }, { status: 400 })

  const sb = createServiceRoleClient()
  const tenant = await resolveTenant(sb, tenantName)
  if (!tenant) return Response.json({ error: `tenant '${tenantName}' not resolved` }, { status: 400 })

  // 1. Validate (hard failures block).
  const readyRes = await sb.rpc('graph_gate_a_readiness', {
    p_tenant: tenant, p_product: product, p_feature_key: feature })
  if (readyRes.error) return Response.json({ error: readyRes.error.message }, { status: 500 })
  const readiness = readyRes.data as { status: string; hard_failures: string[]; warnings: string[] }
  if (readiness.status === 'blocked') {
    return Response.json({ error: 'Gate A blocked', hard_failures: readiness.hard_failures }, { status: 400 })
  }

  // 2. Pull the subgraph; render the spec.
  const graphRes = await sb.rpc('graph_feature_graph', {
    p_tenant: tenant, p_product: product, p_feature_key: feature })
  if (graphRes.error) return Response.json({ error: graphRes.error.message }, { status: 500 })
  const g = graphRes.data as { feature: any; nodes: any[]; edges: any[] }
  const rendered = renderFeatureSpec(g)

  // 3. Manifest (node UUIDs pin the snapshot; accepted nodes are already frozen by trigger) + hash.
  const nodes = g.nodes ?? []
  const manifestCore = {
    node_keys: nodes.map((n) => n.node_key).sort(),
    node_uuids: nodes.map((n) => n.id).sort(),
    edges: (g.edges ?? []).map((e) => `${e.edge_type}:${e.src}->${e.dst}`).sort(),
  }
  const content_hash = createHash('sha256').update(JSON.stringify(manifestCore)).digest('hex')

  // 4. Provenance: link the CCA artifact this feature was scoped against.
  const fa = g.feature?.node_attributes ?? {}
  const scopeArt = await sb.from('agent_outputs').select('content')
    .eq('output_type', 'product_graph_scope').filter('content->>feature_key', 'eq', feature)
    .order('created_at', { ascending: false }).limit(1)
  const ccaId = (scopeArt.data?.[0]?.content as any)?.scoped_against?.codebase_context_artifact_id ?? null

  const provenance = {
    codebase_context_artifact_id: ccaId,
    commit_sha: fa.scoped_against_commit ?? null,
    accepted_decisions: nodes.filter((n) => n.node_type === 'decision' && n.status === 'accepted').map((n) => n.node_key),
    included_rules: nodes.filter((n) => n.node_type === 'rule').map((n) => n.node_key),
    included_attributes: nodes.filter((n) => n.node_type === 'attribute').map((n) => n.node_key),
  }

  // 5. Supersede any prior snapshot for this feature.
  const prior = await sb.from('gate_a_snapshots').select('id')
    .eq('product_key', product).eq('feature_key', feature)
    .order('created_at', { ascending: false }).limit(1)
  const supersedes = prior.data?.[0]?.id ?? null

  // 6. Write the immutable snapshot (dedicated append-only table; no agent-run coupling).
  const ins = await sb.from('gate_a_snapshots').insert({
    tenant_id: tenant,
    product_key: product,
    feature_key: feature,
    content_hash,
    manifest: manifestCore,
    rendered_markdown: rendered,
    provenance,
    pm_layer: body.pm_layer ?? {},
    approved_by: ratifiedBy,
    supersedes,
  }).select('id')
  if (ins.error) return Response.json({ error: ins.error.message }, { status: 500 })
  const snapshotId = (ins.data?.[0] as { id: string })?.id

  // 7. Flip the feature to ready (feature is not frozen in 'scoping').
  await sb.rpc('graph_ratify_node', { p_tenant: tenant, p_product: product,
    p_node_key: feature, p_new_status: 'ready', p_ratified_by: ratifiedBy })

  return Response.json({
    ok: true, snapshot_id: snapshotId, content_hash, supersedes,
    status: readiness.status, warnings: readiness.warnings,
  })
}
