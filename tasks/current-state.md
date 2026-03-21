# Agent Oversight System — Current State

**Last updated:** 2026-03-21
**Status:** Active

## What this project is
Personal control plane for monitoring and coordinating all AI agents across ReformAI, AfterGlow, and Personal projects. Agents report lifecycle events (run_started, run_completed, run_failed) with token/cost telemetry to a central Supabase database via the /api/ingest endpoint.

## Where we are right now
Phase 1 fully complete and validated in production.

- Supabase project: `hdhovyrlnfojtkqbcegh`
- `@supabase/ssr` + `@supabase/supabase-js` installed
- Browser client (`src/lib/supabase/client.ts`) and server/service role clients (`src/lib/supabase/server.ts`) created
- Shared adapter types (`src/lib/adapters/types.ts`) — Agent, AgentRun, IngestPayload
- `POST /api/ingest` route live at `agent-oversight.vercel.app/api/ingest` — validated with real curl
- Python SDK (`python-sdk/oversight.py`) with `OversightClient` and `run()` context manager
- `.env.local` fully populated with all real keys (no placeholders)
- All 7 env vars set in Vercel: NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, INNGEST_SIGNING_KEY, INNGEST_EVENT_KEY, RESEND_API_KEY, INGEST_SECRET
- `runs` table created manually in Supabase (was missing from initial migration)
- Test agent inserted: `7ea87edd-03b9-4eae-9bd4-17e49fea5c32` (name: test-agent, company: Personal)
- Test run confirmed written to `runs` table: run_id `a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d`

## Stack / Key decisions locked in
- Next.js App Router, TypeScript strict mode
- Supabase SSR client pattern (async cookies)
- Service role key used for ingest writes (bypasses RLS)
- Zod v4 validation on ingest payload
- Python SDK supports both `httpx` (preferred) and stdlib `urllib` as fallback
- INGEST_SECRET: `ChArles-Clint0n-Leazer-Jr.-1s-the-B3st` (no special chars — @ removed)
- `runs` table has service_role RLS policy (all operations allowed for service role)

## Active work
Nothing in flight. Phase 1 closed. Ready to start Phase 2.

## What's next
1. Phase 2: dashboard UI
   - Runs list page (paginated, filterable by agent/status)
   - Agent status page (active/paused/error)
   - Cost + token usage charts
2. Wire up Inngest for durable agent triggers (deferred from Phase 1)
3. Resend email alerts on `run_failed` events

## Known issues / blockers
- `runs` table was NOT in the original migration file (`001_initial_schema.sql`) — it was created manually via SQL Editor. Need to add it to the migration file so it's reproducible.
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` in `.env.local` uses new Supabase publishable key format (`sb_publishable_...`) — this is the correct format for new projects.
- Trailing spaces in `.env.local` values will cause silent auth failures — always trim before saving.
