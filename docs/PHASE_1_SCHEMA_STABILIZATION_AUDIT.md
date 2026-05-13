# Phase 1 - Canonical Schema Stabilization Audit (2026-05-13)

## Scope
Phase 1 only: schema/runtime/API contract analysis and documentation. No queue, UI, or orchestration refactors.

## Evidence Sources
Confirmed from repository:
- `supabase/migrations/001_initial_schema.sql`
- `supabase/migrations/002_agent_outputs.sql`
- `src/app/api/ingest/route.ts`
- `src/app/api/project-state/route.ts`
- `src/app/api/project-state/[tag]/route.ts`
- `python-sdk/oversight.py`
- `agents/instances/reformai/orchestrator.py`
- `src/lib/adapters/types.ts`
- `scripts/register_marketing_agent.js`
- `scripts/register_ui_agent.js`

Inferred from prior project records (not re-queried live this session):
- Live Supabase includes additional control-plane entities/views beyond migrations (`projects`, `agent_events`, `policies`, `audit_log`, QA/cost views).

## 1) Canonical Schema Source-of-Truth Decision
Decision:
- Canonical ownership for operational contracts = **live Supabase schema + API/runtime behavior contracts documented in-repo**.
- Canonical reproducibility layer = **forward-only migrations in `supabase/migrations`**.

Operational rule:
- A schema change is not complete until both are true:
  1. applied in live DB
  2. represented in migration + docs contract notes

Rationale:
- Current migrations are incomplete relative to runtime assumptions; treating migrations alone as canonical would hide active contract reality.

## 2) Operationally Critical MVP Tables
Tier 0 (required now):
- `agents`: identity + execution eligibility.
- `agent_definitions`: reusable blueprint metadata.
- `runs`: execution lifecycle summary rows.
- `agent_events` (inferred/live): append-only lifecycle trace.
- `agent_outputs`: persisted result artifacts linked to runs.
- `project_state`: continuity/status payloads for operations.

Tier 1 (required before controlled execute):
- `companies` / workspace ownership scope.
- `projects` (if used for run scoping).
- `policies`: execution/cost/governance controls.
- `audit_log`: actor/action traceability.

Tier 2 (observability confidence):
- cost/telemetry summary tables/views.
- eval/QA tables (e.g., `agent_qa_results`) for quality confidence.

## 3) Canonical Run/Event/Output Semantics
- `runs` = one durable execution summary row per run lifecycle.
  - Should carry: status, start/end timestamps, aggregate tokens/cost, error summary, context keys.
- `agent_events` = append-only event stream for a run.
  - Should carry: event type, timestamp, actor/agent, payload metadata, sequence/order.
- `agent_outputs` = persisted artifacts produced by run/event steps.
  - Should carry: output type, content or pointer, version, lineage (`run_id`, optional `event_id`).

Contract rule:
- Summary fields in `runs` are derivable from `agent_events`, but remain materialized for dashboard/query speed.

## 4) Schema Drift Found
### Confirmed drift: `project_state`
- Migration shape: `project_state(tag, state, updated_at)`.
- API shape: reads/writes `project_tag, current_state, todo, lessons, updated_at`.
- Result: migration and API contracts diverge; one of these is stale.

### Confirmed drift: `runs`
- Migration requires `event` and `run_id` columns, with PK `id`.
- Ingest route inserts only `id, agent_id, status, started_at, metadata` on `run_started`.
- Ingest route updates by `id=run_id` and assumes `error` column exists for failures.
- `src/lib/adapters/types.ts` also models `error` field.
- Migration `runs` table in repo does **not** include `error` column.
- Result: schema/runtime/API mismatch on required/available fields.

### Confirmed drift: `agent_outputs.output_type`
- Migration enum/check does not include `ui_components`.
- Orchestrator inserts `output_type: "ui_components"`.
- Result: write-path mismatch against migration constraints.

### Confirmed drift: `agent_outputs.run_id` semantics
- Migration defines `agent_outputs.run_id -> runs.id` FK.
- Orchestrator passes `run_id` values that are generated in runtime contexts and may not always map to persisted `runs.id` rows depending on ingest path success.
- Result: lineage may be non-durable in failure/offline ingest scenarios.

### Confirmed data quality issue in migrations seed
- `companies` seed UUIDs include invalid UUID characters (`g`, `h`) for two rows.
- Result: migration as written is not safely reproducible.

## 5) Table Contract Definitions (Phase 1 baseline)
### `companies`
Purpose: workspace ownership and billing/governance scope.
Required fields for MVP: `id`, `name`, `display_name`, `created_at`.

### `agent_definitions`
Purpose: reusable capability blueprint.
Required fields: `id`, `name`, `display_name`, `description`, `instance_type`, `default_model`, `version`, `source_path`.

