# Agent Oversight System - Current State

Last updated: 2026-05-14
Status: Active — Contractor PT rollout validated; HubSpot sync path fixed and live.

---

## Completed Phases

### Phase 1-5 ✅
- Schema, telemetry, agent wiring, dashboard MVP, agents page, Netlify deploy

### Phase 6 — AI Ops Dashboard ✅ (2026-05-13)
- `/dashboard/ai-ops` — recommendation engine, provider health, quota confirm, reset schedule
- Migration 008: 5 new tables live

### Phase 7 — quota-sync-agent + Dual-Window Quota Display ✅ (2026-05-14)
- `agents/library/quota-sync-agent/quota_sync.py` — Claude + Codex auto-sync
- Migration 009: `window_type` column on `provider_quota_snapshots` (five_hour / seven_day / primary)
- Posts 4 snapshots per run: Claude 5h + 7d, Codex 5h
- Windows Task Scheduler: `QuotaSyncAgent` every 4h
- `ProviderQuotaStrip` on overview: shows 5h + Weekly bars side by side
- `ProviderStatePanel` on AI Ops: same dual bars, color-coded by urgency
- Committed 0ccbba3 → pushed to main → Netlify deploying

---

## quota-sync-agent Provider Status

| Provider | 5h | Weekly | Notes |
|---|---|---|---|
| Anthropic (Claude) | ✅ live | ✅ live | OAuth via `.credentials.json` |
| OpenAI (Codex) | ✅ live | — | No weekly window in API response |
| Google (Antigravity) | ⏳ v2 | ⏳ v2 | DPAPI-encrypted Chromium profile |

**Codex note:** URL fix was `/backend-api/codex/usage` (not `/backend-api/api/codex/usage`). Codex CLI not installed — auth.json orphaned from prior setup. ChatGPT Pro account confirmed.

**Antigravity v2:** When quota resets, open DevTools → Network tab → capture auth headers → then build DPAPI extractor.

---

## Active Blockers

| Blocker | Fix |
|---|---|
| `NEXT_PUBLIC_SITE_URL` not in Netlify | Add in Netlify env vars |
| LLM billing not enabled | Enable Gemini billing |
| Supabase TS types not generated | Run `mcp__supabase__generate_typescript_types` |
| Codex CLI not installed | `npm install -g @openai/codex` then `codex` to auth |

---

## Next Session Start

1. Process remaining PT `not_synced` rows blocked by extraction (`no_contact_found` / `request_failed`)
2. Keep legacy extractor active until in-repo extractor reaches parity + market profiles
3. Verify next scheduled PT run emits `hubspot_sync_invoked=1` and updates Supabase statuses in same run
4. Backport PT profile framework to MX/ES before activating those markets
5. Continue quota dashboard hardening tasks (Netlify env + Codex CLI + billing)
