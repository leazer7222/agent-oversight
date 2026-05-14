# Session Log — 2026-05-14 — HubSpot Sync

**Date:** 2026-05-14  **Duration:** Medium

## What changed this session

### Data cleanup
- Fixed 388 legacy XLSX rows: had contact data but blank extraction_status — set to extraction_completed
- Cleared fake data: pisosvinilicos.com (domain for sale), filler GoDaddy emails, US phone numbers on CO companies
- 2 pisosvinilicos.com rows marked skipped (fake company)

### sync_to_hubspot.py v2 written
- ONE HubSpot company per domain (not per Supabase row)
- Multi-subcategory companies collapsed: all subcategories in HubSpot description
- Contact association fixed: PUT not POST (v4 API)
- Company update fixed: PATCH not POST (returns 405 on existing company)
- Non-ASCII emails stripped before contact creation (HubSpot rejects them with 400)
- URL encoding applied to domain query params (urllib.parse.quote)
- hs_patch() helper added
- --dry-run mode for preview

### append_discovery_batch.py updated
- load_hubspot_ids_by_domain() added
- New rows inherit hubspot_company_id from existing rows with same domain
- Prevents future duplicate HubSpot records when same company gets new subcategory

### Final sync results
- 513 Supabase rows synced (hubspot_sync_status = 'synced')
- 469 unique HubSpot company IDs
- 44 rows share HubSpot IDs (multi-subcategory companies correctly collapsed)
- ~440 contacts created
- 0 errors

### Lessons from this session
- HubSpot update = PATCH /crm/v3/objects/{type}/{id}, NOT POST
- HubSpot v4 association = PUT not POST
- HubSpot rejects non-ASCII email addresses with 400
- urllib.request fails silently on accented characters in URL params — always urllib.parse.quote()
- Dedup in sync script must use company domain as primary key, not Supabase row ID

---
*Logged by Claude — 2026-05-14*
