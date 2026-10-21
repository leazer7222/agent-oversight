/**
 * Pure derivations for the sourcing workspace: turn the API payload into the
 * things Cameron thinks in - facilities, conversations, decisions, activity.
 *
 * No fetching here. No React here. Everything is a plain function over the
 * `/api/sourcing/operations` response so it is easy to test and reason about.
 * Technical identifiers (run ids, rule ids, model confidence) stay in the data
 * for the "details" disclosures but are never the headline.
 */

export type Research = {
  facility_id: string; name: string; facility_type: string; source: string; website: string | null
  distance_miles: number | null; pipeline_stage: string; triage_state: string | null
  channel_recommended: string | null; qualification_status: string | null; completeness: number | null
  known_count: number; unknown_count: number; contact_count: number
  open_questions: Array<{ attribute: string; question: string }>; updated_at: string
}
export type Contact = {
  contact_id: string; full_name: string | null; role_title: string | null; email: string | null
  phone: string | null; confidence: string; source_url: string; evidence_snippet: string; is_primary: boolean
}
export type Details = {
  facility_id: string; name: string; facility_type: string; website: string | null; phone: string | null
  source: string; source_ref: string | null; source_url: string | null; distance_miles: number | null
  pipeline_stage: string; attributes: Record<string, unknown>; attributes_confidence: Record<string, string>
  unknown_fields: string[]; contacts: Contact[]
  latest_qualification: null | {
    status: string; score: number; completeness: number
    score_breakdown: Record<string, any>; open_questions: Array<{ attribute: string; question: string }>
    disqualifiers: string[]; created_at: string
  }
}
export type Thread = {
  thread_id: string; facility_id: string; facility_name: string; state: string; last_intent: string | null
  subject: string | null; last_inbound_excerpt: string | null; last_inbound_at: string | null
  last_classification: null | Record<string, any>; outbound_count: number; inbound_count: number; updated_at: string
}
export type Message = {
  message_id: string; thread_id: string; facility_id: string; direction: 'outbound' | 'inbound'; status: string
  subject: string | null; body: string; sent_at: string | null; received_at: string | null; created_at: string
}
export type Draft = {
  message_id: string; thread_id: string; facility_id: string; facility_name: string; contact_name: string | null
  contact_email: string | null; subject: string | null; body: string; status: string; thread_state: string; created_at: string
}
export type NextAction = {
  action_type: string; priority: number; facility_id: string; facility_name: string; thread_id: string | null; detail: string
}
export type Run = {
  id: string; status: string; cost_usd: number | string | null; tokens_in: number | null; tokens_out: number | null
  started_at: string; completed_at: string | null; error: string | null; metadata: Record<string, any> | null
  agents: { company_id: string; name: string } | null
}
export type Ops = {
  company_id: string
  summary: Record<string, number>
  objective: Record<string, any>
  pipeline: Array<{ stage: string; facility_count: number }>
  recent_runs: Run[]
  recent_spend_usd: number
  research: Research[]
  drafts: Draft[]
  threads: Thread[]
  next_actions: NextAction[]
  facility_details: Details[]
  messages: Message[]
  errors: string[]
}

// ---------------------------------------------------------------------------
// Labels - plain English, consistent everywhere
// ---------------------------------------------------------------------------

export const STATE: Record<string, { label: string; tone: string; dot: string; explain: string }> = {
  contact_first: { label: 'Ready to contact', tone: 'text-emerald-300', dot: 'bg-emerald-400',
    explain: 'No blockers found and there is a verified way to reach someone.' },
  research_further: { label: 'Needs research', tone: 'text-amber-300', dot: 'bg-amber-400',
    explain: 'Looks plausible, but no verified contact route yet.' },
  not_currently_suitable: { label: 'Not a fit right now', tone: 'text-zinc-400', dot: 'bg-zinc-500',
    explain: 'Real, but a poor fit today (seasonal, competitor, or members-only).' },
  disqualified: { label: 'Ruled out', tone: 'text-rose-300', dot: 'bg-rose-400',
    explain: 'A hard requirement failed, such as outside instructors not being allowed.' },
}
export const UNTRIAGED = { label: 'Not assessed yet', tone: 'text-zinc-500', dot: 'bg-zinc-600', explain: 'Research has not run for this facility.' }

