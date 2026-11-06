# Pool Acquisition System - Prototype Implementation Plan (same-day build)

Status: PLAN FOR APPROVAL. Nothing implemented. No code, migration, schema, data, agent registration, commit, branch, deployment or message was created or changed in producing this document.
Date: 2026-10-20
Executor: Fable (this document is written to be executed without access to any prior conversation)
Architecture reference: `docs/reviews/pool-acquisition-final-design.md`
Platform reference: `docs/PLATFORM_HANDOFF.md`

Evidence labels: `[VERIFIED]` I checked this in the repository, the live database, or a live probe during this review - `[DOC]` documentation claim, not re-verified - `[EXT]` provider documentation - `[ASSUMPTION]` my inference.

---

## 1. Executive Feasibility Verdict

**Yes - a genuine end-to-end integrated prototype is achievable tonight**, and the reason is specific rather than optimistic: the hard, slow parts already exist and are applied in production. The schema, the durable queue with lease/heartbeat/retry, the deterministic scoring module, the outreach safety rails, the exactly-once send protocol, the credential vault, the auth layer, the telemetry SDK and the ingest endpoint are all real code, and 88 tests pass today `[VERIFIED: pytest]`. What is missing is wiring, five small defect fixts, one additive function-only migration, and three LLM-calling handlers.

Two honest figures:

| Scope | Wall-clock estimate |
|---|---|
| **Tier 1 - integrated spine** (controller -> research -> triage -> drafts -> simulated replies -> classification -> dashboard -> real telemetry) | **5.5 - 6.5 hours**, single executor; ~4.5 hours with the dashboard stream run in parallel |
| **Tier 2 - the full capability list in your section 6** (adds the policy ladder, next-action and objective-progress panels, independent pause demonstration) | **+2 - 3 hours** |

Three things make tonight real rather than a demo of a demo:

1. **The AI is real.** Enrichment, drafting and reply classification make live Anthropic calls with the real anti-fabrication and injection gates. `ANTHROPIC_API_KEY` is present `[VERIFIED]`.
2. **The persistence is real.** Production Supabase, the applied `swim_sourcing` schema, the real queue RPCs. 047-052 are recorded in the migration ledger `[VERIFIED: live SQL]`.
3. **The telemetry is real, and I verified the exact credential needed.** A POST to the production ingest endpoint with the value of `AGENT_OVERSIGHT_SECRET` and a nonexistent agent id returns `404 Agent not found` - meaning authentication passed and nothing was written - while the local `INGEST_SECRET` value returns `401 Unauthorized` `[VERIFIED: live probe, no row created]`.

Only the **external I/O is simulated**: Google Places (no API key exists `[VERIFIED]`) and email (nothing is sent, by instruction). Both simulations are clearly labelled in the data, not hidden.

### 1.1 Five blockers I verified, which must be fixed before anything else works

These are not theoretical. Each would stop the prototype, and together they are about 75 minutes of work.

| # | Blocker | Verified how | Fix |
|---|---|---|---|
| **B-1** | **PostgREST does not expose `swim_sourcing`.** A direct `.schema('swim_sourcing')` call returns `PGRST106 Invalid schema: swim_sourcing - Only the following schemas are exposed: public, graphql_public` (HTTP 406) | live probe with the service-role key `[VERIFIED]` | Every app-side read/write of domain tables must go through a `public` RPC. This also means **`src/app/api/sourcing/approvals/route.ts` is broken as written** - it uses `.schema('swim_sourcing')` at lines 49, 66 and 84 and has never been exercised (0 approval rows live `[VERIFIED]`). `src/app/api/estimation/runs/[id]/route.ts:43` already documents this rule in a comment |
| **B-2** | **The telemetry SDK cannot authenticate with the env as it stands.** `python-sdk/oversight.py:176-181` reads `OVERSIGHT_SECRET` then `INGEST_SECRET`, never `AGENT_OVERSIGHT_SECRET`; `.env.local` has `AGENT_OVERSIGHT_SECRET` (the value production accepts) and `INGEST_SECRET` (which production rejects), and has no `OVERSIGHT_URL` at all | file read + live probe `[VERIFIED]` | Export `OVERSIGHT_SECRET="$AGENT_OVERSIGHT_SECRET"` and `OVERSIGHT_URL=https://agent-oversight.vercel.app`. No code change required |
| **B-3** | **The worker emits no telemetry.** `agents/teams/swim-sourcing/worker.py` claims `run_started`/`run_completed` in its docstring; there is no `OversightClient` import and no ingest call. It also only enforces preflight when an agent id happens to resolve | `grep` shows matches in the docstring only `[VERIFIED]` | Wire the SDK into `process_one()`; make the handler-to-identity map explicit and preflight unconditional |
| **B-4** | **Fixture rows are written labelled as live Places data.** `discovery.py normalize_place()` hard-codes `"source": "google_places"` regardless of transport; the schema's `source` CHECK already permits `'fixture'`, which no code path sets | file read `[VERIFIED]` | One-line change plus an explicit `use_fixtures` flag. This is also a stated requirement of tonight's brief ("never represent fixtures as newly verified live research") |
| **B-5** | **`CREDENTIAL_ENCRYPTION_KEY` is absent**, so the vault cannot encrypt or decrypt, and the worker scrubs inherited provider keys at startup - so without the vault there is no API key available to any handler | env inspection `[VERIFIED]` | Generate 32 random bytes base64, add to `.env.local`, seed one credential row |

