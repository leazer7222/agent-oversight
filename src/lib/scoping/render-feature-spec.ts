/**
 * Feature Spec renderer (P2, step 3).
 *
 * Pure function: transitive feature subgraph (from public.graph_feature_graph) -> markdown.
 * Every section is a node query. An empty section renders "_None._", never free prose - so orphan
 * prose is impossible by construction. The graph is the source of truth; this is a projection.
 *
 * Read-time for dashboard preview; the same output is frozen into the Gate A snapshot (step 4).
 */

type Node = Record<string, any>
type Edge = { edge_type: string; src: string; dst: string; edge_attributes?: Record<string, any> }
export type FeatureGraph = { feature: Node; nodes: Node[]; edges: Edge[] }

function bullet(lines: string[]): string {
  return lines.length ? lines.join('\n') : '_None._'
}

export function renderFeatureSpec(g: FeatureGraph): string {
  const feature = g.feature || {}
  const nodes = g.nodes || []
  const edges = g.edges || []
  const fa = feature.node_attributes || {}

  const ofType = (t: string) => nodes.filter((n) => n.node_type === t)
  const concepts = ofType('concept')
  const decisions = ofType('decision')
  const rules = ofType('rule')
  const attributes = ofType('attribute')
  const questions = ofType('question')
  const actors = concepts.filter((c) => c.kind === 'actor')
  const entities = concepts.filter((c) => c.kind !== 'actor')

  const out = (key: string, type: string) =>
    edges.filter((e) => e.src === key && e.edge_type === type).map((e) => e.dst)
  const titleOf = (key: string) => nodes.find((n) => n.node_key === key)?.title ?? key
  const accepted = (n: Node) => n.status === 'accepted'

  const L: string[] = []
  const H = (s: string) => L.push(`\n## ${s}\n`)

  // 1. Header + snapshot metadata
  L.push(`# Feature Spec: ${feature.title ?? feature.node_key ?? '(unknown)'}`)
  L.push('')
  L.push(`- Feature: \`${feature.node_key}\`  |  Status: \`${feature.status}\``)
  L.push(`- Scoped against commit: \`${(fa.scoped_against_commit ?? '-').toString().slice(0, 12)}\``)
  if (fa.codebase_context_artifact_id) L.push(`- Codebase context: \`${fa.codebase_context_artifact_id}\``)

  // 2. Problem / intent
  H('Problem')
  L.push(feature.title ?? '_None._')

  // 3. Actors
  H('Actors')
  L.push(bullet(actors.map((a) => `- **${a.title}** (\`${a.node_key}\`)`)))

  // 4. Scope - in / out (accepted vs rejected decisions)
  H('In scope')
  L.push(bullet(decisions.filter(accepted).map((d) => `- ${d.title} (\`${d.node_key}\`)`)))
  H('Out of scope')
  L.push(bullet(decisions.filter((d) => d.status === 'rejected').map((d) => `- ${d.title} (\`${d.node_key}\`)`)))

  // 5. Concepts & entities
  H('Concepts and entities')
  L.push(bullet(entities.map((c) => {
    const maps = Array.isArray(c.maps_to_codebase) && c.maps_to_codebase.length
      ? ` -> ${c.maps_to_codebase.join(', ')}` : ' (net-new)'
    return `- **${c.title}** (\`${c.node_key}\`, ${c.kind ?? 'entity'})${maps}`
  })))

  // 6. Codebase reconciliation
  H('Codebase reconciliation')
  L.push(bullet(concepts.map((c) => {
    const exists = Array.isArray(c.maps_to_codebase) && c.maps_to_codebase.length
    return `- ${c.title}: ${exists ? `exists -> ${c.maps_to_codebase.join(', ')}` : 'NET-NEW'}`
  })))

  // 7. Key decisions
  H('Key decisions')
  L.push(bullet(decisions.map((d) => {
    const da = d.node_attributes || {}
    const cites = out(d.node_key, 'references').map(titleOf)
    const parts = [`- **${d.title}** (\`${d.node_key}\`, ${d.status})`]
    if (da.rationale) parts.push(`  - Rationale: ${da.rationale}`)
    if (cites.length) parts.push(`  - References: ${cites.join(', ')}`)
    return parts.join('\n')
  })))

  // 8. Functional requirements / Rules
  H('Functional requirements (Rules)')
  L.push(bullet(rules.map((r) => {
    const ra = r.node_attributes || {}
    const cites = out(r.node_key, 'references').map(titleOf)
    const nf = (ra.normative_force ?? 'must').toUpperCase()
    return `- [\`${r.node_key}\`, ${r.status}] **${nf}**: ${ra.statement ?? r.title}`
      + (cites.length ? `  _(cites: ${cites.join(', ')})_` : '')
  })))

  // 9. Data / Attribute specification (grouped by owning concept)
  H('Data specification (Attributes)')
  if (!attributes.length) {
    L.push('_None._')
  } else {
    const ownerOf = (attrKey: string) =>
      edges.find((e) => e.edge_type === 'owns' && e.dst === attrKey)?.src
    const groups = new Map<string, Node[]>()
    for (const a of attributes) {
      const owner = ownerOf(a.node_key) ?? '(unowned)'
      groups.set(owner, [...(groups.get(owner) ?? []), a])
    }
    for (const [owner, attrs] of groups) {
      L.push(`- **${titleOf(owner)}**`)
      for (const a of attrs) {
        const aa = a.node_attributes || {}
        const meta = [aa.data_type, aa.required ? 'required' : null].filter(Boolean).join(', ')
        L.push(`  - ${a.title}${meta ? ` (${meta})` : ''} (\`${a.node_key}\`, ${a.status})`)
      }
    }
  }

  // 10. Acceptance criteria (derived from Rules + authored)
  H('Acceptance criteria')
  const acLines: string[] = []
  for (const r of rules) {
    const ra = r.node_attributes || {}
    const authored = Array.isArray(ra.acceptance_criteria) ? ra.acceptance_criteria : []
    if (authored.length) {
      authored.forEach((ac: any, i: number) =>
        acLines.push(`- \`AC-${r.node_key}-${i + 1}\`: GIVEN ${ac.given ?? '-'} WHEN ${ac.when ?? '-'} THEN ${ac.then ?? '-'}`))
    } else {
      acLines.push(`- \`AC-${r.node_key}-1\` (derived): the system enforces - ${ra.statement ?? r.title}`)
    }
  }
  L.push(bullet(acLines))

  // 11. Open questions
  H('Open questions')
  L.push(bullet(questions.filter((q) => q.status === 'open').map((q) =>
    `- ${q.blocking ? '[BLOCKING] ' : ''}${q.title} (\`${q.node_key}\`, divergence: ${q.divergence ?? '-'})`)))

  // 12. Assumptions / notes
  H('Assumptions and notes')
  L.push(bullet((Array.isArray(fa.notes) ? fa.notes : []).map((n: string) => `- ${n}`)))

  // Footer: node counts + traceability
  L.push('\n---')
  L.push(`_Rendered from graph: ${concepts.length} concepts, ${decisions.length} decisions, `
    + `${rules.length} rules, ${attributes.length} attributes, ${questions.length} questions._`)

  return L.join('\n') + '\n'
}
