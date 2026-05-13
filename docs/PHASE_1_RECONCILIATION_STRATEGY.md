# Phase 1 — Reconciliation Strategy (2026-05-12)
**Status: UPDATED after live schema verification (2026-05-12)**

## Document Purpose
This document defines the architectural reconciliation strategy that must be executed before Phase 2 work begins. It evolved through three analytical passes:
1. Codex's Phase 1 schema stabilization audit (inferred from missing migration file)
2. Claude's reconciliation review (challenged Codex assumptions from code reading)
3. **This version: corrected from live Supabase schema verification via PostgREST API**

Live verification invalidated several assumptions in the previous version. All corrections are noted explicitly.

Related documents:
- `docs/LIVE_SUPABASE_SCHEMA_INVENTORY.md` — authoritative live schema facts
- `docs/PHASE_1_RECONCILIATION_IMPLEMENTATION_PLAN.md` — step-by-step execution plan
- `docs/PHASE_1_SCHEMA_STABILIZATION_AUDIT.md` — Codex's original findings (reference only)

---

## Part 1: Validated Findings and Corrections

### 1.1 Source-of-Truth Governance (Unchanged)

**Confirmed position**:
- **Canonical intent**: migrations + documented API/runtime contracts (what the system *should* be).
- **Operational reality**: live DB (what the system *is*).
- After reconciliation, migrations must reproduce live schema exactly. Any live change requires a migration.

**Status**: ✅ Confirmed correct.

### 1.2 `001_initial_schema.sql` Is Missing (Confirmed)

**Status**: ✅ Confirmed by live verification. Only `002_agent_outputs.sql` exists. All foundational tables are uncovered by migrations. Creating `001_initial_schema.sql` is the highest-priority deliverable.

### 1.3 `agent_events` Write Path Is Absent (Confirmed)

**Status**: ✅ Confirmed by live verification. `agent_events` table exists with 0 rows. The ingest route has never written to it. Event observability is zero.

**New finding**: The ingest-to-agent_events mapping is non-trivial. The live `agent_events` schema requires fields the current SDK does not emit (`severity`, `depth`, `message`, `company_id`). The ingest route must derive these from context. See §2.2.

### 1.4 Dual Run Identifier Concern (Resolved)

**Codex finding**: Concern about `id` vs `run_id` columns in `runs`.

**Status**: ✅ Resolved by live verification. Live `runs` table has only `id` (the canonical identifier). No `run_id` column and no `event` column exist in live DB. The ingest route correctly uses `id: run_id` at insert and `.eq('id', run_id)` at update.

### 1.5 Corrections to Previous Version of This Document

The previous version (before live verification) contained schema proposals that do not match live DB. The following are the confirmed corrections:

| Proposal | Verified live reality | Correction |
|---|---|---|
| `agent_events.run_id` REQUIRED | `run_id` is **NULLABLE** | Events can exist without a run |
| `agent_events.event_time` column | Column is `occurred_at` | Use `occurred_at` |
| `agent_events.sequence` column | Does NOT exist in live | Remove from contract |
| Simple 7-column `agent_events` | 17-column schema with severity, depth, message, company_id, orchestrator/platform run IDs | Match live schema |
| `project_state` PK = `project_tag` | PK = `id` (UUID); `project_tag` is UNIQUE only | Use uuid PK consistent with all other tables |
| `runs` canonical schema (no `created_at`) | Live `runs` HAS `created_at` REQUIRED | Add `created_at` to contract |

---

## Part 2: Canonical Contract Definitions (Post-Verification)

### 2.1 `runs` — Canonical Contract

**Semantics**: One durable execution summary row per run lifecycle. Created at `run_started`, updated at `run_completed` or `run_failed`. Monotonic status transitions only.

**Canonical identifier**: `runs.id` is the single canonical identifier. No `run_id` column exists.

**Canonical status values** (confirmed from live data): `started`, `completed`, `failed`.

**Additional status values to add via migration** (for Phase 5 queue model readiness): `cancelled`, `timed_out`.

