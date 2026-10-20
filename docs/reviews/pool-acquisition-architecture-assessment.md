# Independent Architecture Assessment: Cameron's Pool Acquisition System

Reviewer role: Principal AI systems architect / autonomous-agent engineer / senior PM / technical due diligence.
Review date: 2026-10-20
Repository reviewed: `leazer7222/agent-oversight`, worktree `claude/cameron-pool-acquisition-review-bbee99` at `dfab23b`
Live database inspected read-only: Supabase project `hdhovyrlnfojtkqbcegh`
Scope: assessment only. No application code, migration, database object, configuration, branch or deployment was modified.

## Evidence labels used throughout

| Label | Meaning |
|---|---|
| `[REPO]` | Verified by reading code or SQL in this repository, with a path |
| `[TEST]` | Verified by executing the test suite or a read-only probe script in this session |
| `[LIVE]` | Verified against the production Supabase project by read-only SQL in this session |
| `[DOC]` | Claimed in repository documentation; not independently verified here |
| `[EXT]` | Verified against an external provider's own documentation, with a link |
| `[ASSUMPTION]` | My inference, stated as such |
| `[REC]` | Recommendation |

What I ran: `python -m pytest agents/tests -q` -> `88 passed` `[TEST]`; a numeric probe of `scoring.qualify()` `[TEST]`; read-only SQL against production `[LIVE]`; the Supabase security advisor `[LIVE]`; provider documentation fetches `[EXT]`.

---

## A. Executive Verdict

**REJECT the proposed architecture as described. CONDITIONALLY APPROVE a revised architecture (Option D below), which is closer to what the repository already contains than to the proposal.**

The three decisive reasons:

**1. The proposal is a regression against work that is already built and tested in this repository.** The repo does not contain a greenfield. It contains a bounded, deterministic stage pipeline: a durable job queue with lease, heartbeat, bounded retry and cooperative cancellation (`supabase/migrations/049_swim_sourcing_schema.sql`, `050_swim_sourcing_rpcs.sql`) `[REPO]` `[LIVE]`; deterministic, LLM-free qualification scoring `[REPO]`; approval-gated, content-hash-bound sending with an explicit reconciliation protocol `[REPO]`; and 88 passing tests `[TEST]`. The repo's own audit recorded that there is "no agentic loop anywhere in this codebase" and treated that as a feature to preserve (`docs/swim-school-facility-sourcing-plan.md`) `[REPO]`. The proposed "autonomous Facility Acquisition Orchestrator" replaces a verified, inspectable state machine with LLM planning at precisely the point where planning adds the least: the next action in this pipeline is a pure function of row state (`discovered` -> enrich -> triage -> draft -> approve -> send -> await reply). There is no branch an LLM decides better than a `WHERE` clause.

**2. The system cannot control the stated outcome, and the autonomy is pointed at the wrong bottleneck.** The binding constraints today are not search throughput or coordination. They are: zero facilities in the database `[LIVE]`, zero contacts, zero stored tenant provider credentials `[LIVE]`, no Places API key `[REPO]`, no mailbox, no provisioned worker host `[DOC]`, and seven categories of business input that only Cameron can supply (rate ceiling, insurance posture, identity, FAQ, safety minimums). An orchestrator that "adapts research priorities" and "identifies bottlenecks" would, on day one, be reasoning over an empty table. The proposal spends its complexity budget on coordination between two agents that never need to negotiate, while the actual path to one signed pool partnership runs through Cameron's inputs and through facility owners' decision processes.

**3. The agent count is not supported by the economics, and one specific design choice in the proposal is the only thing in this whole system that can break the $100/month budget.** Total LLM work at the stated volume is small: a few hundred extraction, drafting and classification calls over 60 days, under $5/month at current model prices `[EXT]`. Fixed infrastructure dominates. But a continuously reasoning orchestrator is cost-unbounded by cadence: 288 wake-ups/day at roughly 15K input tokens each is about 4.3M input tokens/day, which is around $17/day on Opus-tier input pricing - over $500/month, five times the entire budget, to decide what a cron expression and an index decide for free `[EXT]` `[ASSUMPTION on token size]`. The proposal's own phrase "event-driven orchestrator rather than a continuously running LLM" is the right instinct; followed honestly, it terminates in a deterministic scheduler, which is Option C/D, not Option A.

What I am *not* saying: the specialist work is not real. Discovery, extraction, qualification, drafting and reply triage are all genuine problems, and two of them genuinely need an LLM. The objection is to modeling them as autonomous agents with an autonomous manager, rather than as stages with narrow AI capabilities inside them.

---

## B. Critical Findings, Ranked by Severity and Business Impact

Severity is judged by business consequence: harm to Cameron's reputation with prospects, cost, or a false picture of progress.

### B1. CRITICAL - "Campaign authorization" has no entity to authorize

The outreach autonomy model is built on campaign-level approval: Cameron approves a campaign, after which the system sends autonomously. `swim_sourcing.outreach_threads.campaign_id` is `NOT NULL`, and `approvals.subject_type` accepts `'campaign'` - but **there is no campaigns table** in the schema; the nine tables are facilities, facility_contacts, qualifications, outreach_threads, outreach_messages, approvals, meetings, suppression_list, jobs `[REPO]` `[LIVE]`. A campaign is therefore a free-floating UUID with no definition of scope, no bounded prospect list, no daily cap binding, no expiry and no revocation. The single most consequential human decision in the design - "you may now email strangers on my behalf" - is unrepresentable. Any approval row pointing at a `campaign` subject_id references nothing.

**Impact:** the authorization boundary that the entire safety argument rests on cannot be audited or revoked. `[REC]` Add a `campaigns` row with explicit scope (prospect id set or a frozen query), caps, start/end, and a revoked state; bind every send to it, and make the daily cap a property of the campaign rather than a function default.

### B2. CRITICAL - The spend ceiling is fail-open, and every live tenant is in the failing state

`public.check_tenant_budget()` returns `allowed = true, reason = 'no_limit_configured'` when `companies.cost_limit_usd IS NULL` `[REPO: 048_auth_and_tenant_credentials.sql]`. All three companies in production have `cost_limit_usd = NULL` `[LIVE]`. The worker's preflight comments and `docs/PLATFORM_HANDOFF.md` describe this as a "fail-closed spend ceiling" `[REPO]` `[DOC]`; the implementation is fail-open on exactly the misconfiguration that is currently universal.

Two further gaps in the same control: the ceiling sums `runs.cost_usd`, which agents **self-report** - an agent that reports nothing spends without limit - and it counts only LLM spend, so Places API calls, email and hosting are outside the cap entirely `[REPO]`.

**Impact:** the budget control is advisory in practice. `[REC]` Invert the default (`NULL` limit -> deny, with an explicit `unlimited` opt-in), move non-LLM spend into the same ledger or cap it structurally at the call site, and treat a run that completes with no cost report as a reportable defect.

