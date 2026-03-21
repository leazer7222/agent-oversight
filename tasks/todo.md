# Agent Oversight System — Todo

## Active
- [ ] Fill in `.env.local` Supabase keys (anon + service role) from dashboard
- [ ] Add env vars to Vercel dashboard (NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, INGEST_SECRET)
- [ ] Test POST /api/ingest with a valid agent_id from agents table
- [ ] Phase 2: dashboard UI — runs list, agent status page, cost/token charts

## Completed
- [x] Install @supabase/ssr + @supabase/supabase-js — 2026-03-21
- [x] Create src/lib/supabase/client.ts — 2026-03-21
- [x] Create src/lib/supabase/server.ts (SSR + service role clients) — 2026-03-21
- [x] Create src/lib/adapters/types.ts — 2026-03-21
- [x] Create src/app/api/ingest/route.ts — 2026-03-21
- [x] Create python-sdk/oversight.py — 2026-03-21
- [x] Scaffold .env.local — 2026-03-21
- [x] Push Phase 1 to main — 2026-03-21

## Parking Lot
- Inngest integration for durable agent triggers — deferred until ingest is validated in production
- Resend email alerts for run_failed events — deferred until Phase 2
- QA rubric/constraints JSON per agent — deferred until first agent is built
