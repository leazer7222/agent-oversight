'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  Target, Building2, MessagesSquare, ClipboardCheck, Activity as ActivityIcon,
  AlertTriangle, ChevronRight, ExternalLink, CheckCircle2, Clock, Circle, Hourglass, RefreshCw,
} from 'lucide-react'
import { cn, formatDateTime } from '@/lib/utils'
import {
  type Ops, type Conversation, type Decision, type Activity, type Profile, type ConvFilter, type ChecklistStep,
  buildFacilities, buildConversations, buildDecisions, buildActivity, buildOverview, buildChecklist, countsForBanner,
  actionLabel, relTime, ACTION, FILTERS,
} from './model'
import { FacilitiesView, ResearchActions } from './facilities'
import { ConversationsView, postJob } from './conversations'

export type Tab = 'overview' | 'facilities' | 'conversations' | 'decisions' | 'activity'

const TABS: Array<{ key: Tab; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { key: 'overview', label: 'Overview', icon: Target },
  { key: 'facilities', label: 'Facilities', icon: Building2 },
  { key: 'conversations', label: 'Conversations', icon: MessagesSquare },
  { key: 'decisions', label: 'Decisions', icon: ClipboardCheck },
  { key: 'activity', label: 'Activity', icon: ActivityIcon },
]

// Shared primitives --------------------------------------------------------

