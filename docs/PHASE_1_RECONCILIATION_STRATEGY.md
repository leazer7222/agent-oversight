# Phase 1 — Reconciliation Strategy (2026-05-12)

## Document Purpose
This document defines the architectural reconciliation strategy that must be executed before Phase 2 work begins. It is the output of a critical review of Codex's Phase 1 schema stabilization audit.

It contains:
- validated and refined architectural decisions
- challenges to Codex assumptions where warranted
- canonical data model semantics
- reconciliation sequencing and migration plan
- governance recommendations
- identified operational risks
- unresolved open questions

---

## Critical New Finding: `001_initial_schema.sql` Does Not Exist

The Codex audit referenced reading `supabase/migrations/001_initial_schema.sql` during analysis. This file does **not** exist in the repository. A glob of `supabase/migrations/*.sql` returns only `002_agent_outputs.sql`.

This means:
- Foundational tables (`companies`, `agents`, `agent_definitions`, `runs`, `project_state`) have no migration documentation in-repo.
- Codex's schema drift analysis for `runs` and `project_state` was comparing against an inferred or synthesized schema, not a committed file.
- The reconciliation scope is **larger** than the Codex audit assumed.
- **Creating `001_initial_schema.sql` is the first deliverable of the reconciliation pass.**

Operational implication: if someone ran `supabase db reset` today, they would get only `agent_outputs` — no base tables. The platform cannot be reproduced from repo state alone.

---

## Part 1: Challenging Codex Assumptions

### 1.1 Source-of-Truth Reversal

**Codex said**: "Canonical ownership for operational contracts = live Supabase schema + API/runtime behavior contracts."

**Challenge**: This inverts the governance model. Treating live DB as canonical creates a governance trap where any ad-hoc live change becomes "truth." The live DB is *operational reality*, not the *canonical contract source*.

**Corrected position**:
- **Canonical**: migrations + documented API/runtime contracts (what the system *should* be).
- **Operational reality**: live DB (what the system *is today*).
- Reconciliation closes the gap from operational reality toward canonical intent.
- After reconciliation, migrations ARE the canonical contract layer — not the live DB.

Practical implication: when live DB and migrations disagree after reconciliation, write a migration. Never let ad-hoc live changes become canonical without a migration.

### 1.2 Phase 2 Prerequisites Should Include Contract Tests in Phase 1

**Codex said**: "Validate API handlers against reconciled schema with contract tests" as a Phase 2 prerequisite.

**Challenge**: Contract tests are the verification mechanism for Phase 1 completion — they should be written *during* reconciliation, not deferred to Phase 2. Without them, "reconciliation is complete" is an untestable claim.

**Corrected position**: Contract tests for `/api/ingest` and `/api/project-state*` are Phase 1 deliverables, not Phase 2 prerequisites.

### 1.3 `agent_events` Observability Is Purely Theoretical

**Codex said**: "`agent_events` (inferred/live): append-only lifecycle trace" — treating this as partially operational.

**Challenge**: The ingest route (`/api/ingest/route.ts`) writes nothing to `agent_events`. Even if the table exists live, it receives zero event writes from the current execution path. The observability function of `agent_events` is entirely absent from the runtime.

**Corrected position**: `agent_events` has no operational value until the ingest route writes to it. Adding the write path is a required Phase 1 reconciliation deliverable, not a Phase 2 enhancement.

### 1.4 Zombie Run Risk Underestimated

**Codex analysis** did not explicitly model the risk of runs that emit `run_started` but never receive a terminal event.

**Finding**: If an agent crashes, is killed, or loses network connectivity after emitting `run_started`, the run stays in `started` status indefinitely. There is no timeout mechanism, no cleanup job, and no dashboard signal distinguishing an active run from a zombie run. This creates:
- Inflated "in-progress" counts.
- Inaccurate success rate metrics (`completed / total` is wrong if zombies inflate `total`).
- Operator confusion when the run list shows perpetually `started` runs.

**Required addition**: A `timeout_at TIMESTAMPTZ` field on `runs`, populated at `run_started` time. A cleanup job (Phase 5+) can mark timed-out runs as `failed` with `error = 'run_timeout'`.

---

## Part 2: Canonical Contract Definitions

### 2.1 `runs` — Canonical Contract

