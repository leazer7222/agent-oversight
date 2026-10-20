import Link from 'next/link'
import { apiFetch } from '@/lib/api/fetch'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { EmptyState } from '@/components/dashboard/EmptyState'
import { formatDateTime } from '@/lib/utils'

/**
 * Facility sourcing workspace.
 *
 * Written for Cameron, not for an engineer: no run_id, no agent_id, no table
 * names in the primary view. The operations strip is deliberately plain-language
 * ("Drafts prepared", "Needs your decision") because the person running this
 * workflow should not need to know an agent exists.
 *
 * Every number on this page is read from the database through the sourcing
 * API (public RPCs). Nothing is hard-coded. Prototype data is labelled as such
 * wherever it appears: fixture facilities carry source='fixture', simulated
 * replies carry a [SIMULATED] subject, drafts are never sent.
 */

const PIPELINE: Array<{ key: string; label: string }> = [
  { key: 'discovered', label: 'Discovered' },
  { key: 'qualified', label: 'Qualified' },
  { key: 'needs_info', label: 'Need info' },
  { key: 'disqualified', label: 'Disqualified' },
  { key: 'responded', label: 'Responded' },
  { key: 'meeting_scheduled', label: 'Meeting set' },
  { key: 'negotiating', label: 'Negotiating' },
  { key: 'secured', label: 'Secured' },
]

const TRIAGE_LABEL: Record<string, string> = {
  contact_first: 'Contact first',
  research_further: 'Research further',
  not_currently_suitable: 'Not suitable now',
  disqualified: 'Disqualified',
}

const TRIAGE_TONE: Record<string, string> = {
  contact_first: 'text-emerald-400',
  research_further: 'text-amber-400',
  not_currently_suitable: 'text-zinc-500',
  disqualified: 'text-rose-400',
}

const ACTION_LABEL: Record<string, string> = {
  review_escalation: 'Needs your decision',
  suppress_contact: 'Opt-out to honour',
  review_proposed_reply: 'Reply proposed',
  review_draft: 'Draft to review',
  prepare_outreach: 'Ready to draft',
  research_further: 'Research further',
}

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: 'warn' | 'good' }) {
  const colour =
    tone === 'warn' ? 'text-amber-400' : tone === 'good' ? 'text-emerald-400' : 'text-zinc-100'
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-3">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${colour}`}>{value}</div>
    </div>
  )
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 className="mb-1 text-sm font-medium text-zinc-300">{title}</h2>
      {hint && <p className="mb-2 text-xs text-zinc-500">{hint}</p>}
      {children}
    </div>
  )
}