A sixth item is not a blocker but makes the demo incoherent if skipped: the scoring confidence/denominator defect means a facility 4.0 miles away scores **0.0** when its distance arrives on the column rather than inside `attributes` `[VERIFIED: executed probe]`. 15 minutes.

---

## 2. Direct Answers to Your Ten Questions

1. **Can we deliver a genuine end-to-end prototype tonight?** Yes. Tier 1 as defined in section 3, with real AI calls, real persistence and real telemetry.
2. **Shortest credible timeline?** 5.5-6.5 hours for Tier 1 from a standing start, including the 75 minutes of blocker fixes. ~4.5 hours if the dashboard work runs as a parallel stream. Tier 2 adds 2-3 hours.
3. **Absolute minimum new code?** Roughly **900-1,200 lines** across **4 new files and 6 edited files**, plus one SQL migration of about 200 lines that contains only `CREATE OR REPLACE FUNCTION` statements and one nullable column. Nothing else is new.
4. **Can the existing queue and worker handle the entire workflow?** Yes, with no new framework. `swim_claim_job` / `swim_heartbeat_job` / `swim_finish_job` / `swim_reap_expired_jobs` / `swim_enqueue_job` are applied and working `[VERIFIED: `swim_reap_expired_jobs` returns 200 over RPC]`. The only constraint is that `jobs.job_type` is a closed CHECK enumeration, which section 6.1 works around without touching it.
5. **Is a new migration necessary?** **One, and it is additive and small**: 8 `public` functions plus one nullable `jsonb` column on `swim_sourcing.outreach_threads`. No table creation, no constraint rewrite, no data change. It is necessary purely because of B-1 - with PostgREST unable to see the schema, a function in `public` is the only way the app or the worker can read or write domain rows. A strict zero-migration variant exists (section 6.3) and I do not recommend it.
6. **How do we demonstrate three identities with one worker?** Register three rows in `public.agents` (controller as parent, researcher and coordinator as children via `parent_agent_id`), map each job type to its owning identity in code, and open every run under that identity. Independent pause is then real: flipping `agents.status` to `paused` makes preflight refuse that capability's jobs while the other keeps running, and ingest returns 403 for it (`src/app/api/ingest/route.ts:90` `[VERIFIED]`).
7. **Real versus simulated?** Real: Supabase persistence, queue mechanics, Anthropic calls for enrichment/drafting/classification, evidence validation, anti-fabrication, injection detection, escalation rules, deterministic scoring, telemetry, cost attribution, budget preflight, credential vault, dashboard reads. Simulated: Google Places responses (labelled `source='fixture'`), inbound replies (labelled scenario fixtures), and sending (never performed).
8. **Fastest route to a functional dashboard?** Extend what exists. `src/app/dashboard/sourcing/page.tsx` already renders the pipeline board and a facilities table from `swim_pipeline_summary`, `swim_list_facilities` and `swim_operations_summary`, and `swim_operations_summary` **already counts drafts, replies and jobs** `[VERIFIED: 050 source]`. So the counters light up the moment rows exist. Add three panels to that one page and three fields to `src/app/api/sourcing/operations/route.ts`. No new pages, no new routes.
9. **Three biggest execution risks?** (a) the DDL apply path - a previous attempt to apply a migration through the Supabase MCP was refused by a permission classifier `[DOC]`, so use `psycopg` with `SUPABASE_DB_URL`, which is present `[VERIFIED]`; (b) Supabase free-tier auto-pause producing a 502/521 cold start in the middle of the demo `[DOC]`; (c) LLM structured-output truncation silently dropping the last fields of a tool input, which is a documented trap in this repo's own lessons.
10. **What would I deliberately avoid building tonight?** The campaigns entity, any send path, `RESEND_API_KEY` (it is present in `.env.local` `[VERIFIED]` - do not touch it), Gmail/OAuth, inbound webhooks, Calendar, hosted worker deployment, the advisory LLM layer, commercial viability scenarios, the four-state triage schema change, and any automatic policy action that reaches outside the database.

---

## 3. Minimum Viable End-to-End Scope

### Tier 1 - the integrated spine (build this first, demo it, then continue)

A single command drives: objective -> controller enqueues research -> 20 facilities ingested with fixture provenance and deduplicated -> enrichment extracts evidence-backed facts via a real LLM call -> deterministic triage assigns a state, a channel and open questions -> coordinator drafts 5 personalised messages through the real anti-fabrication gate -> simulated replies are ingested -> real LLM classification plus deterministic escalation rules -> controller prints a progress summary -> the dashboard shows all of it from the database -> every job appears in Agent Oversight attributed to one of three identities with cost.

### Tier 2 - the remainder of your section 6 list

