'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

type Node = Record<string, any>
type Edge = { edge_type: string; src: string; dst: string; edge_attributes?: Record<string, any> }
type Upstream = {
  clarification: Record<string, any> | null
  codebase_context: {
    artifact_id: string
    commit_sha: string
    generated_at?: string
    counts: { entities: number; actors: number; capabilities: number; domain_signals: number }
    concept_resolution: { requested_noun: string; exists: boolean; cbc_ids: string[]; note?: string }[]
    domain_signals: { signal: string; implication_hint: string; confidence: string }[]
    actors: { name: string; exists: boolean }[]
  } | null
}

type Props = {
  feature: string
  detail: { feature: Node; nodes: Node[]; edges: Edge[] }
  readiness: Record<string, any>
  upstream?: Upstream
}

function divergenceBadge(d?: string) {
  if (d === 'high') return <Badge variant="destructive">high divergence</Badge>
  if (d === 'medium') return <Badge variant="secondary">medium</Badge>
  return <Badge variant="outline">low</Badge>
}

function statusBadge(s: string) {
  const v: Record<string, 'default' | 'secondary' | 'outline' | 'destructive'> = {
    accepted: 'default', answered: 'default', proposed: 'secondary',
    open: 'outline', rejected: 'destructive', superseded: 'outline', deprecated: 'outline',
  }
  return <Badge variant={v[s] ?? 'outline'}>{s}</Badge>
}

function QuestionAnswer({
  feature, q, concepts, onDone,
}: {
  feature: string
  q: Node
  concepts: Node[]
  onDone: () => void
}) {
  const [open, setOpen] = useState(false)
  const [statement, setStatement] = useState('')
  const [rationale, setRationale] = useState('')
  const [refs, setRefs] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  function toggleRef(k: string) {
    setRefs((r) => (r.includes(k) ? r.filter((x) => x !== k) : [...r, k]))
  }

  async function submit() {
    setBusy(true); setErr('')
    const res = await fetch(`/api/scoping/${feature}/answer`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question_key: q.node_key, statement, rationale, references: refs }),
    })
    const j = await res.json().catch(() => ({}))
    setBusy(false)
    if (!res.ok) { setErr(j.error || 'failed'); return }
    onDone()
  }

  if (!open) {
    return <Button variant="outline" size="sm" onClick={() => setOpen(true)}>Answer -&gt; create Decision</Button>
  }
  return (
    <div className="mt-3 space-y-2 rounded-md border border-zinc-800 p-3">
      <textarea
        className="w-full rounded-md bg-zinc-900 border border-zinc-700 p-2 text-sm text-zinc-100"
        rows={2} placeholder="Decision statement (the ratified choice)"
        value={statement} onChange={(e) => setStatement(e.target.value)}
      />
      <input
        className="w-full rounded-md bg-zinc-900 border border-zinc-700 p-2 text-sm text-zinc-100"
        placeholder="Rationale (why this choice)"
        value={rationale} onChange={(e) => setRationale(e.target.value)}
      />
      <div className="text-xs text-zinc-400">References (cite at least one Concept):</div>
      <div className="flex flex-wrap gap-2">
        {concepts.map((c) => (
          <label key={c.node_key} className={`cursor-pointer rounded-md border px-2 py-1 text-xs ${
            refs.includes(c.node_key) ? 'border-emerald-600 bg-emerald-950 text-emerald-200' : 'border-zinc-700 text-zinc-300'
          }`}>
            <input type="checkbox" className="hidden" checked={refs.includes(c.node_key)}
                   onChange={() => toggleRef(c.node_key)} />
            {c.title}
          </label>
        ))}
      </div>
      {err && <div className="text-xs text-red-400">{err}</div>}
      <div className="flex gap-2">
        <Button size="sm" disabled={busy || !statement || refs.length === 0} onClick={submit}>
          {busy ? 'Saving...' : 'Save proposed Decision'}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
      </div>
    </div>
  )
}

