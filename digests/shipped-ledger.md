# Shipped Ledger - what we shipped, across all projects

Generated: 2026-06-24 from live GitHub (`gh pr list --state merged`). This is an INDEX into shipped
work, not the work itself - every PR below lives permanently in GitHub (title, diff, description,
commits). Archiving a Claude Code chat NEVER removes any of this; the chat is scaffolding, the PR is
the record.

Regenerate anytime:
```
for r in ReformAI-Inc/Reform-AI ReformAI-Inc/web-scraper ReformAI-Inc/reformAI-home \
         leazer7222/agent-oversight reformai-admin/reformai_visualizationengine; do
  gh -R "$r" pr list --state merged --limit 100 --json number,title,mergedAt
done
```

> NOTE on coverage: PR-based repos (Reform-AI, web-scraper, reformAI-home) are FULLY captured here.
> `agent-oversight` ships straight-to-main with almost no PRs - its real shipped record is
> `sessions/*.md` + `docs/agent-*.md` + the live registered agents (cost engine, estimation
> dashboard, BA/CCA, Jira agent). Treat the agent-oversight PR list below as partial.

Totals: ~78 merged PRs across 5 repos.

---

## ReformAI-Inc/Reform-AI  (the product app - 51 merged)

| Merged | PR | Title |
|---|---|---|
| 2026-06-24 | #54 | RAI-582 Dynamically Manage Prices |
| 2026-06-19 | #52 | provider interest on listings (v0 of Renovation Concepts) |
| 2026-06-19 | #51 | Operational Health & Reliability monitoring |
| 2026-06-16 | #50 | docs: Jira<->GitHub QA deploy sync design |
| 2026-06-16 | #49 | integrate PostHog across web and API |
| 2026-06-15 | #48 | New dashboards |
| 2026-06-13 | #47 | Hotfix: Google Maps key + optional address ZIP (prod) |
| 2026-06-12 | #46 | Drop zip from manual address guard in PropertyForm |
| 2026-06-12 | #45 | Make address ZIP optional (admin form + address API) |
| 2026-06-12 | #44 | Fix broken Google Maps: dead API key in 4 components |
| 2026-06-12 | #43 | Habi inventory integration: import, AI room visuals, reviewer workflow |
| 2026-06-09 | #42 | RAI-593 New type of service added |
| 2026-06-09 | #41 | RAI-605 Service Provider Profile - Translations |
| 2026-06-05 | #40 | RAI-616 Partnered Projects - Translations and Fixes |
| 2026-06-05 | #39 | Release 1.0.6 |
| 2026-06-05 | #38 | RAI-606 work contract template variables, homeowner/SP legal id |
| 2026-05-29 | #37 | Admin Module - Users - Filter by seller fix |
| 2026-05-29 | #36 | Seller Module Fixes |
| 2026-05-29 | #35 | Seller Module Fixes |
| 2026-05-28 | #34 | RAI-594 HotFix Seller registration, image persistence, sidebar |
| 2026-05-27 | #33 | RAI-594 Dynamically Manage Legal Documents Per Country |
| 2026-05-26 | #32 | Service Provider - Bid Flow Fixes and Improvements |
| 2026-05-25 | #31 | Manas bugs |
| 2026-05-25 | #30 | Renovation game and homeowner fixes |
| 2026-05-21 | #29 | RAI-549 Admin - Distressed Properties and other fixes |
| 2026-05-21 | #28 | RAI-545 Subscription add-on prices + COP currency labels |
| 2026-05-20 | #27 | Service Provider: responsive mobile UI for dashboard |
| 2026-05-20 | #26 | RAI-542 Legal Documents Updated - Spanish |
| 2026-05-19 | #25 | RAI-510 Wire Wompi checkout into subscription/add-on purchases |
| 2026-05-19 | #24 | Homeowner and service provider updates |
| 2026-05-18 | #23 | Homeowner and Service Provider Updates |
| 2026-05-15 | #22 | RAI-515 Switch between Admin and Homeowner menus |
| 2026-05-15 | #21 | Service Provider and Homeowner Fixes |
| 2026-05-14 | #20 | Homeowner and Service Provider Fixes |
| 2026-05-13 | #19 | Several Bug Fixes and Improvements |
| 2026-05-13 | #18 | RAI-511 Hotfix(payments): round COP amounts up |
| 2026-05-12 | #17 | RAI-465 Renovation Game |
| 2026-05-11 | #16 | fix(homeowner): mobile UI polish |
| 2026-05-11 | #15 | Bid Flow And Quick Job Fixes |
| 2026-05-08 | #14 | RAI-464 Inspiration Hub Fixes |
| 2026-05-07 | #13 | RAI-464 Inspiration Hub |
| 2026-05-06 | #12 | RAI-462 Quick Jobs - Trabajos Puntuales |
| 2026-05-04 | #11 | RAI-461 Bid Submission Dashboard |
| 2026-05-04 | #10 | RAI-460 New Project - Address Autocomplete Places |
| 2026-04-30 | #9 | RAI-452 Sidebar Icons Aligned |
| 2026-04-29 | #8 | Hotfix: Broken Navigation Links + Dead Button in SP Billing |
| 2026-04-29 | #7 | RAI-439 Update Bid Process |
| 2026-04-27 | #6 | Hotfix: Broken Navigation Links + Dead Button in SP Billing |
| 2026-04-28 | #5 | fix(seller): onboarding flow + seller listing UX |
| 2026-04-27 | #4 | RAI-435 Spanish/English Logo by Language |
| 2026-04-23 | #3 | fix: login page layout for mobile |
| 2025-08-30 | #2 | Shivi/admin |