Policy ladder evaluation (saturation, eligible-uncontacted floor, schedule risk) with decisions logged; next-actions panel; objective-progress panel; independent pause demonstration; follow-up recommendations surfaced per thread.

### Explicitly out of scope tonight

Everything in answer 10 above. Nothing in tonight's build may make an outbound call to any third party except `api.anthropic.com` and `*.supabase.co`.

---

## 4. Existing Code Reuse Assessment

| Asset | Path | State | Use tonight |
|---|---|---|---|
| Durable queue + RPCs | `supabase/migrations/049`, `050` | **Applied in production** `[VERIFIED: ledger + 9 tables]` | Unchanged |
| Deterministic scoring | `agents/library/facility-qualification-agent/scoring.py` | 19 tests pass; one defect | One fix, then reuse |
| Discovery + fixtures | `agents/library/facility-discovery-agent/discovery.py`, `fixtures/katy_tx_places.json` | 20 tests pass; fixture transport already exists and returns empty for unknown queries | Reuse; fix provenance (B-4) |
| Outreach safety | `agents/library/outreach-agent/safety.py` | 30 tests pass: injection detection, commitment escalation, `assert_no_fabrication`, `can_auto_reply`, `body_sha256` | Reuse unchanged |
| Send protocol | `agents/library/outreach-agent/send.py` | Tested against `MockMailbox` | **Not used tonight** (no sends) |
| Credential vault | `agents/lib/credentials.py` | 17 tests pass; `encrypt_api_key`, `resolve_tenant_api_key`, `tenant_llm_env`, `scrub_platform_provider_env`, `check_tenant_budget` | Reuse; needs B-5 |
| Worker | `agents/teams/swim-sourcing/worker.py` | Lease, heartbeat, retry, cancel, preflight; handlers for `discover` and `qualify` only; **no telemetry** | Extend (B-3) |
| Telemetry SDK | `python-sdk/oversight.py` | `OversightClient.run()` context manager, `ctx.step()`, `ctx.report()`, `timer()` | Reuse; env fix (B-2) |
| Ingest endpoint | `src/app/api/ingest/route.ts` | Live; validates `x-agent-secret` against `INGEST_SECRET` server-side and refuses non-active agents | Unchanged |
| Auth + tenancy | `src/middleware.ts`, `src/lib/auth/require-tenant.ts` | Live: `/dashboard` 307, `/api/*` 401 `[VERIFIED: live probes]` | Unchanged |
| Sourcing read routes | `src/app/api/sourcing/{facilities,operations}/route.ts` | Use `public` RPCs, so they work | Extend `operations` |
| Sourcing dashboard | `src/app/dashboard/sourcing/page.tsx` | Renders pipeline + facilities from real APIs | Extend with 3 panels |
| Approvals route | `src/app/api/sourcing/approvals/route.ts` | **Broken** (B-1) | Not needed tonight; leave alone or fix later |
| Registration script | `scripts/register_swim_sourcing.js` | Dry-run verified `[DOC]`; registers company, project, orchestrator + 4 workers, all paused | Edit to 3 identities |
| Dev dependencies | - | `anthropic 0.97.0`, `psycopg 3.3.6`, `cryptography`, `python-dotenv` all importable `[VERIFIED]` | No installs needed |

---

## 5. Component-by-Component Implementation Plan

| Component | Existing code to reuse | Required changes | New files | Effort |
|---|---|---|---|---|
| **Controller** | `swim_enqueue_job` RPC; `swim_pipeline_summary`, `swim_operations_summary`; `oversight.py` | None to existing files | `agents/teams/swim-sourcing/controller.py` (~220 lines): accepts the objective, reads goal state, enqueues the next stage's jobs, waits for drain, prints a progress summary, emits its own run under the controller identity. Tier 2 adds the policy ladder | 60 min (Tier 1: 35 min for the minimal enqueue + summary form) |
| **Facility Researcher** | `discovery.py` (+ `fixture_transport`), `scoring.py`, `swim_upsert_facility`, `swim_facility_attributes`, `swim_record_qualification` | `discovery.py`: provenance fix (B-4). `scoring.py`: denominator fix. `worker.py`: new `enrich` handler; `qualify` handler extended to write `triage_state` and `channel_recommended` into `score_breakdown` | `agents/library/facility-researcher/enrich.py` (~200 lines): real Anthropic call with forced tool input, evidence-span validation against the source HTML, contact extraction. `agents/library/facility-researcher/fixtures/site_pages.json` (~20 recorded pages, labelled) | 105 min |
| **Partnership Coordinator** | `safety.py` (`assert_no_fabrication`, `requires_human_approval`, `wrap_untrusted`, `detect_injection`, `body_sha256`, `can_auto_reply`) | `worker.py`: new `draft_outreach`, `poll_inbox` (simulated inbound) and `classify_reply` handlers | `agents/library/partnership-coordinator/draft.py` (~180 lines): template with slots + one LLM sentence + fabrication gate. `agents/library/partnership-coordinator/classify.py` (~160 lines): fenced inbound -> forced-tool intent + proposed action -> deterministic safety verdict. `agents/library/partnership-coordinator/fixtures/replies.json` (8 labelled scenarios incl. one injection attempt and one opt-out) | 145 min |
| **Worker and queue** | Entire claim/lease/heartbeat/finish/reap path | `worker.py`: telemetry wiring, unconditional preflight, handler->identity map, five new handlers registered in `HANDLERS` | none | 70 min |
| **Agent Oversight integration** | `oversight.py`, `/api/ingest`, `public.agents`, `check_tenant_budget` | Env: `OVERSIGHT_URL`, `OVERSIGHT_SECRET` (B-2). `scripts/register_swim_sourcing.js`: 3 identities, `status='active'`, real `cost_limit_usd` | `scripts/seed_prototype.py` (~150 lines): company/project/agent rows, vault credential insert via `psycopg`, budget cap, idempotent and re-runnable | 55 min |
| **Dashboard** | `src/app/dashboard/sourcing/page.tsx`, `operations/route.ts`, `swim_operations_summary` | `operations/route.ts`: call 3 new RPCs and return `drafts`, `threads`, `next_actions`, `objective`. `page.tsx`: three new panels (Drafts, Replies and classification, Next actions + objective progress) | none | 75 min |
| **End-to-end testing** | `agents/tests/test_end_to_end.py` as the shape to copy | none | `agents/tests/test_prototype_e2e.py` (~150 lines, offline, mocked LLM) + `scripts/demo_prototype.py` (~80 lines, drives the live demo in order and prints each checkpoint) | 60 min |