### B3. CRITICAL - Scoring facilities before contact is close to vacuous, and the proposed model is worse than the one already built

This answers section 4 of the brief directly, with numbers. Discovery can know exactly one scored attribute from Places: distance `[REPO: discovery.py normalize_place]`. Everything that determines suitability - whether outside instruction is permitted, recurring availability, indoor/heated, length, shallow-end depth, rate, capacity, insurance - is explicitly marked unknown `[REPO]`.

Executed probe of the implemented model `[TEST]`:

| Input | Result |
|---|---|
| Distance 4.0 mi, verified; everything else unknown (exactly what discovery produces) | `score = 100.0`, `status = needs_info`, `completeness = 0.15` |
| One known good attribute only | `score = 100.0` |
| Distance 4.0 mi arriving on the column with no confidence entry | `score = 0.0` |

So the pre-contact score is either 100 or 0 depending on a provenance bookkeeping detail, and conveys no information about suitability. The implemented model is honest about this - it reports `completeness`, routes everything to `needs_info` below 0.45, and generates the question list - but the number itself should not be shown to Cameron as a ranking, and must never be a send threshold.

The proposed replacement model (Pool suitability and safety 30, Recurring availability 25, Economics 20, Location/demand 15, Partnership feasibility 10, outreach threshold 65/100) is a step backwards on four counts: (a) 55 of its 100 points are allocated to facts that are unknowable before contact, so the threshold is decided by priors; (b) it makes **safety a scoring category**, which is the one thing that must be an absolute gate - 30 points of unsafe is still unsafe; (c) a single number with a fixed cut-off creates exactly the false confidence the brief worries about, because it does not carry completeness; (d) it discards the `open_questions` machinery, which is the genuinely valuable output of pre-contact analysis.

### B4. HIGH - Scoring defect: a present value with unstated confidence drags the score down

`scoring.py` states as design rule 2 that "UNKNOWN IS NOT ZERO... It never silently scores as bad" `[REPO]`. But `contribute()` excludes an attribute from the denominator only when the **value** is absent; when the value is present and its confidence is unstated, the attribute is listed in `unknown_fields` *and* added to the denominator at a 0.0 confidence multiplier, earning zero `[REPO: scoring.py contribute]`. Measured: one verified good attribute scores 100.0; adding a second attribute whose confidence is unstated drops it to 66.7 `[TEST]`. The sibling test `test_value_without_stated_confidence_is_treated_as_unknown` only asserts membership in `unknown_fields`, so the suite passes while the documented rule is violated `[REPO]`.

**Impact:** enrichment output that omits a confidence key silently penalises good prospects - the precise failure the module was written to prevent. `[REC]` In `contribute()`, treat unstated confidence identically to a missing value: skip the denominator.

### B5. HIGH - Fixture data is written into the real pipeline labelled as Google Places data

When `GOOGLE_PLACES_API_KEY` is absent, the worker silently switches to recorded fixtures and upserts the results through `swim_upsert_facility` `[REPO: worker.py handle_discover]`. `normalize_place()` hard-codes `"source": "google_places"` regardless of transport `[REPO: discovery.py]`, and the schema's `source` CHECK includes a `'fixture'` value that no code path ever sets `[REPO: 049]`. The synthetic rows are name-prefixed `FIXTURE` `[REPO]`, which is a real mitigation, but provenance - the control the whole design leans on - is recorded falsely.

**Impact:** a production discovery run with a misconfigured key produces facilities that claim a Places origin, and the pipeline's audit trail becomes untrustworthy exactly where it is load-bearing. `[REC]` Set `source='fixture'` for fixture transport; make the fixture fallback opt-in (`use_fixtures: true` in the payload) and fail closed in a hosted environment.

### B6. HIGH - The swim worker emits no telemetry at all

The worker docstring claims steps "3. emit run_started to Agent Oversight" and "6. emit run_completed / run_failed" `[REPO]`. There is no import of `OversightClient` and no `/api/ingest` call anywhere in the file; `grep -n "Oversight\|run_started\|run_completed"` matches only the docstring `[REPO]`. It generates a `run_id` and never uses it. `AGENTS.md` makes `run_started`/`run_completed` mandatory for every agent at runtime `[REPO]`.

**Impact:** the one platform capability that is genuinely mature and operational - the run ledger, 182 runs live `[LIVE]` - is not connected to the new business pipeline. Cost attribution, the kill switch's visibility, error taxonomy and the cost-risk engine are all blind to swim-sourcing work. Also note the kill switch is only partly real here: preflight checks `agents.status` only when an `agent_id` is present in the payload or `SWIM_AGENT_ID` is set, and otherwise runs the job unchecked `[REPO: worker.py process_one]`.

### B7. HIGH - Exactly-once sending assumes a provider idempotency key that Gmail does not offer