**Semantics**: One durable execution summary row per run lifecycle. Created at `run_started`, updated at `run_completed` or `run_failed`. Monotonic status transitions only.

**Canonical identifier**: `runs.id` is the single canonical run identifier. The `run_id` from ingest payloads maps directly to `runs.id` at insert time. There is no separate `run_id` column in `runs`.

This is already correct in the live ingest route:
```typescript
// route.ts: insert with id: run_id
await supabase.from('runs').insert({ id: run_id, ... })
// update by .eq('id', run_id)
await supabase.from('runs').update(update).eq('id', run_id)
```
The Codex confusion about dual-identifiers came from an inferred old migration. The runtime contract is unambiguous.

**Canonical status lifecycle**:
```
started → completed  (terminal success)
started → failed     (terminal failure)
```

For Phase 5 (queue model), extend to:
```
pending → queued → running → completed
                            → failed
                            → cancelled
                            → timed_out
```

For MVP: `started | completed | failed` is sufficient. Add `cancelled` and `timed_out` as nullable/check-constraint-safe additions now to avoid a breaking migration later.

**Canonical schema** (target — to be written as migration):
```sql
create table runs (
  id              uuid        primary key,               -- = run_id from payload
  agent_id        uuid        not null references agents(id),
  status          text        not null
                              check (status in (
                                'started', 'completed', 'failed',
                                'cancelled', 'timed_out'
                              )),
  started_at      timestamptz not null default now(),
  completed_at    timestamptz,
  timeout_at      timestamptz,                           -- set at run_started; enables zombie detection
  tokens_in       int,
  tokens_out      int,
  cost_usd        numeric(12,6),
  cost_reported   boolean     not null default false,    -- distinguishes null-cost from unreported-cost
  error           text,                                  -- terminal error summary
  parent_run_id   uuid        references runs(id),       -- for retry chains (null = first attempt)
  metadata        jsonb       not null default '{}'
);
```

**Immutability rule**:
- `status` transitions are monotonic (no reverting to earlier states).
- `tokens_in`, `tokens_out`, `cost_usd`, `error`, `metadata` may be patched by privileged actors with `updated_at` tracking.
- No row deletions. Logical deletion only if ever needed.

**`cost_reported` field**: Addresses the risk that `null cost_usd` is indistinguishable from "genuinely zero cost" vs "agent never reported cost." When `cost_reported = true`, the cost fields are authoritative (even if zero). When false, cost data is not yet available.

### 2.2 `agent_events` — Canonical Contract

**Semantics**: Append-only event trace for a run. Never updated or deleted. Every lifecycle signal from any agent in a run produces an event row. Events provide debugging granularity beyond what summary rows carry.

**Relationship to `runs`**: `agent_events` traces derive from the same signals that update `runs`. For each ingest event received, the route should: (1) upsert the `runs` summary, and (2) append an `agent_events` row. These are two writes from one ingested signal.

**Canonical event taxonomy**:

Operationally required:
- `run_started` — anchors run timeline
- `run_completed` — terminal success
- `run_failed` — terminal failure with error context
- `run_cancelled` — operator-initiated stop

Strongly recommended:
- `step_started` / `step_completed` — for multi-step agents
- `tool_called` / `tool_returned` — for tool-using agents
- `output_produced` — when an artifact is written to `agent_outputs`
- `cost_reported` — when cost data is updated (allows audit of cost reporting timing)

Future (Phase 8):
- `approval_requested` / `approval_granted` / `approval_denied` — HITL flows

**Canonical schema**:
```sql
create table agent_events (
  id              uuid        primary key default gen_random_uuid(),
  run_id          uuid        not null references runs(id),
  agent_id        uuid        not null references agents(id),
  event_type      text        not null
                              check (event_type in (
                                'run_started', 'run_completed', 'run_failed',
                                'run_cancelled', 'step_started', 'step_completed',
                                'tool_called', 'tool_returned', 'output_produced',
                                'cost_reported', 'checkpoint'
                              )),
  event_time      timestamptz not null default now(),
  sequence        int         not null,                  -- monotonic within run_id; assigned at insert
  payload         jsonb       not null default '{}'
);
-- No UPDATE or DELETE policies. Append-only enforced by policy.
```

**Append-only enforcement**: Row-level security policies should allow INSERT only (no UPDATE/DELETE) for all event rows. This is a governance property, not just a convention.