export function Panel({ title, hint, action, children, className }: {
  title?: string; hint?: string; action?: React.ReactNode; children: React.ReactNode; className?: string
}) {
  return (
    <section className={cn('rounded-lg border border-zinc-800 bg-zinc-900/50', className)}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 border-b border-zinc-800/80 px-4 py-3">
          <div>
            {title && <h2 className="text-sm font-medium text-zinc-200">{title}</h2>}
            {hint && <p className="mt-0.5 text-xs text-zinc-500">{hint}</p>}
          </div>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

export function Pill({ children, tone = 'zinc', className }: { children: React.ReactNode; tone?: 'zinc' | 'amber' | 'emerald' | 'rose' | 'sky'; className?: string }) {
  const tones = {
    zinc: 'border-zinc-700 bg-zinc-800/60 text-zinc-300',
    amber: 'border-amber-900/60 bg-amber-950/40 text-amber-300',
    emerald: 'border-emerald-900/60 bg-emerald-950/40 text-emerald-300',
    rose: 'border-rose-900/60 bg-rose-950/40 text-rose-300',
    sky: 'border-sky-900/60 bg-sky-950/40 text-sky-300',
  }
  return <span className={cn('inline-flex items-center rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-4 whitespace-nowrap', tones[tone], className)}>{children}</span>
}

export function SimulatedPill() {
  return <Pill tone="amber">Simulated</Pill>
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="rounded-md border border-dashed border-zinc-800 px-4 py-6 text-center text-sm text-zinc-500">{children}</p>
}

// Workspace -----------------------------------------------------------------

export function SourcingWorkspace({ ops, initialTab, initialFacility, initialThread, initialFilter, company, profile }: {
  ops: Ops; initialTab: string; initialFacility: string | null; initialThread: string | null; initialFilter: string
  company: string; profile: Profile | null
}) {
  const [tab, setTab] = useState<Tab>((TABS.some((t) => t.key === initialTab) ? initialTab : 'overview') as Tab)
  const [facilityId, setFacilityId] = useState<string | null>(initialFacility)
  const [threadId, setThreadId] = useState<string | null>(initialThread)
  const [filter, setFilter] = useState<ConvFilter>((FILTERS.some((f) => f.key === initialFilter) ? initialFilter : 'all') as ConvFilter)

  const facilities = useMemo(() => buildFacilities(ops), [ops])
  const conversations = useMemo(() => buildConversations(ops, facilities), [ops, facilities])
  const decisions = useMemo(() => buildDecisions(conversations), [conversations])
  const activity = useMemo(() => buildActivity(ops), [ops])
  const overview = useMemo(() => buildOverview(ops, conversations, decisions), [ops, conversations, decisions])
  const checklist = useMemo(() => buildChecklist(overview, conversations, decisions, profile), [overview, conversations, decisions, profile])
  const banner = useMemo(() => countsForBanner(conversations), [conversations])

  // Keep the URL in step so a view can be shared or refreshed, without a reload.
  useEffect(() => {
    const p = new URLSearchParams()
    if (company) p.set('company', company)
    p.set('tab', tab)
    if (tab === 'facilities' && facilityId) p.set('facility', facilityId)
    if (tab === 'conversations' && threadId) p.set('thread', threadId)
    if (tab === 'conversations' && filter !== 'all') p.set('filter', filter)
    window.history.replaceState(null, '', `?${p.toString()}`)
  }, [tab, facilityId, threadId, filter, company])

  const openFacility = (id: string) => { setFacilityId(id); setTab('facilities') }
  const openThread = (id: string) => { setThreadId(id); setTab('conversations') }
  const go = (t: Tab, f?: ConvFilter) => { if (f) { setFilter(f); setThreadId(null) } setTab(t) }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-4 sm:p-6">
      <header className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-zinc-100">Pool partnerships</h1>
            <p className="mt-1 text-sm text-zinc-500">
              Finding pools for {profile?.business_name ?? 'the swim school'} in {profile?.service_area ?? 'Katy and West Houston'}, and where every conversation stands.
            </p>
          </div>
          <div className="flex items-start gap-2 rounded-md border border-amber-900/60 bg-amber-950/30 px-3 py-2 text-xs text-amber-200">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
            <span>
              <strong className="font-medium">Test mode.</strong>{' '}
              {overview.fixtures > 0 ? `${overview.fixtures} of ${overview.total} facilities are test records. ` : ''}
              {banner.simulated > 0 ? `${banner.simulated} scripted test ${banner.simulated === 1 ? 'reply' : 'replies'}, marked "Simulated". ` : ''}
              {banner.sent > 0
                ? `${banner.sent} real ${banner.sent === 1 ? 'email' : 'emails'} sent, each redirected to the allow-listed test address. `
                : 'No email has been sent yet. '}
              No facility has been contacted.
            </span>
          </div>
        </div>

        <nav className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0" aria-label="Workspace sections">
          <div className="flex w-max gap-1 rounded-lg border border-zinc-800 bg-zinc-900/40 p-1 sm:w-auto">
            {TABS.map((t) => {
              const Icon = t.icon
              const active = tab === t.key
              const count = t.key === 'decisions' ? decisions.length : t.key === 'conversations' ? overview.replies : null
              return (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => setTab(t.key)}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors',
                    active ? 'bg-zinc-800 text-zinc-100 shadow-sm' : 'text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200',
                  )}
                >
                  <Icon className="size-4" />
                  {t.label}
                  {count ? (
                    <span className={cn('rounded-full px-1.5 text-[11px] tabular-nums',
                      t.key === 'decisions' ? 'bg-amber-500/20 text-amber-300' : 'bg-zinc-700/60 text-zinc-300')}>
                      {count}
                    </span>
                  ) : null}
                </button>
              )
            })}
          </div>
        </nav>
      </header>

      {ops.errors?.length > 0 && (
        <div className="rounded-md border border-rose-900/60 bg-rose-950/30 px-3 py-2 text-xs text-rose-200">
          Some data did not load: {ops.errors.join('; ')}
        </div>
      )}

      {tab === 'overview' && (
        <OverviewView overview={overview} activity={activity} actions={ops.next_actions} decisions={decisions}
          checklist={checklist} profile={profile} company={company}
          onFacility={openFacility} onThread={openThread} onTab={setTab} onGo={go} />
      )}
      {tab === 'facilities' && (
        <FacilitiesView facilities={facilities} selectedId={facilityId} onSelect={setFacilityId} onThread={openThread} company={company} />
      )}
      {tab === 'conversations' && (
        <ConversationsView conversations={conversations} selectedId={threadId} onSelect={setThreadId} onFacility={openFacility}
          company={company} filter={filter} onFilter={(f) => { setFilter(f); setThreadId(null) }} />
      )}
      {tab === 'decisions' && <DecisionsView decisions={decisions} onThread={openThread} onFacility={openFacility} />}
      {tab === 'activity' && <ActivityView activity={activity} />}
    </div>
  )
}

// Overview --------------------------------------------------------------------

function Stat({ label, value, sub, tone }: { label: string; value: string | number; sub?: string; tone?: 'good' | 'warn' }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-3">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className={cn('mt-1 text-2xl font-semibold tabular-nums', tone === 'good' ? 'text-emerald-300' : tone === 'warn' ? 'text-amber-300' : 'text-zinc-100')}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-zinc-500">{sub}</div>}
    </div>
  )
}