export function ScopingReview({ feature, detail, readiness, upstream }: Props) {
  const router = useRouter()
  const refresh = () => router.refresh()

  const nodes = detail.nodes || []
  const edges = detail.edges || []
  const feat = detail.feature || {}
  const concepts = nodes.filter((n) => n.node_type === 'concept')
  const questions = nodes.filter((n) => n.node_type === 'question')
  const decisions = nodes.filter((n) => n.node_type === 'decision')
  const ready = !!readiness?.scope_ready
  const notes: string[] = feat?.node_attributes?.notes || []

  async function ratify(node_key: string, new_status: string) {
    await fetch(`/api/scoping/${feature}/ratify`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_key, new_status }),
    })
    refresh()
  }

  const resolvesFor = (decKey: string) =>
    edges.filter((e) => e.edge_type === 'resolves' && e.src === decKey).map((e) => e.dst)
  const refsFor = (decKey: string) =>
    edges.filter((e) => e.edge_type === 'references' && e.src === decKey).map((e) => e.dst)

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">{feat.title}</h1>
          <div className="text-xs text-zinc-500 font-mono">
            {feat.node_key} &middot; scoped against {feat?.node_attributes?.scoped_against_commit?.slice(0, 12) ?? '-'}
          </div>
        </div>
        {statusBadge(feat.status ?? 'scoping')}
      </div>

      {/* Readiness banner */}
      <div className={`rounded-md border p-3 text-sm ${
        ready ? 'border-emerald-700 bg-emerald-950/50 text-emerald-200'
              : 'border-amber-700 bg-amber-950/40 text-amber-200'
      }`}>
        {ready
          ? 'SCOPE READY - all blocking forks resolved. The brief below is a live projection of the graph.'
          : `NOT SCOPE READY - ${readiness?.gate_open_blocking_questions ?? 0} blocking question(s) open, `
            + `${readiness?.gate_open_high_divergence ?? 0} high-divergence. The agent withholds the final brief until these are decided.`}
        <span className="ml-2 text-xs opacity-70">(contradiction check: {String(readiness?.gate_contradiction_check ?? 'deferred_v1')})</span>
      </div>

      {/* Upstream lifecycle artifacts */}
      <div className="grid grid-cols-2 gap-4">
        {/* Product Clarification Agent */}
        <Card>
          <CardHeader><CardTitle className="text-sm">Clarification Brief (PCA)</CardTitle></CardHeader>
          <CardContent className="text-sm">
            {upstream?.clarification ? (
              <div className="space-y-1 text-zinc-300">
                <div className="text-xs font-mono text-zinc-500">{upstream.clarification.artifact_id}</div>
                {upstream.clarification.problem_statement && (
                  <div><span className="text-zinc-400">Problem:</span> {upstream.clarification.problem_statement}</div>
                )}
              </div>
            ) : (
              <div className="text-zinc-500">
                No clarification brief linked. This feature was scoped from a raw intent, not a Product
                Clarification Agent brief. (Link via <code>feature.node_attributes.clarification_brief_artifact_id</code>.)
              </div>
            )}
          </CardContent>
        </Card>

        {/* Codebase Context Agent */}
        <Card>
          <CardHeader><CardTitle className="text-sm">Codebase Context (CCA)</CardTitle></CardHeader>
          <CardContent className="text-sm">
            {upstream?.codebase_context ? (
              <div className="space-y-2 text-zinc-300">
                <div className="text-xs font-mono text-zinc-500">
                  @ {upstream.codebase_context.commit_sha?.slice(0, 12)} &middot; {upstream.codebase_context.artifact_id}
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  <Badge variant="outline">{upstream.codebase_context.counts.entities} entities</Badge>
                  <Badge variant="outline">{upstream.codebase_context.counts.actors} actors</Badge>
                  <Badge variant="outline">{upstream.codebase_context.counts.capabilities} capabilities</Badge>
                  <Badge variant="outline">{upstream.codebase_context.counts.domain_signals} signals</Badge>
                </div>
                <div>
                  <div className="text-zinc-400 text-xs mb-1">Concept resolution</div>
                  <ul className="space-y-0.5">
                    {upstream.codebase_context.concept_resolution.map((r) => (
                      <li key={r.requested_noun} className="text-xs">
                        <span className="text-zinc-200">{r.requested_noun}</span>{' '}
                        {r.exists
                          ? <span className="text-sky-300">{r.cbc_ids.join(', ') || 'exists'}</span>
                          : <span className="text-amber-300">NEW</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            ) : (
              <div className="text-zinc-500">No codebase context linked.</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* CCA domain signals (full width) */}
      {upstream?.codebase_context && upstream.codebase_context.domain_signals.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Codebase Domain Signals</CardTitle></CardHeader>
          <CardContent>
            <ul className="list-disc pl-5 space-y-1 text-sm text-zinc-300">
              {upstream.codebase_context.domain_signals.map((s, i) => (
                <li key={i}>
                  <span className="text-zinc-200">{s.signal}</span>{' '}
                  <span className="text-zinc-500">({s.confidence})</span> &rarr; {s.implication_hint}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Questions */}
      <Card>
        <CardHeader><CardTitle>Open Questions ({questions.filter((q) => q.status === 'open').length})</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {questions.length === 0 && <div className="text-sm text-zinc-500">No questions.</div>}
          {questions.map((q) => (
            <div key={q.node_key} className="border-b border-zinc-800 pb-4 last:border-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-mono text-zinc-500">{q.node_key}</span>
                {q.blocking && <Badge variant="destructive">blocking</Badge>}
                {divergenceBadge(q.divergence)}
                {statusBadge(q.status)}
              </div>
              <div className="text-sm text-zinc-200">{q.title}</div>
              {q.status === 'open'
                ? <QuestionAnswer feature={feature} q={q} concepts={concepts} onDone={refresh} />
                : <div className="mt-1 text-xs text-emerald-400">answered</div>}
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Concepts */}
      <Card>
        <CardHeader><CardTitle>Concepts ({concepts.length})</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {concepts.map((c) => (
            <div key={c.node_key} className="flex items-start justify-between border-b border-zinc-800 pb-3 last:border-0">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-zinc-100">{c.title}</span>
                  <Badge variant="outline">{c.kind}</Badge>
                  {statusBadge(c.status)}
                </div>
                <div className="mt-1 text-xs">
                  {Array.isArray(c.maps_to_codebase) && c.maps_to_codebase.length > 0
                    ? <span className="text-sky-300">in code: {c.maps_to_codebase.join(', ')}</span>
                    : <span className="text-zinc-500">net-new (no code identity)</span>}
                </div>
              </div>
              {c.status === 'proposed' && (
                <div className="flex gap-2">
                  <Button size="xs" onClick={() => ratify(c.node_key, 'accepted')}>Accept</Button>
                  <Button size="xs" variant="destructive" onClick={() => ratify(c.node_key, 'rejected')}>Reject</Button>
                </div>
              )}
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Decisions */}
      <Card>
        <CardHeader><CardTitle>Decisions ({decisions.length})</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {decisions.length === 0 && <div className="text-sm text-zinc-500">No decisions yet. Answer the questions above.</div>}
          {decisions.map((d) => (
            <div key={d.node_key} className="border-b border-zinc-800 pb-3 last:border-0">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-zinc-500">{d.node_key}</span>
                  {statusBadge(d.status)}
                </div>
                {d.status === 'proposed' && (
                  <div className="flex gap-2">
                    <Button size="xs" onClick={() => ratify(d.node_key, 'accepted')}>Accept</Button>
                    <Button size="xs" variant="destructive" onClick={() => ratify(d.node_key, 'rejected')}>Reject</Button>
                  </div>
                )}
              </div>
              <div className="text-sm text-zinc-200 mt-1">{d.title}</div>
              {d.node_attributes?.rationale && (
                <div className="text-xs text-zinc-400 mt-1">Rationale: {d.node_attributes.rationale}</div>
              )}
              <div className="text-xs text-zinc-500 mt-1">
                resolves {resolvesFor(d.node_key).join(', ') || '-'} &middot; references {refsFor(d.node_key).join(', ') || '-'}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Feature notes */}
      {notes.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Notes &amp; confirmed constraints</CardTitle></CardHeader>
          <CardContent>
            <ul className="list-disc pl-5 space-y-1 text-sm text-zinc-300">
              {notes.map((n, i) => <li key={i}>{n}</li>)}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Brief projection when ready */}
      {ready && (
        <Card>
          <CardHeader><CardTitle>Feature Scope Brief (live projection)</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm text-zinc-200">
            <div><span className="text-zinc-400">Problem:</span> {feat.title}</div>
            <div>
              <span className="text-zinc-400">Decisions:</span>
              <ul className="list-disc pl-5 mt-1">
                {decisions.filter((d) => d.status === 'accepted').map((d) => (
                  <li key={d.node_key}>{d.title} <span className="text-zinc-500">({d.node_key})</span></li>
                ))}
              </ul>
            </div>
            <div>
              <span className="text-zinc-400">Entities touched:</span>{' '}
              {concepts.map((c) => c.title).join(', ')}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