**Canonical schema — verified live columns plus proposed additions**:
```sql
-- LIVE COLUMNS (document in 001_initial_schema.sql exactly as-is):
create table runs (
  id              uuid        primary key,
  agent_id        uuid        not null references agents(id),
  status          text        not null,              -- check constraint: confirm exact values from SQL editor
  started_at      timestamptz not null,
  completed_at    timestamptz,
  tokens_in       int,
  tokens_out      int,
  cost_usd        numeric,                           -- precision: confirm from SQL editor
  error           text,
  metadata        jsonb,
  created_at      timestamptz not null default now() -- REQUIRED in live, was missing from prior proposal
);

-- ADDITIONS via 007_runs_enhancements.sql:
alter table runs add column if not exists timeout_at    timestamptz;
alter table runs add column if not exists cost_reported boolean not null default false;
alter table runs add column if not exists parent_run_id uuid references runs(id);
```

**`cost_reported` field semantics**: `cost_usd = null` is ambiguous — it could mean "never reported" or "genuinely zero cost." When `cost_reported = true`, cost fields are authoritative even if zero. When false, cost data is absent. This is a **required sentinel** for reliable financial dashboards.

**`timeout_at` field semantics**: Set at `run_started` insert time (e.g., now() + 1 hour as default). Enables a future cleanup job to mark stale `started` runs as `failed`. Live DB has 2+ zombie runs from March 2026 with no cleanup.

**`parent_run_id` semantics**: Links retry attempts to the original run. Null for first attempts. The orchestrator has no retry logic today — this field will remain null until Phase 5.

**Immutability rule**: Status transitions are monotonic. Cost/token/error/metadata fields are patchable by privileged actors but never deleted.

**LIVE COST DATA STATUS**: All 51 live run rows have `cost_usd = null`, `tokens_in = null`, `tokens_out = null`. The cost aggregation views (`agent_cost_summary`, etc.) consequently show zero for all agents. **Cost views must be treated as unreliable until agents begin reporting cost data.**

### 2.2 `agent_events` — Canonical Contract

**Semantics**: Append-only operational event trace. Never updated or deleted.

**Live schema** (17 columns — confirmed from PostgREST OpenAPI):
```sql
-- Document in 003_add_agent_events.sql matching live schema:
create table agent_events (
  id                      uuid        primary key default gen_random_uuid(),
  agent_id                uuid        not null references agents(id),
  company_id              uuid        not null references companies(id),
  project_id              uuid        references projects(id),
  run_id                  uuid,                          -- NULLABLE: events can exist without a run
  event_type              text        not null,          -- check constraint: confirm allowed values
  occurred_at             timestamptz not null default now(),
  message                 text        not null,          -- human-readable event description
  payload                 jsonb       not null default '{}',
  severity                text        not null,          -- e.g., 'info', 'warn', 'error'
  depth                   int         not null,          -- agent hierarchy depth
  duration_ms             int,
  cost_usd                numeric,
  tokens_in               int,
  tokens_out              int,
  orchestrator_run_id     text,                          -- cross-system run correlation
  platform_run_id         text,                          -- platform-level run correlation
  triggered_by_agent_id   uuid        references agents(id)
);
```

**Key design differences from prior proposal**:
- `run_id` is **nullable**: system-level events (startup, policy evaluation) can exist without a run context.
- `occurred_at` (not `event_time`): match live column name.
- `sequence` does not exist: events ordered by `occurred_at` only. Sub-millisecond ordering is not guaranteed under concurrent writes.
- `message` is required: every event must have a human-readable description.
- `severity` is required: `info` / `warn` / `error` taxonomy (exact allowed values to confirm via SQL editor).
- `depth` is required: derived from the agent's hierarchy depth at the time of the event.
- `company_id` is required: events are always scoped to a company.
- `triggered_by_agent_id`: actor agent (orchestrator that triggered the event, if applicable).
- `orchestrator_run_id` / `platform_run_id`: cross-system run correlation for multi-platform environments.

**Append-only enforcement**: RLS policy — INSERT allowed (service role), SELECT allowed (authenticated), UPDATE/DELETE blocked for all roles.

**Ingest route write path — required field mapping**:

The current ingest route receives:
```
{ agent_id, event, run_id, timestamp, tokens_in, tokens_out, cost_usd, error, metadata }
```

