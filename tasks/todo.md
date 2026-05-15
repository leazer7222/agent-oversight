# Agent Oversight System - Todo

## Active

### Immediate
- [ ] Portugal pipeline: resolve remaining `not_synced` rows blocked by `no_contact_found` / `request_failed`
- [ ] Portugal pipeline: run corrective extraction pass for remaining 4 blocked companies, then rerun HubSpot sync
- [ ] Contractor orchestrator: verify every run now emits HubSpot stage outputs (`hubspot_sync_invoked`, status writeback by market)
- [ ] Verify Netlify deploy — check /dashboard for dual quota bars (5h + Weekly)
- [ ] Add `NEXT_PUBLIC_SITE_URL=https://agentoversight.netlify.app` in Netlify env vars
- [ ] Install Codex CLI: `npm install -g @openai/codex` → run `codex` to authenticate → re-run agent to get weekly window

### Platform polish
- [ ] Enable LLM billing → fire real agent run → verify live cost/token data
- [ ] Generate Supabase TypeScript types → `src/lib/supabase/types.ts`
- [ ] Real-time refresh (polling) on overview page
- [ ] Error alerting — notify on agent failure (email / Slack)

### V2 quota sources
- [ ] Antigravity DPAPI extraction (inspect network traffic when quota resets first)
- [ ] Browser extension: detect quota-exhausted on claude.ai / chat.openai.com → POST pct=0

### Contractor pipeline hardening
- [ ] In-repo extractor parity: restore all critical behaviors from legacy extractor before cutover
- [ ] Market profiles for extraction: formalize CO/PT/MX/ES settings (language headers, contact paths, phone validation)
- [ ] Supabase contract checks: ensure extraction status writeback happens in every batch before HubSpot sync

## Completed

### Phase 4 ✅ (2026-05-13)
- [x] Full dashboard MVP — 6 pages

### Phase 5 ✅ (2026-05-13)
- [x] /dashboard/agents + Netlify deploy

### Phase 6 — AI Ops Dashboard ✅ (2026-05-13)
- [x] Migration 008, recommendation engine, provider health, quota/reset UI, API routes

### Phase 7 — quota-sync-agent + Dual-Window Display ✅ (2026-05-14)
- [x] Claude OAuth login (`claude login`)
- [x] Claude quota API: 5h + 7d windows both captured
- [x] Codex quota API: URL fix `/backend-api/codex/usage`
- [x] quota-sync-agent posts 4 snapshots per run (Claude 5h+7d, Codex 5h)
- [x] Migration 009: `window_type` column on `provider_quota_snapshots`
- [x] Windows Task Scheduler: QuotaSyncAgent every 4h
- [x] ProviderQuotaStrip: 5h + Weekly bars on overview page
- [x] ProviderStatePanel: dual bars on AI Ops page, color-coded
- [x] signals.ts: binding = min(5h, 7d) for recommendation engine
- [x] next.config.ts: Turbopack root fix
- [x] git pull + commits + pushed to main

## Parking Lot
- Automatic model routing (V5)
- Multi-user team quota pooling
- Cost forecasting
- Push notifications for provider health changes
