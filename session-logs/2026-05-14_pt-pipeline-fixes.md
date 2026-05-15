# Session Log — 2026-05-14 — PT Pipeline Fixes + Extract Contacts Rewrite

**Date:** 2026-05-14  **Duration:** Medium

## What changed this session

### extract_contacts.py — full rewrite (4 regressions fixed)
Codex identified 4 parity regressions vs the legacy extract_contacts_mvp.py.
The file had been truncated (161 lines, missing extract_one/run_extraction/main).
Rewrote completely with all regressions fixed:

1. **Contact link fallback** — collect_page_text() now accepts contact_link
   parameter and uses the row's Contact link column as a secondary seed URL
2. **Country-biased phone parsing** — dedicated regex per market (CO, PT, MX, ES);
   NIT filter for Colombia; WhatsApp URL extraction; structured JSON-LD scan
3. **Fetch fallback behavior** — build_hostname_fallbacks() tries www/no-www/http
   variants; hostname fallbacks run if all contact paths fail
4. **Skip / NULL handling** — only skips extraction_completed and no_contact_found;
   request_failed rows are re-attempted; empty fields never treated as completed

Also added: ThreadPoolExecutor for parallel batch processing, tel: link priority,
STRUCT_PHONE_RE / STRUCT_EMAIL_RE for JSON-LD extraction.
Validated: extract_one('Persianas Asombra') → extraction_completed, real email+phone.

### quota_sync.py — Task Scheduler fix
Added sys.stdout.reconfigure(encoding="utf-8") at top (line 11).
The arrow and checkmark symbols in print statements crashed Windows stdout
when running headless via Task Scheduler, silently stopping Supabase writes.
Codex made this fix. The task IS running on schedule (4:08 PM last run confirmed).

### PT pipeline — Portuguese search config
Updated pt-renovation pipeline_config in Supabase:
- subcategory_local_map: full Portuguese (pt-PT) translations for all 15 subcategories
  (instalador de ceramica e azulejo, instalador de soalho de madeira, etc.)
- search_templates: ["empresa", "empreiteiro", "Portugal empresa de obras"]
  (replaced "contractor" which is not a Portuguese word)
- cities: updated from [Lisboa, Sintra, VNG, Porto] to [Lisboa, Porto]
  (removed VNG and Sintra — low density suburbs)
- Fixed "Lisbon" → "Lisboa" normalization for 1 Supabase row

### PT batch results
4 consecutive PT batches showing yield improvement:
- VNG + Spanish terms: 2/10 (20%)
- VNG + Portuguese terms: 2/10 (20%)
- Porto: 4/10 (40%)
- Lisboa: 7/10 (70%) — KF Remodela, Leroy Merlin, Lider Reparacoes, MP Reparacoes
  Lisboa, StoneCare, Nelas Gas, Becosan; 6 extraction_completed, 1 request_failed

PT total: 41 rows in Supabase, synced to HubSpot automatically.

## Decisions locked in
- extract_contacts.py is the active extractor (USE_LEGACY_EXTRACTOR=1 for fallback)
- PT cities = Lisboa + Porto only (add Braga/Faro after Lisboa+Porto reach saturation)
- Portuguese search terms are config-driven (subcategory_local_map in pipeline_config)
- 70% yield is the benchmark for a mature city; 20-40% is expected for smaller cities

## What's next
1. Schedule automated PT runs (Task Scheduler or manual trigger)
2. Activate Mexico market (set active=true, first_run gate will apply)
3. Add Mexican Spanish subcategory translations to mx-renovation pipeline_config
4. Continue CO runs to keep pipeline active

---
*Logged by Claude — 2026-05-14*
