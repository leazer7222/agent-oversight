# Phase 1 Reconciliation Implementation Plan

**Status**: Planning complete — ready for execution  
**Last updated**: 2026-05-13  
**Prerequisite docs**: `PHASE_1_RECONCILIATION_STRATEGY.md`, `LIVE_SUPABASE_SCHEMA_INVENTORY.md`  
**Branch**: `claude/suspicious-beaver-226b36`

---

## Executive Summary

Phase 1 schema stabilization is complete as a verification exercise. The live Supabase database diverges from the single committed migration (`002_agent_outputs.sql`) in ways that require 6 new migration files plus 3 targeted code changes before Phase 2 feature work can begin safely.

**Critical blockers** (must ship before Phase 2):
1. `agent_events` has no write path — observability is entirely non-functional
2. `agent_outputs.output_type` CHECK constraint rejects `ui_components` — orchestrator writes silently fail
3. TypeScript `Agent` interface uses wrong field names — any UI consuming live data renders garbage
4. `005_add_cost_views.sql` cannot be written without SQL editor access (view definitions unknown)

**Non-blocking but required before Phase 2 gate**:
5. `001_initial_schema.sql` must be created to bring migrations in sync with live DB
6. `timeout_at` and `parent_run_id` on `runs` are required for Phase 2 retry/cleanup logic
7. Cost observability is zero even where the schema supports it — agents never emit cost data

---

## Verified Starting Point

All findings below are from live PostgREST introspection (2026-05-12). Nothing is inferred.

### What exists in the live DB (verified)

| Table / View | Source | Status |
|---|---|---|
| `companies` | Unknown migration | Live, contains rows |
| `projects` | Unknown migration | Live, empty |
| `agents` | Unknown migration | Live, contains rows |
| `agent_definitions` | Unknown migration | Live, contains rows |
| `runs` | Unknown migration | Live, 51 rows |
| `agent_events` | Unknown migration | Live, **empty** — no write path |
| `agent_outputs` | `002_agent_outputs.sql` | Live, 19 rows |
| `policies` | Unknown migration | Live, empty |
| `budgets` | Unknown migration | Live, empty |
| `project_state` | Unknown migration | Live, empty |
| `runs_with_agents` | Unknown migration | Live view |
| `agent_cost_summary` | Unknown migration | Live view |
| `project_cost_summary` | Unknown migration | Live view |

### What is committed to migrations

Only one file: `supabase/migrations/002_agent_outputs.sql`

All other tables exist live but have **no migration source**. This means:
- The database was bootstrapped manually or via a migration that was never committed
- `001_initial_schema.sql` (referenced by Codex) does not exist in the repo
- All live schema details are the source of truth until `001_initial_schema.sql` is created

### Known live schema gaps vs operational requirements

| Gap | Impact | Phase 1 migration |
|---|---|---|
| `runs.timeout_at` missing | Zombie runs undetectable | `007_runs_reconciliation.sql` |
| `runs.parent_run_id` missing | Retry chains untraceable | `007_runs_reconciliation.sql` |
| `runs.cost_reported` missing | Null cost ambiguous | `007_runs_reconciliation.sql` |
| `agent_outputs.output_type` missing `ui_components` | Orchestrator writes fail silently | `006_fix_agent_outputs_constraint.sql` |
| `agent_events` has no ingest write path | Observability is zero | Code change in `route.ts` |
| `agents.Agent` TS interface wrong field names | UI renders garbage | Code change in `types.ts` |

---

## Reconciliation Principles

1. **Live DB is operational reality; migrations are governance source of truth.** When they conflict, migrations win for intent; live DB reveals what must be reverse-engineered into `001_initial_schema.sql`.

2. **Migrations are forward-only.** Never alter a previously applied migration file. If `001_initial_schema.sql` doesn't match live, fix it before first application — it has never been applied, so it is still editable.

3. **Verify live before writing migrations.** Every migration must pass a verification query before being marked complete.

