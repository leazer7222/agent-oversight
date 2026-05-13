# Agent Oversight System - Todo

## Active
- [ ] Reconcile `runs` schema contract across migration, ingest API, and runtime/types.
- [ ] Reconcile `project_state` contract to a single canonical shape (typed columns vs JSON envelope decision).
- [ ] Reconcile `agent_outputs.output_type` taxonomy with runtime values (include `ui_components` or change runtime emission).
- [ ] Repair invalid UUID seed values in `supabase/migrations/001_initial_schema.sql`.
- [ ] Add/confirm migration coverage for inferred live control-plane tables (`agent_events`, `projects`, `policies`, `audit_log`, telemetry/eval views as applicable).
- [ ] Add schema contract tests for `/api/ingest` and `/api/project-state*` against canonical table definitions.

## Completed
- [x] Phase 1 schema stabilization analysis and contract audit docs created - 2026-05-13
- [x] Handoff + architecture + lessons documentation updated for Phase 1 findings - 2026-05-13
- [x] Git/GitHub persistence and multi-model handoff governance foundation validated (pre-Phase 1) - 2026-05-12

## Deferred (intentional)
- [ ] Phase 2 dashboard implementation (blocked on Phase 1 reconciliation).
- [ ] Execution queue/worker model implementation (later phase).
- [ ] Orchestrator refactor for durable async flow (later phase).
