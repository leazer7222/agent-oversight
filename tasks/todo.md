# Agent Oversight System - Todo

## Active

### Immediate
- [ ] Merge PR → confirm Netlify deploy succeeds
- [ ] Open /dashboard/ai-ops → set reset schedule + confirm quota → verify recommendation fires with High confidence
- [ ] Add `NEXT_PUBLIC_SITE_URL=https://agentoversight.netlify.app` in Netlify env vars

### Platform polish
- [ ] Enable LLM billing → fire real agent run → verify live cost/token data
- [ ] Generate Supabase TypeScript types → `src/lib/supabase/types.ts`
- [ ] Real-time refresh (polling) on overview page
- [ ] Error alerting — notify on agent failure (email / Slack)

### V2 AI Ops
- [ ] Browser extension: detect quota-exhausted message on claude.ai / chat.openai.com → POST to /api/ai-ops/quota-snapshot with pct=0
- [ ] OpenAI API usage endpoint integration (for API key users)

## Completed

### Phase 4 — Dashboard MVP ✅ (2026-05-13)
- [x] /dashboard, /dashboard/runs, /dashboard/runs/[id], /dashboard/agents/[id], /dashboard/costs, /dashboard/errors
- [x] Shared components, apiFetch helper, TypeScript clean

### Phase 5 — Agents Page + Deploy ✅ (2026-05-13)
- [x] /dashboard/agents list page
- [x] Netlify deploy: https://agentoversight.netlify.app

### Phase 6 — AI Ops Dashboard ✅ (2026-05-13)
- [x] Migration 008: 5 AI Ops tables live in Supabase
- [x] Recommendation engine (deterministic rules)
- [x] Provider health polling (status page APIs)
- [x] Signal assembly from existing runs telemetry
- [x] /dashboard/ai-ops page with workload selector
- [x] RecommendationCard + feedback (thumbs up/down)
- [x] ProviderStatePanel with quota bars + health dots
- [x] QuotaConfirmButton (slider, expires 8h)
- [x] ResetScheduleButton (weekly/monthly, day picker)
- [x] API routes: quota-snapshot, feedback, provider-account
- [x] Sidebar: AI Ops nav item
- [x] PR created + branch pushed

## Parking Lot
- Automatic model routing (V5 — requires trust earned through V1-V4)
- Multi-user team quota pooling
- Cost forecasting beyond "trending" signal
- Push notifications for provider health changes
