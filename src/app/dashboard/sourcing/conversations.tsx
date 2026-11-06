'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { X, ArrowUpRight, ArrowDownLeft, AlertTriangle, Inbox, Send, CheckCircle2 } from 'lucide-react'
import { cn, formatDateTime } from '@/lib/utils'
import { type Conversation, type Message, intentLabel, actionLabel, excerpt, relTime } from './model'
import { Pill, SimulatedPill, Empty } from './workspace'

const SEND_STATUS: Record<string, { label: string; tone: 'zinc' | 'amber' | 'emerald' | 'rose' | 'sky' }> = {
  draft: { label: 'Draft - not sent', tone: 'zinc' },
  approved: { label: 'Approved - not sent yet', tone: 'sky' },
  sending: { label: 'Sending...', tone: 'amber' },
  sent: { label: 'Sent', tone: 'emerald' },
  failed: { label: 'Send failed', tone: 'rose' },
}

async function post(path: string, body: Record<string, unknown>): Promise<{ ok: boolean; detail: string }> {
  try {
    const res = await fetch(path, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body),
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) return { ok: false, detail: json.error ?? `HTTP ${res.status}` }
    return { ok: true, detail: json.job_id ? `queued (job ${String(json.job_id).slice(0, 8)})` : 'done' }
  } catch (e) {
    return { ok: false, detail: e instanceof Error ? e.message : String(e) }
  }
}

/** Approve a draft (binds your identity to its exact bytes) and queue it for the
 *  worker. Nothing is sent from the browser: the worker still has to pass the
 *  database chokepoint and the recipient allow-list. */
export function DraftActions({ message, company }: { message: Message; company: string }) {
  const router = useRouter()
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const run = async (label: string, path: string, body: Record<string, unknown>) => {
    setBusy(label); setNote(null)
    const r = await post(path, { ...body, company: company || undefined })
    setNote(r.ok ? `${label}: ${r.detail}` : `${label} failed: ${r.detail}`)
    setBusy(null)
    if (r.ok) router.refresh()
  }
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-zinc-800/80 pt-2 text-xs">
      {message.status === 'draft' && (
        <button type="button" disabled={busy !== null}
          onClick={() => run('Approve', '/api/sourcing/approvals', { subject_type: 'message', subject_id: message.message_id, decision: 'approved' })}
          className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50">
          <CheckCircle2 className="size-4" /> Step 1: Approve this draft
        </button>
      )}
      {message.status === 'approved' && (
        <button type="button" disabled={busy !== null}
          onClick={() => run('Queue send', '/api/sourcing/jobs', { job_type: 'send_outreach', payload: { message_id: message.message_id } })}
          className="inline-flex items-center gap-1.5 rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50">
          <Send className="size-4" /> Step 2: Send it (test mode - goes to the allow-listed address)
        </button>
      )}
      {message.status === 'sent' && <span className="text-emerald-300">Sent. Reply from your inbox, then use "Check mailbox for replies".</span>}
      {busy && <span className="text-zinc-500">{busy}...</span>}
      {note && <span className={note.includes('failed') ? 'text-rose-300' : 'text-zinc-400'}>{note}</span>}
    </div>
  )
}

function MailboxActions({ company }: { company: string }) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const check = async () => {
    setBusy(true); setNote(null)
    const a = await post('/api/sourcing/jobs', { job_type: 'poll_inbox', payload: { source: 'gmail' }, company: company || undefined })
    const b = a.ok ? await post('/api/sourcing/jobs', { job_type: 'classify_reply', payload: {}, company: company || undefined }) : a
    setNote(a.ok && b.ok ? 'Queued: read the mailbox, then classify new replies. Runs on the worker\'s next pass.' : `Failed: ${a.detail} ${b.detail}`)
    setBusy(false)
    if (a.ok) router.refresh()
  }
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <button type="button" onClick={check} disabled={busy}
        className="inline-flex items-center gap-1 rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-zinc-200 hover:bg-zinc-800 disabled:opacity-50">
        <Inbox className="size-3.5" /> Check mailbox for replies
      </button>
      {note && <span className="text-zinc-400">{note}</span>}
    </div>
  )
}