Database: one migration file, `supabase/migrations/053_swim_prototype_rpcs.sql` (~200 lines) - 45 min including apply and verification.

---

## 6. Data Contracts and Integration Design

### 6.1 How the prototype avoids touching any constraint

Three design choices remove every table-level change except one nullable column:

1. **The controller is a process, not a job type.** `jobs.job_type` is a closed CHECK enumeration of nine values `[VERIFIED: 049]`; `evaluate_policies` is not among them. Making the controller the thing that *creates* jobs - a CLI entry point run by hand tonight and by cron later - needs no new job type and matches the agreed architecture.
2. **Simulated inbound uses the existing `poll_inbox` job type.** It polls a simulated inbox; the semantics are honest and the enum is untouched.
3. **Four-state triage rides inside `score_breakdown`.** `qualifications.status` permits only `qualified | disqualified | needs_info` `[VERIFIED: 049]`. Tonight the four triage states live at `score_breakdown.triage_state` (plus `score_breakdown.channel_recommended` and `score_breakdown.gates`), and `status` is set to the nearest legacy value so the existing pipeline-stage advance in `swim_record_qualification` keeps working `[VERIFIED: it updates `facilities.pipeline_stage`]`. The schema change to a first-class column belongs to MVP 1, not tonight.

### 6.2 Migration 053 - the only DDL

Function-only plus one additive column. Every function: `SECURITY DEFINER`, `SET search_path = pg_catalog, swim_sourcing, public`, `REVOKE ALL ... FROM PUBLIC, anon, authenticated`, `GRANT EXECUTE ... TO service_role` - copy the grant block at the end of `050_swim_sourcing_rpcs.sql` verbatim.

| Function | Purpose |
|---|---|
`swim_apply_enrichment(p_company_id uuid, p_payload jsonb)` | merge `attributes` / `attributes_confidence`, shrink `unknown_fields`, bump `source_fetched_at` |
`swim_record_contact(p_company_id uuid, p_payload jsonb)` | insert into `facility_contacts`; **raise** if `source_url` or `evidence_snippet` is absent (both are `NOT NULL` already) |
`swim_record_draft(p_company_id uuid, p_payload jsonb)` | upsert the thread on `(facility_id, campaign_id)`, insert an `outbound` `draft` message with `body_sha256`, return both ids |
`swim_record_inbound(p_company_id uuid, p_payload jsonb)` | insert an `inbound` `received` message, set `threads.state='replied'`, advance `facilities.pipeline_stage='responded'` |
`swim_record_classification(p_company_id uuid, p_payload jsonb)` | set `threads.last_intent`, `threads.state` (`replied` or `escalated`), and store the full verdict in the new column |
`swim_list_drafts(p_company_id uuid, p_limit int)` | drafts joined to facility name, contact and open questions |
`swim_list_threads(p_company_id uuid, p_limit int)` | thread + last inbound excerpt + intent + classification verdict |
`swim_next_actions(p_company_id uuid)` | derived action list: facilities awaiting enrichment, drafts awaiting review, threads needing escalation, questions still unanswered |
`swim_objective_progress(p_company_id uuid)` | objective counters: discovered / triaged / contactable / drafted / replied / escalated, plus the saturation figure |

Column: `ALTER TABLE swim_sourcing.outreach_threads ADD COLUMN IF NOT EXISTS last_classification JSONB;` - nullable, additive, no rewrite.