**Ingest route write path (required addition)**:
For every event received at `/api/ingest`:
1. Update `runs` (current behavior — retain).
2. INSERT a corresponding row into `agent_events` (new behavior — must add).

The `sequence` value should be computed as `SELECT COALESCE(MAX(sequence), 0) + 1 FROM agent_events WHERE run_id = $run_id`. This is slightly racy under concurrent writes but acceptable for current scale. For Phase 5+, consider a dedicated sequence mechanism.

### 2.3 `agent_outputs` — Canonical Contract

**Semantics**: Durable artifact produced by a run. Immutable after creation. New version = new row with `version + 1`. Links to the run that produced it via `run_id`.

**Artifact vs Event distinction**:
- **Event**: a point-in-time lifecycle occurrence (something that happened).
- **Artifact**: a durable object produced as output (something that was created and persisted).

**Output taxonomy — reconciled** (add `ui_components` and `code_artifact`):
```sql
check (output_type in (
  'marketing_brief',
  'lp_blueprint',
  'strategy_summary',
  'context_snapshot',
  'ui_components',       -- ADD: emitted by orchestrator currently
  'code_artifact',       -- ADD: for code generation outputs
  'research_report',     -- ADD: for research agent outputs
  'eval_result',         -- ADD: for evaluation agent outputs
  'other'                -- RETAIN: fallback, but discourage in production
))
```

**Governance rule**: `other` is acceptable for prototyping only. Before any new `output_type` is used in a production agent, it must be added to the check constraint via a migration.

**Immutability rule**: No updates to existing output rows. If content changes, insert a new row with `version = previous_version + 1`. The `(run_id, output_type, version)` combination should be unique.

**Lineage**: `run_id` FK is the primary lineage link. Optional `event_id UUID REFERENCES agent_events(id)` provides sub-run lineage when an output is produced by a specific step event.

**`gdrive_file_id` and `gdrive_url`**: These are useful for GDrive integration but should not be the primary content store. `content JSONB` holds the authoritative artifact. GDrive pointers are supplementary.

### 2.4 `project_state` — Canonical Contract

**Decision**: Typed columns (Option A). The live API already implements this correctly.

**Rationale**:
- The three fields (`current_state`, `todo`, `lessons`) are universal operational concepts applicable to every project type.
- The API already implements Option A and it works.
- Flexibility is covered by the `project_tag` enum being extensible.
- JSON envelope (Option B) would add parsing complexity for no gain at current scale.
- Hybrid (Option C) creates "where does state go" ambiguity.

**Canonical schema**:
```sql
create table project_state (
  project_tag     text        primary key
                              check (project_tag in (
                                'master-agentic-flow',
                                'reformai',
                                'notion-personal-os',
                                'resume-career',
                                'global'
                              )),
  current_state   text        not null default '',
  todo            text        not null default '',
  lessons         text        not null default '',
  updated_at      timestamptz not null default now()
);
```

The `project_tag` check constraint mirrors the Zod enum in the API route. Both must be updated together when a new project is added.

**Extension path**: If project-specific structured state is needed later, add `metadata JSONB DEFAULT '{}'` to this table. Do not switch to a JSON envelope model.

---

## Part 3: Schema Governance Strategy

### 3.1 Canonical Source-of-Truth Hierarchy

1. **Canonical intent**: migrations + documented API/runtime contracts in this repo.
2. **Operational reality**: live Supabase schema.
3. **During reconciliation**: live DB may diverge from migrations. Reconciliation migrations close the gap.
4. **After reconciliation**: migrations must exactly reproduce live schema. Any live change requires a migration.

### 3.2 Schema Change Lifecycle

Every schema change must complete ALL steps before being considered done:

```
1. PROPOSE  → document the change rationale (PR description)
2. VALIDATE → check API/runtime impact (column names, types, constraints)
3. MIGRATE  → write forward-only SQL migration in supabase/migrations/NNN_description.sql
4. APPLY    → run migration against live DB
5. ALIGN    → update API routes and runtime code atomically
6. VERIFY   → run contract tests confirming new schema shape
7. DOCUMENT → update HANDOFF_PROTOCOL.md and AI_AGENT_INFRASTRUCTURE_MASTER_DOCUMENT.md
```

A schema change is incomplete if any step is skipped.

