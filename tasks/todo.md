# Agent Oversight System — Todo

## Active
- [ ] Add `runs` table to `001_initial_schema.sql` migration file (was created manually — needs to be in source)
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
- [x] Scaffold .env.local — 2026-03-21
- [x] Push Phase 1 to main — 2026-03-21
- [x] Set all env vars in Vercel — 2026-03-21
- [x] Create runs table in Supabase — 2026-03-21
- [x] Validate POST /api/ingest end-to-end in production — 2026-03-21

## Parking Lot
- QA rubric/constraints JSON per agent — deferred until first agent is built
