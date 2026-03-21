# Agent Oversight System — Current State

**Last updated:** 2026-03-21
**Status:** Active

## What this project is
Personal control plane for monitoring and coordinating all AI agents across ReformAI, AfterGlow, and Personal projects. Agents report lifecycle events (run_started, run_completed, run_failed) with token/cost telemetry to a central Supabase database via the /api/ingest endpoint.

## Where we are right now
Phase 1 complete. The ingest pipeline is wired up:
- Supabase schema already deployed (project: hdhovyrlnfojtkqbcegh)
- `@supabase/ssr` + `@supabase/supabase-js` installed
- Browser client (`src/lib/supabase/client.ts`) and server client + service role client (`src/lib/supabase/server.ts`) created
- Shared adapter types (`src/lib/adapters/types.ts`) define Agent, AgentRun, IngestPayload
- POST /api/ingest route validates `x-agent-secret`, verifies agent exists + is active, upserts run records
- Python SDK (`python-sdk/oversight.py`) with `OversightClient` and `run()` context manager
- `.env.local` scaffolded — **Supabase anon key and service role key still need to be filled in**

## Stack / Key decisions locked in
- Next.js 16 App Router, TypeScript strict mode
- Supabase SSR client pattern (async cookies)
- Service role key used for ingest writes (bypasses RLS)
- Zod validation on ingest payload
- Python SDK supports both `httpx` (preferred) and stdlib `urllib` as fallback
- `INGEST_SECRET=agent-oversight-secret-2026-secure-key`

## Active work
Phase 1 just completed. Branch: `claude/affectionate-goldstine` — needs to be merged to main.

## What's next
1. Fill in `.env.local` with real Supabase anon + service role keys (from dashboard → Project Settings → API)
2. Also add these env vars to Vercel dashboard for production
3. Push branch → merge to main → Vercel auto-deploy
4. Test: `POST /api/ingest` with header `x-agent-secret: agent-oversight-secret-2026-secure-key` and a valid `agent_id`
5. Phase 2: dashboard UI (runs list, agent status, cost tracking)

## Known issues / blockers
- `.env.local` has placeholder values for `NEXT_PUBLIC_SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY` — must be set before running locally or deploying
- TypeScript check requires `next build` or `next typegen` to generate the `RouteContext` types; tsc --noEmit should pass with skipLibCheck