4. **Code changes and migrations are coupled.** The `agent_events` write path in `route.ts` depends on `003_add_agent_events.sql` being applied first. Ship them together; do not apply one without the other.

5. **SQL editor access is required for 3 items.** Cost views, CHECK constraints, and RLS policies cannot be introspected via PostgREST. Obtain Supabase SQL editor access before attempting `005_add_cost_views.sql`.

6. **Don't assume idempotency.** Each migration must be tested against the live DB (which already has the objects). Use `IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`, and `ON CONFLICT` where appropriate, or confirm the migration is only applied to a fresh DB.

---

## Migration Backfill Sequence

```
001_initial_schema.sql          ← reverse-engineered from live DB
002_agent_outputs.sql           ← already committed (no changes)
003_add_agent_events.sql        ← CREATE TABLE with correct 17-column schema
004_add_governance_tables.sql   ← governance for output_type, event_type taxonomies
005_add_cost_views.sql          ← BLOCKED: requires SQL editor to view current definitions
006_fix_agent_outputs_constraint.sql  ← ADD ui_components to output_type CHECK
007_runs_reconciliation.sql     ← ADD timeout_at, parent_run_id, cost_reported
```

**Dependency graph**:
- `001` → `002` (agent_outputs requires agent_definitions and agents)
- `001` → `003` (agent_events FKs to companies, projects, agents)
- `001` → `004` (governance tables reference existing taxonomy)
- `002`, `004` → `005` (cost views JOIN agent_outputs and runs)
- `002` → `006` (ALTER TABLE agent_outputs)
- `001` → `007` (ALTER TABLE runs)

---

## Migration File Plan

### `001_initial_schema.sql`

**Purpose**: Reverse-engineer and document the schema that was applied manually to the live DB. This file is governance documentation that brings migrations into alignment with live reality. It has never been applied to the live DB and must be marked with a flag or applied to a fresh schema only.

**Objects**: `companies`, `projects`, `agents`, `agent_definitions`, `runs`, `agent_events` (empty shell), `policies`, `budgets`, `project_state`, `runs_with_agents` view (if applicable), `agent_cost_summary` view (if applicable), `project_cost_summary` view (if applicable)

**Key column contracts to encode**:

```sql
-- companies
create table companies (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  created_at  timestamptz not null default now()
  -- additional columns: verify via SQL editor
);

-- projects
create table projects (
  id          uuid primary key default gen_random_uuid(),
  company_id  uuid not null references companies(id),
  name        text not null,
  created_at  timestamptz not null default now()
  -- additional columns: verify via SQL editor
);

-- agent_definitions
create table agent_definitions (
  id              uuid primary key default gen_random_uuid(),
  name            text not null,
  display_name    text,
  description     text,
  capability_tags text[],
  instance_type   text,
  default_model   text,
  input_schema    jsonb,
  output_schema   jsonb,
  config_schema   jsonb,
  version         text,
  source_path     text,
  created_at      timestamptz not null default now()
);

-- agents
create table agents (
  id                  uuid primary key default gen_random_uuid(),
  name                text not null,
  company_id          uuid references companies(id),
  project_id          uuid references projects(id),
  definition_id       uuid references agent_definitions(id),
  agent_type          text,
  parent_agent_id     uuid references agents(id),
  depth               int,
  platform            text,
  model               text,
  trigger_type        text,
  trigger_config      jsonb,
  status              text,
  cost_limit_usd      numeric,
  cost_limit_period   text,
  max_errors_per_hour int,
  priority            int,
  tags                text[],
  can_trigger         uuid[],
  can_be_triggered_by uuid[],
  config_overrides    jsonb,
  registered_at       timestamptz,
  last_run_at         timestamptz,
  paused_at           timestamptz,
  paused_reason       text,
  metadata            jsonb
);

-- runs
create table runs (
  id              uuid primary key default gen_random_uuid(),
  agent_id        uuid not null references agents(id),
  status          text not null default 'started',
  started_at      timestamptz not null default now(),
  created_at      timestamptz not null default now(),
  completed_at    timestamptz,
  tokens_in       int,
  tokens_out      int,
  cost_usd        numeric,
  error           text,
  metadata        jsonb
);

-- agent_events (initial empty shell — write path added in 003)
create table agent_events (
  id                    uuid primary key default gen_random_uuid(),
  agent_id              uuid not null references agents(id),
  company_id            uuid not null references companies(id),
  project_id            uuid references projects(id),
  run_id                uuid,
  event_type            text not null,
  occurred_at           timestamptz not null default now(),
  message               text not null,
  payload               jsonb not null default '{}',
  severity              text not null,
  depth                 int not null,
  duration_ms           int,
  cost_usd              numeric,
  tokens_in             int,
  tokens_out            int,
  orchestrator_run_id   text,
  platform_run_id       text,
  triggered_by_agent_id uuid references agents(id)
);

-- project_state
create table project_state (
  id            uuid primary key default gen_random_uuid(),
  project_tag   text not null unique,
  current_state text,
  todo          text,
  lessons       text,
  updated_at    timestamptz not null default now()
);

-- policies, budgets: verify full schema via SQL editor
```