The send protocol is well reasoned - durable `send_attempt_id` before the call, `pending_reconciliation` on ambiguity, never a blind retry `[REPO: send.py]`. But it passes `attempt_id` to the provider as "an idempotency header", and `MockMailbox.find_by_attempt_id` stands in for a lookup the comment describes as searching "for the custom header carrying this id" `[REPO]`. Gmail's `users.messages.send` has no idempotency-key parameter, and arbitrary custom headers are not searchable `[EXT: Gmail API reference]` `[ASSUMPTION: no idempotency key exists; verified absent from the method's documented parameters]`.

**Impact:** the reconciliation step - the thing that makes exactly-once real rather than aspirational - has no implementation path as designed, and the first real ambiguous failure would leave a message stuck in `sending` with no way to resolve it. `[REC]` Send `raw` MIME with a self-generated `Message-ID` derived from `send_attempt_id`, then reconcile with a Gmail search for `rfc822msgid:<that id>`. That is a supported, indexed lookup, and it also gives the thread a stable external identity.

Related: the daily cap is counted in memory (`SendStore.sent_today`) `[REPO]`, so it resets on every worker restart, and the default is 25/day in code against 15/day in the proposal `[REPO]`.

### B8. HIGH - Gmail scope reality differs from the plan, and it changes the MVP sequence

Verified against Google's own scope table `[EXT]`:

| Scope | Tier |
|---|---|
| `gmail.send` | **Sensitive** |
| `gmail.readonly` | **Restricted** |
| `gmail.modify` | Restricted |
| `gmail.compose` | Restricted |
| `gmail.metadata` | Restricted |

The existing plan states that both `gmail.send` and `gmail.readonly` are restricted `[REPO: plan section H]`. Sending is the *lighter* of the two; **inbox reading is the heavy one**, and it is the restricted scope that drags in a security assessment for a published external app. Internal (same-Workspace-domain) apps and domain-wide delegation remain the fast paths `[EXT, partially: Google's scope page documents the tiers and the Workspace/DWD requirement; the internal-app verification exemption is documented in Google's OAuth verification FAQ, which I did not fetch]`.

**Impact, and it is a favourable one:** a send-only MVP needs only a Sensitive scope, which is materially easier. `[REC]` Avoid `gmail.readonly` in v1 entirely: set `Reply-To` to an address at an email provider with inbound webhooks and ingest replies over HTTP. That removes the restricted scope, removes polling, removes `users.history.list` state management, and gives a cleaner injection boundary, at the cost of replies not landing in Cameron's own mailbox thread (which a BCC-to-self or forwarding rule mitigates).

Volume is not a constraint: Workspace allows 2,000 messages/day, 3,000 external recipients/day, with trial accounts at 500/day and increases requiring $100 paid and up to 75 days `[EXT]`. At 15/day the only email risk is reputation, not caps.

### B9. MEDIUM-HIGH - Places cost tier and caching terms: the implemented field mask costs more and earns a 5x smaller free allowance than necessary

`FIELD_MASK` in `discovery.py` requests `places.websiteUri` and `places.nationalPhoneNumber` `[REPO]`. Those two fields are **Enterprise** SKU for Text Search; everything else requested is Pro or Essentials `[EXT]`. A mixed-tier request is "billed at the highest SKU applicable" `[EXT]`. So every search request bills at Enterprise: $35.00/1,000 with a **1,000** free events/month cap, instead of Pro at $32.00/1,000 with a **5,000** free cap `[EXT]`.

`[REC]` Drop those two fields from the search, keep the search in Pro, and fetch website/phone with Place Details only for the shortlist. At the volumes here that is the difference between "free forever" and "free until someone raises the query count".

Caching: Google's policies state that "the place ID... is exempt from the caching restrictions" and may be stored indefinitely, while "You must not pre-fetch, cache, or store Places API content beyond the allowed exceptions" `[EXT]`. The implemented schema persists name, address, phone and website indefinitely with no TTL or refresh policy `[REPO: 049]`. `[REC]` Read the Maps Service Terms caching exception before the first live run, set a refresh/expiry policy against `source_fetched_at` (the column already exists), and treat `source_ref` as the only field safe to retain without limit.

### B10. MEDIUM - Operational substrate is thinner than the handoff implies

- Supabase is on the **Free** plan with auto-pause confirmed as the root cause of past 502/521 responses `[DOC]`, which makes a queue-polling worker intermittently fail in ways that look like application bugs. Branching is unavailable on the plan `[DOC]`.
- Daily backups and PITR are paid features; the completed backup covers the public schema, and the six private schemas have no logical backup because PostgREST cannot reach them and no direct connection string is configured `[DOC]`. The handoff lists "restore never rehearsed" as the single remaining limitation `[DOC]`.
- The repository cannot reproduce production: the migration ledger records a `021` with no file, and 024-046 are unrecorded `[DOC]`, which I corroborated - the ledger jumps from `023_estimation_accuracy_improvements` to `047_p0_0_database_hardening` `[LIVE]`.
- CI: `docs/PLATFORM_HANDOFF.md` says in section 10 that "CI does not run on GitHub" and in its final line that "CI runs on every push (`.github/workflows/ci.yml`)" `[REPO]`. The commit log shows the workflow was deliberately parked outside `.github/workflows` so the branch could ship (`f793d91`) `[REPO]`, and the file lives at `ci/github-workflow-ci.yml` `[REPO]`. The second claim is stale; no automated gate runs in front of a system intended to send email.
- The service-role key is the whole security boundary after 047, sits in Vercel env, on any agent host, and in plaintext in a gitignored local settings file, with rotation unaddressed `[DOC]`.

### B11. MEDIUM - Security posture is genuinely good, and I could verify the headline claim

Independently confirmed: migrations 047-052 are recorded in the production ledger `[LIVE]`; `swim_sourcing` exists with 9 tables `[LIVE]`; the Supabase security advisor returns **zero ERROR-level lints**, with one unrelated WARN (leaked-password protection, which does not apply to magic-link auth) `[LIVE]`. The auth design is sound on inspection: broad middleware matcher with explicit exemptions and `getUser()` rather than `getSession()` `[REPO: src/middleware.ts]`; tenant identity from `company_members` with a disagreeing `?company=` rejected rather than honoured `[REPO: require-tenant.ts]`; approvals bound to session identity and a content hash rather than a free-text `ratified_by` `[REPO: api/sourcing/approvals/route.ts]`; append-only triggers that bind the service role, which RLS cannot `[REPO: 049]`.

Two residual items: `requireTenant` falls back to `memberships[0]` when no company is requested, which is order-dependent across multiple memberships `[REPO]` - the repo's own lessons file warns against exactly this pattern for company lookups `[REPO: LESSONS_LEARNED.md]`; and the live app isolation result (13/13, including the cross-tenant 403) is a `[DOC]` claim I cannot re-verify, consistent with the live state showing one auth user and three admin memberships `[LIVE]` (the test's throwaway users are gone).

### B12. MEDIUM - The new agents do not meet this repository's own agent standard, and are not registered

`AGENTS.md` requires every agent to have a Supabase registry row, a `README.md` and an `agent.json` `[REPO]`. The four new agent directories have none of the three: no `agent.json`, no `README.md` `[REPO]`, and production still holds 25 agents with no swim/facility/outreach rows `[LIVE]`. `scripts/register_swim_sourcing.js` exists and dry-runs `[REPO]` `[DOC]` but has not been applied. There is also no `swim-school-tbd` company `[LIVE]`.

This is partly a labelling problem that supports the architectural argument: `scoring.py`, `discovery.py`, `safety.py` and `send.py` are **libraries with no entry point** - there is no `agent.py` in any of those directories `[REPO]`. They are capabilities. Calling them agents created five registry entries' worth of ceremony around four modules that the worker imports by file path.

### B13. LOW-MEDIUM - Suppression and opt-out have no write path

`swim_sourcing.suppression_list` exists with the right unique index `[REPO]`, `send()` checks it `[REPO]`, and `unsubscribe` is in `ESCALATE_ALWAYS` so an opt-out reply routes to a human `[REPO]`. But there is no API route to write a suppression (`src/app/api/sourcing/suppression` does not exist `[REPO]`), no reply-triage code at all, and the send path reads suppression from an in-memory `SendStore` rather than the table `[REPO]`. CAN-SPAM's 10-business-day window is comfortable, but the mechanism to honour an opt-out is currently manual SQL.

---

## C. Assumptions That Need Challenging

| # | Assumption | Status | Why it matters |
|---|---|---|---|
| C1 | One viable partnership in 60 days is a goal the system can be held to | **Unsupported** | Facility decisions are made by other organisations on their calendars. See section 3 response below. |
| C2 | Outreach volume is the constraint on the outcome | **Likely false** | The constraint is qualified-prospect supply (a 15-mile radius around Katy contains tens, not thousands, of lesson-capable pools) and Cameron's input latency. 15 emails/day would exhaust the entire market in under a week. |
| C3 | Email is the right primary channel | **Doubtful** | Aquatic directors at municipal, ISD and HOA facilities typically respond to phone calls and in-person visits; many publish only a generic info@ address. `[ASSUMPTION]` The highest-value week-one artifact is probably a **call sheet**, not an email campaign. |
| C4 | Google Places gives adequate coverage of lesson-capable pools | **Partly false, acknowledged** | The plan already flags HOA/residential absence `[REPO]`. Add: ISD natatoriums and municipal aquatic centers are discoverable but their access process is a facility-use application to a district or city, not an email thread; swim schools are competitors, not landlords. |
| C5 | A facility can be qualified before contact | **False** | Measured: pre-contact scores carry one bit of information (B3) `[TEST]`. |
| C6 | Instructor capacity, safety suitability and recurring availability are inferable | **False** | Shallow-end depth, lane availability at 4pm on Tuesdays, lifeguard requirements and deck supervision rules are not published anywhere. They require a phone call and then a site visit. |
| C7 | Autonomous replies save meaningful work | **False at this scale** | A few hundred contacts over 60 days yields a reply volume a human handles in minutes a day. Automating it trades minutes saved against the business relationship and against injection risk. |
| C8 | Cold email from a new domain will be delivered | **Risky** | A brand-new domain with no sending history, mailing strangers, is the classic path to spam placement. Needs warm-up, SPF/DKIM/DMARC, plain text, no tracking pixels, and low volume. |
| C9 | ~$100/month covers it | **Plausible, but driven by fixed costs** | See section J. LLM spend is a rounding error; infra and Workspace are the bill; an LLM planning loop is the one line item that can break it. |
| C10 | The platform is production-ready for an unattended business agent | **Partly** | Security: yes, verified `[LIVE]`. Operations: no - free-tier auto-pause, unbacked private schemas, no CI gate, unprovisioned worker host, no telemetry from the new worker (B6, B10). |
| C11 | Agent Oversight telemetry will give visibility into this business | **Not yet true** | The worker emits nothing (B6). |
| C12 | The 65-point threshold expresses a risk appetite | **False** | It expresses nothing until completeness is high; and the implemented threshold is 60 with a completeness floor, not 65 `[REPO]`. |

---

## D. Architecture Comparison

Scores are 1 (poor) to 5 (strong) for *this* problem at *this* scale, not in general.

| Criterion | A: Orchestrator + 2 specialists | B: Single goal-directed agent with tools | C: Deterministic workflow + selective AI | D: Recommended (C plus a human review loop and a call-first channel model) |
|---|---|---|---|---|
| Business outcome alignment | 2 - optimises throughput, not the real bottleneck | 2 - fastest to a demo, weakest at the regulated steps | 4 - matches the funnel's actual shape | **5** - adds the channel (phone) and the weekly decision that actually moves the outcome |
| Autonomy and adaptability | 4 - genuinely adaptive | 5 | 2 - adapts only where coded | 3 - adapts where it pays (copy, extraction, triage), not elsewhere |
| Reliability | 2 - non-deterministic control flow over irreversible actions | 1 - an agent holding a send tool is the top risk in the whole design | 5 - state machine, replayable | **5** |
| Engineering complexity | 2 - 3 registries, 2 inter-agent contracts, planner prompts and evals | 3 - simple to write, hard to constrain | 4 - mostly already written | **4** |
| Operating cost | 2 - cost scales with planning cadence (section J) | 3 | 5 | **5** |
| Observability | 3 - traces exist, but "why did it do that" is a prompt-archaeology question | 2 | 5 - every transition is a row | **5** |
| Security / injection posture | 3 - depends on the planner never holding a capability | 1 - inbound text reaches a tool-using loop | 5 - the model cannot act; a DB row authorises sends | **5** |
| Ease of testing | 2 - planner behaviour needs evals, not unit tests | 1 | 5 - 88 tests already pass `[TEST]` | **5** |
| Maintainability | 2 | 2 | 4 | **4** |
| Future reuse across businesses | 3 - agents are tenant-agnostic but the planner encodes this domain | 2 | 4 - stage descriptors plus config | **5** - the stage set is generic prospect sourcing; the schema is already the extraction seam `[REPO]` |
| **Total (50)** | **27** | **22** | **43** | **46** |

Notes on the two I did not choose:

- **A** is not absurd; it is premature. Autonomous planning pays off when the action space is large, the cost of a wrong action is low, and the state is too rich to encode. Here the action space is nine job types `[REPO]`, the cost of a wrong action is an email to a real business, and the state is nine tables. All three conditions point the other way.
- **B** is the worst fit despite being the easiest to build. A single goal-directed agent reading inbound email and holding a send tool merges the untrusted-input boundary with the capability boundary. The repo's own safety module makes the opposite argument explicitly and correctly: fencing is not a control, "THE MODEL CANNOT ACT" is `[REPO: safety.py]`.

---

## E. Recommended Architecture (Option D)

Same three physical pieces the repo already has - Postgres, a hosted worker, a Next.js operator surface - with the orchestrator demoted from an agent to a scheduler plus a policy table, and the specialists demoted from agents to capabilities.

```
   Cron (Railway schedules)            Operator UI (/dashboard/sourcing)
            |                                     |
            v                                     v
   public.swim_enqueue_job()            approvals, campaigns, call outcomes
            |                                     |
            +------------------+------------------+
                               v
                swim_sourcing.jobs  (lease, heartbeat, retry, cancel)   [EXISTS]
                               |
                               v
        +----------------------------------------------------------+
        |  Worker: claim -> preflight -> handler -> finish          |
        |  (telemetry to /api/ingest on every job: MISSING today)   |
        +----------------------------------------------------------+
            |            |             |            |           |
         discover     enrich        triage        draft       intake
         (Places,     (website      (rules,       (template   (inbound
          no LLM)      fetch +       no LLM)       + LLM       webhook,
                       LLM extract                 slot copy)  then LLM
                       w/ evidence)                            classify
                                                               -> proposal)
                               |
                               v
                     send  (approval row + content hash + campaign + suppression
                            + Message-ID idempotency; no LLM in this path)