**Apply path.** Use `psycopg` with `SUPABASE_DB_URL` (present `[VERIFIED]`), inside one transaction. A prior attempt to apply DDL through the Supabase MCP was refused by a permission classifier `[DOC]`, so do not plan on that route. Afterwards insert a ledger row into `supabase_migrations.schema_migrations` (version `20261020213000`, name `053_swim_prototype_rpcs`) - the repository's own lessons record that applying SQL outside a recording path is how migrations 024-046 went missing from the ledger `[VERIFIED: ledger jumps 023 -> 047]`.

### 6.3 The strict zero-migration alternative, and why not

Adding `swim_sourcing` to Supabase's exposed schemas (project API settings) would let the app use `.schema('swim_sourcing')` directly and would need no DDL. It is tempting and it would also un-break the approvals route. I do not recommend it tonight: it widens PostgREST's surface on a production project to satisfy a prototype, it diverges from the pattern every other private schema in this repo uses, and it is a settings change nobody will remember to revert. Keep the API surface at `public`.

### 6.4 Data contracts

All payloads are JSON. Field names match the existing columns so no mapping layer is needed.

**Enrichment output** (`enrich.py` -> `swim_apply_enrichment` + `swim_record_contact`):

```json
{
  "facility_id": "uuid",
  "attributes": { "indoor": true, "heated": null, "pool_length_m": 25.0 },
  "attributes_confidence": { "indoor": "verified", "pool_length_m": "inferred" },
  "evidence": [ { "field": "indoor", "source_url": "https://...", "snippet": "verbatim text from the page" } ],
  "contacts": [ { "full_name": "...", "role_title": "Aquatics Director", "email": "...",
                  "phone": null, "channel_kind": "email", "confidence": "verified",
                  "source_url": "https://...", "evidence_snippet": "verbatim text" } ],
  "unknown_fields": ["hourly_rate_usd", "commercial_instruction_allowed"]
}
```

Hard rule, enforced in code before any write: **every `evidence.snippet` and `contacts[].evidence_snippet` must appear verbatim in the fetched page text**, after whitespace normalisation. A field whose snippet is not found is dropped and counted in the job result as `evidence_rejected`. This is the anti-hallucination control and it must be a code check, not a prompt instruction.

**Triage output** (`scoring.qualify()` + mapping -> `swim_record_qualification`): the existing payload from `QualificationResult.to_payload()`, with `score_breakdown` extended by `triage_state` (`contact_first | research_further | not_currently_suitable | disqualified`), `channel_recommended` (`email | phone | facility_use_application | none`), and `gates` (the hard-gate results).

**Draft output** (`draft.py` -> `swim_record_draft`):

```json
{ "facility_id": "uuid", "contact_id": "uuid|null", "campaign_id": "uuid (prototype-generated, constant per run)",
  "subject": "...", "body": "...", "open_questions_used": ["commercial_instruction_allowed", "recurring_availability"],
  "model": "claude-haiku-5-5", "tokens_in": 0, "tokens_out": 0 }
```

`campaign_id` is a plain UUID generated once per demo run. There is no campaigns table and none is created tonight; nothing authorises a send, because nothing sends.

**Simulated reply** (`replies.json` -> `poll_inbox` -> `swim_record_inbound`): `{ "scenario_id": "...", "persona": "...", "facility_match": "FIXTURE Facility 003", "body": "..." }` - and every row is written with `subject` prefixed `[SIMULATED]` so no reader can mistake it for real correspondence.

**Classification output** (`classify.py` -> `swim_record_classification`):

```json
{ "thread_id": "uuid", "intent": "pricing_discussion", "model_confidence": 0.0,
  "proposed_reply": "…|null", "proposed_action": "escalate|auto_reply|follow_up|close",
  "safety": { "requires_approval": true, "reasons": ["intent 'pricing_discussion' always requires Cameron's decision"],
              "topics": ["price"], "injection_suspected": false, "injection_matches": [] },
  "recommended_followup_at": "2026-10-24T00:00:00Z|null" }
```

`safety` comes from `safety.requires_human_approval()` and is authoritative. The model's own confidence is recorded and deliberately not used as an input to the gate.

**Identity map** (in `worker.py`):

| Job type | Identity |
|---|---|
`discover`, `enrich`, `qualify` | `swimschool.facility-researcher` |
`draft_outreach`, `poll_inbox`, `classify_reply` | `swimschool.partnership-coordinator` |
(controller process) | `swimschool.facility-acquisition-controller` |

### 6.5 Environment

| Variable | State | Action |
|---|---|---|
`NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | present `[VERIFIED]` | none |
`SUPABASE_DB_URL` | present `[VERIFIED]` | used for DDL and the vault insert |
`ANTHROPIC_API_KEY` | present `[VERIFIED]` | seeded into the vault for the prototype company |
`AGENT_OVERSIGHT_SECRET` | present `[VERIFIED]` | **also export as `OVERSIGHT_SECRET`** (B-2) |
`OVERSIGHT_URL` | **absent** `[VERIFIED]` | set to `https://agent-oversight.vercel.app` |
`CREDENTIAL_ENCRYPTION_KEY` | **absent** `[VERIFIED]` | `python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"` |
`GOOGLE_PLACES_API_KEY` | absent `[VERIFIED]` | not needed - fixtures |
`RESEND_API_KEY` | present `[VERIFIED]` | **do not use it tonight** |