export default async function SourcingPage({
  searchParams,
}: {
  searchParams: Promise<{ stage?: string; company?: string }>
}) {
  const sp = await searchParams
  const stage = sp.stage ?? ''
  const company = sp.company ?? ''
  const qs = (extra: Record<string, string>) => {
    const p = new URLSearchParams()
    if (company) p.set('company', company)
    for (const [k, v] of Object.entries(extra)) if (v) p.set(k, v)
    const s = p.toString()
    return s ? `?${s}` : ''
  }

  const ops = await apiFetch(`/api/sourcing/operations${qs({})}`)

  const summary: Record<string, number> = ops?.summary ?? {}
  const objective: Record<string, any> = ops?.objective ?? {}
  const pipeline: Array<{ stage: string; facility_count: number }> = ops?.pipeline ?? []
  const researchAll: any[] = ops?.research ?? []
  const research = stage ? researchAll.filter((r) => r.pipeline_stage === stage) : researchAll
  const drafts: any[] = ops?.drafts ?? []
  const threads: any[] = ops?.threads ?? []
  const actions: any[] = ops?.next_actions ?? []
  const counts = new Map(pipeline.map((p) => [p.stage, Number(p.facility_count)]))
  const target = Number(objective.target_partnerships ?? 1)
  const secured = Number(objective.secured ?? 0)
  const replied = threads.filter((t) => Number(t.inbound_count ?? 0) > 0)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Facility sourcing</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Swimming pool facilities that could host recurring lessons, and where each
          conversation stands.
        </p>
        {Number(objective.facilities_fixture ?? 0) > 0 && (
          <p className="mt-2 inline-block rounded border border-amber-900/60 bg-amber-950/40 px-2 py-1 text-xs text-amber-300">
            Prototype data: {objective.facilities_fixture} of {objective.facilities_total} facilities are
            recorded fixtures, replies are simulated, and no email has been sent.
          </p>
        )}
      </div>

      {/* Objective progress: the goal, then the funnel with denominators. */}
      <Section title="Objective" hint="One recurring pool partnership. Counts, not scores.">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
          <Stat label="Secured / target" value={`${secured} / ${target}`} tone={secured >= target ? 'good' : undefined} />
          <Stat label="Facilities found" value={objective.facilities_total ?? 0} />
          <Stat label="Researched" value={objective.enriched ?? 0} />
          <Stat label="Contact first" value={objective.contact_first ?? 0} tone="good" />
          <Stat label="Drafts prepared" value={objective.drafts ?? 0} />
          <Stat label="Replies" value={objective.replies ?? 0} />
          <Stat label="Needs your decision" value={objective.escalated ?? 0} tone={(objective.escalated ?? 0) > 0 ? 'warn' : undefined} />
          <Stat label="Open questions" value={objective.open_questions_total ?? 0} />
        </div>
      </Section>

      {/* Pipeline board. */}
      <Section title="Pipeline">
        <div className="flex flex-wrap gap-2">
          {PIPELINE.map((s) => {
            const n = counts.get(s.key) ?? 0
            const active = stage === s.key
            return (
              <Link
                key={s.key}
                href={`/dashboard/sourcing${qs({ stage: active ? '' : s.key })}`}
                className={`rounded-md border px-3 py-2 text-xs transition-colors ${
                  active
                    ? 'border-zinc-600 bg-zinc-800 text-zinc-100'
                    : 'border-zinc-800 bg-zinc-900/50 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200'
                }`}
              >
                <span className="block font-medium">{s.label}</span>
                <span className="mt-0.5 block text-lg font-semibold tabular-nums">{n}</span>
              </Link>
            )
          })}
        </div>
      </Section>

      {/* Next actions: what a human (or the controller) should do next. */}
      <Section title="Next actions" hint="Derived from the pipeline each time the page loads.">
        {actions.length === 0 ? (
          <EmptyState message="Nothing waiting. Run the controller to refresh research or prepare drafts." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Action</TableHead>
                <TableHead>Facility</TableHead>
                <TableHead>Detail</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {actions.slice(0, 25).map((a: any, i: number) => (
                <TableRow key={`${a.action_type}-${a.facility_id}-${i}`}>
                  <TableCell className={`font-medium ${a.priority === 1 ? 'text-amber-300' : 'text-zinc-200'}`}>
                    {ACTION_LABEL[a.action_type] ?? a.action_type}
                  </TableCell>
                  <TableCell className="text-zinc-300">{a.facility_name}</TableCell>
                  <TableCell className="text-xs text-zinc-500">{a.detail}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>

      {/* Replies and their classification. */}
      <Section title="Replies" hint="Simulated in the prototype. Each is classified; anything touching price, terms, insurance or a meeting is escalated by rule, not by the model's judgement.">
        {replied.length === 0 ? (
          <EmptyState message="No replies yet." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Facility</TableHead>
                <TableHead>Intent</TableHead>
                <TableHead>Proposed</TableHead>
                <TableHead>Why</TableHead>
                <TableHead>Reply excerpt</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {replied.map((t: any) => {
                const c = t.last_classification ?? {}
                const safety = c.safety ?? {}
                return (
                  <TableRow key={t.thread_id}>
                    <TableCell className="font-medium text-zinc-200">{t.facility_name}</TableCell>
                    <TableCell className="text-zinc-300">
                      {String(t.last_intent ?? 'pending').replace(/_/g, ' ')}
                      {safety.injection_suspected && (
                        <span className="ml-2 rounded bg-rose-950/60 px-1.5 py-0.5 text-[10px] text-rose-300">injection flagged</span>
                      )}
                    </TableCell>
                    <TableCell className={t.state === 'escalated' || t.state === 'opted_out' ? 'text-amber-300' : 'text-zinc-300'}>
                      {String(c.proposed_action ?? t.state ?? '-').replace(/_/g, ' ')}
                    </TableCell>
                    <TableCell className="text-xs text-zinc-500">
                      {(safety.reasons ?? []).slice(0, 2).join('; ') || c.summary || '-'}
                    </TableCell>
                    <TableCell className="max-w-md truncate text-xs text-zinc-500" title={t.last_inbound_excerpt ?? ''}>
                      {t.last_inbound_excerpt ?? '-'}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </Section>

      {/* Drafts. */}
      <Section title="Outreach drafts" hint="Prepared, never sent. Each asks that facility's own open questions and passed the anti-fabrication gate.">
        {drafts.length === 0 ? (
          <EmptyState message="No drafts yet." />
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {drafts.map((d: any) => (
              <div key={d.message_id} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
                <div className="flex items-baseline justify-between gap-3">
                  <div className="font-medium text-zinc-200">{d.facility_name}</div>
                  <div className="text-xs text-zinc-500">
                    {String(d.status).replace(/_/g, ' ')} - {String(d.thread_state).replace(/_/g, ' ')}
                  </div>
                </div>
                <div className="mt-1 text-xs text-zinc-400">
                  To: {d.contact_name ?? 'contact'}{d.contact_email ? ` <${d.contact_email}>` : ''}
                </div>
                <div className="mt-1 text-sm text-zinc-300">{d.subject}</div>
                <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap rounded bg-zinc-950/60 p-3 text-xs text-zinc-400">{d.body}</pre>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* Agent health. */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Jobs queued" value={summary.jobs_queued ?? 0} />
        <Stat label="Jobs running" value={summary.jobs_running ?? 0} />
        <Stat
          label="Jobs failed"
          value={summary.jobs_failed ?? 0}
          tone={(summary.jobs_failed ?? 0) > 0 ? 'warn' : undefined}
        />
        <Stat label="Agent spend (recent)" value={`$${(ops?.recent_spend_usd ?? 0).toFixed(4)}`} />
      </div>

      {/* Research worksheet. */}
      <Section
        title={stage ? `Facilities: ${stage.replace(/_/g, ' ')}` : 'Research worksheet'}
        hint="Triage is evidence-based: a state, a recommended channel and the questions still open. The internal score is not shown because before contact it carries almost no information."
      >
        {research.length === 0 ? (
          <EmptyState message="No facilities yet. Run discovery to find pools near Katy - every facility links back to its source." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Facility</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="text-right">Distance</TableHead>
                <TableHead>Triage</TableHead>
                <TableHead>Channel</TableHead>
                <TableHead className="text-right">Known</TableHead>
                <TableHead className="text-right">Unknown</TableHead>
                <TableHead className="text-right">Contacts</TableHead>
                <TableHead>Open questions</TableHead>
                <TableHead>Source</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {research.map((f: any) => {
                const qs_ = Array.isArray(f.open_questions) ? f.open_questions : []
                return (
                  <TableRow key={f.facility_id}>
                    <TableCell className="font-medium text-zinc-200">
                      {f.website ? (
                        <a href={f.website} target="_blank" rel="noreferrer" className="hover:text-white hover:underline">
                          {f.name}
                        </a>
                      ) : f.name}
                    </TableCell>
                    <TableCell className="text-zinc-400">{String(f.facility_type ?? 'unknown').replace(/_/g, ' ')}</TableCell>
                    <TableCell className="text-right tabular-nums text-zinc-400">
                      {f.distance_miles != null ? `${Number(f.distance_miles).toFixed(1)} mi` : '-'}
                    </TableCell>
                    <TableCell className={TRIAGE_TONE[f.triage_state] ?? 'text-zinc-500'}>
                      {TRIAGE_LABEL[f.triage_state] ?? 'not triaged'}
                    </TableCell>
                    <TableCell className="text-zinc-400">{String(f.channel_recommended ?? '-').replace(/_/g, ' ')}</TableCell>
                    <TableCell className="text-right tabular-nums text-zinc-300">{f.known_count ?? 0}</TableCell>
                    <TableCell className="text-right tabular-nums text-zinc-500">{f.unknown_count ?? 0}</TableCell>
                    <TableCell className="text-right tabular-nums text-zinc-300">{f.contact_count ?? 0}</TableCell>
                    <TableCell className="max-w-xs text-xs text-zinc-500" title={qs_.map((q: any) => q.question).join(' ')}>
                      {qs_.length === 0 ? '-' : `${qs_.length}: ${String(qs_[0]?.question ?? '').slice(0, 60)}${qs_.length > 1 ? '...' : ''}`}
                    </TableCell>
                    <TableCell className="text-xs">
                      <span className={f.source === 'fixture' ? 'text-amber-300' : 'text-zinc-400'}>{f.source}</span>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </Section>

      <p className="text-xs text-zinc-600">
        Last refreshed {objective.generated_at ? formatDateTime(objective.generated_at) : '-'}.
      </p>
    </div>
  )
}