## ReformAI-Inc/reformAI-home  (marketing site - 7 merged)

| Merged | PR | Title |
|---|---|---|
| 2026-06-23 | #7 | refined ES copy + EN parity; force Spanish default |
| 2026-06-22 | #6 | real Bogota inventory + before/after sliders |
| 2026-06-22 | #5 | activate social links + update contact email |
| 2026-06-22 | #4 | ci(prod): inject Notion env vars into Cloud Run deploy |
| 2026-06-22 | #3 | Real Estate Investors nav tab + pt parity |
| 2026-06-22 | #2 | investor/STR landing page + lead capture |
| 2026-06-17 | #1 | About/Homeowners/Sellers/Contractors landing pages + navbar + pt i18n |

## ReformAI-Inc/web-scraper  (lead pipeline - 7 merged)

| Merged | PR | Title |
|---|---|---|
| 2026-06-18 | #8 | Stage 3: hard room rules (best kitchen + best bathroom) |
| 2026-06-18 | #6 | Phase A: Stage 3 visualization - before/after renders |
| 2026-06-18 | #5 | Scoring model v2 - value-add deal engine |
| 2026-06-17 | #4 | fix(vision): gemini-2.5-flash default + lead counting |
| 2026-06-17 | #3 | fix(workers): private-ranges-only VPC egress |
| 2026-06-17 | #2 | Phase 2: automated discovery (fincaraiz) + daily cap |
| 2026-06-17 | #1 | Phase 1: pipeline hardening |

## leazer7222/agent-oversight  (PARTIAL - straight-to-main; see note above)

| Merged | PR | Title |
|---|---|---|
| 2026-05-14 | #8 | Phase 0A - contractor pipeline migration to Supabase |
| 2026-05-14 | #7 | Agile Team Phase 1 - PCA, canonical docs, schema, orchestrator |
| 2026-05-14 | #6 | AI Ops dashboard - provider health, recommendation engine |
| 2026-05-13 | #5 | docs: ai-assisted software delivery operating system |
| 2026-03-21 | #4 | session close - phase 1 complete, memory loop wired up |
| 2026-03-21 | #3 | install supabase agent skills + project-state endpoints |
| 2026-03-21 | #2 | add project-state endpoints and update session state |
| 2026-03-21 | #1 | Phase 1 ingest pipeline - Supabase clients, /api/ingest |

Straight-to-main shipped (NOT PRs - from sessions/ + docs/): Cost Risk Engine (mig 012-022),
Estimation Dashboard, BA Scoping Agent, Codebase Context Agent, Jira Sprint Reporting Agent.

## reformai-admin/reformai_visualizationengine  (5 merged)

| Merged | PR | Title |
|---|---|---|
| 2026-05-11 | #6 | fix: contract test runner compiles includes on main |
| 2026-05-11 | #4 | ci: auto-deploy vis-service to Cloud Run on push |
| 2026-05-11 | #3 | complete apps/vis-service - AGT extraction, full pipeline |
| 2026-05-11 | #2 | add balanced_v6/v7 to Cloud Run schema and dispatcher |
| 2026-05-11 | #1 | add balanced_v7 to sandbox UI pipeline selector |