```

**Component responsibilities and autonomy boundaries**

| Component | Decides autonomously | Requires a human | AI involved |
|---|---|---|---|
| Scheduler (cron + `swim_enqueue_job`) | when stages run | nothing | none |
| `discover` | which queries, which results pass the radius/dedup filters | nothing | none |
| `enrich` | which page to fetch, which contacts/facts to extract | nothing (writes are proposals with evidence) | **yes** - extraction with verbatim evidence spans, rejected if the span is absent from the fetched HTML |
| `triage` | eligibility gates, bucket assignment, question list | nothing | none (deterministic) |
| `draft` | nothing - produces a draft row | **approval to send** | **yes** - slot copy inside a fixed template |
| `send` | ordering, pacing, retry/reconcile | campaign + message approval | none |
| `intake` | parsing, threading | nothing | none |
| `classify` | intent, proposed next action | any send; any commercial topic | **yes** - classification only, output is a proposal row |
| `call sheet` | prioritisation | the call itself | none |
| Scheduling | nothing | Cameron books, or sends a booking link | none |

Three invariants, all of which the repo already implements and which I would not relax:

1. **No LLM output ever becomes an action.** Sends read an `approvals` row written by an authenticated session, whose `approved_sha256` must equal the hash of the exact bytes `[REPO]`. Keep this.
2. **Inbound text is data.** Fence it, log injection matches, escalate on any match, and let the rule layer - not the model - decide escalation `[REPO: safety.py]`. Keep this.
3. **Provenance or it did not happen.** Every stored fact carries source, URL, fetch time, confidence; unknown is representable `[REPO: 049]`. Keep this, and fix B5 so it is true in the fixture path too.

What I would add that is not there: a **campaigns** entity (B1), **telemetry** in the worker (B6), a **call-outcome log** (phone is a first-class channel, section C3), and a **weekly review view** that shows the funnel with denominators.

---

## F. Revised Facility Qualification Model

Replace "one weighted score with a threshold" with a four-part structure. Each part answers a different question and is computed from a different information set.

### F1. Hard eligibility gates - absolute, never scored

A gate failure disqualifies regardless of everything else, and **safety belongs here, not in the score**:

- Commercial instruction by an outside instructor is prohibited -> disqualified.
- Outside the travel radius -> disqualified.
- No shallow area usable by children under 8 -> disqualified (requires contact or inspection).
- Required insurance/certification that Cameron does not hold and will not obtain -> disqualified.
- Rate above her stated ceiling, or terms she has excluded -> disqualified.
- **Any safety condition unmet after an on-site check** -> disqualified. Not 30 points. A gate.

The implemented model already treats distance, prohibited instruction, minimum length and rate ceiling as absolute disqualifiers `[REPO]`. Extend, do not replace.

### F2. Pre-contact triage - priors and contactability, not suitability

Before contact, do not pretend to score suitability. Sort into three buckets using only what is actually known (category, distance, whether an indoor pool is evidenced, whether a named contact with on-page evidence exists, access-process class):

- **Call first** - category prior is good and a named contact or direct phone exists.
- **Email first** - only a generic address exists, or the access path is a published facility-use process.
- **Research more** - no contact evidence; needs a human look or a different source.

Publish the **completeness ratio and the question list**, not a 0-100 number. The existing `OPEN_QUESTIONS` map is the single most useful artifact in the current code: it doubles as the body of the first message and as the call script `[REPO]`.

### F3. Post-contact viability - scenarios, not a point score

Once a rate, a slot pattern and a capacity are known, viability is arithmetic, and it should be presented as scenarios because every input is uncertain:

```
contribution per slot = (students per slot x price per student)
                        - instructor cost - facility cost per slot - travel/overhead
