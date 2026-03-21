# Session Log — 2026-03-21 — Agent Oversight (Phase 1 Deploy)

**Date:** 2026-03-21  **Duration:** Medium

## What changed this session
- Merged PR #1 (`claude/affectionate-goldstine` → `main`) — Phase 1 ingest pipeline
- Imported repo into Vercel, confirmed production deploy at `agent-oversight.vercel.app`
- Added all 7 env vars to Vercel: NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, INNGEST_SIGNING_KEY, INNGEST_EVENT_KEY, RESEND_API_KEY, INGEST_SECRET
- Created `runs` table in Supabase via SQL Editor (was missing from migration)
- Inserted test agent (`7ea87edd-03b9-4eae-9bd4-17e49fea5c32`) into agents table under Personal company
- Validated POST /api/ingest end-to-end — `{"ok":true,"run_id":"a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"}`

## Decisions made
- INGEST_SECRET uses no special characters (@ removed) to avoid curl/shell escaping issues
- `runs` table uses service_role RLS policy (all operations) — ingest route writes with service role client
- New Supabase publishable key format (`sb_publishable_...`) confirmed working for anon key

## Problems encountered
- Initial curl returned 401 — root cause was trailing spaces in INGEST_SECRET value in both .env.local and Vercel
- `runs` table didn't exist — the original migration only had agent_events, not a dedicated runs table
- Windows CMD doesn't support multiline backslash curl — had to use single-line command

## What to do better
- Check that all tables referenced in route files exist in Supabase before testing
- Always trim env var values — trailing spaces cause silent failures that are hard to debug

---
*Logged by Claude — 2026-03-21*