**Disclosure that must be stated in the demo, not buried:** the vault will hold the *platform's* Anthropic key, so tonight's LLM spend bills to the platform account, not to Cameron. The vault path is still the right one to exercise (the worker scrubs inherited provider keys at startup, so a key outside the vault would not reach a handler), but the key must be replaced with Cameron's own before any real campaign. Set the prototype company's `cost_limit_usd` to **5.00** so the budget preflight is exercised and bounded - note that `check_tenant_budget` currently returns `allowed` when the limit is NULL, and all three existing companies are NULL `[VERIFIED: live SQL]`, which is why setting it explicitly matters tonight.

---

## 7. Implementation Sequence

Critical path is marked **[CP]**. Two streams can run in parallel: **A** (backend/worker) and **B** (migration + dashboard).

| # | Step | Files | Output | Depends on | Time | Verify |
|---|---|---|---|---|---|---|
| 1 **[CP]** | Environment and secret check | `.env.local` | all variables in 6.5 set | - | 15 min | `curl` ingest with `x-agent-secret: $AGENT_OVERSIGHT_SECRET` and a nonexistent agent id -> expect **404**, not 401 (this writes nothing) |
| 2 (B) | Write and apply migration 053 | new `supabase/migrations/053_swim_prototype_rpcs.sql`; apply via `psycopg` | 8 functions + 1 column live | 1 | 45 min | `python scripts/check_migrations.py --from-migration 053` -> 0 failures; `select to_regprocedure('public.swim_list_drafts(uuid,integer)')` is not null; ledger row inserted |
| 3 (A) | Defect fixes | `discovery.py` (provenance + `use_fixtures`), `scoring.py` (denominator) | fixtures labelled `source='fixture'`; unstated confidence leaves the denominator | 1 | 30 min | `python -m pytest agents/tests -q` -> 88 pass; add 2 tests (fixture source, denominator) -> 90 pass |
| 4 (A) **[CP]** | Worker telemetry + identity map + unconditional preflight | `worker.py` | every job opens a run under its identity, reports cost, blocks when paused or over budget | 1 | 40 min | run one `discover` job; a run appears at `/dashboard/runs` attributed to the researcher identity |
| 5 (A) **[CP]** | Seed company, project, 3 identities, vault credential, budget cap | new `scripts/seed_prototype.py`; edit `scripts/register_swim_sourcing.js` | tenant exists, 3 agents `active`, 1 credential, `cost_limit_usd = 5.00` | 1 | 30 min | `select name,status from public.agents where name like 'swimschool.%'` -> 3 active; `resolve_tenant_api_key()` returns a credential; re-running the script changes nothing |
| | **CHECKPOINT 1** | | *An empty but live tenant whose worker reports telemetry.* Demo: run `--once`, show the run in Oversight. | | | |
| 6 (A) **[CP]** | Researcher: discovery into the real tenant | `controller.py` (minimal), existing `handle_discover` | >= 20 facilities, `source='fixture'`, zero duplicates on re-run | 4, 5 | 20 min | `swim_pipeline_summary` shows ~20 `discovered`; second run inserts 0 |
| 7 (A) **[CP]** | Researcher: enrichment | new `agents/library/facility-researcher/enrich.py` + `fixtures/site_pages.json`; `worker.py` handler | attributes and contacts with validated evidence; rejected snippets counted | 6 | 105 min | a mutated snippet is rejected (unit test); no contact row without a resolvable `source_url`; `evidence_rejected` visible in the job result |
| 8 (A) **[CP]** | Researcher: triage | `worker.py` `handle_qualify` + mapping | every facility has a triage state, channel and open questions | 7 | 30 min | `swim_list_facilities` shows states; no facility with completeness below the floor is `qualified` |
| | **CHECKPOINT 2** | | *20 facilities, evidence-backed, triaged, visible in the dashboard.* This alone is a useful deliverable. | | | |
| 9 (B) | Dashboard panels | `src/app/api/sourcing/operations/route.ts`, `src/app/dashboard/sourcing/page.tsx` | Drafts, Replies, Next actions + objective panels | 2 | 75 min | `npx tsc --noEmit` clean; `/dashboard/sourcing` renders real rows while signed in |
| 10 (A) **[CP]** | Coordinator: drafting | new `draft.py`; `worker.py` handler | >= 5 drafts, each citing that facility's open questions, all `status='draft'` | 8 | 60 min | `assert_no_fabrication` rejects a seeded bad draft; `swim_list_drafts` returns >= 5; no message leaves `draft` |
| 11 (A) | Coordinator: simulated inbound | new `fixtures/replies.json`; `worker.py` `poll_inbox` handler | 8 inbound rows, subjects prefixed `[SIMULATED]` | 10 | 40 min | threads move to `replied`; facilities to `responded` |
| 12 (A) **[CP]** | Coordinator: classification + escalation | new `classify.py`; `worker.py` handler | intent, proposed action, safety verdict per thread | 11 | 45 min | the injection scenario yields a classification and an escalation and **no** proposed send; the pricing scenario escalates; the opt-out scenario is flagged for suppression |
| 13 (A) | Controller: progress summary | `controller.py` | printed objective summary + next actions; own telemetry run | 12 | 25 min | summary counts match `swim_objective_progress` |
| | **CHECKPOINT 3** | | *Tier 1 complete: full spine, dashboard, telemetry.* | | | |
| 14 | Offline E2E test + demo script | new `agents/tests/test_prototype_e2e.py`, `scripts/demo_prototype.py` | one command runs the whole demo; tests pass without network | 13 | 60 min | `python -m pytest agents/tests -q` all green; `python scripts/demo_prototype.py --dry-run` prints the sequence |
| 15 (Tier 2) | Policy ladder + pause demo | `controller.py`; `scripts/demo_prototype.py` | saturation and floor rules enqueue work; pausing the coordinator blocks only its jobs | 13 | 90 min | pause the coordinator -> its next job ends `blocked`, researcher jobs still complete |