```

Run three scenarios (conservative / expected / optimistic) over fill rate and slot count, and report break-even fill rate and monthly contribution at expected fill. A facility that needs 90 percent fill to break even is a different decision from one that breaks even at 40 percent, and a single weighted score cannot express that difference. This directly answers brief item 4.10: yes, use scenarios.

### F4. Category-specific access models

One qualification model does not fit these five categories, because the *decision process* differs more than the pool does:

| Category | Who decides | Realistic path | Typical cycle |
|---|---|---|---|
| Hotel with indoor pool | GM or director of ops | email/call, commercial-use and liability questions dominate | weeks |
| Gym / private club | club manager, sometimes a regional office | call; may conflict with their own programming | weeks |
| Municipal aquatic center | parks and rec facility coordinator | facility-use application, fee schedule, sometimes council approval | weeks to months |
| ISD natatorium | district athletics/facilities office | formal facility-use agreement, insurance certificate, board policy | months, calendar-bound |
| HOA community pool | volunteer board | introduction via a resident; board meeting cadence | months, not discoverable via Places |

`[ASSUMPTION]` - these are my expectations for the Katy market, not repository or provider facts. They are worth validating in week one precisely because they determine where effort goes. The actionable consequence: **weight the first 60 days toward hotels, gyms and private clubs**, where a single operator can say yes, and treat municipal/ISD/HOA as a pipeline for month three and beyond.

### F5. How unknowns affect the model

- Unknown never contributes, positively or negatively (fix B4 so this is true).
- Unknown generates a question and raises the facility's position in whichever contact channel can answer it fastest.
- Status stays `needs_info` below a completeness floor and may never become `qualified` `[REPO]` - keep this, it is the right call.
- Nothing is ever inferred into a field. Already enforced for discovery `[REPO]` `[TEST]`; must be enforced for enrichment via the evidence-span check.

---

## G. Revised Outreach and Conversation Policy

Judgement against the proposed settings:

| Proposed | Verdict | Revised |
|---|---|---|
| Autonomous initial outreach after campaign authorization | **Conditionally reject** | Supervised for the first batch: Cameron reads and approves each of the first 10-15 messages individually. Then campaign-scoped autonomy with a bounded prospect list, a cap, and a revoke switch (B1). |
| Max 15 initial emails/day | **Reject as too high for this market** | 5-8/day. The addressable set within 15 miles is small; burning it in a week on a cold domain is the worst available trade. Volume caps should bind on the campaign, not a function default (B7). |
| Min qualification score 65 | **Reject** | No score gate. Gate on: eligibility gates passed, a contact with on-page evidence, not suppressed, not previously contacted, inside the campaign's prospect list. |
| Max 3 follow-ups, days 4/10/18 | **Accept with conditions** | Keep the cadence; cap at 2 for silent prospects, and stop immediately on any negative or ambiguous signal. A third follow-up to a non-responder is where cold outreach starts to cost reputation. |
| Autonomous routine replies | **Reject for v1** | All replies produce a proposal with a suggested answer; Cameron or an operator approves with one click. Revisit after 30 days of logged classifications, with measured precision. The reply volume here is tens, not thousands - automation buys minutes and risks the relationship. |
| Meeting proposals drafted for Cameron | **Accept** | Better: send a booking link she controls. Skip the Calendar integration entirely in v1 (section I). |
| No autonomous contractual or financial commitments | **Accept, strongly** | Already enforced by rule, not by prompt `[REPO: safety.py ESCALATE_ALWAYS and COMMITMENT_PATTERNS]`. Keep the deterministic gate and the DB-level restriction on action types. |

**Personalization:** mostly deterministic. A fixed template with slots (facility name, facility type, the two or three specific questions drawn from `OPEN_QUESTIONS` for that facility, one evidenced detail such as "your indoor pool" where the evidence exists) plus at most one LLM-written sentence. Deterministic templates are more reviewable, cheaper, more consistent and less likely to invent a claim. Every LLM-written draft passes `assert_no_fabrication()` before it can be approved `[REPO]`.

**What the agent may say about Cameron's business:** only values from her confirmed configuration. `assert_no_fabrication()` already refuses experience claims, insurance claims, credentials, guarantees, superlatives, budget and authority claims unless the corresponding fact was supplied `[REPO]` `[TEST]`. That default-refuse posture is correct and should extend to: student counts, years in operation, number of instructors, references, and anything about other facilities.

**Deliverability and compliance**

- Dedicated domain, SPF + DKIM + DMARC before the first send; warm up by volume over two weeks.
- Plain text or near-plain HTML, no tracking pixels, no link shorteners, a real human signature, a reply-to that a human reads.
- CAN-SPAM: accurate From and Subject, Cameron's physical postal address, a working opt-out honoured within 10 business days, suppression checked before every send `[REC: build the suppression write path, B13]`.
- Keep targeting inside Texas; CASL/GDPR change the consent analysis if Canadian or EU recipients enter the list.

**Reply classification reliability:** treat it as unproven. There is no classifier code in the repo at all - only the intent list and the escalation rules `[REPO]`. Measure precision on 50 real replies before granting it any autonomy, and make `unknown` the cheap default (already the design `[REPO]`).

**Prompt injection:** the current posture is the right one and is tested `[TEST: 30 outreach-safety tests]`. Strengthen it by (a) ingesting inbound mail through a webhook rather than a mailbox read, so the untrusted text never passes through a credential-bearing client, and (b) storing the raw inbound body and the fenced body separately, so a reviewer can always see what arrived.

**Duplicate prevention:** `ux_thread_facility_campaign`, `ux_msg_send_attempt`, `ux_msg_provider_message` and the suppression unique index are all correct and already in place `[REPO: 049]`. Add the Message-ID reconciliation path (B7) and count the daily cap from the table rather than memory.

---

## H. Repository Gap Assessment

### Implemented and tested (unit level; no live dependency)

| Component | Path | Evidence |
|---|---|---|
| Deterministic qualification scoring | `agents/library/facility-qualification-agent/scoring.py` | 19 tests pass `[TEST]`; one defect B4 |
| Places discovery with provenance and a structural request ceiling | `agents/library/facility-discovery-agent/discovery.py` | 20 tests pass `[TEST]`; fixtures only, no API key |
| Outreach safety rails (injection, commitment escalation, anti-fabrication) | `agents/library/outreach-agent/safety.py` | part of 30 tests `[TEST]` |
| Send protocol with approval hash, suppression, cap, reconciliation | `agents/library/outreach-agent/send.py` | part of 30 tests `[TEST]`; mock transport only; B7 |
| Tenant credential vault, env scrubbing, fail-closed resolution | `agents/lib/credentials.py` | 17 tests pass `[TEST]`; 13/13 live `[DOC]` |
| Route authorization gate, secret scanner | `scripts/tests/check_route_authorization.py`, `check_no_secrets.py` | `[DOC]` 415/499 checks, self-tested |

### Implemented and applied, but not integration-tested with real data

| Component | Path | Evidence |
|---|---|---|
| `swim_sourcing` schema, 9 tables, RLS, append-only triggers | `supabase/migrations/049_swim_sourcing_schema.sql` | applied `[LIVE]`; **0 rows in every table** `[LIVE]` |
| Durable queue RPCs (claim/heartbeat/finish/reap/enqueue/cancel + facility and qualification writers) | `050_swim_sourcing_rpcs.sql` | applied `[LIVE]`; 0 jobs ever recorded `[LIVE]` |
| Auth middleware, `requireTenant`, admin guard | `src/middleware.ts`, `src/lib/auth/require-tenant.ts`, `require-admin.ts` | code reviewed `[REPO]`; live 13/13 `[DOC]`; B11 residuals |
| Approvals route | `src/app/api/sourcing/approvals/route.ts` | reviewed `[REPO]`; never exercised (0 approvals `[LIVE]`) |
| Facilities and operations read routes, sourcing dashboard | `src/app/api/sourcing/{facilities,operations}/route.ts`, `src/app/dashboard/sourcing/page.tsx` | reviewed `[REPO]`; renders against empty data |
| Database hardening and tenant credential vault schema | `047`, `048` | applied `[LIVE]`; advisor clean `[LIVE]` |

### Mock-only

| Component | Note |
|---|---|
| Email delivery | `MockMailbox` in `send.py`; no Gmail or provider client exists `[REPO]` |
| End-to-end pipeline | `agents/tests/test_end_to_end.py` - in-memory store, recorded fixtures, mock mailbox; its own docstring states what it does not prove `[REPO]` |
| Discovery against live Places | fixtures only; no `GOOGLE_PLACES_API_KEY` `[REPO]` |

### Incomplete

| Component | Gap |
|---|---|
| Worker job coverage | `HANDLERS` implements 2 of the 9 job types the schema allows: `discover`, `qualify`. Missing: `enrich`, `draft_outreach`, `send_outreach`, `poll_inbox`, `classify_reply`, `schedule_meeting`, `reconcile_sends` `[REPO: worker.py]` |
| Worker telemetry | none, despite the docstring and `AGENTS.md` (B6) |
| Kill switch coverage | only enforced when an agent id is resolvable (B6) |
| Fixture provenance | fixture rows labelled `google_places` (B5) |
| Budget enforcement | fail-open on NULL limit; every live company NULL (B2) |
| Agent standards | no `agent.json`, no `README.md` in the four new agent directories; not registered in production (B12) |
| Approvals surface | POST only; no GET; no suppression, discovery-trigger, threads or credentials routes (B13) |
| CI | workflow exists at `ci/github-workflow-ci.yml`, parked outside `.github/workflows` (`f793d91`); handoff self-contradicts (B10) |

### Missing

Contact enrichment (`enrich.py` is referenced by the plan but does not exist) - Gmail or any email client - inbound ingestion - reply triage agent - scheduling agent and Calendar client - outreach draft generation - **campaigns entity** (B1) - call-outcome logging - hosted worker (Railway config written, not provisioned `[DOC]`) - Places API key - Workspace mailbox and domain - `CREDENTIAL_ENCRYPTION_KEY` in a deployment env - Cameron's tenant company, agents and stored Anthropic key (0 credentials live `[LIVE]`) - logical backup of the six private schemas `[DOC]` - rehearsed restore `[DOC]`.

**Reuse verdict:** roughly 60 percent of the pipeline's non-integration code exists and is worth keeping unchanged, which matches the earlier audit's estimate `[DOC]`. The reusable core is: the queue and its RPCs, the schema, the scoring module (with B4 fixed), the safety module, the send protocol (with B7 re-implemented against a real provider), the credential vault, the auth layer, and the telemetry SDK that the new worker has not yet been wired to.

---

## I. MVP Scope and Implementation Sequence

The first release is trying to do too much. The parts that generate business value in week one need neither autonomy nor email.

### Phase 0 - Unblock (days, mostly not engineering)

Dependencies for everything: Cameron's business identity and postal address; her commercial boundaries (rate ceiling, revenue share, insurance posture); her safety minimums; the pre-approved FAQ; her Anthropic key stored in the vault; a Places API key with the field mask corrected to Pro (B9); `CREDENTIAL_ENCRYPTION_KEY` set; the tenant company and agents registered with a real `cost_limit_usd` (B2, B12).

Engineering in parallel, all small: fix B4 (scoring denominator), B5 (fixture provenance), B2 (budget default), B6 (worker telemetry), and B1 (campaigns table) - the last one before any send path is written.

### Phase 1 - The list and the questions (the real MVP)

Deliverable: **a ranked, sourced worksheet of real Katy-area facilities, each with the specific questions that would qualify it, and a recommended channel.** Stages: `discover` (live Places), `enrich` (website fetch + evidence-bound extraction), `triage` (gates + buckets + question list). Surfaces: the sourcing dashboard plus a CSV/print view Cameron can work from on the phone.

**First meaningful end-to-end demonstration:** 20 or more distinct real facilities, every row traceable to a Places `place_id` and a fetched URL, zero invented contacts, each row carrying its open questions and its bucket - and a re-run that creates zero duplicates. No email is sent in this phase. This proves the expensive-to-verify half of the system (provenance discipline, dedup, the question generator) while risking nothing externally.

### Phase 2 - Supervised outreach

Campaigns table, draft generation, individual approval for the first 10-15 messages, send via a real provider with Message-ID idempotency (B7), suppression write path (B13), CAN-SPAM footer, 5-8/day cap bound to the campaign, daily cap counted from the table.

**Readiness for a supervised pilot** (all required): Phase 1 delivered with real data; campaigns entity in place; approval-to-hash binding exercised end to end against the real schema; suppression enforced from the table; sender domain authenticated (SPF/DKIM/DMARC); CAN-SPAM footer with a real address; the injection and idempotency tests running in CI on GitHub; worker telemetry visible in the run ledger; budget cap populated and fail-closed.

### Phase 3 - Inbound and triage

Inbound webhook (not `gmail.readonly`, B8), raw+fenced storage, classification producing proposals, one-click human approval of replies, follow-up scheduler for days 4 and 10.

**Readiness for autonomous outreach** (in addition to the pilot list): 30 days of supervised operation; a measured classification precision on at least 50 real replies; zero fabrication or unapproved-send incidents; a hosted worker that survives a `kill -9` with the reaper returning the job (the mechanism exists `[REPO]`, the proof does not); a database that does not auto-pause; a rehearsed restore; and a revocable campaign with a working kill switch exercised at least once.

### Phase 4 - Deliberately deferred

Calendar integration (send a booking link instead), autonomous negotiation beyond the FAQ, HOA and county-record sourcing, third-party contact enrichment, SMS, learned weights, conversion analytics, and any cross-business generalisation. Each is justifiable later; none is on the path to the first partnership.

### Dependency order

```
Phase 0 inputs ----+
                   |
