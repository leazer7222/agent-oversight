'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

const SOURCE_TYPES = [
  ['paragraph', 'Paragraph / description'],
  ['idea', 'One-line idea'],
  ['prd', 'PRD'],
  ['jira_text', 'Jira ticket text'],
  ['customer_feedback', 'Customer feedback'],
  ['bug_enhancement', 'Bug / enhancement request'],
  ['text_workflow', 'Workflow (described in text)'],
] as const

type Job = {
  id: string; status: string; decision: string | null; pass: string; product_key: string
  brief_id: string | null; assessment_id: string | null; parent_job_id: string | null
  intake: { source_type: string; text: string }[] | null; created_at: string
}
type Detail = { job: Job; assessment: any; brief: any }

const TERMINAL = new Set(['done', 'clarify', 'blocked', 'error'])

function statusVariant(s: string): 'default' | 'secondary' | 'outline' {
  if (s === 'done') return 'default'
  if (s === 'running' || s === 'queued') return 'secondary'
  return 'outline'
}

function Bar({ label, value }: { label: string; value: number }) {
  const pct = Math.round((value ?? 0) * 100)
  return (
    <div>
      <div className="flex justify-between text-xs text-zinc-400"><span>{label}</span><span>{pct}%</span></div>
      <div className="mt-1 h-1.5 w-full rounded bg-zinc-800">
        <div className="h-1.5 rounded bg-zinc-400" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export function IntakeConsole() {
  const [text, setText] = useState('')
  const [sourceType, setSourceType] = useState('paragraph')
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [answering, setAnswering] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const refreshJobs = useCallback(async () => {
    const r = await fetch('/api/agile/jobs', { cache: 'no-store' })
    if (r.ok) setJobs((await r.json()).jobs ?? [])
  }, [])

  const loadDetail = useCallback(async (id: string) => {
    const r = await fetch(`/api/agile/jobs/${id}`, { cache: 'no-store' })
    if (!r.ok) return
    const d: Detail = await r.json()
    setDetail(d)
    if (!TERMINAL.has(d.job.status)) {
      timer.current = setTimeout(() => loadDetail(id), 3000)
    } else {
      refreshJobs()
    }
  }, [refreshJobs])

  useEffect(() => { refreshJobs() }, [refreshJobs])
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current)
    setAnswers({})
    if (activeId) loadDetail(activeId)
    return () => { if (timer.current) clearTimeout(timer.current) }
  }, [activeId, loadDetail])

  async function submit() {
    setErr(null); setSubmitting(true)
    try {
      const r = await fetch('/api/agile/intake', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, source_type: sourceType }),
      })
      const j = await r.json()
      if (!r.ok) { setErr(j.error ?? 'submit failed'); return }
      setText(''); setActiveId(j.job_id)
    } finally { setSubmitting(false) }
  }

  async function submitAnswers(questions: string[]) {
    if (!activeId) return
    setAnswering(true); setErr(null)
    try {
      const payload = questions.map((q, i) => ({ question: q, answer: answers[i] ?? '' }))
      const r = await fetch(`/api/agile/jobs/${activeId}/answer`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers: payload }),
      })
      const j = await r.json()
      if (!r.ok) { setErr(j.error ?? 'answer failed'); return }
      setActiveId(j.job_id)
    } finally { setAnswering(false) }
  }

  const job = detail?.job
  const a = detail?.assessment
  const brief = detail?.brief
  const questions: string[] = a?.draft_brief?.open_questions ?? []

  return (
    <div className="grid grid-cols-3 gap-4">
      {/* Left: submit + history */}
      <div className="col-span-1 space-y-4">
        <Card>
          <CardHeader><CardTitle className="text-sm">New intake</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <select value={sourceType} onChange={(e) => setSourceType(e.target.value)}
              className="w-full rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200">
              {SOURCE_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={8}
              placeholder="Paste the idea, paragraph, PRD, ticket, feedback, or bug..."
              className="w-full rounded-md border border-zinc-800 bg-zinc-900 p-2 text-sm text-zinc-200 placeholder:text-zinc-600" />
            <Button onClick={submit} disabled={submitting || !text.trim()} className="w-full">
              {submitting ? 'Submitting...' : 'Submit intake'}
            </Button>
            {err && <p className="text-xs text-red-400">{err}</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-sm">Recent</CardTitle></CardHeader>
          <CardContent className="p-0">
            <ul className="divide-y divide-zinc-800">
              {jobs.map((jb) => (
                <li key={jb.id}>
                  <button onClick={() => setActiveId(jb.id)}
                    className={`flex w-full items-center justify-between gap-2 px-4 py-2 text-left hover:bg-zinc-800/50 ${activeId === jb.id ? 'bg-zinc-800/60' : ''}`}>
                    <span className="truncate text-xs text-zinc-300">
                      {jb.intake?.[0]?.text?.slice(0, 48) ?? jb.id.slice(0, 8)}
                    </span>
                    <Badge variant={statusVariant(jb.status)} className="shrink-0">
                      {jb.pass === 'b' ? 'B:' : ''}{jb.status}
                    </Badge>
                  </button>
                </li>
              ))}
              {jobs.length === 0 && <li className="px-4 py-3 text-xs text-zinc-500">No intake yet.</li>}
            </ul>
          </CardContent>
        </Card>
      </div>

      {/* Right: live job */}
      <div className="col-span-2 space-y-4">
        {!job && (
          <Card><CardContent className="py-10 text-center text-sm text-zinc-500">
            Submit an intake or pick one from Recent to see the Intake Assessment and Brief.
          </CardContent></Card>
        )}

        {job && (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-sm">Job {job.id.slice(0, 8)} · pass {job.pass.toUpperCase()}</CardTitle>
              <Badge variant={statusVariant(job.status)}>{job.status}</Badge>
            </CardHeader>
            <CardContent className="text-sm text-zinc-300">
              {!TERMINAL.has(job.status) && (
                <p className="text-zinc-400">Worker is processing... (is <code>worker.py</code> running?)</p>
              )}

              {/* Intake Assessment */}
              {a && (
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xs uppercase tracking-wide text-zinc-500">Decision</span>
                    <Badge variant="outline">{a.decision}</Badge>
                  </div>
                  <p className="text-zinc-300">{a.rationale}</p>
                  {a.scores && (
                    <div className="grid grid-cols-2 gap-3">
                      <Bar label="Completeness" value={a.scores.completeness} />
                      <Bar label="Fidelity" value={a.scores.fidelity} />
                      <Bar label="Ambiguity" value={a.scores.ambiguity} />
                      <Bar label="Context confidence" value={a.scores.context_confidence} />
                    </div>
                  )}
                  {Array.isArray(a.field_coverage) && a.field_coverage.length > 0 && (
                    <div className="rounded-md border border-zinc-800">
                      {a.field_coverage.map((f: any, i: number) => (
                        <div key={i} className="flex items-center justify-between border-b border-zinc-800 px-3 py-1.5 text-xs last:border-0">
                          <span className="text-zinc-400">{f.field}</span>
                          <span className={f.covered ? 'text-emerald-400' : 'text-amber-400'}>
                            {f.covered ? 'covered' : 'gap'} · {Math.round((f.confidence ?? 0) * 100)}%
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Clarify: answer the blocking questions */}
        {job && job.status === 'clarify' && questions.length > 0 && (
          <Card>
            <CardHeader><CardTitle className="text-sm">Clarification needed ({questions.length})</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {questions.map((q, i) => (
                <div key={i} className="space-y-1">
                  <p className="text-sm text-zinc-200">{i + 1}. {q}</p>
                  <textarea rows={2} value={answers[i] ?? ''} onChange={(e) => setAnswers({ ...answers, [i]: e.target.value })}
                    className="w-full rounded-md border border-zinc-800 bg-zinc-900 p-2 text-sm text-zinc-200" />
                </div>
              ))}
              <Button onClick={() => submitAnswers(questions)} disabled={answering} className="w-full">
                {answering ? 'Finalizing...' : 'Submit answers (finalize)'}
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Final brief + handoff */}
        {job && job.status === 'done' && brief && (
          <Card>
            <CardHeader><CardTitle className="text-sm">Clarification Brief</CardTitle></CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div><span className="text-zinc-500">Restated goal:</span> <span className="text-zinc-200">{brief.restated_goal}</span></div>
              <div><span className="text-zinc-500">Problem:</span> <span className="text-zinc-300">{brief.problem_statement}</span></div>
              <div><span className="text-zinc-500">Target user:</span> <span className="text-zinc-300">{brief.target_user}</span></div>
              {brief.handoff && (
                <div className="rounded-md border border-emerald-900/50 bg-emerald-950/20 p-3">
                  <div className="text-xs uppercase tracking-wide text-emerald-400">Handoff to CCA / BA</div>
                  <div className="mt-1 text-zinc-200">{brief.handoff.feature_intent}</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {(brief.handoff.concepts_to_check ?? []).map((c: string) => (
                      <Badge key={c} variant="secondary">{c}</Badge>
                    ))}
                  </div>
                  {job.brief_id && (
                    <div className="mt-2 font-mono text-xs text-zinc-500">
                      clarification_brief_artifact_id: {job.brief_id}
                    </div>
                  )}
                </div>
              )}
              <Link href="/dashboard/scoping" className="inline-block text-xs text-zinc-400 underline hover:text-zinc-200">
                Run CCA then BA, then view it under Scoping -&gt;
              </Link>
            </CardContent>
          </Card>
        )}

        {job && job.status === 'blocked' && (
          <Card><CardContent className="py-6 text-sm text-amber-400">
            Intake too thin to scope. {a?.rationale}
          </CardContent></Card>
        )}
      </div>
    </div>
  )
}