### 3.3 Migration Discipline

- **Forward-only**: no down migrations. Rollback means a follow-on migration.
- **Sequential**: `001_`, `002_`, `003_` — no gaps, no out-of-order applies.
- **Self-contained**: each migration is safe to run in isolation.
- **No invalid seed data**: fix the UUID seed errors in `companies` (invalid characters `g`, `h`) before the next migration apply.
- **Idempotent where possible**: use `IF NOT EXISTS` for table/column additions.

### 3.4 API Contract Validation

- Zod schemas in API routes are the contract validators for incoming payloads.
- Contract tests should POST known-good and known-bad payloads and assert response codes and body shapes.
- Add contract tests for: `/api/ingest`, `PUT /api/project-state`, `GET /api/project-state/[tag]`.
- Long-term: `/api/v1/ingest` versioned path for breaking changes without breaking agents in the field.

### 3.5 Runtime Contract Validation

- Python SDK `emit()` already validates event type at Zod level (via API).
- Add an allowed-event-type list to `OversightClient.emit()` for client-side early validation.
- Orchestrator should validate `output_type` against a known-good list before writing to Supabase.
- Add output type validation as a shared utility in the Python SDK or agent library.

---

## Part 4: Operational Risks Inventory

### 4.1 Zombie Run Risk (HIGH)
**Description**: Runs that emit `run_started` but never receive a terminal event (`run_completed` or `run_failed`) stay in `started` status indefinitely. No mechanism exists to detect or close them.
**Impact**: Inflated in-progress counts; inaccurate success rate metrics; operator confusion.
**Mitigation**: Add `timeout_at` to `runs` at insert time. Build a cleanup job (Phase 5+) to mark timed-out runs as `failed`.

### 4.2 `agent_events` Write Path Missing (HIGH)
**Description**: The ingest route never writes to `agent_events`, even though the table likely exists live. All observability from event traces is absent.
**Impact**: Run detail pages will have no event timeline. Debugging is limited to summary fields only.
**Mitigation**: Add `agent_events` INSERT to ingest route as part of Phase 1 reconciliation.

### 4.3 `001_initial_schema.sql` Missing (HIGH)
**Description**: The foundational migration file for `companies`, `agents`, `agent_definitions`, `runs`, `project_state` does not exist in the repo.
**Impact**: The platform cannot be reproduced from migrations alone. Any reset destroys foundational tables.
**Mitigation**: Create `001_initial_schema.sql` as the first reconciliation deliverable.

### 4.4 Cost Null Ambiguity (MEDIUM)
**Description**: `cost_usd = null` is indistinguishable from "agent never reported cost" vs "genuinely zero cost." Cost dashboards will aggregate with silent holes.
**Impact**: Cost reporting is unreliable as an operational metric.
**Mitigation**: Add `cost_reported BOOLEAN DEFAULT false` to `runs`. Agents set `cost_reported = true` when they report cost, even if zero.

### 4.5 FK Violation on Output Write (MEDIUM)
**Description**: If the `run_started` ingest call fails (network error, auth failure), the `runs` row is never created. If the orchestrator then writes an `agent_outputs` row with that `run_id`, the FK constraint triggers a violation.
**Impact**: Output artifacts lost or write fails silently; lineage broken.
**Mitigation**: Orchestrator should verify ingest success before proceeding. OversightClient should raise (not swallow) ingest failures in critical paths. Add retry logic to SDK emit().

### 4.6 Token/Cost Data Loss on Agent Crash (MEDIUM)
**Description**: The Python SDK accumulates `tokens_in`, `tokens_out`, `cost_usd` in-memory via `RunContext.report()`. If the agent process crashes before emitting `run_completed`, all accumulated data is lost.
**Impact**: Runs show null cost/token fields even when work was performed.
**Mitigation (Phase 2)**: Add a `step_cost_reported` event type to `agent_events` so step-level cost data is persisted incrementally. `runs` aggregate cost can be recalculated from events if needed.

### 4.7 AI-Generated Output Type Drift (LOW-MEDIUM)
**Description**: When LLMs write new agent code, they may introduce new `output_type` values not in the check constraint. The Supabase insert silently fails (or raises an error that the agent ignores).
**Impact**: Artifact writes fail without clear operator visibility.
**Mitigation**: Add `output_type` validation to the Python SDK or agent base class before the Supabase write. Log failed writes with clear error context.