function StepStatus({ status, count }: { status: ChecklistStep['status']; count: number }) {
  if (status === 'done') return <Pill tone="emerald"><CheckCircle2 className="mr-1 size-3" />Done</Pill>
  if (status === 'attention') return <Pill tone="amber"><AlertTriangle className="mr-1 size-3" />{count ? `${count} waiting` : 'Needs you'}</Pill>
  if (status === 'waiting') return <Pill tone="sky"><Hourglass className="mr-1 size-3" />Waiting</Pill>
  return <Pill tone="zinc"><Circle className="mr-1 size-3" />Not yet</Pill>
}

/** Rewrites every draft that has not been sent, using the current business profile. */
function RedraftButton({ company }: { company: string }) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const run = async () => {
    setBusy(true); setNote(null)
    const r = await postJob({ job_type: 'draft_outreach', payload: { redraft: true, limit: 50 }, company: company || undefined })
    setNote(r.ok ? 'Queued. On its next pass the worker writes a draft for every ready facility and rewrites every unsent one; each then needs approving.' : `Failed: ${r.detail}`)
    setBusy(false)
    if (r.ok) router.refresh()
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" onClick={run} disabled={busy}
        className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-200 hover:bg-zinc-800 disabled:opacity-50">
        <RefreshCw className={cn("size-4", busy && "animate-spin")} /> Write or rewrite drafts
      </button>
      {note && <span className={cn('text-xs', note.startsWith('Failed') ? 'text-rose-300' : 'text-zinc-400')}>{note}</span>}
    </div>
  )
}

function Checklist({ steps, profile, company, onGo }: {
  steps: ChecklistStep[]; profile: Profile | null; company: string; onGo: (t: Tab, f?: ConvFilter) => void
}) {
  const current = steps.find((s) => s.status === 'attention') ?? steps.find((s) => s.status === 'todo' || s.status === 'waiting') ?? null
  return (
    <Panel title="How this works, and where you are"
      hint="Six steps, in order. Only you approve and only you press send; the system drafts, sends what you approved, reads replies and flags what needs you.">
      <ol className="divide-y divide-zinc-800/80">
        {steps.map((s) => {
          const isCurrent = current?.key === s.key
          return (
            <li key={s.key} className={cn('py-3 first:pt-0 last:pb-0', isCurrent && '-mx-4 bg-zinc-900/80 px-4')}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex min-w-0 items-start gap-3">
                  <span className={cn('mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold',
                    s.status === 'done' ? 'bg-emerald-900/60 text-emerald-300' : isCurrent ? 'bg-amber-500 text-zinc-950' : 'bg-zinc-800 text-zinc-300')}>{s.n}</span>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-sm font-medium text-zinc-100">{s.title}</h3>
                      <StepStatus status={s.status} count={s.count} />
                      {isCurrent && <span className="text-xs text-amber-300">You are here</span>}
                    </div>
                    <p className="mt-1 text-sm text-zinc-300">{s.summary}</p>
                    <p className="mt-1 text-xs text-zinc-500"><span className="text-zinc-400">How:</span> {s.how}</p>
                    {s.key === 'profile' && profile && (
                      <details className="mt-2 text-xs text-zinc-500">
                        <summary className="cursor-pointer select-none hover:text-zinc-300">What the emails are allowed to say</summary>
                        <dl className="mt-2 grid gap-x-4 gap-y-1 sm:grid-cols-[10rem_1fr]">
                          <dt className="text-zinc-500">Business</dt><dd className="text-zinc-300">{profile.business_name}, owner {profile.owner_name}</dd>
                          <dt className="text-zinc-500">Area</dt><dd className="text-zinc-300">{profile.service_area}</dd>
                          <dt className="text-zinc-500">Students</dt><dd className="text-zinc-300">{profile.students_per_year} a year, {profile.ages_served}</dd>
                          <dt className="text-zinc-500">Programs</dt><dd className="text-zinc-300">{(profile.programs ?? []).join('; ')}</dd>
                          <dt className="text-zinc-500">Credentials</dt><dd className="text-zinc-300">{(profile.credentials ?? []).join('; ')}</dd>
                          <dt className="text-zinc-500">Partnership options</dt><dd className="text-zinc-300">{(profile.partnership_structures ?? []).join('; ')}</dd>
                          <dt className="text-zinc-500">Replies go to</dt><dd className="text-zinc-300">{profile.reply_email}</dd>
                          <dt className="text-zinc-500">Never said</dt><dd className="text-zinc-300">Prices, budgets or percentages; schedules; insurance; exclusivity or contract terms; that any pool is suitable before Cameron has seen it.</dd>
                        </dl>
                      </details>
                    )}
                  </div>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-2">
                  {s.go && (
                    <button type="button" onClick={() => onGo(s.go!.tab, s.go!.filter)}
                      className={cn('inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-sm font-medium',
                        s.status === 'attention' ? 'bg-amber-500 text-zinc-950 hover:bg-amber-400' : 'border border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800')}>
                      {s.go.label} <ChevronRight className="size-4" />
                    </button>
                  )}
                  {s.key === 'profile' && <RedraftButton company={company} />}
                  {s.key === 'research' && <ResearchActions company={company} compact />}
                </div>
              </div>
            </li>
          )
        })}
      </ol>
    </Panel>
  )
}

