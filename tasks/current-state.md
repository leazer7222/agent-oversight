# Agent Oversight System - Current State

Last updated: 2026-05-12
Status: Active — Phase 3 complete; Phase 4 (Dashboard MVP) is next.

---

## Completed Phases

### Phase 1 — Schema Stabilization ✅
- `001_initial_schema.sql` — reverse-engineered from live DB (governance doc, not re-applied)
- `003_add_agent_events_indexes.sql` — 4 indexes applied live
- `004_add_governance_tables.sql` — output_type_registry, event_type_registry applied live
- `005_add_cost_views.sql` — agent_cost_summary, project_cost_summary views applied live
- `006_fix_agent_outputs_constraint.sql` — added ui_components to output_type CHECK constraint applied live
- `007_runs_reconciliation.sql` — timeout_at, parent_run_id, cost_reported columns applied live
- Ingest route updated: agent_events write path activated, timeout_at set on run_started, cost_reported set on terminal events
- TypeScript `Agent` interface corrected to match live DB column names (25 fields)

### Phase 2 — Telemetry Standardization ✅
- `run_step` event type added to ingest schema — writes directly to agent_events, bypasses runs table
- `StepTimer` context manager added to Python SDK for wall-clock step measurement
- Error taxonomy added to Python SDK: `categorize_error()` with 5 error categories; errors prefixed `[category]`
- `RunContext.step()` method added — emits run_step events, accumulates cost, non-fatal
- Real token/cost capture wired in marketing-agent: `response.usage` (OpenAI) and `usage_metadata` (Gemini)
- Per-model cost estimation functions added to marketing-agent
- Windows UTF-8 stdout fix applied to marketing-agent and orchestrator
- orchestrator.py updated with step events: context_ready, llm_synthesis (with timer), output_persisted (with timer)
- context-agent updated with step events: docs_discovered, docs_extracted (with timer)

### Phase 3 — Read APIs ✅ (commit c06ef74)
- `src/lib/api/pagination.ts` — shared parsePagination + paginationMeta helpers
- `GET /api/agents` — list with cost summary, status/company filter, pagination
- `GET /api/agents/[id]` — full agent detail + recent 10 runs
- `GET /api/agents/[id]/runs` — paginated run history, status filter
- `GET /api/runs` — cross-agent run list, status/agent/errors_only filters
- `GET /api/runs/[id]` — full run detail with events + outputs
- `GET /api/runs/[id]/events` — event trace with cumulative token/cost summary
- `GET /api/cost` — cost aggregates from cost views, group_by=agent|project
- `GET /api/errors` — failed runs with error category breakdown + frequency table

---

## Current Objective

**Phase 4 — Dashboard MVP**

Build the UI pages that consume the Phase 3 APIs. Priority order:

1. `/dashboard` — agent list, total cost, recent errors (uses /api/agents, /api/errors)
2. `/dashboard/runs` — execution history with filters (uses /api/runs)
3. `/dashboard/runs/[id]` — run detail with event timeline + outputs (uses /api/runs/[id], /api/runs/[id]/events)
4. `/dashboard/agents/[id]` — agent detail with run history (uses /api/agents/[id], /api/agents/[id]/runs)
5. `/dashboard/costs` — cost breakdown by agent/project (uses /api/cost)
6. `/dashboard/errors` — error feed with category grouping (uses /api/errors)

---

## Known Blockers / Caveats

- **LLM billing**: tokens_in/tokens_out/cost_usd fields produce nulls because both OpenAI and Gemini free tiers are exhausted. Token/cost pipeline code is correct; blocked on enabling billing.
- **Supabase types**: Phase 3 routes use `as any[]` casts instead of generated types. A background task has been flagged to generate types via `mcp__supabase__generate_typescript_types` and wire them in.
- **Vercel SSO**: Preview deployment has SSO protection. Python agents must POST to `http://localhost:3000` (local Next.js server) for local runs.

---

## Key Technical References

| Concern | Location |
|---------|----------|
| Supabase project | `hdhovyrlnfojtkqbcegh` |
| Live DB schema | `docs/LIVE_SUPABASE_SCHEMA_INVENTORY.md` |
| Migration files | `supabase/migrations/` |
| Python SDK | `python-sdk/oversight.py` |
| Ingest API | `src/app/api/ingest/route.ts` |
| Read APIs | `src/app/api/agents/`, `src/app/api/runs/`, `src/app/api/cost/`, `src/app/api/errors/` |
| Orchestrator | `agents/instances/reformai/orchestrator.py` |
| Agent library | `agents/library/` |