**Dependency order**: Applied first, all others depend on it  
**Risk level**: Medium — reverse-engineered; any missed column or wrong type becomes a drift source  
**Verification query**:
```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
-- Must list all 11 tables
```
**Rollback**: Drop all objects in reverse FK order. Do NOT apply to live DB — this file is for documentation and fresh deploys only.

---

### `002_agent_outputs.sql`

**Purpose**: Already committed. Documents the `agent_outputs` table and its initial `output_type` CHECK constraint.

**Status**: No changes needed. Apply as-is on fresh deploys.

**Note**: The current CHECK constraint (`marketing_brief`, `lp_blueprint`, `strategy_summary`, `context_snapshot`, `other`) is missing `ui_components`. Fixed in `006`.

---

### `003_add_agent_events.sql`

**Purpose**: Since `agent_events` exists live but receives zero writes, this migration establishes the write path contract. In practice, the table already exists — this migration documents the canonical schema and enables future fresh-deploy reproducibility. It also adds the missing RLS policies (details require SQL editor).

**Objects**: `agent_events` (complete 17-column schema with indexes and RLS)

```sql
-- On fresh DB: create table
-- On live DB: verify columns match; add any missing with ALTER TABLE ADD COLUMN IF NOT EXISTS

-- Recommended indexes (not verifiable via PostgREST — confirm via SQL editor)
CREATE INDEX IF NOT EXISTS agent_events_run_id_idx ON agent_events(run_id);
CREATE INDEX IF NOT EXISTS agent_events_agent_id_idx ON agent_events(agent_id);
CREATE INDEX IF NOT EXISTS agent_events_occurred_at_idx ON agent_events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS agent_events_company_id_idx ON agent_events(company_id);

-- RLS: verify current policies via SQL editor before adding
ALTER TABLE agent_events ENABLE ROW LEVEL SECURITY;
```

**Dependency order**: After `001`  
**Risk level**: Low — table exists live but is empty; adding indexes is safe  
**Verification query**:
```sql
SELECT COUNT(*) FROM agent_events;
-- Should return 0 (empty table, write path not yet active)

SELECT column_name FROM information_schema.columns
WHERE table_name = 'agent_events'
ORDER BY ordinal_position;
-- Must return 17 columns matching canonical contract
```
**Rollback**: `DROP TABLE agent_events CASCADE;` — safe since it is always empty when this runs

---

### `004_add_governance_tables.sql`

**Purpose**: Add taxonomy governance so that runtime-emitted values have a sanctioned list in the DB. Prevents silent constraint violations like the `ui_components` incident.

**Objects**: `output_type_registry`, `event_type_registry` (lookup tables), seed data

