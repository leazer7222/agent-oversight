# Agent Oversight System - Current State

Last updated: 2026-05-13
Status: Active — Phases 1-6 complete. PR open for AI Ops feature.

---

## Completed Phases

### Phase 1 — Schema Stabilization ✅
- Migrations 001-007 applied live; ingest route, agent_events, cost views all active.

### Phase 2 — Telemetry Standardization ✅
- `run_step` event type, StepTimer, error taxonomy, cost capture in agents.

### Phase 3 — Agent Wiring ✅
- context-agent and marketing-agent emit full telemetry; orchestrator wired with step events.

### Phase 4 — Dashboard MVP ✅ (2026-05-13)
- 6 pages: overview, runs list, run detail, agent detail, costs, errors
- shadcn/ui + Tailwind v4 + forced dark mode

### Phase 5 — Agents Page + Deploy ✅ (2026-05-13)
- `/dashboard/agents` list page with status filter + full stats
- Live at: https://agentoversight.netlify.app

### Phase 6 — AI Ops Dashboard ✅ (2026-05-13, commits bd296ae + 1371967)
- `/dashboard/ai-ops` — AI operational advisor page
- Workload selector (General / Reasoning / Code / Creative / Bulk)
- Recommendation card: headline, visible reasoning, confidence badge, thumbs up/down
- Provider state panel: quota bar, reset countdown, health dot, source label
- Recommendation engine: health 35% / quota use-it-or-lose-it 40% / error rate 15% / workload fit 10%
- Provider health: polls status pages every 5 min, caches in DB
- Signal assembly: derives cost trend + error rate from existing runs telemetry
- Reset schedule UI: weekly/monthly toggle + day picker, saves to provider_accounts
- Quota confirm UI: slider popover, expires after 8h
- API routes: /api/ai-ops/quota-snapshot, /api/ai-ops/feedback, /api/ai-ops/provider-account
- Migration 008: 5 new tables applied live
- TypeScript: clean
- **PR open → pending merge → Netlify deploy**

---

## Active Blockers

| Blocker | Impact | Owner |
|---|---|---|
| PR not yet merged | AI Ops not live on Netlify | Merge PR |
| `NEXT_PUBLIC_SITE_URL` not set in Netlify | API routes may misroute | Add env var + redeploy |
| LLM billing not enabled | cost/token columns null | Enable Gemini billing |
| Supabase TS types not generated | `any` casts in API routes | run generate_typescript_types |

---

## Next Session Start

1. Confirm PR merged + Netlify deploy succeeded
2. Open /dashboard/ai-ops → set reset schedule for each provider → confirm quota → verify recommendation fires
3. Add `NEXT_PUBLIC_SITE_URL=https://agentoversight.netlify.app` in Netlify env vars
4. Enable LLM billing → fire real agent run → verify live cost data
5. V2 AI Ops: browser extension spec (catches quota-exhausted events from claude.ai / chat.openai.com)