export function stateOf(s: string | null | undefined) { return (s && STATE[s]) || UNTRIAGED }

export const CHANNEL: Record<string, string> = {
  email: 'Email', phone: 'Phone call', facility_use_application: 'Facility-use application', none: 'No route yet',
}
export function channelLabel(c: string | null | undefined) { return CHANNEL[c ?? 'none'] ?? 'No route yet' }

export const TYPE: Record<string, string> = {
  hotel: 'Hotel', gym: 'Gym', aquatic_center: 'Aquatic center', recreation_center: 'Recreation center',
  hoa_community: 'HOA community pool', school: 'School / district', private_club: 'Private club',
  swim_school: 'Swim school', other: 'Other', unknown: 'Unknown type',
}
export function typeLabel(t: string | null | undefined) { return TYPE[t ?? 'unknown'] ?? titleCase(t ?? 'unknown') }

export const INTENT: Record<string, string> = {
  interested: 'Interested', not_interested: 'Not interested', more_info_requested: 'Asked a question',
  pricing_discussion: 'Talked about price', availability_discussion: 'Talked about availability',
  meeting_requested: 'Wants to meet', requires_owner_decision: 'Needs your decision',
  out_of_office: 'Out of office', unsubscribe: 'Asked not to be contacted', unknown: 'Unclear',
}
export function intentLabel(i: string | null | undefined) { return i ? (INTENT[i] ?? titleCase(i)) : 'Not yet classified' }

export const ACTION: Record<string, string> = {
  escalate: 'Needs your decision', auto_reply: 'Routine answer ready for review', close: 'No further action',
  follow_up: 'Follow up later', suppress: 'Stop contacting', review_escalation: 'Needs your decision',
  suppress_contact: 'Honour opt-out', review_proposed_reply: 'Review suggested reply',
  review_draft: 'Review draft', prepare_outreach: 'Ready to draft', research_further: 'Research further',
}
export function actionLabel(a: string | null | undefined) { return a ? (ACTION[a] ?? titleCase(a)) : '-' }

export const ATTR: Record<string, { label: string; unit?: string }> = {
  distance_miles: { label: 'Distance from Katy', unit: 'mi' },
  commercial_instruction_allowed: { label: 'Outside instructors allowed' },
  recurring_availability: { label: 'Recurring weekly slots' },
  indoor: { label: 'Indoor pool' },
  heated: { label: 'Heated' },
  pool_length_m: { label: 'Pool length', unit: 'm' },
  depth_ft: { label: 'Shallow-end depth', unit: 'ft' },
  hourly_rate_usd: { label: 'Hourly rate', unit: 'USD/hr' },
  lesson_capacity: { label: 'Students at once' },
  insurance_required: { label: 'Insurance certificate required' },
  revenue_share_possible: { label: 'Revenue share possible' },
  facility_use_application_url: { label: 'Facility-use application' },
}
export function attrLabel(k: string) { return ATTR[k]?.label ?? titleCase(k) }
export function attrValue(k: string, v: unknown): string {
  if (v === null || v === undefined) return 'Unknown'
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  const unit = ATTR[k]?.unit
  if (typeof v === 'number') {
    if (unit === 'USD/hr') return `$${v.toFixed(0)} / hr`
    return unit ? `${v} ${unit}` : String(v)
  }
  return String(v)
}
export const CONFIDENCE: Record<string, { label: string; tone: string }> = {
  verified: { label: 'Stated on their site', tone: 'text-emerald-300' },
  inferred: { label: 'Implied on their site', tone: 'text-amber-300' },
  unknown: { label: 'Unconfirmed', tone: 'text-zinc-500' },
}

