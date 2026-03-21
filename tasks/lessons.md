# Agent Oversight System — Lessons Learned

[2026-03-21] | Next.js 16 (same as 15+): cookies() is async — always await it | Use `const cookieStore = await cookies()` in server.ts and route handlers
[2026-03-21] | Service role client must bypass RLS for ingest writes | Use createServiceRoleClient() (not the anon SSR client) in /api/ingest
[2026-03-21] | Python SDK should fall back to stdlib urllib when httpx isn't installed | Keep httpx as optional, wrap with try/except at import time