### 4.8 Event Taxonomy Drift (LOW)
**Description**: New event types emitted by agents will fail Zod validation at the ingest route (`event` field is an enum). Agents will receive 422 errors.
**Impact**: New agent behaviors can't report new event types without API changes.
**Mitigation**: Design the ingest schema to accept a broader `event` type (text + server-side allowlist) rather than a strict Zod enum. This allows new types to be added without API version bumps.

### 4.9 Sequence Race Condition in `agent_events` (LOW)
**Description**: The proposed sequence number strategy (`MAX(sequence) + 1`) is slightly racy under concurrent writes for the same `run_id`.
**Impact**: Sequence numbers may not be strictly monotonic under concurrent multi-agent runs.
**Mitigation (Phase 1)**: Accept this for now — concurrent writes to the same run are rare in the current synchronous execution model. Phase 5 introduces a proper sequence mechanism.

---

## Part 5: Reconciliation Implementation Plan

### Priority 1: Foundation Migration (BLOCKING everything else)

**Create `001_initial_schema.sql`** — foundational tables matching live DB.

The live schema must be inspected (via Supabase PostgREST `/rest/v1/` OpenAPI or direct query) before writing this file. The migration must reflect actual live column names and types, not inferred ones.

Tables to include:
- `companies` (fix invalid UUID seeds)
- `agent_definitions`
- `agents` (with all columns from LESSONS_LEARNED, including `parent_agent_id`, `depth`, `cost_limit_usd`, etc.)
- `runs` (with canonical schema from §2.1)
- `project_state` (with canonical schema from §2.4)

**Safest approach**: Query live DB first. Write migration to match. Do not guess column types or constraints.

### Priority 2: Reconcile `runs` Contract

**Create `003_reconcile_runs.sql`** — alter `runs` to canonical contract.

Changes needed (based on ingest route analysis):
- Add `completed_at TIMESTAMPTZ` if missing.
- Add `tokens_in INT`, `tokens_out INT`, `cost_usd NUMERIC(12,6)` if missing.
- Add `error TEXT` if missing.
- Add `timeout_at TIMESTAMPTZ` (new field for zombie detection).
- Add `cost_reported BOOLEAN NOT NULL DEFAULT false`.
- Add `parent_run_id UUID REFERENCES runs(id)` (nullable, for retry chains).
- Ensure status check constraint includes `cancelled` and `timed_out`.
- Remove any ambiguous `run_id` or `event` columns if they exist in old migration (not needed — `id` is canonical).

### Priority 3: Reconcile `project_state` Contract

**Create `004_reconcile_project_state.sql`** — align to typed column schema.

If migration `001` creates the table correctly, this may be a no-op. Validate live schema first.

Changes needed:
- Rename `tag` → `project_tag` if old column name is `tag`.
- Rename `state` → flatten into `current_state`, `todo`, `lessons` if old column is generic JSON.
- Add `check` constraint on `project_tag` values.

### Priority 4: `agent_outputs` Taxonomy Update

**Create `005_agent_outputs_taxonomy.sql`** — add missing output types.

```sql
-- Drop and recreate check constraint with expanded taxonomy
ALTER TABLE agent_outputs DROP CONSTRAINT IF EXISTS agent_outputs_output_type_check;
ALTER TABLE agent_outputs ADD CONSTRAINT agent_outputs_output_type_check
  CHECK (output_type IN (
    'marketing_brief', 'lp_blueprint', 'strategy_summary', 'context_snapshot',
    'ui_components', 'code_artifact', 'research_report', 'eval_result', 'other'
  ));
```

Also add:
- `event_id UUID REFERENCES agent_events(id)` (nullable) — sub-run lineage.
- Unique constraint on `(run_id, output_type, version)`.

### Priority 5: `agent_events` Table

**Create `006_agent_events.sql`** — append-only event trace table.

Use schema from §2.2. Include:
- RLS policy: INSERT allowed for service role; SELECT allowed for authenticated; UPDATE and DELETE blocked for all.

### Priority 6: Ingest Route Update

**Update `src/app/api/ingest/route.ts`** — add `agent_events` write path.