export function titleCase(s: string) {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}
export function excerpt(s: string | null | undefined, n = 140) {
  if (!s) return ''
  const t = s.replace(/\s+/g, ' ').trim()
  return t.length > n ? t.slice(0, n - 1) + '…' : t
}
export function relTime(iso: string | null | undefined, now = Date.now()) {
  if (!iso) return ''
  const d = (now - new Date(iso).getTime()) / 1000
  if (d < 60) return 'just now'
  if (d < 3600) return `${Math.floor(d / 60)} min ago`
  if (d < 86400) return `${Math.floor(d / 3600)} h ago`
  return `${Math.floor(d / 86400)} d ago`
}

// ---------------------------------------------------------------------------
// Joined views
// ---------------------------------------------------------------------------

export type Facility = Research & {
  details: Details | null
  thread: Thread | null
  draft: Draft | null
  messages: Message[]
  nextAction: NextAction | null
  state: ReturnType<typeof stateOf>
}

export function buildFacilities(ops: Ops): Facility[] {
  const details = new Map(ops.facility_details.map((d) => [d.facility_id, d]))
  const threads = new Map(ops.threads.map((t) => [t.facility_id, t]))
  const drafts = new Map(ops.drafts.map((d) => [d.facility_id, d]))
  const msgs = new Map<string, Message[]>()
  for (const m of ops.messages) {
    const arr = msgs.get(m.facility_id) ?? []
    arr.push(m)
    msgs.set(m.facility_id, arr)
  }
  const actions = new Map<string, NextAction>()
  for (const a of [...ops.next_actions].sort((x, y) => x.priority - y.priority)) {
    if (!actions.has(a.facility_id)) actions.set(a.facility_id, a)
  }
  return ops.research.map((r) => ({
    ...r,
    details: details.get(r.facility_id) ?? null,
    thread: threads.get(r.facility_id) ?? null,
    draft: drafts.get(r.facility_id) ?? null,
    messages: (msgs.get(r.facility_id) ?? []).sort((a, b) => a.created_at.localeCompare(b.created_at)),
    nextAction: actions.get(r.facility_id) ?? null,
    state: stateOf(r.triage_state),
  }))
}

export type Conversation = {
  thread: Thread
  facility: Facility | null
  messages: Message[]
  latest: Message | null
  needsReview: boolean
  simulated: boolean
}

export function buildConversations(ops: Ops, facilities: Facility[]): Conversation[] {
  const byId = new Map(facilities.map((f) => [f.facility_id, f]))
  const msgs = new Map<string, Message[]>()
  for (const m of ops.messages) {
    const arr = msgs.get(m.thread_id) ?? []
    arr.push(m)
    msgs.set(m.thread_id, arr)
  }
  return ops.threads.map((t) => {
    const ms = (msgs.get(t.thread_id) ?? []).sort((a, b) => a.created_at.localeCompare(b.created_at))
    const c = t.last_classification ?? null
    const needsReview = t.state === 'escalated' || t.state === 'opted_out' ||
      c?.proposed_action === 'escalate' || c?.proposed_action === 'suppress' || c?.proposed_action === 'auto_reply'
    return {
      thread: t, facility: byId.get(t.facility_id) ?? null, messages: ms,
      latest: ms.length ? ms[ms.length - 1] : null, needsReview,
      simulated: ms.some((m) => m.direction === 'inbound' && (m.subject ?? '').startsWith('[SIMULATED]')) || t.state === 'draft',
    }
  }).sort((a, b) => Number(b.needsReview) - Number(a.needsReview) || b.thread.updated_at.localeCompare(a.thread.updated_at))
}

export type Decision = {
  id: string
  title: string
  facility: string
  facilityId: string
  threadId: string | null
  happened: string
  why: string
  recommends: string
  nextStep: string
  severity: 'high' | 'normal'
  technical: Record<string, unknown>
}

