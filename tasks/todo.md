# Agent Oversight System — Todo

## Active
- [ ] Fund Gemini or OpenAI API key and run engineering review to completion
- [ ] Review engineering review output, iterate on prompt if needed
- [ ] Add `runs` and `project_state` tables to `001_initial_schema.sql` migration file
- [ ] Phase 2: dashboard UI — runs list, agent status page, cost/token charts
- [ ] Inngest integration for durable agent triggers
- [ ] Resend email alerts for run_failed events

## Completed
- [x] Install @supabase/ssr + @supabase/supabase-js — 2026-03-21
- [x] Create src/lib/supabase/client.ts — 2026-03-21
- [x] Create src/lib/supabase/server.ts (SSR + service role clients) — 2026-03-21
- [x] Create src/lib/adapters/types.ts — 2026-03-21
- [x] Create src/app/api/ingest/route.ts — 2026-03-21
- [x] Create python-sdk/oversight.py — 2026-03-21
- [x] Push Phase 1 to main — 2026-03-21
- [x] Set all env vars in Vercel — 2026-03-21
- [x] Create runs table in Supabase — 2026-03-21
- [x] Validate POST /api/ingest end-to-end in production — 2026-03-21
- [x] Create project_state table and seed all 5 project tags — 2026-03-21
- [x] PUT /api/project-state and GET /api/project-state/[tag] endpoints live — 2026-03-21
- [x] Seed master-agentic-flow state into Supabase — 2026-03-21
- [x] Install supabase/agent-skills — 2026-03-21
- [x] Install gh CLI, authenticate — 2026-03-21
- [x] Register all 5 Claude session agents in agents table — 2026-03-21
- [x] Update session-logger skill to use API instead of local files — 2026-03-21
- [x] Build Engineering Review Agent (agent.py, prompt.md, README, agent.json, LESSONS) — 2026-03-27
- [x] Register engineering-review-agent in Supabase (agent_definitions + agents) — 2026-03-27
- [x] Validate GDrive feedback fetch (3 docs, 44k chars) — 2026-03-27
- [x] Validate GitHub code fetch (16 files from reformai_visualization_agenettest) — 2026-03-27

## Parking Lot
- QA rubric/constraints JSON per agent — deferred until first agent is built
