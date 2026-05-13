# Agent Oversight System - Todo

## Active (Phase 4 — Dashboard MVP)

### Core pages (in priority order)
- [ ] `/dashboard` — overview: agent status table, total cost KPIs, recent error feed
- [ ] `/dashboard/runs` — run history table with status/agent/errors_only filter, pagination
- [ ] `/dashboard/runs/[id]` — run detail: lifecycle summary, event timeline, outputs viewer
- [ ] `/dashboard/agents/[id]` — agent detail: run history table, cost/token breakdown
- [ ] `/dashboard/costs` — cost breakdown by agent and by project, using /api/cost
- [ ] `/dashboard/errors` — failed run feed grouped by error category

### Supporting infrastructure
- [ ] Shared `<StatusChip>` component (started | completed | failed | unknown)
- [ ] Shared `<DurationLabel>` component (human-readable ms → s/m/h)
- [ ] Shared `<CostLabel>` component ($0.0042 formatting)
- [ ] Data fetching pattern: server components + fetch from Read APIs
- [ ] Empty state + loading state components
- [ ] Navigation sidebar / top nav (links to all dashboard pages)

## Active (Ongoing)
- [ ] Generate Supabase TypeScript types → `src/lib/supabase/types.ts` (flagged as background task)
  - Command: `mcp__supabase__generate_typescript_types` for project `hdhovyrlnfojtkqbcegh`
  - Then wire into Supabase client and remove `as any[]` casts from Phase 3 routes
- [ ] Enable LLM billing (OpenAI or Gemini) to verify token/cost pipeline end-to-end
- [ ] Add `schema_version` tracking mechanism for applied migrations

## Completed

### Phase 3 — Read APIs
- [x] `src/lib/api/pagination.ts` - 2026-05-12
- [x] `GET /api/agents` - 2026-05-12
- [x] `GET /api/agents/[id]` - 2026-05-12
- [x] `GET /api/agents/[id]/runs` - 2026-05-12
- [x] `GET /api/runs` - 2026-05-12
- [x] `GET /api/runs/[id]` - 2026-05-12
- [x] `GET /api/runs/[id]/events` - 2026-05-12
- [x] `GET /api/cost` - 2026-05-12
- [x] `GET /api/errors` - 2026-05-12

### Phase 2 — Telemetry Standardization
- [x] run_step event type in ingest schema - 2026-05-12
- [x] StepTimer + RunContext.step() in Python SDK - 2026-05-12
- [x] Error taxonomy (categorize_error, 5 categories) in Python SDK - 2026-05-12
- [x] Real token/cost capture in marketing-agent (OpenAI + Gemini usage objects) - 2026-05-12
- [x] Cost estimation tables in marketing-agent - 2026-05-12
- [x] UTF-8 stdout fix in marketing-agent and orchestrator - 2026-05-12
- [x] Step events in context-agent and orchestrator - 2026-05-12

### Phase 1 — Schema Stabilization
- [x] Live Supabase schema verification (11 tables, 3 views) - 2026-05-12
- [x] 001_initial_schema.sql (governance doc) - 2026-05-12
- [x] 003_add_agent_events_indexes.sql applied live - 2026-05-12
- [x] 004_add_governance_tables.sql applied live - 2026-05-12
- [x] 005_add_cost_views.sql applied live - 2026-05-12
- [x] 006_fix_agent_outputs_constraint.sql applied live - 2026-05-12
- [x] 007_runs_reconciliation.sql applied live - 2026-05-12
- [x] Ingest route: agent_events write path activated - 2026-05-12
- [x] Ingest route: timeout_at, cost_reported, parent_run_id wired - 2026-05-12
- [x] TypeScript Agent interface corrected to live DB columns - 2026-05-12

## Deferred (intentional)

- [ ] Execution queue / worker model (Phase 5)
- [ ] Controlled execute flow from dashboard (Phase 6)
- [ ] Zombie run cleanup job — requires timeout_at (Phase 5)
- [ ] Retry conventions by error class (Phase 7)
- [ ] HITL approval events in agent_events taxonomy (Phase 8)
- [ ] RBAC / ACL governance model (Phase 8)
- [ ] Eval framework integration (Phase 8)
- [ ] Alerts via Resend email (post-Phase 4)
- [ ] Inngest durable execution queue (Phase 5)
