'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import {
  Target, Building2, MessagesSquare, ClipboardCheck, Activity as ActivityIcon,
  AlertTriangle, ChevronRight, ExternalLink, CheckCircle2, Clock,
} from 'lucide-react'
import { cn, formatDateTime } from '@/lib/utils'
import {
  type Ops, type Facility, type Conversation, type Decision, type Activity,
  buildFacilities, buildConversations, buildDecisions, buildActivity, buildOverview,
  actionLabel, relTime, ACTION,
} from './model'
import { FacilitiesView } from './facilities'
import { ConversationsView } from './conversations'

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

export function SourcingWorkspace({ ops, initialTab, initialFacility, initialThread, company }: {
  ops: Ops; initialTab: string; initialFacility: string | null; initialThread: string | null; company: string
}) {
  const [tab, setTab] = useState<Tab>((TABS.some((t) => t.key === initialTab) ? initialTab : 'overview') as Tab)
  const [facilityId, setFacilityId] = useState<string | null>(initialFacility)
  const [threadId, setThreadId] = useState<string | null>(initialThread)

  const facilities = useMemo(() => buildFacilities(ops), [ops])
  const conversations = useMemo(() => buildConversations(ops, facilities), [ops, facilities])
  const decisions = useMemo(() => buildDecisions(conversations), [conversations])
  const activity = useMemo(() => buildActivity(ops), [ops])
  const overview = useMemo(() => buildOverview(ops, conversations, decisions), [ops, conversations, decisions])

  // Keep the URL in step so a view can be shared or refreshed, without a reload.
  useEffect(() => {
    const p = new URLSearchParams()
    if (company) p.set('company', company)
    p.set('tab', tab)
    if (tab === 'facilities' && facilityId) p.set('facility', facilityId)
    if (tab === 'conversations' && threadId) p.set('thread', threadId)
    window.history.replaceState(null, '', `?${p.toString()}`)
  }, [tab, facilityId, threadId, company])

  const openFacility = (id: string) => { setFacilityId(id); setTab('facilities') }
  const openThread = (id: string) => { setThreadId(id); setTab('conversations') }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-4 sm:p-6">
      <header className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-zinc-100">Facility sourcing</h1>
            <p className="mt-1 text-sm text-zinc-500">
              Finding a pool for recurring children's swim lessons near Katy, and where every conversation stands.
            </p>
          </div>
          {overview.fixtures > 0 && (
            <div className="flex items-start gap-2 rounded-md border border-amber-900/60 bg-amber-950/30 px-3 py-2 text-xs text-amber-200">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              <span>
                <strong className="font-medium">Prototype data.</strong> Facilities are recorded test records, replies are
                simulated, and nothing has been emailed to anyone.
              </span>
            </div>
          )}
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
          onFacility={openFacility} onThread={openThread} onTab={setTab} />
      )}
      {tab === 'facilities' && (
        <FacilitiesView facilities={facilities} selectedId={facilityId} onSelect={setFacilityId} onThread={openThread} />
      )}
      {tab === 'conversations' && (
        <ConversationsView conversations={conversations} selectedId={threadId} onSelect={setThreadId} onFacility={openFacility} />
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

function OverviewView({ overview, activity, actions, decisions, onFacility, onThread, onTab }: {
  overview: ReturnType<typeof buildOverview>; activity: Activity[]; actions: Ops['next_actions']; decisions: Decision[]
  onFacility: (id: string) => void; onThread: (id: string) => void; onTab: (t: Tab) => void
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
              <div className="mt-0.5 text-base font-medium text-zinc-100">Secure one recurring pool partnership for private children's lessons</div>
              <div className="mt-1 text-sm text-zinc-400">{overview.goal.statusLine}</div>
            </div>
          </div>
          <div className="text-right">
            <div className="text-3xl font-semibold tabular-nums text-zinc-100">{overview.goal.secured}<span className="text-zinc-600"> / {overview.goal.target}</span></div>
            <div className="text-xs text-zinc-500">partnerships secured</div>
          </div>
        </div>
      </Panel>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Facilities researched" value={`${overview.researched} / ${overview.total}`} sub="websites read, facts verified" />
        <Stat label="Ready to contact" value={overview.ready} sub="no blockers, verified route" tone="good" />
        <Stat label="Conversations (simulated)" value={`${overview.replies} / ${overview.conversations}`} sub="replied / drafted" />
        <Stat label="Need your decision" value={overview.decisions} sub={overview.decisions ? 'open the Decisions tab' : 'nothing waiting'} tone={overview.decisions ? 'warn' : undefined} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="What to do next" hint="Highest-impact items first. Nothing here sends anything.">
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