Places key --> discover --> enrich --> triage --> WORKSHEET (Phase 1 demo)
                                          |
campaigns + domain auth + provider -------+--> draft --> approve --> send (Phase 2)
                                                                      |
                                        inbound webhook --> classify --> propose (Phase 3)
```

---

## J. Cost and Complexity Assessment

### Fixed, monthly

| Item | Cost | Note |
|---|---|---|
| Supabase Pro | ~$25 | `[EXT, third-party sources; supabase.com/pricing not fetched]`. Needed to stop free-tier auto-pause breaking an unattended worker `[DOC]`, and to get daily backups. Alternative: stay free and add a keep-warm ping, accepting no backups and known intermittent failures. |
| Railway Hobby (worker + cron) | ~$5 | `[EXT, third-party/forum sources]`, includes $5 of usage |
| Google Workspace, 1 mailbox | ~$7-14 | `[ASSUMPTION]`; not verified against Google's price list |
| Domain | ~$1-2 amortised | |
| Vercel | $0 | existing hobby deployment `[DOC]` |
| **Fixed subtotal** | **~$38-46** | |

### Usage-based, at the recommended volume

| Item | Estimate | Basis |
|---|---|---|
| Places Text Search | **$0** if kept under the free cap | Pro: 5,000 free events/month at $32/1,000 after; Enterprise: 1,000 free at $35/1,000 `[EXT]`. 8 queries/run, daily, is ~240/month - free either way, but the current Enterprise-tier field mask leaves only a 1,000-event margin (B9) |
| Place Details for the shortlist | a few dollars at most | ~100-200 lookups/month |
| LLM - enrichment extraction | ~$0.30 | ~200 facilities x ~10K input / ~1K output on Haiku 5.5 at $0.10/$0.50 per MTok `[EXT]` |
| LLM - drafting | ~$1 | ~100 drafts x ~2K input / ~0.5K output on Sonnet 5.5 at $2/$10 per MTok `[EXT]` |
| LLM - reply classification | under $1 | tens of replies |
| Email sending | $0 | inside the Workspace mailbox; 2,000/day limit `[EXT]` |
| **Usage subtotal** | **under $5** | |

**Total: roughly $43-51/month**, comfortably inside $100, with the headroom sitting in infrastructure rather than AI.

### The cost driver nobody expects

The single line item that can break the budget is **planning cadence x model tier**, not volume. A reasoning orchestrator woken every 10 minutes at ~15K input tokens per wake-up is ~4.3M input tokens/day; on Opus-tier input pricing that is roughly $17/day, over $500/month `[EXT prices; ASSUMPTION on token size]`. The same loop on Haiku is roughly $13/month. A deterministic scheduler is $0. This is the clearest quantitative case against Option A: the orchestrator's entire cost is a function of a decision - "how often should I think?" - that has no business justification, because the pipeline's next action is already written in the `jobs` table.

### Unnecessary LLM calls to eliminate by design

- Any LLM in the control flow (which job runs next) - it is a query.
- Any LLM in scoring or gating - already correctly arithmetic `[REPO]`.
- Any LLM in the send path - already correctly absent `[REPO]`.
- Any LLM re-reading a page that has not changed - cache by `source_fetched_at` and content hash.
- Per-message rewriting of boilerplate - template with slots; one LLM sentence at most.
- Any LLM "strategic recommendation" produced on a cadence rather than on demand. A weekly funnel summary with denominators is a SQL view; have the LLM comment on it only when Cameron asks.

### Complexity

Option D's incremental engineering is small because the hard parts exist: a campaigns table and route, one provider client with Message-ID reconciliation, one inbound webhook, two more worker handlers, enrichment with evidence checking, telemetry wiring, and five defect fixes. Option A would add, on top of all of that, a planner prompt, a planner eval suite, inter-agent contracts, three more registry entries and a new class of failure ("the planner decided something strange") that unit tests cannot cover.

---

## K. Decisions Required

### Business decisions - Cameron only

| # | Decision | Why it blocks |
|---|---|---|
| K1 | Legal/trading name, physical postal address, phone, how she wants to be described | CAN-SPAM requires the address; `swim-school-tbd` cannot email anyone `[REPO]` |
| K2 | Maximum hourly rate acceptable without asking; is revenue share acceptable | Sets a hard gate and the viability scenarios (F1, F3) |
| K3 | Actual insurance and certification posture, stated as fact | `assert_no_fabrication()` refuses any claim she has not supplied `[REPO]` |
| K4 | Non-negotiable safety minimums (shallow-end depth, water temperature, supervision, deck rules) | These become gates, not score points (F1) |
| K5 | Is a phone-first channel acceptable, and who makes the calls | Determines whether Phase 1's deliverable is a call sheet or an email list (C3) |
| K6 | Pre-approved FAQ answers | The only content any automated reply could ever use |
| K7 | Is exclusive access required or is shared acceptable per facility type | Changes which categories are worth pursuing |
| K8 | Approve supervised-first outreach (individual approval for the first 10-15) rather than immediate campaign autonomy | The safety recommendation in G |

### Technical decisions - the development team

| # | Decision | Recommendation |
|---|---|---|
| K9 | Architecture: A, B, C or D | **D.** Deterministic pipeline, AI at three narrow points, human in the loop on sends and replies |
| K10 | Supabase Free + keep-warm, or Pro at ~$25 | **Pro** before any unattended operation; auto-pause is a documented production failure mode `[DOC]` |
| K11 | Inbound channel: `gmail.readonly` polling, or a provider inbound webhook | **Webhook.** Avoids the restricted scope entirely (B8) and is a cleaner injection boundary |
| K12 | Send path: Gmail API from a Workspace mailbox, or an email API (the repo already has `resend` installed and unused `[REPO]`) | Either; **Gmail from Workspace** keeps the thread in Cameron's mailbox, and `gmail.send` is only Sensitive (B8). Decide before writing the client |
| K13 | Worker host | Railway config already written `[REPO]`; provision it |
| K14 | Fix the five defects (B2, B4, B5, B6, B7) before or after Phase 1 | **Before.** All are small; B6 and B2 are the difference between operating blind and operating observably |
| K15 | Campaigns entity now or later | **Now**, before any send code (B1) |
| K16 | Get CI actually running on GitHub | Required before autonomous sending; the workflow exists and is parked (B10) |
| K17 | Migration ledger drift and private-schema backups | Not on the critical path for Cameron, but it is what makes any future replay or restore possible `[DOC]` |

---

## L. Final Recommendation

**What I would build.** A deterministic, queue-driven prospect pipeline on the schema and queue that already exist, with AI at exactly three points: extracting facts and contacts from facility websites with verbatim evidence, writing one sentence of a templated email, and classifying inbound replies into a proposal a human approves. One hosted worker, one cron, one operator surface. A campaigns entity that makes "you may send" a revocable, bounded, auditable fact. Phone treated as a first-class channel, because for municipal, ISD and HOA pools it is the channel that works. The first deliverable is a sourced worksheet of real Katy facilities with per-facility questions - valuable to Cameron on day one, and it risks nothing outside the building.

**What I would deliberately not build.** An autonomous orchestrator - the next action is a query, and a reasoning loop on a cadence is the only way this system can exceed its budget by an order of magnitude. Two "specialist agents" - they are four library modules with no entry points, and the registry ceremony around them buys nothing. Autonomous replies in v1 - the volume is tens of messages, the saving is minutes, and the downside is a misrepresentation to the exact person Cameron is trying to win over. Calendar integration - a booking link is better and free. A 100-point pre-contact score - measured, it carries one bit; the question list it implies is the actual product. And no pursuit of HOA or multi-market coverage until one partnership exists.

**The honest read on the objective.** "One recurring pool partnership within 60 days" is a reasonable business aspiration and a poor system specification, because the system does not get a vote on a facility manager's decision. I would hold the system to supply, speed and integrity - qualified prospects contacted, questions answered, no fabricated facts, no unapproved sends, no duplicate contacts, a measured response rate with honest denominators - and hold the *partnership* as a forecast reviewed weekly with Cameron. Specifically, for section 3 of the brief: track **contact-rate** (prospects with an evidenced decision-maker / prospects discovered), **response rate**, **qualified-conversation rate** (replies that answered at least the permission and availability questions), **site-visit rate**, and **terms-received rate**. Those five are controllable, measurable from week one, and they make the 60-day question answerable with evidence instead of hope. If after three weeks the discovered universe inside 15 miles is exhausted and the response rate is low, the correct response is to expand the radius and add the phone channel - a decision for Cameron at a weekly review, not an inference for an orchestrator at 2 a.m.

**Verdict restated.** Reject Option A. Approve Option D subject to K1-K8 from Cameron and K9-K16 from the team, with the five defects fixed and the campaigns entity in place before a single external email is sent.

---

## Sources

Repository and live-database evidence is cited inline by path. External verification:

- [Gmail API OAuth scopes (tier classification)](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Google Maps Platform pricing (Places API New SKU rates and free caps)](https://developers.google.com/maps/billing-and-pricing/pricing)
- [Places API data fields to SKU mapping](https://developers.google.com/maps/documentation/places/web-service/data-fields)
- [Places API usage and billing (highest-SKU rule)](https://developers.google.com/maps/documentation/places/web-service/usage-and-billing)
- [Places API policies (place ID caching exemption)](https://developers.google.com/maps/documentation/places/web-service/policies)
- [Gmail sending limits in Google Workspace](https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace)
- Claude model pricing (Haiku 5.5 $0.10/$0.50, Sonnet 5.5 $2/$10, Opus 5.5 $4/$20 per million tokens) - from the bundled `claude-api` reference in this session
- Supabase Pro and Railway Hobby pricing - third-party summaries only, not the vendors' own pages: [Supabase pricing overview](https://www.jetadmin.io/blog/supabase-pricing-2026-guide-to-plans-limits-and-real-world-costs/), [Railway pricing overview](https://livemy.app/blog/railway-pricing). Confirm at supabase.com/pricing and railway.com/pricing before committing.