To write to `agent_events`, the route must:
1. Expand `agents` select to include `company_id` and `depth`:
   ```typescript
   .select('id, status, company_id, depth')
   ```
2. Map fields:
   | SDK field | agent_events column | Derivation |
   |---|---|---|
   | `agent_id` | `agent_id` | Direct |
   | (from agents row) | `company_id` | From agent record |
   | (from agents row) | `depth` | From agent record |
   | `run_id` | `run_id` | Direct (nullable) |
   | `event` | `event_type` | Direct rename |
   | `timestamp` or now() | `occurred_at` | Direct or default |
   | (derived) | `message` | Derive from event_type: "Run started", "Run completed", "Run failed" |
   | (derived) | `severity` | Map: run_started/completed → 'info'; run_failed → 'error' |
   | `metadata` | `payload` | Map + merge with error field |

3. Write the event row after the `runs` upsert succeeds.

**Open question**: Should the ingest route fail (5xx) if the `agent_events` write fails, or silently continue? Recommendation: log the failure and return success — event trace writes should be best-effort to avoid blocking agents on observability failures. Mark as tech debt.

**Event taxonomy** (what `event_type` values to allow in CHECK constraint):

Operationally required (map from current SDK):
- `run_started`
- `run_completed`
- `run_failed`

Recommended additions (for future SDK expansion):
- `run_cancelled`
- `step_started` / `step_completed`
- `tool_called` / `tool_returned`
- `output_produced`
- `checkpoint`

Note: the exact live CHECK constraint expression for `event_type` is **unconfirmed** (requires Supabase SQL editor). The migration file should define these values explicitly and reconcile with live constraint.

### 2.3 `agent_outputs` — Canonical Contract

**Semantics**: Durable artifact produced by a run. Immutable after creation.

**Live schema** (confirmed from rows + OpenAPI):
```sql
-- Already in 002_agent_outputs.sql (keep as-is for 001/002):
id, agent_id, run_id, company_id, output_type, content, gdrive_file_id, gdrive_url, version, created_at
```

**CHECK constraint — current (from migration 002)**:
```sql
check (output_type in (
  'marketing_brief', 'lp_blueprint', 'strategy_summary', 'context_snapshot', 'other'
))
```
`ui_components` is NOT allowed, which is why orchestrator writes for it fail silently.

**Live data reality**: All 19 live rows are `lp_blueprint`. `ui_components` has never successfully been written.

**Taxonomy expansion (via `006_fix_agent_outputs_constraint.sql`)**:
```sql
alter table agent_outputs drop constraint if exists agent_outputs_output_type_check;
alter table agent_outputs add constraint agent_outputs_output_type_check
  check (output_type in (
    'marketing_brief', 'lp_blueprint', 'strategy_summary', 'context_snapshot',
    'ui_components',    -- add: emitted by orchestrator
    'code_artifact',    -- add: for code generation
    'research_report',  -- add: for research outputs
    'eval_result',      -- add: for evaluation outputs
    'other'             -- retain: fallback (discourage in production)
  ));
```

**`event_id` linkage**: The prior proposal suggested adding `event_id UUID REFERENCES agent_events(id)` for sub-run lineage. This column does NOT exist in live. Decision: defer to Phase 7. `run_id` FK is sufficient for MVP observability.

**Unique constraint**: Defer `UNIQUE(run_id, output_type, version)` to Phase 7. Not blocking for Phase 1.

### 2.4 `project_state` — Canonical Contract

**Decision**: Typed columns. Live API already implements this correctly.

**Correction from previous version**: Live DB has `id UUID PRIMARY KEY` (auto-generated), not `project_tag TEXT PRIMARY KEY`.

**Live schema** (confirmed from rows):
```sql
-- In 001_initial_schema.sql:
create table project_state (
  id            uuid        primary key default gen_random_uuid(),
  project_tag   text        not null unique,          -- unique constraint, not PK
  current_state text        not null default '',
  todo          text        not null default '',
  lessons       text        not null default '',
  updated_at    timestamptz not null default now()
);
```

