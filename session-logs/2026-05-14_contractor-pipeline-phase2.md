# Session Log — 2026-05-14 — Contractor Pipeline Phase 2

**Date:** 2026-05-14  **Duration:** Medium

## What changed this session

### API keys configured
- TAVILY_API_KEY: added to Windows user env vars (had leading-space typo in name — fixed)
- ANTHROPIC_API_KEY: Anthropic key was saved as 'reformai-agents' — renamed to ANTHROPIC_API_KEY
- Both keys verified working via live API test (Tavily search + Claude Haiku)
- tavily-python package installed

### research_tool.py written
- ReformAI_Agents/Contractor_Orchestrator_Agent/research_tool.py
- Inputs: planner targets JSON, market_id
- Flow per target: Tavily search (2 queries) -> Tavily Extract (top 3 URLs) -> Claude Haiku extraction -> validate -> dedupe against Supabase -> write row
- Deduplication: loads 757 existing dedupe_keys + domains from Supabase before starting
- Output: _researched_rows.json (pipeline-compatible format) + _evidence.json (audit trail)
- Model: claude-haiku-4-5-20251001 (cost ~$0.02-0.05 per 3-target batch)
- JSON parse fix: uses json.JSONDecoder().raw_decode() to handle multiple JSON objects in Claude response

### run_contractor_pipeline.py updated (Phase 2)
- Plan-only stop replaced with automatic research_tool call
- --skip-research flag added (preserves old plan-only behavior if needed)
- Full flow now: plan -> research -> batch (append + extract + catalog + sync)

### End-to-end test passed
- run_id: 9be1eddf-16f4-42af-b988-7d506a6723e3
- 3 targets researched (Santa Marta)
- 1 net-new contractor found: BrilloMax Colombia (Concrete Polishing & Grinding)
- Dedup correctly skipped 2 existing companies (Kachel Colombia, Brilladora Ground)
- 1 row appended to XLSX, cataloged, pipeline summary refreshed
- exit code 0, status=completed in Supabase

### Path fixes (also this session)
- All 27 legacy scripts updated from OneDrive\Desktop path to AI-Projects path
- agent UUID corrected (invalid variant byte in d2e3f4a5... -> valid 73de0fbc...)

## Decisions locked in
- Claude Haiku for extraction (not Sonnet) — sufficient quality, much cheaper
- Tavily basic search depth (not advanced) — cost control
- Evidence written locally as _evidence.json (Phase 3 moves to Supabase)
- --skip-research flag preserves old manual workflow when needed

## What's next
1. Phase 3: switch plan_batch() to read from Supabase contractor_rows instead of XLSX
2. Phase 4: build in-repo extractor (replace legacy extract_contacts_mvp.py)

---
*Logged by Claude — 2026-05-14*