For each validated ingest event:
1. Compute `sequence` via subquery.
2. INSERT into `agent_events`.
3. Return error if event insert fails (don't silently drop).

Also expand the Zod `event` enum to allow step/tool events for forward compatibility:
```typescript
event: z.enum([
  'run_started', 'run_completed', 'run_failed',
  'step_started', 'step_completed',
  'tool_called', 'tool_returned',
  'output_produced', 'checkpoint'
])
```

### Priority 7: Contract Tests

**Add contract tests** for:
- `POST /api/ingest` with `run_started` → verify `runs` row created and `agent_events` row created.
- `POST /api/ingest` with `run_completed` → verify `runs` updated and event appended.
- `PUT /api/project-state` with valid/invalid payloads.
- `GET /api/project-state/[tag]` with known tag.

### Implementation Order Summary

```
1. Inspect live DB (Supabase) to confirm actual column names/types
2. Create 001_initial_schema.sql
3. Create 003_reconcile_runs.sql
4. Create 004_reconcile_project_state.sql
5. Create 005_agent_outputs_taxonomy.sql
6. Create 006_agent_events.sql
7. Apply migrations to live DB (in order)
8. Update ingest route to write agent_events
9. Write and run contract tests
10. Update docs to reflect reconciled state
```

### Rollback Considerations
- All migrations are forward-only. No down migrations.
- If a migration fails: assess damage, write a follow-on corrective migration.
- Never drop columns with live data without confirming data is backed up.
- `agent_events` additions are purely additive — safe to roll forward if issues arise.

---

## Part 6: Roadmap Impact Assessment

### Phase 1 scope expands — does this change phase sequencing?

No major resequencing needed. The additional work (primarily creating `001_initial_schema.sql` and adding the `agent_events` write path) belongs in Phase 1 scope. The MVP roadmap phases remain valid.

**What changes**: Phase 1 completion criteria now explicitly include:
- `001_initial_schema.sql` exists and matches live DB.
- `agent_events` write path is active in the ingest route.
- Contract tests verify the reconciled schema.

### Phase 2 is still gated on Phase 1 completion

Do not begin Phase 2 (Telemetry Standardization) until:
- [ ] `001_initial_schema.sql` created and validated.
- [ ] `runs` canonical contract implemented (migration + tests).
- [ ] `project_state` canonical contract implemented.
- [ ] `agent_outputs` taxonomy reconciled.
- [ ] `agent_events` table created and ingest route writes to it.
- [ ] Contract tests pass for ingest and project-state APIs.

---

## Part 7: Unresolved Questions

1. **Live DB column confirmation**: What are the exact column names, types, and constraints in the live `runs`, `companies`, `agents`, `agent_definitions`, and `project_state` tables? This must be verified before writing `001_initial_schema.sql`.

2. **`agent_events` live status**: Does `agent_events` already exist in the live DB? If so, what is its exact schema? This determines whether `006_agent_events.sql` is `CREATE TABLE` or `ALTER TABLE`.

3. **`projects` table**: Is there a `projects` table in the live DB? If so, should `project_state.project_tag` eventually FK to it rather than use a check constraint?

4. **Governance table existence**: Do `policies` and `audit_log` tables exist in the live DB? What is their exact schema? These are required before Phase 6 (Controlled Execute).

5. **Live QA/cost views**: What summary views exist live (mentioned in Codex audit and master doc)? These should be backfilled into a migration before they can be relied on.

6. **`event` field expansion in ingest**: Expanding the Zod enum for `event` types is a breaking change for old SDK versions. Do any deployed agents use hardcoded event types that would be impacted?

7. **Retry semantics**: When should `parent_run_id` be set? The orchestrator currently doesn't have retry logic — this field can be left null until Phase 5 introduces the queue model.

8. **`cost_usd` precision**: Is `NUMERIC(12,6)` the right precision for cost fields? This allows up to $999,999.999999 per run. Should this be `NUMERIC(18,8)` for sub-cent precision at high token volumes?

---

## Part 8: Recommended Next Implementation Step

**Immediate first action**: Query the live Supabase DB to confirm exact column names and types for all foundational tables. Use the Supabase PostgREST OpenAPI spec at `https://<project-ref>.supabase.co/rest/v1/` or run `SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'runs'` via the Supabase SQL editor.

**Second action**: Write `001_initial_schema.sql` based on confirmed live schema.

**Do not**: Begin Phase 2 features before these actions complete.
