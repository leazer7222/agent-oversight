# Agent Oversight System — Lessons Learned

[2026-03-21] | Next.js 16 (same as 15+): cookies() is async — always await it | Use `const cookieStore = await cookies()` in server.ts and route handlers
[2026-03-21] | Service role client must bypass RLS for ingest writes | Use createServiceRoleClient() (not the anon SSR client) in /api/ingest
[2026-03-21] | Python SDK should fall back to stdlib urllib when httpx isn't installed | Keep httpx as optional, wrap with try/except at import time
[2026-03-21] | Trailing spaces in .env.local or Vercel env var values cause silent auth failures | Always trim whitespace from secret values before saving — a trailing space makes the string comparison fail with no useful error
[2026-03-21] | Special characters (@ in particular) in secrets can cause issues in curl commands on Windows | Use only alphanumeric + hyphens in INGEST_SECRET to avoid shell escaping headaches
[2026-03-21] | runs table was missing from initial migration | When the route.ts references a table, verify it exists in Supabase before testing — don't assume schema is complete
[2026-03-21] | Vercel env vars added after a deploy require a manual redeploy to take effect | Always redeploy after adding/changing env vars — the running deployment won't pick them up automatically
[2026-03-21] | If a task can be done by Claude, do it — don't hand it back to Chuck | If a required CLI tool is missing, suggest it, install it, then complete the task without asking Chuck to do the steps
[2026-03-21] | When asking Chuck to run a command, always specify WHERE | Say explicitly "run this in your terminal" vs "I'll run this here" — never leave it ambiguous
[2026-03-21] | Claude CAN run commands in Chuck's terminal via the Bash tool | Use Bash tool for all commands that don't require interactive input (browser auth, password prompts). For interactive commands like `gh auth login`, clearly explain why Chuck must run it himself