### `agents`
Purpose: deployable/operable agent instance.
Required fields: `id`, `name`, `company_id`, `definition_id`, `agent_type`, `status`, `trigger_type`, `registered_at`, `last_run_at`, `model`, `metadata`.

### `runs`
Purpose: run lifecycle summary.
Required fields (canonical target):
- identity/linkage: `id`, `agent_id`, `company_id` (or via join), optional `project_id`
- lifecycle: `status`, `started_at`, `completed_at`
- observability: `tokens_in`, `tokens_out`, `cost_usd`, `error`, `metadata`
- external correlation: exactly one canonical external run key (`id` OR `run_id`, not ambiguous dual-primary semantics)

### `agent_events` (expected canonical)
Purpose: append-only trace for lifecycle/debug.
Required fields: `id`, `run_id`, `agent_id`, `event_type`, `event_time`, `payload`, `sequence`.

### `agent_outputs`
Purpose: persisted artifacts.
Required fields: `id`, `agent_id`, `run_id`, `company_id`, `output_type`, `content`, `version`, `created_at`.
Optional lineage extensions: `event_id`, `uri`, `checksum`.

### `project_state`
Purpose: operational continuity state.
Canonical decision needed now:
- Option A: typed columns (`current_state`, `todo`, `lessons`) for direct tooling use.
- Option B: generic JSON `state` with structured schema versioning.

### `policies`, `audit_log`, telemetry/eval tables
Status in repo migrations: absent.
Status in architecture intent: required for governed execution + trust.
Phase 1 decision: keep in canonical target model and schedule migration coverage before Phase 2 execution controls.

## 6) Required Fields for MVP Observability
Minimum per run:
- `run_id`/`id` (single canonical id)
- `agent_id`
- `status`
- `started_at`, `completed_at`
- `duration_ms` (derived or stored)
- `tokens_in`, `tokens_out`, `cost_usd`
- `error` (nullable structured summary)
- `metadata` (bounded JSON)

Minimum per event:
- `event_type`
- `event_time`
- `run_id`
- `agent_id`
- `payload`

Minimum per output:
- `run_id`
- `agent_id`
- `output_type`
- `created_at`
- `content` or content pointer

## 7) API/Schema Mismatch List
1. `POST /api/ingest` writes `runs` without required migration fields (`event`, `run_id`), but expects `error` column that migration omits.
2. `PUT /api/project-state` and `GET /api/project-state/[tag]` use column names not present in migration (`project_tag`, `current_state`, `todo`, `lessons`).
3. `src/lib/adapters/types.ts` models `Agent` fields (`description`, `hierarchy`, `company`, `project`, `created_at`) that do not match migration column names directly.

## 8) Runtime/Schema Mismatch List
1. `orchestrator.py` inserts `agent_outputs.output_type='ui_components'` (not allowed by migration constraint).
2. `orchestrator.py` output write assumes run linkage exists; dependency on successful ingest is implicit and not contract-enforced.
3. Oversight SDK emits run lifecycle events, but there is no event-table write path in current Next.js ingest route (events collapsed into summary updates only).

## 9) Migration Gap Analysis
Missing or stale in migrations:
- live-compatible `runs` schema (status/error/event/correlation clarity)
- live-compatible `project_state` schema used by API
- `agent_events` table (append-only trace)
- `projects` table and relational constraints (if in live env)
- `policies` table
- `audit_log` table
- telemetry/cost summary views and eval tables (if live)
- correction of invalid UUID seeds in `companies`

## 10) Risks / Open Questions
Risks:
- Contract ambiguity in `runs` prevents reliable run traceability.
- API endpoints may fail or silently drift across environments depending on live schema state.
- Artifact lineage can fragment if output writes occur without durable run/event linkage.
- Governance tables absent from migrations blocks safe execute-from-dashboard evolution.

Open questions:
1. Canonical run identifier: keep both `id` and `run_id` or collapse to one?
2. Should `project_state` be typed columns or a versioned JSON envelope?
3. Is `agent_events` already live and if so what exact fields/types/constraints exist?
4. Which tables are hard MVP blockers vs post-MVP governance upgrades?

## 11) Recommended Phase 2 Prerequisites (do before building Phase 2 features)
1. Publish canonical schema contract doc with explicit table/field semantics and lifecycle states.
2. Reconcile migrations to current live schema for `runs`, `project_state`, and `agent_outputs` at minimum.
3. Introduce/confirm `agent_events` append-only contract and ingestion write path.
4. Validate API handlers against reconciled schema with contract tests.
5. Decide and document source-of-truth ownership workflow:
   - proposal in docs
   - migration PR
   - live apply
   - post-apply verification

## Confirmed vs Inferred Legend
- Confirmed: directly validated from current repository files listed above.
- Inferred: derived from prior architecture documents/session records where live DB was not re-queried during this session.