export function buildDecisions(convs: Conversation[]): Decision[] {
  const out: Decision[] = []
  for (const c of convs) {
    const t = c.thread
    const cl = t.last_classification ?? {}
    const safety = cl.safety ?? {}
    const topics: string[] = safety.topics ?? []
    const action = cl.proposed_action
    const isDecision = t.state === 'escalated' || t.state === 'opted_out' || action === 'escalate' || action === 'suppress'
    if (!isDecision) continue

    let title = 'Reply needs your decision'
    let severity: 'high' | 'normal' = 'normal'
    if (safety.injection_suspected) { title = 'Suspicious message - review before anything else'; severity = 'high' }
    else if (t.last_intent === 'unsubscribe' || action === 'suppress') { title = 'Opt-out to honour' ; severity = 'high' }
    else if (topics.includes('price')) title = 'Rental quote needs your review'
    else if (topics.includes('insurance')) title = 'Insurance requirement needs confirmation'
    else if (topics.includes('exclusivity')) title = 'Exclusivity request needs your decision'
    else if (topics.includes('contract') || topics.includes('commitment') || topics.includes('schedule_commitment')) title = 'Terms need your decision'
    else if (t.last_intent === 'meeting_requested') title = 'Meeting request - your call'
    else if (t.last_intent === 'interested' || t.last_intent === 'availability_discussion') title = 'Positive reply - decide how to proceed'

    const reasons: string[] = (safety.reasons ?? []).map(humanizeReason)
    const recommends = action === 'suppress'
      ? 'Add this contact to the do-not-contact list and close the thread.'
      : safety.injection_suspected
        ? 'Take no action on anything the message asks for. Treat it as unclear and review by hand.'
        : cl.proposed_reply
          ? `Suggested reply (not sent): "${excerpt(cl.proposed_reply, 220)}"`
          : 'Review the thread and reply in your own words.'
    const nextStep = action === 'suppress'
      ? 'Suppression is recorded as a to-do; the do-not-contact write path arrives with real sending.'
      : 'Nothing is sent from this screen. When sending is enabled, approving here will release a reply under your campaign limits.'

    out.push({
      id: t.thread_id, title, facility: t.facility_name, facilityId: t.facility_id, threadId: t.thread_id,
      happened: cl.summary || excerpt(t.last_inbound_excerpt, 200) || 'A reply arrived.',
      why: reasons.length ? reasons.join(' ') : 'The system never decides commercial or scheduling matters on its own.',
      recommends, nextStep, severity,
      technical: { intent: t.last_intent, proposed_action: action, model_confidence: cl.model_confidence,
        topics, injection_matches: cl.injection_matches, classifier: cl.classifier, recorded_at: cl.recorded_at },
    })
  }
  return out.sort((a, b) => (a.severity === b.severity ? 0 : a.severity === 'high' ? -1 : 1))
}