```sql
CREATE TABLE IF NOT EXISTS output_type_registry (
  output_type   text primary key,
  description   text,
  added_at      timestamptz not null default now()
);

INSERT INTO output_type_registry (output_type, description) VALUES
  ('marketing_brief',   'Full marketing brief artifact'),
  ('lp_blueprint',      'Landing page blueprint'),
  ('strategy_summary',  'Strategic planning summary'),
  ('context_snapshot',  'Agent context snapshot'),
  ('ui_components',     'Generated UI component code'),
  ('other',             'Uncategorized output')
ON CONFLICT (output_type) DO NOTHING;

CREATE TABLE IF NOT EXISTS event_type_registry (
  event_type    text primary key,
  description   text,
  added_at      timestamptz not null default now()
);

INSERT INTO event_type_registry (event_type, description) VALUES
  ('run_started',    'Agent run initiated'),
  ('run_completed',  'Agent run completed successfully'),
  ('run_failed',     'Agent run terminated with error'),
  ('step_completed', 'Intermediate step completed'),
  ('tool_called',    'External tool or MCP invoked'),
  ('cost_reported',  'Cost/token usage reported mid-run')
ON CONFLICT (event_type) DO NOTHING;
```

**Dependency order**: After `001`  
**Risk level**: Low — additive only, no schema alterations  
**Verification query**:
```sql
SELECT output_type FROM output_type_registry ORDER BY output_type;
SELECT event_type FROM event_type_registry ORDER BY event_type;
-- Must return seeded values
```
**Rollback**: `DROP TABLE output_type_registry, event_type_registry;`

---

### `005_add_cost_views.sql`

**Status**: BLOCKED

**Reason**: The live DB has `agent_cost_summary` and `project_cost_summary` views. Their SQL bodies are not accessible via PostgREST (it returns 404 on `information_schema` queries). The view definitions must be retrieved from the Supabase SQL editor before this migration can be written.

**Required SQL editor queries before unblocking**:
```sql
-- Retrieve view definitions
SELECT pg_get_viewdef('agent_cost_summary'::regclass, true);
SELECT pg_get_viewdef('project_cost_summary'::regclass, true);
SELECT pg_get_viewdef('runs_with_agents'::regclass, true);
```

**Dependency order**: After `001`, `002`  
**Risk level**: Medium — cost views currently show zero due to null cost data; need to ensure view logic is correct before documenting as canonical  
**Placeholder action**: Until unblocked, document that cost views exist live and show zero; do not attempt to recreate or alter them

---

### `006_fix_agent_outputs_constraint.sql`

**Purpose**: Add `ui_components` to the `output_type` CHECK constraint on `agent_outputs`. This is the most urgent operational fix — the orchestrator currently fails silently when trying to write `ui_components` rows.

**Objects**: `agent_outputs.output_type` CHECK constraint

```sql
-- PostgreSQL does not support ALTER TABLE ... ALTER CONSTRAINT
-- Must drop and recreate:

ALTER TABLE agent_outputs DROP CONSTRAINT IF EXISTS agent_outputs_output_type_check;

ALTER TABLE agent_outputs ADD CONSTRAINT agent_outputs_output_type_check
  CHECK (output_type IN (
    'marketing_brief',
    'lp_blueprint',
    'strategy_summary',
    'context_snapshot',
    'ui_components',
    'other'
  ));
```

**Dependency order**: After `002`  
**Risk level**: Low — existing 19 rows all use `lp_blueprint` which remains valid; no data migration needed  
**Verification query**:
```sql
-- Test the new constraint is active:
INSERT INTO agent_outputs (agent_id, run_id, output_type, content)
VALUES ('00000000-0000-0000-0000-000000000000', null, 'ui_components', '{}');
-- Should succeed (or fail only on FK violation, not CHECK)

-- Confirm constraint name:
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'agent_outputs'::regclass AND contype = 'c';
```
**Rollback**:
```sql
ALTER TABLE agent_outputs DROP CONSTRAINT agent_outputs_output_type_check;
ALTER TABLE agent_outputs ADD CONSTRAINT agent_outputs_output_type_check
  CHECK (output_type IN ('marketing_brief','lp_blueprint','strategy_summary','context_snapshot','other'));
```

---

### `007_runs_reconciliation.sql`

