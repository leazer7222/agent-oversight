# Agent Oversight System - Todo

## Completed

### Phase 4 — Dashboard MVP ✅ (2026-05-13)
- [x] `/dashboard` — overview KPIs, agents table, recent failures, recent runs
- [x] `/dashboard/runs` — paginated list, status filter bar
- [x] `/dashboard/runs/[id]` — stats, error block, event timeline, outputs
- [x] `/dashboard/agents/[id]` — metadata, stats, run history
- [x] `/dashboard/costs` — cost by agent / by project toggle
- [x] `/dashboard/errors` — category chip filters, paginated failure table
- [x] Shared components: StatusBadge, DurationLabel, CostLabel, EmptyState, Sidebar
- [x] shadcn/ui + Tailwind v4 dark mode
- [x] `apiFetch` server-side helper

### Phase 5 — Agents Page + Deploy ✅ (2026-05-13)
- [x] `/dashboard/agents` list page with status filter + full stats
- [x] Sidebar Agents link + active state fix
- [x] Netlify config (`netlify.toml` + `@netlify/plugin-nextjs`)
- [x] Fix git worktree gitlinks blocking Netlify build
- [x] Root redirect `/` → `/dashboard`
- [x] OAuth2 client recreated + `.mcp.json` updated
- [x] Deployed: https://agentoversight.netlify.app

## Next Up (Phase 6)

### Immediate
- [ ] Add `NEXT_PUBLIC_SITE_URL=https://agentoversight.netlify.app` in Netlify → redeploy
- [ ] Enable LLM billing
- [ ] Fire a real agent run → verify live data in dashboard

### Polish
- [ ] Generate Supabase TypeScript types → `src/lib/supabase/types.ts`
- [ ] Real-time refresh (polling) on overview page
- [ ] Error alerting — notify on agent failure (email / Slack)
