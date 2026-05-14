# Phase 0A — Legacy XLSX Migration

Migrates all historical contractor records from the REFORM AI workbooks into
Supabase `contractor_rows`. This must complete and validate before any
automated orchestrator runs are enabled.

---

## What this does

1. Inventories every sheet in both source workbooks
2. Reads `Contractors master`, `Contractors enriched`, `Request Failed`, and
   `Catalog Classification` **directly** — no rebuild scripts used
3. Handles the legacy `Contractors` sheet if present
4. Merges with canonical priority: **enriched > master > request_failed**
5. Enriches catalog fields from `Catalog Classification`
6. Preserves each company-subcategory pair as a separate row
7. Generates a full reconciliation report in `migration/reports/`
8. Upserts all records to Supabase with `ON CONFLICT (dedupe_key) DO UPDATE`
9. Is **idempotent** — safe to run multiple times

---

## Prerequisites

### 1. Apply the SQL migration

Run migration `010_contractor_rows.sql` against the live Supabase project
(`hdhovyrlnfojtkqbcegh`) **before** running the Python script:

```
supabase db push
```

Or apply it manually via the Supabase dashboard SQL editor.

This creates: `contractor_rows`, `contractor_evidence`,
`contractor_approval_queue`, `contractor_sync_log`, and `pipeline_config`
(seeded with all four markets).

### 2. Set environment variables

Add to `.env.local` in the project root:

```
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
```

The service role key is required. The anon key will fail on INSERT due to RLS.
Get it from: Supabase Dashboard → Project Settings → API → service_role.

### 3. Install Python dependencies

From the project root:

```
pip install openpyxl python-dotenv supabase
```

These should already be present if you have run other agents in this repo.

---

## Run order

### Step 1 — Dry run (validate counts, no writes)

```
cd C:\Users\cjlea\AI-Projects\agent-oversight
python migration\migrate_legacy_xlsx.py --dry-run
```

Read the reconciliation summary printed to the console. Verify:
- Source row counts match what you know is in the workbooks (~700 in master)
- No unexpected blank company names
- No unexpected enriched/failed conflicts
- Delta is >= 0

### Step 2 — Live run (writes to Supabase)

```
python migration\migrate_legacy_xlsx.py
```

### Step 3 — Validate the report

The report is written to `migration/reports/migration_report_<timestamp>.json`.

Check:
- `validation.status` is `PASS`
- `import_result.errors` is empty
- `preservation.pending_extraction_rows` matches your expectation
- `merge_results.catalog_rows_enriched` is non-zero

### Step 4 — Release the migration lock

Once the report validates, release the lock so the orchestrator can run:

```sql
UPDATE pipeline_config
SET migration_locked = false,
    migration_validated_at = now(),
    migration_row_count = <upserted_count_from_report>
WHERE market_id = 'co-renovation';
```

Run this in the Supabase SQL editor.

---

## Source file paths

The script reads from:

```
C:\Users\cjlea\AI-Projects\ReformAI_Agents\Shared Docs\REFORM AI B2B PIPELINE (official).xlsx
C:\Users\cjlea\AI-Projects\ReformAI_Agents\Shared Docs\Master_ReformAI_Contractor_Catalogs.xlsx
```

These files are **read-only** — the migration script never writes to them.

---

## Dedupe key

```
dedupe_key = sha256( norm(company) | norm(subcategory) | market_id )
```

Where `norm()` = lowercase + strip accents + collapse whitespace.

- One company with two subcategories → two rows, two different `dedupe_key`s
- Same company + subcategory in master AND enriched → one row, enriched wins

---

## Merge rules

| Sheet | Role |
|---|---|
| Contractors master | Baseline — every tracked company lives here |
| Contractors enriched | Overrides extraction fields when same dedupe_key found |
| Request Failed | Fills extraction fields only if master row has no status yet |
| Catalog Classification | Enriches catalog fields on matching (company, subcategory) |
| Contractors (legacy) | Added if dedupe_key not already in canonical set |

---

## Reconciliation report fields

| Field | Meaning |
|---|---|
| `source_row_counts` | Raw row count per source sheet |
| `merge_results.unique_records_after_merge` | Final distinct records going to Supabase |
| `merge_results.master_internal_collisions` | Same dedupe_key appeared twice in master |
| `merge_results.enriched_vs_failed_conflicts` | Row is request_failed in master but extraction_completed in enriched — enriched wins |
| `preservation.pending_extraction_rows` | Records with no extraction yet — preserved intact |
| `data_quality.blank_subcategory_count` | Rows missing subcategory — dedupe key uses company+market only |
| `ambiguous_dedup_cases` | All collisions and conflicts for manual review |
| `validation.delta` | Supabase upserted minus master rows. Should be >= 0 |
| `validation.status` | PASS or FAIL |

---

## After migration

- `contractor_rows` is the canonical source of truth for all contractor data
- The XLSX workbooks become **export artifacts only** — never read as input
- Future orchestrator runs deduplicate against Supabase, not the workbooks
- Mexico / Portugal / Spain pipelines start fresh (no migration needed)
- HubSpot sync is a future phase — `hubspot_*` columns are reserved but empty