**Purpose**: Add three columns required for Phase 2 reliability features: zombie run detection (`timeout_at`), retry chain linkage (`parent_run_id`), and cost observability sentinel (`cost_reported`).

**Objects**: `runs` table — ADD COLUMN only

```sql
ALTER TABLE runs
  ADD COLUMN IF NOT EXISTS timeout_at      timestamptz,
  ADD COLUMN IF NOT EXISTS parent_run_id   uuid REFERENCES runs(id),
  ADD COLUMN IF NOT EXISTS cost_reported   boolean NOT NULL DEFAULT false;

-- Backfill: mark all existing runs as cost unreported (default handles this, but explicit for clarity)
UPDATE runs SET cost_reported = false WHERE cost_reported IS NULL;

-- Index for zombie run cleanup queries
CREATE INDEX IF NOT EXISTS runs_timeout_status_idx ON runs(timeout_at, status)
  WHERE status = 'started' AND timeout_at IS NOT NULL;
```

**Dependency order**: After `001`  
**Risk level**: Low — ADD COLUMN IF NOT EXISTS is safe on live data; existing 51 rows get null timeout_at (correct — they were not created with timeout tracking)  
**Verification query**:
```sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'runs'
  AND column_name IN ('timeout_at', 'parent_run_id', 'cost_reported')
ORDER BY column_name;
-- Must return 3 rows with correct types
```
**Rollback**:
```sql
ALTER TABLE runs
  DROP COLUMN IF EXISTS timeout_at,
  DROP COLUMN IF EXISTS parent_run_id,
  DROP COLUMN IF EXISTS cost_reported;
```

---

## API Alignment Plan

### `src/app/api/ingest/route.ts`

**Current state**: Handles `run_started`, `run_completed`, `run_failed`. Never writes to `agent_events`.

**Required changes**:

#### 1. Expand agent SELECT to fetch required fields

Current:
```typescript
const { data: agent } = await supabase
  .from('agents')
  .select('id, status')
  .eq('id', agent_id)
  .single();
```

Required:
```typescript
const { data: agent } = await supabase
  .from('agents')
  .select('id, status, company_id, depth, agent_type')
  .eq('id', agent_id)
  .single();
```

#### 2. Add `agent_events` write on every ingest event

After the existing `runs` upsert logic, add:

```typescript
// Write to agent_events for full observability trace
if (agent.company_id) {
  const eventRow = {
    agent_id:     agent_id,
    company_id:   agent.company_id,
    run_id:       run_id,
    event_type:   event,
    occurred_at:  timestamp ?? new Date().toISOString(),
    message:      buildEventMessage(event, body),
    payload:      body.metadata ?? {},
    severity:     event === 'run_failed' ? 'error' : 'info',
    depth:        agent.depth ?? 0,
    tokens_in:    body.tokens_in ?? null,
    tokens_out:   body.tokens_out ?? null,
    cost_usd:     body.cost_usd ?? null,
  };

  await supabase.from('agent_events').insert(eventRow);
  // Non-fatal: if agent_events write fails, run record is already committed
}
```

#### 3. Set `timeout_at` on `run_started` insert (after `007` migration)

```typescript
// On run_started insert:
const timeout_at = new Date(Date.now() + 30 * 60 * 1000).toISOString(); // 30 min default

await supabase.from('runs').insert({
  id:         run_id,
  agent_id:   agent_id,
  status:     'started',
  started_at: timestamp ?? new Date().toISOString(),
  timeout_at: timeout_at,
  metadata:   body.metadata ?? null,
});
```

#### 4. Set `cost_reported` on terminal events (after `007` migration)

```typescript
// On run_completed / run_failed:
const hasCostData = body.cost_usd !== undefined && body.cost_usd !== null;

await supabase.from('runs').update({
  status:         resolvedStatus,
  completed_at:   new Date().toISOString(),
  tokens_in:      body.tokens_in ?? null,
  tokens_out:     body.tokens_out ?? null,
  cost_usd:       body.cost_usd ?? null,
  cost_reported:  hasCostData,
  error:          body.error ?? null,
}).eq('id', run_id);
```

