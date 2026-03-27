# Agent Oversight System — Current State

**Last updated:** 2026-03-27
**Status:** Active

## What this project is
Personal control plane for monitoring and coordinating all AI agents across ReformAI, AfterGlow, and Personal projects. Agents report lifecycle events (run_started, run_completed, run_failed) with token/cost telemetry to a central Supabase database. Claude sessions are treated as first-class agents in the system.

## Where we are right now
Phase 1 fully complete. Three agents are registered and active in the agent library.

- Supabase project: `hdhovyrlnfojtkqbcegh`
- `POST /api/ingest` live and validated at `agent-oversight.vercel.app`
- `PUT /api/project-state` and `GET /api/project-state/[tag]` live and validated
- `project_state` table seeded with all 5 project tags
- All 5 Claude session agents registered in `agents` table
- `runs` and `project_state` tables created (note: `runs` missing from migration file)
- `gh` CLI installed at `/c/Program Files/GitHub CLI/gh.exe`

## Stack / Key decisions locked in
- Next.js App Router, TypeScript strict mode
- Supabase SSR client pattern (async cookies)
- Service role key used for all API writes (bypasses RLS)
- Zod v4 validation on ingest payload
- Python SDK supports both `httpx` and stdlib `urllib` as fallback
- INGEST_SECRET: `ChArles-Clint0n-Leazer-Jr.-1s-the-B3st` (no special chars)
- `gh` CLI path: `/c/Program Files/GitHub CLI/gh.exe`
- Supabase is source of truth for session state — local files are backup only
- `OversightClient` appends `/api/ingest` internally — `OVERSIGHT_URL` must be base URL only (e.g. `https://agent-oversight.vercel.app`)
- Agent instance configs live in `agents/instances/<company>/<name>.config.json` — env vars always override

## Agent Library
| Agent | agent_id | Status |
|---|---|---|
| `context-agent` | `40b5e259-5b28-44fd-9c5b-e758093e5d3d` | Active |
| `marketing-agent` | `761c56f6-4de8-4859-974a-43d964de62f0` | Active |
| `engineering-review-agent` | `e6229606-78b9-4fd7-9424-6a62eb574255` | Active — pending first successful LLM run |

## Active work
Engineering Review Agent is built and registered. Pipeline is fully validated (GDrive fetch + GitHub fetch both confirmed working). Blocked only on LLM API quota — needs funded Gemini or OpenAI key.

- Config: `agents/instances/reformai/engineering-review-agent.config.json`
- Repo target: `leazer7222/reformai_visualization_agenettest`
- Feedback folder: `1dQqaXId3_RiR7Nq8xakI-XPxVzxAhosK` (3 docs, 44k chars)

## What's next
1. Fund LLM API key (Gemini or OpenAI) and run full engineering review
2. Review output, iterate on prompt if needed
3. Phase 2: dashboard UI — runs list, agent status page, cost/token charts
4. Add `runs` and `project_state` tables to `001_initial_schema.sql` migration file
5. Inngest integration for durable agent triggers
6. Resend email alerts for run_failed events

## Known issues / blockers
- `runs` and `project_state` tables were created manually — not in migration file yet
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` uses new publishable key format (`sb_publishable_...`) — correct for new Supabase projects
- Gemini free tier exhausted; OpenAI billing quota exceeded — need funded key to run LLM synthesis
