# Agent Oversight System - Current State

Last updated: 2026-05-12
Status: Active (Phase 1 Reconciliation Review complete; reconciliation implementation pending)

## Current Objective State
Phase 1 analysis is complete. Phase 1 Reconciliation Review is complete. Implementation of the reconciliation migrations and ingest route update is the next required work.

## What Was Completed
- Phase 1 schema stabilization analysis (Codex, 2026-05-13).
- Phase 1 reconciliation review and architecture validation (Claude, 2026-05-12).
- Canonical contract definitions for `runs`, `agent_events`, `agent_outputs`, `project_state`.
- Reconciliation strategy and migration sequencing documented.
- All continuity/architecture/lessons documents updated.

## Critical Gap Identified
`001_initial_schema.sql` does NOT exist in the repo. The foundational tables (`companies`, `agents`, `agent_definitions`, `runs`, `project_state`) are undocumented in migrations. The platform cannot be reproduced from repo state alone. This must be fixed before any other migration work.

## Confirmed Critical Drift
1. `001_initial_schema.sql` missing — foundational tables not in migrations.
2. `runs` mismatch — `error`, `completed_at`, `cost_*` fields used by API but status of migration columns unconfirmed.
3. `project_state` mismatch — migration shape unknown; API uses `project_tag/current_state/todo/lessons`.
4. `agent_outputs.output_type` — `ui_components` emitted by runtime not allowed by migration constraint.
5. `agent_events` write path — ingest route never writes to this table; event traces are zero.
6. Invalid UUID literals in `companies` seed rows (if they existed in the uncommitted migration).

## Canonical Decisions Made
- Source of truth: migrations + documented contracts (not live DB).
- `runs.id` is the single canonical run identifier.
- `project_state` uses typed columns (Option A).
- `agent_events` is append-only, write path is required in ingest route.
- `cost_reported BOOLEAN` required on `runs` to distinguish unreported from zero cost.
- `timeout_at TIMESTAMPTZ` required on `runs` for zombie run detection.
- `parent_run_id UUID` on `runs` for retry chain linkage.
- Output taxonomy expanded to include: `ui_components`, `code_artifact`, `research_report`, `eval_result`.

## Exact Next Priority
1. Query live Supabase to confirm exact column names/types for all foundational tables.
2. Create `001_initial_schema.sql` matching confirmed live schema.
3. Create `003_reconcile_runs.sql`.
4. Create `004_reconcile_project_state.sql`.
5. Create `005_agent_outputs_taxonomy.sql`.
6. Create `006_agent_events.sql`.
7. Update ingest route to write to `agent_events`.
8. Write and run contract tests.

## Blocking Condition for Phase 2
Phase 2 (Telemetry Standardization) must NOT begin until all 8 items above are complete and verified.

## Explicit Non-Work This Session
- No frontend build work.
- No queue/worker implementation.
- No orchestration refactor.
- No Phase 2+ features.
