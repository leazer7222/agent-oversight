# Agent Oversight System - Todo

## Active (Phase 1 Reconciliation Implementation)
- [ ] Query live Supabase to confirm exact column names/types for all foundational tables.
- [ ] Create `001_initial_schema.sql` matching confirmed live schema (companies, agents, agent_definitions, runs, project_state).
- [ ] Create `003_reconcile_runs.sql` — add error, completed_at, cost_*, timeout_at, cost_reported, parent_run_id to runs.
- [ ] Create `004_reconcile_project_state.sql` — align to typed column schema with project_tag check constraint.
- [ ] Create `005_agent_outputs_taxonomy.sql` — expand output_type check constraint; add event_id FK; add unique constraint.
- [ ] Create `006_agent_events.sql` — append-only event trace table with RLS insert-only policy.
- [ ] Update `src/app/api/ingest/route.ts` — add agent_events INSERT write path for all lifecycle events.
- [ ] Add contract tests for `/api/ingest` and `/api/project-state*`.
- [ ] Repair invalid UUID seed values in companies (if present in committed migration).

## Active (Ongoing Documentation)
- [ ] Add `schema_version` tracking mechanism for tracking which migrations have been applied to live DB.

## Completed
- [x] Phase 1 Reconciliation Review: canonical contracts, reconciliation sequencing, risk inventory - 2026-05-12
- [x] Phase 1 schema stabilization analysis and contract audit docs created - 2026-05-13
- [x] Handoff + architecture + lessons documentation updated for Phase 1 findings - 2026-05-13
- [x] Git/GitHub persistence and multi-model handoff governance foundation validated (pre-Phase 1) - 2026-05-12

## Deferred (intentional)
- [ ] Phase 2 dashboard implementation (blocked on Phase 1 reconciliation completion).
- [ ] Execution queue/worker model implementation (Phase 5).
- [ ] Orchestrator refactor for durable async flow (Phase 5).
- [ ] Zombie run cleanup job (Phase 5 — requires timeout_at field from Phase 1 reconciliation).
- [ ] Step-level cost events for incremental cost persistence (Phase 2).
- [ ] HITL approval event types in agent_events taxonomy (Phase 8).