**Zod schema extension** (add optional fields):
```typescript
const IngestSchema = z.object({
  agent_id:    z.string().uuid(),
  event:       z.enum(['run_started', 'run_completed', 'run_failed']),
  run_id:      z.string().uuid(),
  timestamp:   z.string().datetime().optional(),
  tokens_in:   z.number().int().nonneg().optional(),
  tokens_out:  z.number().int().nonneg().optional(),
  cost_usd:    z.number().nonneg().optional(),
  error:       z.string().optional(),
  metadata:    z.record(z.unknown()).optional(),
  // New optional fields for Phase 2:
  parent_run_id: z.string().uuid().optional(),
  step_name:     z.string().optional(),
});
```

**Dependency**: `003_add_agent_events.sql` and `007_runs_reconciliation.sql` must be applied before deploying code changes.

---

### `src/app/api/project-state/route.ts`

**Current state**: Correct. Uses typed columns (`project_tag`, `current_state`, `todo`, `lessons`). Upserts on `project_tag`. No changes needed.

---

## Runtime Alignment Plan

### `src/lib/adapters/types.ts` — `Agent` interface

**Current (wrong)**:
```typescript
interface Agent {
  id: string;
  name: string;
  description: string;    // NOT in agents table — lives in agent_definitions
  hierarchy: AgentHierarchy;  // live column is agent_type (text)
  company: Company;       // live column is company_id (uuid)
  project: string;        // live column is project_id (uuid)
  created_at: string;     // NOT in live agents table
  // ...
}
```

**Required (aligned with live agents columns)**:
```typescript
interface Agent {
  id:                  string;
  name:                string;
  company_id:          string | null;
  project_id:          string | null;
  definition_id:       string | null;
  agent_type:          string | null;
  parent_agent_id:     string | null;
  depth:               number | null;
  platform:            string | null;
  model:               string | null;
  trigger_type:        string | null;
  trigger_config:      Record<string, unknown> | null;
  status:              string | null;
  cost_limit_usd:      number | null;
  cost_limit_period:   string | null;
  max_errors_per_hour: number | null;
  priority:            number | null;
  tags:                string[] | null;
  can_trigger:         string[] | null;
  can_be_triggered_by: string[] | null;
  config_overrides:    Record<string, unknown> | null;
  registered_at:       string | null;
  last_run_at:         string | null;
  paused_at:           string | null;
  paused_reason:       string | null;
  metadata:            Record<string, unknown> | null;
}
```

**Note**: Any UI component rendering `agent.description` or `agent.hierarchy` must be updated to join against `agent_definitions` for description and read `agent.agent_type` for hierarchy.

---

### `python-sdk/oversight.py` — `OversightClient`

**Current state**: `report()` accumulates `tokens_in`, `tokens_out`, `cost_usd` in memory on the `RunContext` object. On `run_completed`, these are emitted. The implementation is correct in design but produces zero cost data in practice.

**Root cause**: Agents are not calling `ctx.report(tokens_in=..., tokens_out=..., cost_usd=...)` after LLM calls. This is an agent discipline problem, not an SDK bug.

**Required action**: Update each active agent to call `ctx.report()` with actual LLM response metadata.

**SDK enhancement (optional, Phase 2)**: Add mid-run step events:

```python
def step(self, event_type: str, message: str, payload: dict = None, **kwargs):
    """Emit a step event to agent_events (not just runs)."""
    self._post({
        "agent_id":   self.agent_id,
        "event":      event_type,
        "run_id":     self.run_id,
        "message":    message,
        "metadata":   payload or {},
        **kwargs,
    })
```

---

## Contract Test Plan

These are the verifications that must pass before Phase 1 is declared complete.

### Schema contract tests