function OverviewView({ overview, activity, actions, decisions, checklist, profile, company, onFacility, onThread, onTab, onGo }: {
  overview: ReturnType<typeof buildOverview>; activity: Activity[]; actions: Ops['next_actions']; decisions: Decision[]
  checklist: ChecklistStep[]; profile: Profile | null; company: string
  onFacility: (id: string) => void; onThread: (id: string) => void; onTab: (t: Tab) => void; onGo: (t: Tab, f?: ConvFilter) => void
}) {
  const topActions = [...actions].sort((a, b) => a.priority - b.priority).slice(0, 6)
  const recent = activity.filter((a) => a.status !== 'failed').slice(0, 5)
  return (
    <div className="space-y-5">
      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="rounded-md bg-sky-950/60 p-2 text-sky-300"><Target className="size-5" /></div>
            <div>
              <div className="text-xs uppercase tracking-wide text-zinc-500">Goal</div>
              <div className="mt-0.5 text-base font-medium text-zinc-100">Secure one recurring pool partnership for {profile?.business_name ?? 'the swim school'}</div>
              <div className="mt-1 text-sm text-zinc-400">{overview.goal.statusLine}</div>
            </div>
          </div>
          <div className="text-right">
            <div className="text-3xl font-semibold tabular-nums text-zinc-100">{overview.goal.secured}<span className="text-zinc-600"> / {overview.goal.target}</span></div>
            <div className="text-xs text-zinc-500">partnerships secured</div>
          </div>
        </div>
      </Panel>

      <Checklist steps={checklist} profile={profile} company={company} onGo={onGo} />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Facilities researched" value={`${overview.researched} / ${overview.total}`} sub="websites read, facts verified" />
        <Stat label="Ready to contact" value={overview.ready} sub="no blockers, verified route" tone="good" />
        <Stat label="Conversations" value={`${overview.replies} / ${overview.conversations}`} sub="replied / drafted" />
        <Stat label="Need your decision" value={overview.decisions} sub={overview.decisions ? 'open the Decisions tab' : 'nothing waiting'} tone={overview.decisions ? 'warn' : undefined} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="Individual items" hint="Highest-impact first. Clicking opens the item; nothing is sent from this list.">
          {topActions.length === 0 ? <Empty>Nothing waiting. Research will add new items as it runs.</Empty> : (
            <ul className="divide-y divide-zinc-800/80">
              {topActions.map((a, i) => (
                <li key={`${a.action_type}-${a.facility_id}-${i}`}>
                  <button type="button"
                    onClick={() => (a.thread_id ? onThread(a.thread_id) : onFacility(a.facility_id))}
                    className="group flex w-full items-center justify-between gap-3 py-2.5 text-left hover:bg-zinc-900/70">
                    <div className="min-w-0">
                      <div className={cn('text-sm font-medium', a.priority === 1 ? 'text-amber-300' : 'text-zinc-200')}>{actionLabel(a.action_type)}</div>
                      <div className="truncate text-xs text-zinc-500">{a.facility_name}{a.detail ? ` - ${ACTION[a.detail] ?? a.detail}` : ''}</div>
                    </div>
                    <ChevronRight className="size-4 shrink-0 text-zinc-600 group-hover:text-zinc-300" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          {decisions.length > 0 && (
            <button type="button" onClick={() => onTab('decisions')} className="mt-3 text-xs text-sky-300 hover:underline">
              See all {decisions.length} decision{decisions.length === 1 ? '' : 's'} waiting on you
            </button>
          )}
        </Panel>

        <Panel title="Recently accomplished" hint="What the team has done, in plain terms." action={
          <button type="button" onClick={() => onTab('activity')} className="text-xs text-sky-300 hover:underline">Full activity</button>
        }>
          {recent.length === 0 ? <Empty>No activity yet.</Empty> : (
            <ul className="space-y-3">
              {recent.map((a) => (
                <li key={a.id} className="flex gap-3">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-400" />
                  <div className="min-w-0">
                    <div className="text-sm text-zinc-200">{a.what}</div>
                    <div className="text-xs text-zinc-500">{a.who} - {relTime(a.when)}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <p className="text-xs text-zinc-600">
        {overview.questions} qualification questions are still open across all facilities. Team spend so far: ${overview.spend.toFixed(2)}.
      </p>
    </div>
  )
}

// Decisions -------------------------------------------------------------------

function DecisionsView({ decisions, onThread, onFacility }: { decisions: Decision[]; onThread: (id: string) => void; onFacility: (id: string) => void }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-zinc-400">Items that need your judgement before anything else happens.</p>
        <Pill tone="sky">Review only - nothing is executed from this screen</Pill>
      </div>
      {decisions.length === 0 ? <Empty>Nothing is waiting on you right now.</Empty> : (
        <ul className="space-y-3">
          {decisions.map((d) => (
            <li key={d.id} className={cn('rounded-lg border bg-zinc-900/50 p-4', d.severity === 'high' ? 'border-amber-800/70' : 'border-zinc-800')}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="flex items-start gap-2">
                  {d.severity === 'high' ? <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-300" /> : <ClipboardCheck className="mt-0.5 size-4 shrink-0 text-zinc-400" />}
                  <div>
                    <h3 className="text-sm font-medium text-zinc-100">{d.title}</h3>
                    <button type="button" onClick={() => onFacility(d.facilityId)} className="text-xs text-zinc-400 hover:text-zinc-200 hover:underline">{d.facility}</button>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <SimulatedPill />
                  {d.threadId && (
                    <button type="button" onClick={() => onThread(d.threadId!)} className="text-xs text-sky-300 hover:underline">Open conversation</button>
                  )}
                </div>
              </div>
              <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-[9rem_1fr]">
                <dt className="text-zinc-500">What happened</dt><dd className="text-zinc-200">{d.happened}</dd>
                <dt className="text-zinc-500">Why it is yours</dt><dd className="text-zinc-300">{d.why}</dd>
                <dt className="text-zinc-500">Recommendation</dt><dd className="text-zinc-300">{d.recommends}</dd>
                <dt className="text-zinc-500">Next step</dt><dd className="text-zinc-400">{d.nextStep}</dd>
              </dl>
              <details className="mt-3 text-xs text-zinc-500">
                <summary className="cursor-pointer select-none hover:text-zinc-300">Technical details</summary>
                <pre className="mt-2 overflow-x-auto rounded bg-zinc-950/60 p-2 text-[11px] text-zinc-400">{JSON.stringify(d.technical, null, 2)}</pre>
              </details>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// Activity ----------------------------------------------------------------------

function ActivityView({ activity }: { activity: Activity[] }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-zinc-400">What each team member did, most recent first.</p>
        <Link href="/dashboard/runs" className="inline-flex items-center gap-1 text-xs text-sky-300 hover:underline">
          Technical run log <ExternalLink className="size-3" />
        </Link>
      </div>
      {activity.length === 0 ? <Empty>No activity recorded yet.</Empty> : (
        <ol className="relative space-y-0 border-l border-zinc-800 pl-5">
          {activity.map((a) => (
            <li key={a.id} className="relative pb-5">
              <span className={cn('absolute -left-[1.45rem] top-1 size-2.5 rounded-full ring-4 ring-zinc-950',
                a.status === 'failed' ? 'bg-rose-400' : a.what.startsWith('Paused') ? 'bg-amber-400' : 'bg-emerald-400')} />
              <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                <div className="text-sm text-zinc-200">{a.what}</div>
                <div className="flex items-center gap-1 text-xs text-zinc-500"><Clock className="size-3" />{formatDateTime(a.when)}</div>
              </div>
              {a.detail && <div className="mt-0.5 text-sm text-zinc-400">{a.detail}</div>}
              <div className="mt-1 text-xs text-zinc-500">{a.who}{a.cost ? ` - $${a.cost.toFixed(4)}` : ''}</div>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