**CHECK constraint on `project_tag`**: Not confirmed from PostgREST (requires SQL editor). The live data shows 5 project_tag values: `notion-personal-os`, `resume-career`, `global`, `master-agentic-flow`, `reformai`. The API Zod enum enforces these at the application layer. Decision: **do not add a CHECK constraint in the migration** — use only the UNIQUE constraint. Allowed tags are governed by the Zod enum in the API, which is easier to evolve than a DB constraint.

Rationale: a DB CHECK constraint on project_tag would require a migration every time a new project is added. The Zod enum in the API route is sufficient governance for this field at current scale.

**API compatibility**: The API's `.upsert({project_tag, ...}, {onConflict: 'project_tag'})` is correct. `id` auto-generates on new inserts; existing rows are updated on project_tag conflict. ✅

---

## Part 3: Schema Governance Strategy (Unchanged from previous version)

### 3.1 Canonical Source-of-Truth Hierarchy
1. **Canonical intent**: migrations + documented API/runtime contracts.
2. **Operational reality**: live Supabase schema.
3. **During reconciliation**: live DB may diverge. Reconciliation migrations close the gap.
4. **After reconciliation**: migrations must exactly reproduce live. Any live change requires a migration.

### 3.2 Schema Change Lifecycle
```
1. PROPOSE  → document rationale
2. VALIDATE → check API/runtime impact
3. MIGRATE  → write forward-only SQL migration
4. APPLY    → run against live DB
5. ALIGN    → update API/runtime code atomically
6. VERIFY   → run contract tests
7. DOCUMENT → update HANDOFF_PROTOCOL.md + AI_AGENT_INFRASTRUCTURE_MASTER_DOCUMENT.md
```

### 3.3 Migration Discipline
- **Forward-only**: no down migrations.
- **Sequential**: 001_, 002_, 003_ — no gaps.
- **Self-contained**: each migration runs safely in isolation.
- **Idempotent**: use `IF NOT EXISTS` / `IF NOT EXISTS` for additive changes.
- **No invalid seed data**: `companies` seed uses valid UUIDs confirmed from live data.

### 3.4 API Contract Validation
- Zod schemas in API routes are the contract validators.
- Contract tests: known-good and known-bad payloads → assert HTTP status and response shape.
- Contract tests for `/api/ingest` and `/api/project-state*` are Phase 1 deliverables.

### 3.5 Runtime Contract Validation
- Add `output_type` validation to orchestrator before Supabase write.
- Add allowed event-type list to `OversightClient.emit()` for client-side early validation.
- Ingest route should map SDK `event` field to `agent_events.event_type` consistently.

---

## Part 4: Operational Risks Inventory (Post-Verification)

### 4.1 Zombie Runs — CONFIRMED HIGH
**Status**: Confirmed by live data. Multiple runs from 2026-03-21 with `status='started'` and `completed_at=null`.
**Mitigation**: Add `timeout_at` via `007_runs_enhancements.sql`. Cleanup job in Phase 5.

### 4.2 `agent_events` Write Path Absent — CONFIRMED HIGH
**Status**: Confirmed. Table exists with 0 rows.
**Mitigation**: Update ingest route after `003_add_agent_events.sql` is applied.
**New complexity**: The field mapping requires `company_id` and `depth` from the agents record; message and severity must be derived.

### 4.3 `001_initial_schema.sql` Missing — CONFIRMED CRITICAL
**Status**: Confirmed. All 10+ foundational objects have no migration.
**Mitigation**: Write `001_initial_schema.sql` from verified live schema.

### 4.4 Cost Data Universally Null — CONFIRMED MEDIUM
**Status**: Confirmed. All 51 live runs have null cost/token data. All 3 cost views show zero. Cost observability is completely non-functional.
**Root cause**: `OversightClient.report()` exists but agents never call it with real cost data, OR the `run_completed` event fires but accumulates zero because agents don't call `run.report()`.
**Mitigation**: Add `cost_reported` sentinel via `007_runs_enhancements.sql`. Separately, investigate why agents never report cost data and fix in Phase 2 (Telemetry Standardization).

### 4.5 `agent_outputs.output_type` Constraint — CONFIRMED BLOCKING
**Status**: Confirmed. `ui_components` fails constraint. Only `lp_blueprint` used in practice.
**Mitigation**: `006_fix_agent_outputs_constraint.sql`.