```bash
# 1. Verify all 11 tables exist
GET /rest/v1/ → check definitions section for all table names

# 2. Verify agent_events columns match canonical contract
GET /rest/v1/ → definitions.agent_events.properties must include all 17 fields

# 3. Verify output_type constraint includes ui_components
INSERT agent_outputs with output_type='ui_components' → must succeed

# 4. Verify runs has timeout_at, parent_run_id, cost_reported
GET /rest/v1/ → definitions.runs.properties must include these 3 columns
```

### API contract tests

```bash
# 5. run_started creates a runs row
POST /api/ingest { agent_id, event: 'run_started', run_id }
GET /rest/v1/runs?id=eq.<run_id>
→ must return 1 row with status='started'

# 6. run_started creates an agent_events row (after code change)
GET /rest/v1/agent_events?run_id=eq.<run_id>
→ must return 1 row with event_type='run_started'

# 7. run_completed marks cost_reported correctly (after migration + code change)
POST /api/ingest { agent_id, event: 'run_completed', run_id, cost_usd: 0.05 }
GET /rest/v1/runs?id=eq.<run_id>
→ must return cost_reported=true, cost_usd=0.05

# 8. run_completed without cost leaves cost_reported=false
POST /api/ingest { agent_id, event: 'run_completed', run_id }
GET /rest/v1/runs?id=eq.<run_id>
→ must return cost_reported=false, cost_usd=null

# 9. project_state upsert is idempotent on project_tag
PUT /api/project-state { project_tag: 'test', current_state: 'x' }
PUT /api/project-state { project_tag: 'test', current_state: 'y' }
GET /api/project-state/test → must return current_state='y'
```

### Runtime contract tests

```bash
# 10. Python SDK end-to-end with cost reporting
python test_sdk_cost_reporting.py
→ must show cost_usd in completed run row and cost_reported=true

# 11. TypeScript Agent interface fields match live DB columns
→ TypeScript compiler must accept live API response without type assertion
```

---

## Rollback / Safety Strategy

### Migration rollback order

If a migration must be rolled back, reverse in dependency order:

```
007 → 006 → 005 → 004 → 003 → 002 → 001
```

Each migration's rollback SQL is defined in its section above.

### Code change rollback

API changes to `route.ts` are isolated to the `agent_events` write block and are marked non-fatal (wrapped in try/catch or conditional). If the agent_events write fails, it does not affect run record writes — rollback by reverting the file.

TypeScript `Agent` interface change is a pure type update — no runtime behavior change. Any component using removed fields will produce a TypeScript compile error, which is the intended safety signal.

### DB safety rules

- Never run `DROP TABLE` in a migration without verifying the table is empty
- Never run `ALTER TABLE ... DROP COLUMN` without confirming no application code references it
- Always test CHECK constraint changes with a sample INSERT before committing the migration
- `005_add_cost_views.sql` must not be attempted until view SQL bodies are retrieved from the SQL editor

---

## Remaining SQL Editor Checks

These items are blocked until Supabase SQL editor access is obtained. None block Phase 1 code changes; they block only the documentation and `005` migration.

| Check | SQL | Purpose |
|---|---|---|
| Cost view definitions | `SELECT pg_get_viewdef('agent_cost_summary'::regclass, true)` | Required for `005_add_cost_views.sql` |
| Runs view definition | `SELECT pg_get_viewdef('runs_with_agents'::regclass, true)` | Required for `001_initial_schema.sql` completeness |
| Full CHECK constraints | `SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'agent_outputs'::regclass` | Confirm constraint name before dropping in `006` |
| RLS policies on agent_events | `SELECT * FROM pg_policies WHERE tablename = 'agent_events'` | Required before adding RLS in `003` |
| RLS policies on runs | `SELECT * FROM pg_policies WHERE tablename = 'runs'` | Verify service role bypass is in place |
| Full companies columns | `SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'companies'` | Complete `001` company table spec |
| Full policies columns | Same for `policies` table | Complete `001` spec |
| Full budgets columns | Same for `budgets` table | Complete `001` spec |

---

## Phase 1 Completion Criteria

Phase 1 is complete when ALL of the following are true:

### Schema
- [ ] `001_initial_schema.sql` created and committed (reverse-engineered from live)
- [ ] `003_add_agent_events.sql` applied to live DB
- [ ] `004_add_governance_tables.sql` applied to live DB
- [ ] `005_add_cost_views.sql` created and committed (unblocked by SQL editor access)
- [ ] `006_fix_agent_outputs_constraint.sql` applied to live DB
- [ ] `007_runs_reconciliation.sql` applied to live DB

### API
- [ ] `src/app/api/ingest/route.ts` writes to `agent_events` on every ingest event
- [ ] `src/app/api/ingest/route.ts` sets `timeout_at` on `run_started`
- [ ] `src/app/api/ingest/route.ts` sets `cost_reported` on terminal events

### Runtime
- [ ] `src/lib/adapters/types.ts` `Agent` interface aligned with live agents columns
- [ ] At least one active agent calls `ctx.report(cost_usd=..., tokens_in=..., tokens_out=...)` after each LLM call

### Observability
- [ ] A live test run produces: 1 runs row + ≥2 agent_events rows (started + completed)
- [ ] A live test run with `cost_usd` produces `cost_reported=true` and non-null cost in runs
- [ ] `agent_cost_summary` view returns non-zero values for the test run

### Documentation
- [ ] All 6 migration files committed to `supabase/migrations/`
- [ ] `LIVE_SUPABASE_SCHEMA_INVENTORY.md` updated with SQL editor findings
- [ ] SQL editor checks table above marked as complete

---

## Risks Before Phase 2

| Risk | Severity | Mitigation |
|---|---|---|
| `agent_events` ingest field mapping fails for agents without `company_id` | High | Make agent_events write conditional on `company_id` being non-null; log a warning when skipped |
| Cost views silently wrong (view SQL unknown) | High | Obtain SQL editor access; validate with a test run before marking `005` complete |
| `001_initial_schema.sql` misses columns (reverse-engineering is incomplete) | Medium | Document known-unknown columns; use `IF NOT EXISTS` throughout `001` for fresh-deploy safety |
| Zombie run cleanup job missing | Medium | `timeout_at` field is Phase 1; cleanup cron job is Phase 5; document interim manual cleanup |
| TypeScript interface mismatch causes UI runtime errors | Medium | Fix `types.ts` before any UI dashboard work; add compile-time checks |
| `python-sdk` agents never call `ctx.report()` | Medium | Add mandatory `ctx.report()` to agent template and audit all 2 registered agents |
| `005_add_cost_views.sql` remains unwritten at Phase 2 start | Low | Phase 2 does not require cost views to be written from scratch, only to exist live (they do) |

---

## Recommended Next Execution Step

**Immediate** (unblocks everything):
1. Open Supabase SQL editor for project `hdhovyrlnfojtkqbcegh`
2. Run the 8 SQL editor checks listed above
3. Record findings to complete `001_initial_schema.sql` and unblock `005_add_cost_views.sql`

**First code change** (highest operational impact, safest):
1. Apply `006_fix_agent_outputs_constraint.sql` to live DB — fixes silent orchestrator failures immediately
2. Apply `007_runs_reconciliation.sql` to live DB — adds observability sentinel and zombie detection fields

**Second code change** (activates observability):
1. Apply `003_add_agent_events.sql` (mostly a no-op since table exists; adds indexes and documents schema)
2. Deploy `route.ts` changes to write `agent_events` on ingest
3. Run a live test with the Python SDK and verify agent_events rows appear

**Third code change** (eliminates type safety debt):
1. Update `src/lib/adapters/types.ts` `Agent` interface
2. Fix any downstream components that reference removed fields
3. Add TypeScript compilation to CI gate

**Documentation completion** (can parallel the above):
1. Obtain SQL editor access → fill in remaining SQL editor checks
2. Create `001_initial_schema.sql` with complete column inventory
3. Write `005_add_cost_views.sql`
4. Apply `004_add_governance_tables.sql`
5. Commit all migration files in order

Once all Phase 1 completion criteria are checked, advance to Phase 2 with confidence that schema, API, and runtime are aligned.
