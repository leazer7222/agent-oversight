'use client'

import { useMemo, useState } from 'react'
import { Search, X, Mail, Phone, FileText, ExternalLink, ChevronRight } from 'lucide-react'
import { cn, formatDateTime } from '@/lib/utils'
import {
  type Facility, STATE, stateOf, channelLabel, typeLabel, actionLabel,
  attrLabel, attrValue, CONFIDENCE, excerpt,
} from './model'
import { Panel, Pill, SimulatedPill, Empty } from './workspace'

const STATE_FILTERS = [
  { key: '', label: 'All' },
  { key: 'contact_first', label: 'Ready to contact' },
  { key: 'research_further', label: 'Needs research' },
  { key: 'not_currently_suitable', label: 'Not a fit now' },
  { key: 'disqualified', label: 'Ruled out' },
]

export function FacilitiesView({ facilities, selectedId, onSelect, onThread }: {
  facilities: Facility[]; selectedId: string | null; onSelect: (id: string | null) => void; onThread: (id: string) => void
}) {
  const [q, setQ] = useState('')
  const [state, setState] = useState('')
  const [channel, setChannel] = useState('')

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return facilities.filter((f) => {
      if (state && (f.triage_state ?? '') !== state) return false
      if (channel && (f.channel_recommended ?? 'none') !== channel) return false
      if (!needle) return true
      const hay = [f.name, typeLabel(f.facility_type), channelLabel(f.channel_recommended), f.state.label,
        ...(f.details?.contacts ?? []).map((c) => `${c.full_name ?? ''} ${c.email ?? ''}`)].join(' ').toLowerCase()
      return hay.includes(needle)
    })
  }, [facilities, q, state, channel])

  const selected = facilities.find((f) => f.facility_id === selectedId) ?? null
  const channels = Array.from(new Set(facilities.map((f) => f.channel_recommended ?? 'none')))

  return (
    <div className={cn('grid gap-4', selected ? 'lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]' : '')}>
      <div className="min-w-0 space-y-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <label className="relative flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-zinc-500" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search facilities, types, contacts"
              className="w-full rounded-md border border-zinc-800 bg-zinc-900/60 py-2 pl-9 pr-8 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-zinc-600 focus:outline-none focus:ring-2 focus:ring-sky-900"
            />
            {q && <button type="button" onClick={() => setQ('')} aria-label="Clear search" className="absolute right-2 top-2 text-zinc-500 hover:text-zinc-200"><X className="size-4" /></button>}
          </label>
          <select value={channel} onChange={(e) => setChannel(e.target.value)}
            className="rounded-md border border-zinc-800 bg-zinc-900/60 px-2 py-2 text-sm text-zinc-200 focus:border-zinc-600 focus:outline-none">
            <option value="">Any channel</option>
            {channels.map((c) => <option key={c} value={c}>{channelLabel(c)}</option>)}
          </select>
        </div>
        <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <div className="flex w-max gap-1.5">
            {STATE_FILTERS.map((s) => {
              const n = s.key ? facilities.filter((f) => f.triage_state === s.key).length : facilities.length
              const active = state === s.key
              return (
                <button key={s.key} type="button" onClick={() => setState(s.key)}
                  className={cn('rounded-full border px-2.5 py-1 text-xs transition-colors',
                    active ? 'border-zinc-500 bg-zinc-800 text-zinc-100' : 'border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200')}>
                  {s.label} <span className="tabular-nums text-zinc-500">{n}</span>
                </button>
              )
            })}
          </div>
        </div>

        {filtered.length === 0 ? (
          <Empty>{facilities.length === 0 ? 'No facilities yet. Research adds them as it runs.' : 'No facilities match this search.'}</Empty>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden overflow-hidden rounded-lg border border-zinc-800 md:block">
              <table className="w-full text-sm">
                <thead className="bg-zinc-900/70 text-left text-xs text-zinc-500">
                  <tr>
                    <th className="px-3 py-2 font-medium">Facility</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">Contact via</th>
                    <th className="px-3 py-2 text-right font-medium">Open questions</th>
                    <th className="px-3 py-2 font-medium">Next</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/80">
                  {filtered.map((f) => {
                    const active = f.facility_id === selectedId
                    return (
                      <tr key={f.facility_id} onClick={() => onSelect(active ? null : f.facility_id)}
                        className={cn('cursor-pointer border-l-2 transition-colors', active ? 'border-l-sky-500 bg-zinc-900' : 'border-l-transparent hover:bg-zinc-900/70')}>
                        <td className="max-w-[18rem] px-3 py-2.5">
                          <div className="truncate font-medium text-zinc-200">{f.name}</div>
                          <div className="truncate text-xs text-zinc-500">
                            {typeLabel(f.facility_type)}{f.distance_miles != null ? ` - ${Number(f.distance_miles).toFixed(1)} mi` : ''}
                            {f.source === 'fixture' && <span className="ml-1.5 text-amber-400/80">test record</span>}
                          </div>
                        </td>
                        <td className="px-3 py-2.5"><StateDot f={f} /></td>
                        <td className="px-3 py-2.5 text-zinc-300">{channelLabel(f.channel_recommended)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-zinc-300">{f.open_questions?.length ?? 0}</td>
                        <td className="max-w-[12rem] truncate px-3 py-2.5 text-xs text-zinc-400">{f.nextAction ? actionLabel(f.nextAction.action_type) : '-'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {/* Mobile cards */}
            <ul className="space-y-2 md:hidden">
              {filtered.map((f) => (
                <li key={f.facility_id}>
                  <button type="button" onClick={() => onSelect(f.facility_id)}
                    className="flex w-full items-center justify-between gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-left hover:bg-zinc-900/80">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-zinc-200">{f.name}</div>
                      <div className="truncate text-xs text-zinc-500">{typeLabel(f.facility_type)} - {channelLabel(f.channel_recommended)}</div>
                      <div className="mt-1"><StateDot f={f} /></div>
                    </div>
                    <ChevronRight className="size-4 shrink-0 text-zinc-600" />
                  </button>
                </li>
              ))}
            </ul>
            <p className="text-xs text-zinc-600">{filtered.length} of {facilities.length} facilities</p>
          </>
        )}
      </div>

      {selected && <FacilityDetail f={selected} onClose={() => onSelect(null)} onThread={onThread} />}
    </div>
  )
}

function StateDot({ f }: { f: Facility }) {
  const s = f.state
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-xs', s.tone)}>
      <span className={cn('size-1.5 rounded-full', s.dot)} />{s.label}
    </span>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h4 className="text-xs font-medium uppercase tracking-wide text-zinc-500">{title}</h4>
      <div className="mt-2">{children}</div>
    </section>
  )
}

function FacilityDetail({ f, onClose, onThread }: { f: Facility; onClose: () => void; onThread: (id: string) => void }) {
  const d = f.details
  const attrs = Object.entries(d?.attributes ?? {}).filter(([k]) => k !== 'distance_miles')
  const unknown = (d?.unknown_fields ?? []).filter((k) => !(k in (d?.attributes ?? {})))
  const questions = d?.latest_qualification?.open_questions ?? f.open_questions ?? []
  const reasons: string[] = d?.latest_qualification?.score_breakdown?.triage_reasons ?? []
  const draftMsg = f.messages.find((m) => m.direction === 'outbound')
  const inbound = f.messages.filter((m) => m.direction === 'inbound')

  return (
    <aside
      className="fixed inset-0 z-40 overflow-y-auto bg-zinc-950 p-4 lg:static lg:z-auto lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto lg:rounded-lg lg:border lg:border-zinc-800 lg:bg-zinc-900/50"
      role="dialog" aria-label={`${f.name} details`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="break-words text-base font-semibold text-zinc-100">{f.name}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
            <span>{typeLabel(f.facility_type)}</span>
            {f.distance_miles != null && <span>{Number(f.distance_miles).toFixed(1)} miles from Katy</span>}
            {f.source === 'fixture' ? <Pill tone="amber">Test record</Pill> : <Pill>Google Places</Pill>}
          </div>
        </div>
        <button type="button" onClick={onClose} aria-label="Close details" className="rounded-md p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"><X className="size-4" /></button>
      </div>

      <div className="mt-4 space-y-5">
        <Section title="Where it stands">
          <div className={cn('text-sm font-medium', f.state.tone)}>{f.state.label}</div>
          <p className="mt-0.5 text-sm text-zinc-400">{reasons.length ? reasons.join('. ') + '.' : f.state.explain}</p>
          <p className="mt-2 text-sm text-zinc-300">
            <span className="text-zinc-500">Best way to reach them: </span>{channelLabel(f.channel_recommended)}
          </p>
          {f.nextAction && (
            <p className="mt-1 text-sm text-zinc-300"><span className="text-zinc-500">Next: </span>{actionLabel(f.nextAction.action_type)}
              {f.nextAction.thread_id && <button type="button" onClick={() => onThread(f.nextAction!.thread_id!)} className="ml-2 text-xs text-sky-300 hover:underline">open conversation</button>}
            </p>
          )}
        </Section>

        <Section title="What we verified">
          {attrs.length === 0 ? <p className="text-sm text-zinc-500">Nothing verified beyond the location yet.</p> : (
            <dl className="divide-y divide-zinc-800/80 rounded-md border border-zinc-800">
              {attrs.map(([k, v]) => {
                const c = CONFIDENCE[d?.attributes_confidence?.[k] ?? 'unknown'] ?? CONFIDENCE.unknown
                return (
                  <div key={k} className="flex items-start justify-between gap-3 px-3 py-2">
                    <dt className="text-sm text-zinc-400">{attrLabel(k)}</dt>
                    <dd className="text-right">
                      <div className="break-words text-sm text-zinc-100">
                        {k === 'facility_use_application_url' && typeof v === 'string'
                          ? <a href={v} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sky-300 hover:underline">Open form <ExternalLink className="size-3" /></a>
                          : attrValue(k, v)}
                      </div>
                      <div className={cn('text-[11px]', c.tone)}>{c.label}</div>
                    </dd>
                  </div>
                )
              })}
            </dl>
          )}
          {(d?.website || d?.source_url) && (
            <p className="mt-2 text-xs text-zinc-500">
              Source: {d?.website ? <a href={d.website} target="_blank" rel="noreferrer" className="text-zinc-400 hover:underline">{d.website.replace(/^https?:\/\//, '')}</a> : d?.source_url}
              {f.source === 'fixture' && ' (recorded test page)'}
            </p>
          )}
        </Section>

        <Section title="Still unknown">
          {unknown.length === 0 ? <p className="text-sm text-zinc-500">Nothing outstanding.</p> : (
            <p className="text-sm text-zinc-400">{unknown.map(attrLabel).join(', ')}</p>
          )}
        </Section>

        <Section title={`Questions to ask (${questions.length})`}>
          {questions.length === 0 ? <p className="text-sm text-zinc-500">None.</p> : (
            <ul className="list-disc space-y-1 pl-5 text-sm text-zinc-300">
              {questions.map((qq) => <li key={qq.attribute}>{qq.question}</li>)}
            </ul>
          )}
        </Section>

        <Section title="Contacts">
          {(d?.contacts?.length ?? 0) === 0 ? (
            <p className="text-sm text-zinc-500">No named contact found on their site{d?.phone ? ` - main number ${d.phone}` : ''}.</p>
          ) : (
            <ul className="space-y-2">
              {d!.contacts.map((c) => (
                <li key={c.contact_id} className="rounded-md border border-zinc-800 px-3 py-2">
                  <div className="text-sm font-medium text-zinc-200">{c.full_name ?? 'Unnamed contact'}{c.role_title ? <span className="font-normal text-zinc-500"> - {c.role_title}</span> : null}</div>
                  <div className="mt-1 space-y-0.5 text-sm text-zinc-300">
                    {c.email && <div className="flex items-center gap-1.5 break-all"><Mail className="size-3.5 shrink-0 text-zinc-500" />{c.email}</div>}
                    {c.phone && <div className="flex items-center gap-1.5"><Phone className="size-3.5 shrink-0 text-zinc-500" />{c.phone}</div>}
                  </div>
                  <details className="mt-1 text-xs text-zinc-500">
                    <summary className="cursor-pointer hover:text-zinc-300">Where we found this</summary>
                    <p className="mt-1 italic text-zinc-400">"{excerpt(c.evidence_snippet, 240)}"</p>
                    <a href={c.source_url} target="_blank" rel="noreferrer" className="text-zinc-500 hover:underline">{c.source_url}</a>
                  </details>
                </li>
              ))}
            </ul>
          )}
        </Section>

        {draftMsg && (
          <Section title="Outreach draft">
            <div className="rounded-md border border-zinc-800 bg-zinc-950/50">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800/80 px-3 py-2 text-xs text-zinc-500">
                <span className="truncate text-zinc-300">{draftMsg.subject}</span>
                <span className="flex items-center gap-2"><Pill>Draft - not sent</Pill>{formatDateTime(draftMsg.created_at)}</span>
              </div>
              <pre className="max-h-72 overflow-y-auto whitespace-pre-wrap break-words px-3 py-2 font-sans text-sm leading-relaxed text-zinc-300">{draftMsg.body}</pre>
            </div>
          </Section>
        )}

        {inbound.length > 0 && (
          <Section title="Conversation">
            <div className="flex items-center gap-2 text-xs text-zinc-500"><FileText className="size-3.5" />{inbound.length} repl{inbound.length === 1 ? 'y' : 'ies'} <SimulatedPill /></div>
            <ul className="mt-2 space-y-2">
              {inbound.map((m) => (
                <li key={m.message_id} className="rounded-md border border-amber-900/40 bg-amber-950/10 px-3 py-2">
                  <div className="text-xs text-zinc-500">{formatDateTime(m.received_at ?? m.created_at)}</div>
                  <p className="mt-1 whitespace-pre-wrap break-words text-sm text-zinc-300">{m.body}</p>
                </li>
              ))}
            </ul>
            {f.thread && <button type="button" onClick={() => onThread(f.thread!.thread_id)} className="mt-2 text-xs text-sky-300 hover:underline">Open in Conversations</button>}
          </Section>
        )}
      </div>
    </aside>
  )
}

export { STATE, stateOf }