### 4.6 FK Violation Risk on Output Write — MEDIUM
**Status**: Unchanged. If `run_started` ingest fails, subsequent output writes fail FK constraint.
**Mitigation**: Orchestrator should check ingest success before proceeding.

### 4.7 Token/Cost Data Loss on Crash — MEDIUM
**Status**: Unchanged (now confirmed empirically — zero cost data in 51 runs).
**Mitigation (Phase 2)**: Add step-level cost events to `agent_events` so cost is persisted incrementally.

### 4.8 AI-Generated Output Type Drift — LOW-MEDIUM
**Status**: Unchanged.
**Mitigation**: Add output_type validation to SDK/orchestrator before Supabase write.

### 4.9 `agent_events.sequence` Race Condition — REMOVED
**Correction**: Removed. The live `agent_events` schema has no `sequence` column. Events are ordered by `occurred_at` only. This risk is moot.

### 4.10 Ingest-to-agent_events Field Mapping Complexity — NEW MEDIUM
**Description**: The live `agent_events` schema requires `company_id`, `depth`, `message`, and `severity` — none of which the current SDK emits directly. The ingest route must derive these from context.
**Risk**: If the derivation logic is wrong (e.g., agent record not found, depth is 0 by default), event rows will be written with incorrect data that pollutes observability.
**Mitigation**: Implement carefully with explicit fallbacks; test with contract tests before activating.

### 4.11 Cost Views Unreliable — CONFIRMED MEDIUM
**Description**: Three cost aggregation views (`agent_cost_summary`, `company_cost_summary`, `project_cost_summary`) are live but show zero for all values because `runs.cost_usd` is universally null.
**Impact**: Dashboard cost displays will show zero even after implementation — will look like a bug.
**Mitigation**: Label these views as unreliable in API responses and dashboard until cost population is fixed. Fix cost population in Phase 2.

---

## Part 5: Revised Reconciliation Sequence

### Migration Backfill Sequence

```
Migration 001 — 001_initial_schema.sql (CREATE, foundation)
  Purpose: Document and reproduce all live foundational tables
  Objects: companies, agent_definitions, agents, projects, runs, project_state
  Risk: HIGH (creates tables that already exist live — must use IF NOT EXISTS)
  Dependency: None (first migration)

Migration 002 — 002_agent_outputs.sql (already exists)
  Purpose: agent_outputs table
  Status: File exists, but CHECK constraint is stale
  Do not modify this file — the constraint fix is in 006

Migration 003 — 003_add_agent_events.sql (CREATE)
  Purpose: Document agent_events table matching live schema
  Objects: agent_events (17 columns)
  Risk: MEDIUM (table already exists live — IF NOT EXISTS required)
  Dependency: 001 (agents, companies, projects, runs FKs)

Migration 004 — 004_add_governance_tables.sql (CREATE)
  Purpose: Document policies, audit_log, agent_qa_results
  Objects: 3 tables
  Risk: LOW (tables exist live but are empty)
  Dependency: 001 (agents FK)

Migration 005 — 005_add_cost_views.sql (CREATE VIEW)
  Purpose: Document 3 cost aggregation views
  Objects: agent_cost_summary, company_cost_summary, project_cost_summary
  Risk: LOW (views exist live — CREATE OR REPLACE)
  Dependency: 001, 003 (runs, agent_events, agents, companies)
  BLOCKER: View SQL bodies not yet retrievable via PostgREST — requires SQL editor

Migration 006 — 006_fix_agent_outputs_constraint.sql (ALTER)
  Purpose: Expand output_type CHECK to allow ui_components and others
  Objects: agent_outputs (ALTER CONSTRAINT)
  Risk: LOW (additive constraint change, no data migration needed)
  Dependency: 002

Migration 007 — 007_runs_enhancements.sql (ALTER)
  Purpose: Add sentinel fields to runs for operational trust
  Objects: runs (ADD COLUMN x3)
  Risk: LOW (additive columns, all nullable or with defaults)
  Dependency: 001
```

### Code Changes Required (Phase 1 scope)