**Tier 1 total: 5h 50m sequential; about 4h 35m with stream B in parallel.** Tier 2: +1h 30m to +3h.

---

## 8. Fable Handoff Instructions

Everything needed, assuming no prior conversation.

**Starting state.** Repository `leazer7222/agent-oversight`. Work from a fresh branch off `main` (`claude/pool-prototype-<date>`). `main` is at `dfab23b`. Migrations 047-052 are already applied to production Supabase `hdhovyrlnfojtkqbcegh` and recorded in the ledger; do not re-apply them. `node_modules` may be empty in a worktree - run `npm ci` in the main checkout before `tsc`, and note that a worktree needs `cmd /c mklink /J node_modules ..\node_modules` on Windows per this repo's lessons. `next dev --no-turbo` is required in worktrees.

**Read these first, in order:** `docs/reviews/pool-acquisition-final-design.md` (the agreed architecture), `AGENTS.md` and `LESSONS_LEARNED.md` (standing rules - no emojis anywhere, among others), `supabase/migrations/049_swim_sourcing_schema.sql` and `050_swim_sourcing_rpcs.sql` (the data model and the RPC patterns to copy), `agents/teams/swim-sourcing/worker.py` (the execution shell), `agents/library/outreach-agent/safety.py` (the safety contract you must not weaken), `python-sdk/oversight.py` (telemetry).

**Decisions already made - do not relitigate.** One deterministic controller plus two AI-enabled capabilities; three registered identities in one worker process; no inter-agent protocols and no new orchestration framework; the queue is the only channel between capabilities; the LLM never holds a send capability; evidence spans are mandatory and validated in code; fixtures are always labelled as fixtures; nothing is sent tonight.

**Required changes.** Sections 5, 6 and 7 of this document are the specification. Do not add tables beyond the one nullable column in 6.2. Do not alter any CHECK constraint. Do not change `src/middleware.ts`.

**Interfaces and data contracts.** Section 6.4, verbatim. Field names match existing columns deliberately.

**Environment and external dependencies.** Section 6.5. Only two external hosts may be contacted: `api.anthropic.com` and `*.supabase.co`. `RESEND_API_KEY` exists in `.env.local` - do not use it. There is no Google Places key; use the fixture transport.

**Model choice.** Use `claude-haiku-5-5` for enrichment extraction and classification, `claude-sonnet-5-5` for drafting. Give structured-output calls a generous `max_tokens` (>= 8000) - this repo has already been bitten by tool-input truncation silently emptying the last fields of a response.

**Testing commands.**

```bash
python -m pytest agents/tests -q
python scripts/check_migrations.py --from-migration 053
python scripts/tests/check_route_authorization.py
python scripts/tests/check_no_secrets.py --self-test
npx tsc --noEmit
python agents/teams/swim-sourcing/worker.py --once
python scripts/demo_prototype.py
```

**Definition of done.** All of: 90+ Python tests pass; `tsc` clean; the route-authorization gate passes; >= 20 facilities in the database all with `source='fixture'`; every facility has a triage state, a recommended channel and an open-question list; >= 5 drafts, none past `draft`; 8 simulated inbound rows with `[SIMULATED]` subjects; every thread classified with a safety verdict; the injection scenario produces an escalation and no proposed send; `/dashboard/sourcing` shows pipeline, drafts, replies, next actions and objective progress from real rows; every job has a run in Agent Oversight attributed to the correct identity with a cost figure; pausing one identity blocks only its jobs; `scripts/demo_prototype.py` reproduces the whole sequence from a clean tenant.

**Explicit exclusions.** No email send of any kind. No Gmail, OAuth, webhook or Calendar work. No campaigns table. No hosted worker deployment. No new tables. No constraint changes. No changes to migrations 047-052. No agent registration outside the three prototype identities. No commit to `main`. No production project settings changed.

**Known risks.** Section 10.

---

## 9. Test and Demonstration Plan

