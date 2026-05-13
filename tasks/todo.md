# Agent Oversight System - Todo

## Completed

### Phase 4 — Dashboard MVP ✅ (2026-05-13, commit 4f73813)
- [x] `/dashboard` — overview KPIs, agents table, recent failures, recent runs
- [x] `/dashboard/runs` — paginated list, status filter bar
- [x] `/dashboard/runs/[id]` — stats, error block, event timeline, outputs
- [x] `/dashboard/agents/[id]` — metadata, stats, run history
- [x] `/dashboard/costs` — cost by agent / by project toggle
- [x] `/dashboard/errors` — category chip filters, paginated failure table
- [x] Shared components: StatusBadge, DurationLabel, CostLabel, EmptyState, Sidebar
- [x] shadcn/ui + Tailwind v4 dark mode
- [x] `apiFetch` server-side helper

## Next Up (Phase 5)

### Immediate blockers
- [ ] Merge `claude/suspicious-beaver-226b36` → main
- [ ] Recreate GCP OAuth2 client (project `1060125879836`), update `.mcp.json`
- [ ] Enable LLM billing for real token/cost data

### Polish
- [ ] Generate Supabase TypeScript types → `src/lib/supabase/types.ts`
- [ ] Set `NEXT_PUBLIC_SITE_URL` in Vercel env vars
- [ ] Deploy to Vercel / hosting
- [ ] Add agents page (`/dashboard/agents` list view)
- [ ] Real-time refresh (polling or SSE) on overview page