```
Change A — Update /api/ingest/route.ts:
  - Expand agents SELECT to include company_id and depth
  - Add agent_events INSERT after runs upsert
  - Map SDK fields to agent_events columns (severity, depth, message, company_id)
  - Expand Zod event enum for future event types
  Dependency: Migration 003 applied

Change B — Update orchestrator.py (output validation only):
  - Add output_type validation before agent_outputs write
  - Validate against allowed list matching DB constraint
  Dependency: Migration 006 applied (constraint expanded)
```

### Contract Tests Required

```
Test 1: POST /api/ingest run_started
  - Verify: runs row created with correct fields
  - Verify: agent_events row created with correct mapping

Test 2: POST /api/ingest run_completed
  - Verify: runs row updated (status, completed_at, cost fields)
  - Verify: agent_events row appended

Test 3: POST /api/ingest run_failed
  - Verify: runs row updated (status=failed, error field)
  - Verify: agent_events row appended with severity=error

Test 4: PUT /api/project-state valid payload
  - Verify: row upserted on project_tag conflict
  - Verify: id auto-generated (uuid)

Test 5: GET /api/project-state/[tag] known tag
  - Verify: correct row returned
  - Verify: all expected fields present including id
```

---

## Part 6: Roadmap Impact — Unchanged

Phase sequencing remains valid. Phase 2 (Telemetry Standardization) must not begin until Phase 1 completion criteria are met.

**Phase 1 completion gate (updated)**:
- [ ] `001_initial_schema.sql` created and validated against live schema.
- [ ] `003_add_agent_events.sql` created and matches live schema (17 columns).
- [ ] `004_add_governance_tables.sql` created.
- [ ] `005_add_cost_views.sql` created (requires SQL editor for view SQL bodies).
- [ ] `006_fix_agent_outputs_constraint.sql` applied — `ui_components` writes succeed.
- [ ] `007_runs_enhancements.sql` applied — `timeout_at`, `cost_reported`, `parent_run_id` added.
- [ ] Ingest route updated to write `agent_events` (Change A).
- [ ] Contract tests pass for `/api/ingest` (both runs and agent_events writes verified).
- [ ] Contract tests pass for `/api/project-state`.
- [ ] Cost views labeled unreliable in documentation until Phase 2 cost population fix.

---

## Part 7: Resolved Questions (from previous version)

| Question | Status | Answer |
|---|---|---|
| Live DB column confirmation for `runs`, `companies`, `agents`, etc. | ✅ RESOLVED | See LIVE_SUPABASE_SCHEMA_INVENTORY.md |
| `agent_events` live status and schema | ✅ RESOLVED | Exists, 0 rows, 17-column schema confirmed |
| `projects` table live status | ✅ RESOLVED | Exists, empty, 7 columns |
| `policies` / `audit_log` live status | ✅ RESOLVED | Both exist, empty |
| Live cost views | ✅ RESOLVED | 3 views confirmed (agent_cost_summary, company_cost_summary, project_cost_summary) |
| Retry semantics / `parent_run_id` | ✅ RESOLVED | Defer to Phase 5; field null by default |

## Part 8: Remaining Open Questions

1. **CHECK constraint values** — exact allowed values for `runs.status`, `agent_events.severity`, `agent_events.event_type`, `project_state.project_tag` (if a check exists). Requires Supabase SQL editor.

2. **View SQL bodies** — exact SQL for the 3 cost views. Requires Supabase SQL editor. Needed to write `005_add_cost_views.sql`.

3. **RLS policy expressions** — exact RLS policies for each table. Needed to accurately write migrations.

4. **`numeric` precision for `cost_usd`** — live DB type shown as `numeric` (unqualified). Should migrations use `numeric(12,6)` or match unqualified `numeric`?

5. **`policies` scoping** — no `company_id` FK exists on `policies`. Are policies global-only, or should scoping be added in Phase 8?

6. **`agent_events` CHECK constraint** — does the live `event_type` column have a CHECK constraint? If so, what are the allowed values? This determines whether `003_add_agent_events.sql` is creating the table from scratch or must match an existing constraint.

7. **`agent_events.severity` allowed values** — what are the exact allowed strings? (`info`, `warn`, `error`? or more?)

8. **Cost population root cause** — why are all 51 runs showing null cost? Is `OversightClient.report()` never called, or called but with no arguments? Diagnosing this informs Phase 2 telemetry standardization work.