**Automated.** Extend the suite rather than replacing it: the 88 existing tests must stay green `[VERIFIED: they pass today]`. Add: fixture provenance (`source='fixture'`); scoring denominator with unstated confidence; evidence-span rejection on a mutated snippet; draft rejection by `assert_no_fabrication`; the injection reply producing escalation and no send; the opt-out reply producing a suppression recommendation; `swim_record_draft` idempotency on `(facility_id, campaign_id)`. All offline with a stubbed LLM.

**The demo, in the order a sceptical observer would ask for it.**

1. Show the tenant is empty: `swim_operations_summary` all zeros.
2. `python scripts/demo_prototype.py` - prints the objective, then each stage as it completes.
3. Show 20 facilities with `source='fixture'` and `FIXTURE`-prefixed names; say plainly that discovery data is recorded, not live, and that no Places key exists.
4. Show one facility's enrichment: the attribute, its confidence, its `source_url` and the verbatim snippet. Then show the rejected-snippet counter and explain the validation.
5. Show triage: states, channels, open questions. Point out that nothing is `qualified` on thin evidence.
6. Show 5 drafts, each asking that facility's specific open questions. Show one deliberately bad draft being refused by the fabrication gate.
7. Show the simulated replies, then the classifications. Open the injection scenario and show it produced an escalation, not an action.
8. Open `/dashboard/sourcing` signed in: pipeline, drafts, replies, next actions, objective progress - all from the database.
9. Open `/dashboard/runs` and `/dashboard/costs`: runs attributed to three identities, with cost.
10. Pause the coordinator identity, re-run: its job ends `blocked` while the researcher's completes. Un-pause.
11. State the four things that are simulated and the one disclosure about billing.

---

## 10. Risks, Blockers and Deferred Work

| Risk | Likelihood | Mitigation |
|---|---|---|
DDL apply path refused (MCP permission classifier) `[DOC]` | medium | `psycopg` + `SUPABASE_DB_URL`, verified with `select 1` first; Supabase SQL editor as the manual fallback |
Supabase free-tier auto-pause mid-demo (502/521 cold start) `[DOC]` | medium | warm the project with a read 2 minutes before demoing; the worker already has bounded retry; `apiFetch` retries 5xx |
LLM structured-output truncation dropping trailing fields | medium | `max_tokens >= 8000`, short per-field instructions, validate the parsed input against the schema and fail the job rather than writing a partial row |
Fabrication gate rejecting legitimate drafts | medium | keep claims out of the template; seed `business_facts` with explicit placeholders; log the refusal reason into the job result so it is visible rather than mysterious |
Evidence validation too strict (whitespace, entities) | medium | normalise whitespace and decode HTML entities before comparison; count rejections instead of silently dropping |
Telemetry 401/403 | low now that B-2 is diagnosed | step 1's 404 probe; agents must be `status='active'` (ingest refuses otherwise `[VERIFIED]`) |
Scope creep into sends | low | `RESEND_API_KEY` is present; the plan forbids its use, and no send handler is registered in `HANDLERS` tonight |
Demo misread as live research | medium | `source='fixture'`, `FIXTURE` name prefix, `[SIMULATED]` subjects, and the spoken disclosure in step 11 |

**Deferred without weakening the demonstration:** campaign authorisation, live Gmail or Resend sending, OAuth, inbound webhooks, Calendar, production worker hosting, commercial viability scenarios, autonomous campaign activation, the advisory LLM layer, first-class triage columns, suppression write path, and the full remediation backlog in the final design (sections H.1 and H.2 there). All of it is MVP 1 and MVP 2 work, and none of it is needed to prove the spine.

**What tonight will not prove, and should not be claimed:** that live Places returns 20 real Katy facilities; that drafts land in an inbox; that classification is accurate on real correspondence (8 scripted scenarios are a smoke test, not a precision measurement); that the worker survives on a host; or that any of this is safe to point at real facilities. The final design's ten-condition autonomy gate still governs that, and none of its conditions are met by a prototype.

---

## 11. Final Recommendation

Build Tier 1 tonight, in the order in section 7, and stop at Checkpoint 3 if time runs short - Checkpoint 2 alone (20 evidence-backed, triaged facilities visible in the dashboard with real telemetry) is already a deliverable Cameron would recognise as useful.

Three things I would insist on, because they are what separate a prototype from a misleading one:

1. **Fix the five verified blockers first.** They are 75 minutes, and four of the five are failures that would otherwise be discovered at 2 a.m. with the demo half-built.
2. **Keep the AI real and the externals simulated, and label the simulation in the data.** `source='fixture'`, `[SIMULATED]` subjects, and no send handler registered. A prototype that fakes the model is a slide deck; a prototype that fakes the labels is a liability.
3. **Do not create the campaigns entity or any send path tonight.** The absence of a send path is the strongest safety property tonight's build can have, and it costs nothing to preserve.

One line of scope I would cut if asked to go faster: the Tier 2 policy ladder. Deterministic saturation and floor rules are valuable, but they are only interesting once there is more than one day of pipeline history, and they can be added later without touching anything built tonight.