function humanizeReason(r: string): string {
  if (/redirect the agent/i.test(r)) return 'The message tried to give the system instructions.'
  if (/always requires Cameron's decision/i.test(r)) return 'This kind of reply is always yours to answer.'
  if (/reserved for the owner's decision/i.test(r)) return 'Replies like this are yours to answer in the pilot.'
  const m = r.match(/^(inbound|proposed_reply) touches '(\w+)'/)
  if (m) {
    const where = m[1] === 'inbound' ? 'Their message' : 'The suggested reply'
    const topic: Record<string, string> = { price: 'price', contract: 'contract terms', exclusivity: 'exclusivity',
      insurance: 'insurance', commitment: 'a commitment', schedule_commitment: 'a recurring schedule', credentials: 'your credentials' }
    return `${where} mentions ${topic[m[2]] ?? m[2]}.`
  }
  if (/unrecognised intent/i.test(r)) return 'The reply could not be classified confidently.'
  return r
}

export type Activity = {
  id: string; when: string; who: string; what: string; detail: string | null; cost: number; status: string
}

const WHO: Record<string, string> = {
  'facility-acquisition-controller': 'Acquisition Controller',
  'facility-researcher': 'Facility Researcher',
  'partnership-coordinator': 'Partnership Coordinator',
}

export function buildActivity(ops: Ops): Activity[] {
  return ops.recent_runs.map((r) => {
    const md = r.metadata ?? {}
    const s = md.summary ?? {}
    const agent = r.agents?.name ?? ''
    const who = WHO[agent.split('.').slice(1).join('.')] ?? agent.split('.').pop() ?? 'System'
    let what = 'Completed a step'
    let detail: string | null = null
    const n = (k: string) => Number(s[k] ?? 0)
    if (md.outcome === 'blocked') {
      what = 'Paused by a safety control'
      detail = md.blocked_category === 'agent_paused' ? 'This team member was paused, so its job was stopped before it started.'
        : `Stopped before starting: ${titleCase(String(md.blocked_category ?? 'control'))}.`
    } else if (r.status === 'failed') {
      what = 'A step failed and was queued to retry'
      detail = r.error ? excerpt(r.error.replace(/^\[[^\]]+\]\s*/, ''), 160) : null
    } else {
      switch (md.job_type) {
        case 'discover':
          what = `Researched ${n('found')} facilities`
          detail = n('inserted') ? `${n('inserted')} new, ${n('matched_existing')} already known.` : `All ${n('matched_existing')} already known - no duplicates created.`
          break
        case 'enrich':
          what = `Read ${n('enriched')} facility websites`
          detail = `${n('facts_written')} facts and ${n('contacts_written')} contact details recorded, each backed by text found on the page.${n('evidence_rejected') ? ` ${n('evidence_rejected')} unsupported claims rejected.` : ''}`
          break
        case 'qualify':
          what = `Assessed ${n('scored')} facilities`
          detail = `${n('contact_first')} ready to contact, ${n('research_further')} need research, ${n('disqualified')} ruled out.`
          break
        case 'draft_outreach':
          what = `Prepared ${n('drafted')} outreach drafts`
          detail = n('no_contact') ? `${n('no_contact')} facilities skipped - no email address on record.` : 'Nothing was sent.'
          break
        case 'poll_inbox':
          what = `Received ${n('replies_written')} simulated replies`
          detail = 'Scripted test replies, labelled as such.'
          break
        case 'classify_reply':
          what = `Read ${n('classified')} replies`
          detail = `${n('escalated')} need your decision${n('opt_outs') ? `, ${n('opt_outs')} asked not to be contacted` : ''}${n('injection_flagged') ? `, ${n('injection_flagged')} flagged as suspicious` : ''}.`
          break
        default:
          if (md.progress || md.decisions) {
            what = 'Reviewed progress and planned the next steps'
            const d = (md.decisions ?? []) as Array<Record<string, unknown>>
            const rec = d.find((x) => x.rule === 'expand_radius')
            detail = rec ? 'Recommended widening the search to 30 miles (recorded, not acted on).' : `${md.next_actions ?? 0} next actions on the list.`
          } else if (who === 'Facility Researcher') {
            what = 'Completed a research step'
          } else if (who === 'Partnership Coordinator') {
            what = 'Completed an outreach step'
          }
      }
    }
    return { id: r.id, when: r.started_at, who, what, detail,
      cost: typeof r.cost_usd === 'number' ? r.cost_usd : Number(r.cost_usd ?? 0), status: r.status }
  })
}

export type Overview = {
  goal: { target: number; secured: number; statusLine: string }
  researched: number; total: number; ready: number; conversations: number; replies: number; decisions: number
  questions: number; fixtures: number; spend: number
}

export function buildOverview(ops: Ops, convs: Conversation[], decisions: Decision[]): Overview {
  const o = ops.objective
  const secured = Number(o.secured ?? 0)
  const target = Number(o.target_partnerships ?? 1)
  const replies = convs.filter((c) => c.thread.inbound_count > 0).length
  const statusLine = secured >= target
    ? 'Goal reached.'
    : replies > 0
      ? `Not yet secured. ${replies} conversation${replies === 1 ? '' : 's'} in progress, ${decisions.length} waiting on you.`
      : Number(o.contact_first ?? 0) > 0
        ? `Not yet secured. ${o.contact_first} facilities are ready to contact.`
        : 'Not yet secured. Research is under way.'
  return {
    goal: { target, secured, statusLine },
    researched: Number(o.enriched ?? 0), total: Number(o.facilities_total ?? 0),
    ready: Number(o.contact_first ?? 0), conversations: convs.length, replies,
    decisions: decisions.length, questions: Number(o.open_questions_total ?? 0),
    fixtures: Number(o.facilities_fixture ?? 0), spend: Number(ops.recent_spend_usd ?? 0),
  }
}
