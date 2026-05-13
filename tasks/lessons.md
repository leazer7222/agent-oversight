# Agent Oversight System — Lessons Learned

[2026-03-21] | Next.js 16 (same as 15+): cookies() is async — always await it | Use `const cookieStore = await cookies()` in server.ts and route handlers
[2026-03-21] | Service role client must bypass RLS for ingest writes | Use createServiceRoleClient() (not the anon SSR client) in /api/ingest
[2026-03-21] | Python SDK should fall back to stdlib urllib when httpx isn't installed | Keep httpx as optional, wrap with try/except at import time
[2026-03-21] | Trailing spaces in .env.local or Vercel env var values cause silent auth failures | Always trim whitespace from secret values before saving
[2026-03-21] | Special characters (@ in particular) in secrets can cause issues in curl commands on Windows | Use only alphanumeric + hyphens in INGEST_SECRET
[2026-03-21] | runs table was missing from initial migration | When route.ts references a table, verify it exists in Supabase before testing
[2026-03-21] | Vercel env vars added after a deploy require a manual redeploy | Always redeploy after adding/changing env vars
[2026-03-21] | If a task can be done by Claude, do it — don't hand it back to Chuck | Use Bash tool for all commands that don't require interactive input
[2026-03-21] | gh CLI is installed at /c/Program Files/GitHub CLI/gh.exe — not on PATH | Always call it with the full path in Bash tool commands
[2026-03-30] | OversightClient takes base URL only — SDK appends /api/ingest automatically | Never pass the full endpoint path to OversightClient constructor; pass domain only (e.g. http://localhost:3000)
[2026-03-30] | OVERSIGHT_SECRET is not set in .env.local — the var is named INGEST_SECRET | Always fall back to INGEST_SECRET when reading OVERSIGHT_SECRET; add both to env lookups in agents
[2026-03-30] | Unicode characters (→, —) in print statements crash on Windows cp1252 stdout | Add sys.stdout.reconfigure(encoding="utf-8") at top of any agent that prints non-ASCII
[2026-03-30] | Vercel preview URL has SSO protection — Python agents cannot POST without bypass token | Default agent OVERSIGHT_URL to localhost:3000 for local runs; production ingest requires Vercel bypass token or custom domain without protection
[2026-03-30] | session-logs and tasks are not being updated between sessions — state goes stale | Session end ritual is mandatory: rewrite current-state.md, update todo.md and lessons.md before closing
[2026-05-13] | API column assumptions in `/api/ingest` and `/api/project-state*` drifted from migrations | Treat API-to-table mappings as contract-critical and validate against migration schema in every phase gate.
[2026-05-13] | `runs` semantics blurred between summary row and event trace | Keep `runs` as lifecycle summary and use append-only `agent_events` for trace detail.
[2026-05-13] | Runtime emitted `agent_outputs.output_type=ui_components` not allowed by migration constraints | Enforce output taxonomy governance: runtime values must be codified in DB constraints before use.
[2026-05-13] | Schema source-of-truth ambiguity slowed confidence in Phase sequencing | Require dual completion for schema changes: live apply + migration/doc reconciliation.
[2026-05-12] | Codex analyzed 001_initial_schema.sql but the file was never committed | Always verify source files exist before treating audit findings as authoritative.
[2026-05-12] | agent_events receives zero writes despite possibly existing live — ingest route never writes to it | Table existence is not observability; write path must be explicitly implemented.
[2026-05-12] | null cost_usd is indistinguishable from unreported vs genuinely zero | Add cost_reported BOOLEAN to runs as sentinel field.
[2026-05-12] | runs stuck in started status are zombie runs with no cleanup mechanism | Add timeout_at TIMESTAMPTZ to runs at insert time; build cleanup job in Phase 5.
[2026-05-12] | migrations + documented contracts are canonical, not live DB | Live DB is operational reality; reconciliation closes the gap toward canonical intent.