export function ConversationsView({ conversations, selectedId, onSelect, onFacility, company }: {
  conversations: Conversation[]; selectedId: string | null; onSelect: (id: string | null) => void
  onFacility: (id: string) => void; company: string
}) {
  const selected = conversations.find((c) => c.thread.thread_id === selectedId) ?? null
  const anyReal = conversations.some((c) => c.messages.some((m) => m.direction === 'inbound' && !(m.subject ?? '').startsWith('[SIMULATED]')))
  return (
    <div className={cn('grid gap-4', 'lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]')}>
      <div className="min-w-0 space-y-2">
        <p className="text-sm text-zinc-400">Every facility we have drafted to, and what came back.{' '}
          {anyReal ? <span className="text-zinc-500">Simulated replies are marked.</span> : <span className="text-amber-300/90">All replies are simulated.</span>}
        </p>
        <MailboxActions company={company} />
        {conversations.length === 0 ? <Empty>No conversations yet. Drafts appear here once research finds a contact.</Empty> : (
          <ul className="space-y-2">
            {conversations.map((c) => {
              const active = c.thread.thread_id === selectedId
              const cl = c.thread.last_classification
              return (
                <li key={c.thread.thread_id}>
                  <button type="button" onClick={() => onSelect(active ? null : c.thread.thread_id)}
                    className={cn('w-full rounded-lg border p-3 text-left transition-colors',
                      active ? 'border-sky-800 bg-zinc-900' : 'border-zinc-800 bg-zinc-900/50 hover:bg-zinc-900/80')}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium text-zinc-200">{c.thread.facility_name}</div>
                        <div className="mt-0.5 text-xs text-zinc-500">
                          {c.thread.inbound_count > 0 ? intentLabel(c.thread.last_intent) : 'Draft prepared, no reply yet'}
                          {' - '}{relTime(c.thread.updated_at)}
                        </div>
                      </div>
                      {c.needsReview && c.thread.inbound_count > 0 && <Pill tone="amber">Review</Pill>}
                    </div>
                    {c.latest && (
                      <p className="mt-2 line-clamp-2 text-xs text-zinc-400">
                        <span className="text-zinc-600">{c.latest.direction === 'inbound' ? 'They: ' : 'Draft: '}</span>{excerpt(c.latest.body, 160)}
                      </p>
                    )}
                    {cl?.proposed_action && (
                      <div className="mt-2 text-xs text-zinc-300">{actionLabel(cl.proposed_action)}</div>
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {selected ? <ConversationDetail c={selected} onClose={() => onSelect(null)} onFacility={onFacility} company={company} /> : (
        <div className="hidden items-center justify-center rounded-lg border border-dashed border-zinc-800 text-sm text-zinc-500 lg:flex">
          Select a conversation to read it in full.
        </div>
      )}
    </div>
  )
}

function ConversationDetail({ c, onClose, onFacility, company }: { c: Conversation; onClose: () => void; onFacility: (id: string) => void; company: string }) {
  const cl = c.thread.last_classification ?? null
  const safety = cl?.safety ?? null
  return (
    <aside className="fixed inset-0 z-40 overflow-y-auto bg-zinc-950 p-4 lg:static lg:z-auto lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto lg:rounded-lg lg:border lg:border-zinc-800 lg:bg-zinc-900/50"
      role="dialog" aria-label={`Conversation with ${c.thread.facility_name}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="break-words text-base font-semibold text-zinc-100">{c.thread.facility_name}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
            <span className="truncate">{c.thread.subject}</span>
            <SimulatedPill />
            <button type="button" onClick={() => onFacility(c.thread.facility_id)} className="text-sky-300 hover:underline">Facility details</button>
          </div>
        </div>
        <button type="button" onClick={onClose} aria-label="Close conversation" className="rounded-md p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"><X className="size-4" /></button>
      </div>

      {cl && (
        <div className={cn('mt-4 rounded-md border p-3', safety?.requires_approval ? 'border-amber-800/70 bg-amber-950/20' : 'border-zinc-800 bg-zinc-950/40')}>
          <div className="flex flex-wrap items-center gap-2">
            {safety?.injection_suspected && <AlertTriangle className="size-4 text-amber-300" />}
            <span className="text-sm font-medium text-zinc-100">{intentLabel(c.thread.last_intent)}</span>
            <span className="text-zinc-600">-</span>
            <span className="text-sm text-zinc-300">{actionLabel(cl.proposed_action)}</span>
          </div>
          {cl.summary && <p className="mt-1 text-sm text-zinc-400">{cl.summary}</p>}
          {safety?.injection_suspected && (
            <p className="mt-2 text-sm text-amber-200">This message tried to give the system instructions. Nothing it asked for was done.</p>
          )}
          {cl.proposed_reply && !safety?.injection_suspected && (
            <div className="mt-3">
              <div className="text-xs text-zinc-500">Suggested reply (not sent)</div>
              <p className="mt-1 whitespace-pre-wrap rounded bg-zinc-950/60 px-3 py-2 text-sm text-zinc-300">{cl.proposed_reply}</p>
            </div>
          )}
          {cl.recommended_followup_at && (
            <p className="mt-2 text-xs text-zinc-500">Suggested follow-up: {formatDateTime(cl.recommended_followup_at)}</p>
          )}
          <details className="mt-3 text-xs text-zinc-500">
            <summary className="cursor-pointer select-none hover:text-zinc-300">Why the system decided this</summary>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-zinc-400">
              {(safety?.reasons ?? []).map((r: string, i: number) => <li key={i}>{r}</li>)}
              {(safety?.reasons ?? []).length === 0 && <li>No escalation rule fired.</li>}
            </ul>
            <pre className="mt-2 overflow-x-auto rounded bg-zinc-950/60 p-2 text-[11px] text-zinc-500">{JSON.stringify({
              intent: c.thread.last_intent, model_confidence: cl.model_confidence, topics: safety?.topics,
              injection_matches: cl.injection_matches, answered_questions: cl.answered_questions, classifier: cl.classifier,
            }, null, 2)}</pre>
          </details>
        </div>
      )}

      <ol className="mt-4 space-y-3">
        {c.messages.map((m) => {
          const inbound = m.direction === 'inbound'
          return (
            <li key={m.message_id} className={cn('rounded-lg border px-3 py-2', inbound ? 'border-amber-900/40 bg-amber-950/10' : 'border-zinc-800 bg-zinc-950/40')}>
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-500">
                <span className="flex items-center gap-1.5">
                  {inbound ? <ArrowDownLeft className="size-3.5 text-amber-300" /> : <ArrowUpRight className="size-3.5 text-sky-300" />}
                  {inbound ? 'Their reply' : m.status === 'sent' ? 'Our email' : 'Our draft'}
                  {inbound
                    ? ((m.subject ?? '').startsWith('[SIMULATED]') ? <SimulatedPill /> : <Pill tone="emerald">Real reply</Pill>)
                    : <Pill tone={(SEND_STATUS[m.status] ?? SEND_STATUS.draft).tone}>{(SEND_STATUS[m.status] ?? SEND_STATUS.draft).label}</Pill>}
                </span>
                <span>{formatDateTime(m.received_at ?? m.sent_at ?? m.created_at)}</span>
              </div>
              {m.subject && !inbound && <div className="mt-1 text-sm text-zinc-300">{m.subject}</div>}
              <pre className="mt-2 whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-zinc-300">{m.body}</pre>
              {!inbound && <DraftActions message={m} company={company} />}
            </li>
          )
        })}
      </ol>
    </aside>
  )
}
