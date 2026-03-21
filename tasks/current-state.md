# Agent Oversight System — Current State

**Last updated:** 2026-03-21
**Status:** Active

## What this project is
Personal control plane for monitoring and coordinating all AI agents across ReformAI, AfterGlow, and Personal projects. Agents report lifecycle events (run_started, run_completed, run_failed) with token/cost telemetry to a central Supabase database. Claude sessions are treated as first-class agents in the system.

## Where we are right now
Phase 1 fully complete and validated in production. The full memory loop is wired up.

- Supabase project: `hdhovyrlnfojtkqbcegh`
- `POST /api/ingest` live and validated at `agent-oversight.vercel.app`
- `PUT /api/project-state` and `GET /api/project-state/[tag]` live and validated
- `project_state` table seeded with all 5 project tags — `master-agentic-flow` has real content
- All 5 Claude session agents registered in `agents` table (one per project tag)
- `runs` and `project_state` tables created (note: `runs` missing from migration file)
- `supabase/agent-skills` (Postgres best practices) installed in `.claude/skills`
- `gh` CLI installed at `/c/Program Files/GitHub CLI/gh.exe` — Claude handles all PRs
- Session-logger skill updated — reads/writes state via API, emits run events, Supabase is source of truth
- All 7 env vars set in Vercel and `.env.local`

## Stack / Key decisions locked in
- Next.js App Router, TypeScript strict mode
- Supabase SSR client pattern (async cookies)
- Service role key used for all API writes (bypasses RLS)
- Zod v4 validation on ingest payload
- Python SDK supports both `httpx` and stdlib `urllib` as fallback
- INGEST_SECRET: `ChArles-Clint0n-Leazer-Jr.-1s-the-B3st` (no special chars)
- `gh` CLI path: `/c/Program Files/GitHub CLI/gh.exe`
- Supabase is source of truth for session state — local files are backup only

## Active work
Nothing in flight. Phase 1 fully closed including memory loop.

## What's next
1. Start ReformAI session — session-logger will auto read/write state via API
2. Phase 2: dashboard UI
   - Runs list page (paginated, filterable by agent/status)
   - Agent status page (active/paused/error)
   - Cost + token usage charts
3. Add `runs` and `project_state` tables to `001_initial_schema.sql` migration file
4. Inngest integration for durable agent triggers
5. Resend email alerts on `run_failed` events

## Known issues / blockers
- `runs` and `project_state` tables were created manually — not in migration file yet
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` uses new publishable key format (`sb_publishable_...`) — correct for new Supabase projects
