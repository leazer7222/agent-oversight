# Live Supabase Schema Inventory
**Last updated: 2026-05-19**
**Supabase Project**: `hdhovyrlnfojtkqbcegh`
**Verification method**: Direct SQL query via Supabase MCP.

---

## Current Schema State (2026-05-18)

Migrations 012–022 applied. 37 tables across 6 schemas.

### Schemas

| Schema | Purpose | Migrations |
|---|---|---|
| `public` | Original agent oversight tables + monitoring + estimation dashboard functions | 001–011, 020, 021, 022 |
| `platform` | Governance foundations (append-only enforcement, correction records) | 012 |
| `cost_intelligence` | Pricing, taxonomy, estimates, evaluations | 013, 017, 019 |
| `telemetry` | Raw event store (RFC-003 envelope) | 014 |
| `model_intelligence` | Recommendation artifacts | 016 |
| `runtime_governance` | Budget periods, reservations, settlements | 018 |

### Tables by schema

**`public`** (original operational tables)
- `agent_definitions`, `agents`, `agent_events`, `agent_outputs`, `agent_qa_results`
- `companies`, `projects`, `runs`, `policies`, `project_state`
- `provider_accounts`, `provider_quota_snapshots`, `provider_health_snapshots`
- `recommendation_events`, `recommendation_feedback`
- `contractor_rows`, `contractor_approval_queue`, `contractor_evidence`, `contractor_sync_log`
- `output_type_registry`, `event_type_registry`, `pipeline_config`, `audit_log`
- `runs` has Phase 1 columns: `task_type_id` (FK), `task_complexity_bucket`, `task_classifier_version`, `secondary_task_type_id`

**`platform`** (governance — append-only)
- `schema_registry` — governance metadata for all artifact schemas
- `correction_records` — immutable amendment records

**`cost_intelligence`** (append-only artifact tables)
- `pricing_table_versions` — per-model pricing (1 active: pricing-2026-05, 10 models)
- `task_taxonomy_versions` — taxonomy versions (1 active: taxonomy-v1)
- `task_types` — 8 task types with complexity_definition JSONB
- `estimate_artifacts` — pre-run cost estimates (ART-001)
- `evaluation_artifacts` — post-run actuals vs estimates (ART-002)

**`telemetry`** (append-only)
- `raw_events` — RFC-003 event envelope store

**`model_intelligence`** (append-only)
- `recommendation_artifacts` — model selection decisions (ART-007, passthrough mode in Phase 1)

**`runtime_governance`** (mixed: budget_periods mutable, settlements append-only)
- `budget_periods` — tenant budget allocations ($9999/month default)
- `budget_reservations` — per-run budget holds (ART-005)
- `settlement_records` — final cost accounting (ART-006, append-only)

### Public SECURITY DEFINER Functions

All cross-schema reads/writes go through these functions. PostgREST only exposes `public` — never call `.schema('x').from('y')` at runtime.

| Function | Migration | Purpose | Called by |
|---|---|---|---|
| `invariant_report()` | 020 | Phase 1 Class C monitoring — all invariant checks in one JSONB blob | `/api/monitoring/invariants` |
| `get_task_type_id(code)` | 021 | Resolves task type UUID from code string | `/api/ingest` |
| `write_run_started_artifacts(...)` | 021 | Writes recommendation + estimate + reservation + budget period atomically | `/api/ingest` |
| `write_run_completed_artifacts(...)` | 021 | Writes evaluation + settles reservation | `/api/ingest` |
| `ingest_telemetry_event(...)` | 021 | Writes RFC-003 event envelope to `telemetry.raw_events` | `/api/telemetry/ingest` |
| `get_estimation_run_detail(run_id)` | 022 | Returns all 4 estimation artifacts for a single run | `/api/estimation/runs/[id]` |
| `get_estimation_accuracy_overview()` | 022 | Headline accuracy metrics — MAPE, direction, band containment | `/api/estimation/overview` |
| `get_biggest_misses(limit)` | 022 | Top-N runs by absolute_error_usd (complete telemetry only) | `/api/estimation/biggest-misses` |
| `get_bucket_accuracy()` | 022 | All 24 buckets (8 task types × 3 complexities) with calibration status | `/api/estimation/buckets` |
| `get_calibration_readiness()` | 022 | Phase 2 schema-freeze gate + bucket eligibility summary | `/api/estimation/calibration` |

`platform.apply_append_only_rls(schema, table)` — applies no-UPDATE/no-DELETE RLS to artifact tables.

### Live Data (as of 2026-05-19)

| Entity | Count | Notes |
|---|---|---|
| Runs | 52+ | 51 historical + Phase 1 runs |
| Estimate artifacts | 2 | Both from code-review-agent run on 2026-05-19 |
| Evaluation artifacts | 1 | code-review run: actual $0.775, estimated $0.033, +2,248% error |
| Recommendation artifacts | 2 | Both passthrough mode |
| Budget reservations | 2 | One settled (overrun), one active |
| Settlement records | 1 | settlement_type: overrun, settlement_source: telemetry |
| Raw events | — | RFC-003 telemetry events from all agent runs |

**First live estimation miss (code-review-agent, 2026-05-19):**
- Run ID: `59b10b4f-8551-42c1-8dd2-f7624bba9c8d`
- Estimated p50: $0.033 | Estimated p95: $0.069 | Actual: $0.774942
- Error: +2,248% (underestimated)
- Root cause: `context_size_unknown` — feature snapshot has `prompt_chars=0` (ingest endpoint cannot observe actual LLM prompt). Input token estimate: 2,000. Actual: 217,364.
- Replayability: PASS — valid calibration training point when bucket reaches 30 observations.

---

## Pre-Phase 1 Notes (from 2026-05-12 audit — now historical)

Several issues documented in the original audit have since been addressed:
- Cost/token data was universally null → now tracked via evaluation_artifacts
- No task classification → runs.task_type_id added (migration 015, backfilled)
- Zombie runs → timeout_at column added (migration 007)

The original full audit text is preserved below for historical reference.

---

## Original Audit (2026-05-12, pre-Phase 1)

**Verified: 2026-05-12**

All 11 expected tables exist in the live database. Three materialized views exist for cost aggregation. Zero tables are missing. Several critical schema differences exist between live DB and repo artifacts:

1. **`001_initial_schema.sql` is entirely absent from the repo.** The foundational tables are defined nowhere in version control. This is the top remediation priority.
2. **`agent_events` exists live but is completely empty.** The ingest route never writes to it. Event observability is zero despite the table being present.
3. **`agent_events` live schema is significantly richer** than what was proposed in the Phase 1 Reconciliation Strategy — it has severity, depth, message, company_id, orchestrator linkage fields, and `run_id` is nullable. The proposed simpler schema must be reconciled to the live reality.
4. **`project_state` has a uuid `id` PK** in addition to `project_tag` (unique). My reconciliation strategy incorrectly proposed `project_tag TEXT PRIMARY KEY` — the live table has `id` as PK and `project_tag` as a unique index.
5. **`runs` does NOT have** `event` or `run_id` columns (Codex's concern about dual identifiers was based on an inferred/missing migration — live DB is clean).
6. **`runs` has a `created_at` column** not present in the reconciliation strategy contract.
7. **Only `lp_blueprint` output_type** exists in live `agent_outputs` rows — `ui_components` has never successfully been written (likely due to check constraint violation).
8. **Cost/token data is universally null** across all 51 run rows — the financial observability risk is confirmed as real.
9. **Three active cost aggregation views** exist: `agent_cost_summary`, `company_cost_summary`, `project_cost_summary` — all showing zero cost because runs have null cost data.
10. **Zombie runs confirmed**: rows with `status='started'` and `completed_at=null` from March 2026 are present.

---

## Verification Method

Scripts used:
- `inspect_schema.py`: fetched PostgREST OpenAPI spec, queried each table for existence and HTTP status, extracted column definitions from OpenAPI `definitions` section.
- `inspect_rows.py`: fetched actual rows from tables with data, confirmed column names from real API responses, checked distinct values for enum-like fields.

**What was NOT verified** (limitations of PostgREST introspection):
- Exact CHECK constraint values (e.g., allowed `status` values, `output_type` allowed list)
- Index definitions (names, uniqueness guarantees beyond FK)
- Sequence definitions
- Function/trigger definitions
- RLS policy names and expressions (only presence/absence via HTTP status behavior)
- Exact column defaults (inferred from OpenAPI nullable/required fields)

No secrets are included in this document. Credentials used for inspection were read-only service role key from local `.env.local` (not committed to repo).

---

## Live Tables and Views Found

### Tables (11 confirmed)

| Table | Has Rows | Row Count (approx) | Migration Coverage |
|---|---|---|---|
| `companies` | ✅ | 3 | ❌ None (001 missing) |
| `projects` | ✅ (empty) | 0 | ❌ None (001 missing) |
| `agents` | ✅ | Multiple | ❌ None (001 missing) |
| `agent_definitions` | ✅ | Multiple | ❌ None (001 missing) |
| `runs` | ✅ | ~51 | ❌ None (001 missing) |
| `agent_events` | ✅ (empty) | 0 | ❌ None |
| `agent_outputs` | ✅ | ~19 | ⚠️ Partial (002 present, constraint drift) |
| `project_state` | ✅ | 5 | ❌ None (001 missing) |
| `policies` | ✅ (empty) | 0 | ❌ None |
| `audit_log` | ✅ (empty) | 0 | ❌ None |
| `agent_qa_results` | ✅ (empty) | 0 | ❌ None |

### Views (3 confirmed)

| View | Migration Coverage |
|---|---|
| `agent_cost_summary` | ❌ None |
| `company_cost_summary` | ❌ None |
| `project_cost_summary` | ❌ None |

### Views Checked and NOT Found

- `agent_run_summaries` — not found
- `agent_cost_summaries` — not found
- `run_cost_view` — not found
- `cost_summary` — not found
- `telemetry_summary` — not found
- `run_metrics` — not found
- `agent_metrics` — not found

---

## Table-by-Table Schema Inventory

Legend: [R] = REQUIRED (not null / present in all rows), [N] = NULLABLE, [FK→] = foreign key target.

---

### `companies`

**Confirmed from**: live API rows + OpenAPI definition.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | uuid | [R] | Primary key |
| `name` | text | [R] | Company display name |
| `slug` | text | [R] | URL-safe identifier |
| `description` | text | [N] | Optional |
| `cost_limit_usd` | numeric | [N] | Company-level cost cap |
| `cost_limit_period` | text | [N] | Period for cost cap |
| `created_at` | timestamptz | [R] | |

**Live data observations**:
- 3 companies: ReformAI (`1021c018`), AfterGlow (`e3a841ab`), Personal (`87fb6e0d`)
- All `cost_limit_usd` = null (cost caps not configured)
- `slug` field: not in original reconciliation strategy contract

**Migration coverage**: None (`001_initial_schema.sql` absent).

---

### `projects`

**Confirmed from**: OpenAPI definition (table exists, empty).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | uuid | [R] | Primary key |
| `company_id` | uuid | [R] | [FK→ companies.id] |
| `name` | text | [R] | |
| `description` | text | [N] | |
| `status` | text | [R] | Allowed values: unknown |
| `orchestrator_id` | uuid | [N] | [FK→ agents.id] |
| `created_at` | timestamptz | [R] | |

**Live data observations**: Table exists, zero rows.

**Migration coverage**: None.

---

### `agent_definitions`

**Confirmed from**: live API rows + OpenAPI definition.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | uuid | [R] | Primary key |
| `name` | text | [R] | Machine identifier |
| `display_name` | text | [R] | Human-readable name |
| `description` | text | [N] | |
| `capability_tags` | text[] | [R] | Array of tags |
| `instance_type` | text | [R] | e.g., `stateless` |
| `default_model` | text | [N] | Default LLM model |
| `input_schema` | jsonb | [R] | Input contract |
| `output_schema` | jsonb | [R] | Output contract |
| `config_schema` | jsonb | [R] | Config contract |
| `version` | text | [R] | Semantic version string |
| `source_path` | text | [N] | Agent source file path |
| `created_at` | timestamptz | [R] | |

**Live data observations**:
- context-agent (`aacea273`) and marketing-agent (`8482d8c3`) registered.
- `default_model` null for both (model not locked at definition level).

**Migration coverage**: None (`001_initial_schema.sql` absent).

---

### `agents`

**Confirmed from**: live API rows + OpenAPI definition.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | uuid | [R] | Primary key |
| `name` | text | [R] | Instance identifier |
| `company_id` | uuid | [R] | [FK→ companies.id] |
| `project_id` | uuid | [N] | [FK→ projects.id] |
| `definition_id` | uuid | [N] | [FK→ agent_definitions.id] |
| `agent_type` | text | [R] | `worker` or `orchestrator` |
| `parent_agent_id` | uuid | [N] | [FK→ agents.id] self-ref |
| `depth` | int | [R] | Hierarchy depth |
| `platform` | text | [N] | Execution platform |
| `model` | text | [N] | Override model for this instance |
| `trigger_type` | text | [N] | `manual`, `scheduled`, etc. |
| `trigger_config` | jsonb | [R] | Default: `{}` |
| `status` | text | [R] | `active`, `paused`, `retired` |
| `cost_limit_usd` | numeric | [N] | Agent-level cost cap |
| `cost_limit_period` | text | [N] | |
| `max_errors_per_hour` | int | [R] | Default: `10` |
| `priority` | int | [R] | Default: `5` |
| `tags` | text[] | [R] | Default: `[]` |
| `can_trigger` | text[] | [R] | Agent IDs this can trigger |
| `can_be_triggered_by` | text[] | [R] | Agent IDs that can trigger this |
| `config_overrides` | jsonb | [R] | Instance config overrides |
| `registered_at` | timestamptz | [R] | |
| `last_run_at` | timestamptz | [N] | Updated on run completion |
| `paused_at` | timestamptz | [N] | When paused |
| `paused_reason` | text | [N] | Reason for pause |
| `metadata` | jsonb | [R] | Default: `{}` |

**Drift from `src/lib/adapters/types.ts` `Agent` interface** (CRITICAL):
| TypeScript field | Live DB column | Status |
|---|---|---|
| `description` | not in `agents` (in `agent_definitions`) | MISMATCH |
| `hierarchy` | `agent_type` | MISMATCH (name) |
| `company` | `company_id` (UUID not enum) | MISMATCH (type + name) |
| `project` | `project_id` (UUID not string) | MISMATCH (type + name) |
| `created_at` | not in `agents` | MISMATCH (absent) |

**Migration coverage**: None.

---

### `runs`

**Confirmed from**: live API rows + OpenAPI definition. 51 rows in live DB.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | uuid | [R] | Primary key. Also the canonical run_id. |
| `agent_id` | uuid | [R] | [FK→ agents.id] |
| `status` | text | [R] | `started`, `completed`, `failed` |
| `started_at` | timestamptz | [R] | |
| `completed_at` | timestamptz | [N] | Null while in progress |
| `tokens_in` | int | [N] | Null in all observed rows |
| `tokens_out` | int | [N] | Null in all observed rows |
| `cost_usd` | numeric | [N] | Null in all observed rows |
| `error` | text | [N] | Terminal error summary |
| `metadata` | jsonb | [N] | |
| `created_at` | timestamptz | [R] | Auto-set at insert |

**NOT present in live `runs`** (contradicts Codex's inferred migration):
- `run_id` column — does not exist. `id` is the single canonical identifier.
- `event` column — does not exist.

**NOT present in live `runs`** (proposed in reconciliation strategy, need to add):
- `timeout_at` — not present
- `cost_reported` — not present
- `parent_run_id` — not present

**Live data observations**:
- 51 total runs. Status distribution: started (zombie), completed, failed.
- ALL `tokens_in`, `tokens_out`, `cost_usd` values are null — zero cost data has ever been written to the DB.
- Zombie runs confirmed: rows from 2026-03-21 with `status='started'` and `completed_at=null`.
- `created_at` exists in live DB but was not in the reconciliation strategy's canonical contract — must be added.

**Migration coverage**: None (`001_initial_schema.sql` absent). `002_agent_outputs.sql` references `runs(id)` FK but `runs` itself has no migration.

---

### `agent_events`

**Confirmed from**: live table exists, confirmed empty (zero rows). OpenAPI definition provides full column schema.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | uuid | [R] | Primary key |
| `agent_id` | uuid | [R] | [FK→ agents.id] |
| `company_id` | uuid | [R] | [FK→ companies.id] |
| `project_id` | uuid | [N] | [FK→ projects.id] |
| `run_id` | uuid | **[N]** | FK → runs.id (NULLABLE — events can exist without a run) |
| `event_type` | text | [R] | Event classification |
| `occurred_at` | timestamptz | [R] | Event timestamp |
| `message` | text | [R] | Human-readable description |
| `payload` | jsonb | [R] | Structured event data |
| `severity` | text | [R] | Event severity level |
| `depth` | int | [R] | Agent hierarchy depth |
| `duration_ms` | int | [N] | Duration if measurable |
| `cost_usd` | numeric | [N] | Cost attributed to this event |
| `tokens_in` | int | [N] | Tokens consumed |
| `tokens_out` | int | [N] | Tokens produced |
| `orchestrator_run_id` | text | [N] | Orchestrator-level run correlation |
| `platform_run_id` | text | [N] | Platform (external) run correlation |
| `triggered_by_agent_id` | uuid | [N] | [FK→ agents.id] Actor agent |

**Critical discrepancies from Phase 1 Reconciliation Strategy**:

| My proposed field | Live DB field | Resolution |
|---|---|---|
| `sequence` | NOT present | Remove from reconciliation — live schema doesn't use it |
| `event_time` | `occurred_at` | Use `occurred_at` |
| (simple schema) | `company_id`, `project_id`, `severity`, `depth`, `message`, `orchestrator_run_id`, `platform_run_id`, `triggered_by_agent_id` | Live schema is richer; retain all live fields |
| `run_id` required | `run_id` nullable | Events don't require a run — system-level events may exist without runs |

**Ingest route contract gap**: The Python SDK emits events with `event`, `run_id`, `agent_id` etc. to `/api/ingest`. The ingest route validates these but writes ONLY to `runs` — never to `agent_events`. To write to `agent_events`, the ingest route needs to map SDK event fields to the live `agent_events` column schema. This mapping is non-trivial:
- SDK's `event` → `agent_events.event_type`
- SDK's `metadata` → `agent_events.payload`
- `severity` has no equivalent in current SDK — needs default (`info`)
- `message` has no equivalent in current SDK — needs default or derived value
- `depth` has no equivalent in current SDK — needs to be derived from agent record

**Migration coverage**: None. Table exists live with no migration file.

---

### `agent_outputs`

**Confirmed from**: live API rows + OpenAPI definition. 19 rows in live DB.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | uuid | [R] | Primary key |
| `agent_id` | uuid | [R] | [FK→ agents.id] |
| `run_id` | uuid | [R] | [FK→ runs.id] |
| `company_id` | uuid | [R] | [FK→ companies.id] |
| `output_type` | text | [R] | CHECK constraint (see below) |
| `content` | jsonb | [R] | Default: `{}` |
| `gdrive_file_id` | text | [N] | Google Drive file ID |
| `gdrive_url` | text | [N] | Google Drive URL |
| `version` | int | [R] | Default: `1` |
| `created_at` | timestamptz | [R] | |

**CHECK constraint on `output_type`** (from migration 002):
Allowed: `marketing_brief`, `lp_blueprint`, `strategy_summary`, `context_snapshot`, `other`
NOT in constraint: `ui_components` (but orchestrator tries to write it)

**Distinct `output_type` values in live data**: `['lp_blueprint']` only.
This means `ui_components` writes either never happened or failed silently. The 19 rows are all `lp_blueprint`.

**This table IS covered by migration 002** — but the constraint is stale relative to runtime behavior.

**Not present in live** (proposed in reconciliation strategy):
- `event_id` FK → agent_events.id (not present; acceptable for MVP)

**Migration coverage**: `002_agent_outputs.sql` covers this table. CHECK constraint needs expansion.

---

### `project_state`

**Confirmed from**: live API rows + OpenAPI definition. 5 rows in live DB.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | uuid | [R] | Primary key (uuid, NOT project_tag) |
| `project_tag` | text | [R] | Unique constraint (upsert conflict key) |
| `current_state` | text | [R] | Default: `''` |
| `todo` | text | [R] | Default: `''` |
| `lessons` | text | [R] | Default: `''` |
| `updated_at` | timestamptz | [R] | |

**Critical discrepancy from reconciliation strategy**: Phase 1 Reconciliation Strategy proposed `project_tag TEXT PRIMARY KEY`. Live DB has `id UUID PRIMARY KEY` with `project_tag` as a separate unique-constrained column. This is the correct design (consistent with all other tables using uuid PKs). The reconciliation strategy must be updated.

**Live project_tag values**: `notion-personal-os`, `resume-career`, `global`, `master-agentic-flow`, `reformai`. These match the Zod enum in the API route. ✓

**API compatibility**: The API's `.upsert({project_tag, ...}, {onConflict: 'project_tag'})` is correct — it upserts on the unique `project_tag` column while letting `id` auto-generate. ✓

**Migration coverage**: None (`001_initial_schema.sql` absent).

---

### `policies`

**Confirmed from**: OpenAPI definition (table exists, empty).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | uuid | [R] | Primary key |
| `name` | text | [R] | Policy name |
| `enabled` | boolean | [R] | |
| `global_cost_cap_usd` | numeric | [N] | |
| `global_cost_cap_period` | text | [N] | |
| `auto_pause_on_cap` | boolean | [R] | |
| `auto_pause_on_error_spike` | boolean | [R] | |
| `error_spike_threshold` | int | [R] | |
| `auto_resume` | boolean | [R] | |
| `alert_email` | text | [N] | |
| `alert_slack_webhook` | text | [N] | |
| `alert_on_latency_ms` | int | [N] | |
| `updated_at` | timestamptz | [R] | |

**Observation**: Policies are not scoped to a company or agent in this schema — they appear to be global platform policies. No FK to companies or agents.

**Migration coverage**: None.

---

### `audit_log`

**Confirmed from**: OpenAPI definition (table exists, empty).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | uuid | [R] | Primary key |
| `actor` | text | [R] | Who performed the action |
| `action` | text | [R] | What action was taken |
| `agent_id` | uuid | [N] | [FK→ agents.id] |
| `detail` | jsonb | [R] | Structured action details |
| `occurred_at` | timestamptz | [R] | |
| `reason` | text | [N] | |

**Migration coverage**: None.

---

### `agent_qa_results`

**Confirmed from**: OpenAPI definition (table exists, empty).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | uuid | [R] | Primary key |
| `agent_id` | uuid | [R] | [FK→ agents.id] |
| `run_id` | uuid | [N] | Optional run linkage |
| `score` | numeric | [N] | Quality score |
| `criteria_scores` | jsonb | [R] | Per-criterion breakdown |
| `constraints_passed` | boolean | [R] | Whether all constraints passed |
| `constraints_detail` | jsonb | [R] | Per-constraint results |
| `flagged_for_review` | boolean | [R] | |
| `evaluated_at` | timestamptz | [R] | |
| `notes` | text | [N] | |

**Migration coverage**: None.

---

## Views — Schema Inventory

### `agent_cost_summary`

| Column | Type | Source |
|---|---|---|
| `agent_id` | uuid | agents.id |
| `agent_name` | text | agents.name |
| `company_id` | uuid | agents.company_id |
| `project_id` | uuid | agents.project_id |
| `total_runs` | int | COUNT(runs) |
| `total_cost_usd` | numeric | SUM(runs.cost_usd) |
| `total_tokens_in` | int | SUM(runs.tokens_in) |
| `total_tokens_out` | int | SUM(runs.tokens_out) |
| `last_event_at` | timestamptz | MAX(agent_events.occurred_at?) |

**Note**: All `total_cost_usd` values are 0 because all `runs.cost_usd` values are null.

### `company_cost_summary`

| Column | Type |
|---|---|
| `company_id` | uuid |
| `company_name` | text |
| `cost_limit_usd` | numeric |
| `cost_limit_period` | text |
| `active_agents` | int |
| `total_runs` | int |
| `total_cost_usd` | numeric |
| `total_tokens_in` | int |
| `total_tokens_out` | int |
| `last_event_at` | timestamptz |

### `project_cost_summary`

Same structure as `company_cost_summary` but scoped to projects. Empty (no project rows).

**Migration coverage for all views**: None.

---

## Live Schema vs Existing Migrations

| Table | Migration File | Status |
|---|---|---|
| companies | None | ❌ MISSING |
| projects | None | ❌ MISSING |
| agents | None | ❌ MISSING |
| agent_definitions | None | ❌ MISSING |
| runs | None | ❌ MISSING |
| agent_events | None | ❌ MISSING |
| agent_outputs | `002_agent_outputs.sql` | ⚠️ PARTIAL — CHECK constraint stale |
| project_state | None | ❌ MISSING |
| policies | None | ❌ MISSING |
| audit_log | None | ❌ MISSING |
| agent_qa_results | None | ❌ MISSING |
| agent_cost_summary (view) | None | ❌ MISSING |
| company_cost_summary (view) | None | ❌ MISSING |
| project_cost_summary (view) | None | ❌ MISSING |

**Summary**: Only 1 of 14 schema objects has any migration coverage, and that one has a stale constraint.

---

## Live Schema vs API Expectations

### `/api/ingest` route

| API assumption | Live schema | Status |
|---|---|---|
| Writes to `runs` with `id = run_id` | `runs.id` exists | ✅ Match |
| `runs.status` field | exists | ✅ Match |
| `runs.started_at` field | exists | ✅ Match |
| `runs.completed_at` field | exists | ✅ Match |
| `runs.error` field | exists | ✅ Match |
| `runs.tokens_in/out` fields | exist | ✅ Match |
| `runs.cost_usd` field | exists | ✅ Match |
| `runs.metadata` field | exists | ✅ Match |
| Writes to `agent_events` | ❌ never writes | ❌ MISSING write path |
| Agent status check via `agents.status` | exists | ✅ Match |

### `/api/project-state` route

| API assumption | Live schema | Status |
|---|---|---|
| `project_state.project_tag` | exists | ✅ Match |
| `project_state.current_state` | exists | ✅ Match |
| `project_state.todo` | exists | ✅ Match |
| `project_state.lessons` | exists | ✅ Match |
| `project_state.updated_at` | exists | ✅ Match |
| Upsert on `project_tag` conflict | project_tag is unique | ✅ Match |
| `id` column (auto-generated) | exists | ✅ Match (API doesn't touch it) |

### `src/lib/adapters/types.ts` `Agent` interface

| TypeScript field | Live DB column | Status |
|---|---|---|
| `id` | `agents.id` | ✅ Match |
| `name` | `agents.name` | ✅ Match |
| `description` | NOT in `agents` | ❌ MISMATCH (in agent_definitions) |
| `hierarchy` | `agents.agent_type` | ❌ MISMATCH (name) |
| `company` | `agents.company_id` (UUID) | ❌ MISMATCH (type + name) |
| `project` | `agents.project_id` (UUID) | ❌ MISMATCH (type + name) |
| `status` | `agents.status` | ✅ Match |
| `created_at` | NOT in `agents` | ❌ MISMATCH (absent from live) |

---

## Live Schema vs Runtime Expectations

### Python SDK (`oversight.py`)

| SDK behavior | Live schema impact | Status |
|---|---|---|
| Emits `run_started` → `/api/ingest` | Creates `runs` row | ✅ Works |
| Emits `run_completed` → `/api/ingest` | Updates `runs` row | ✅ Works |
| Emits `run_failed` → `/api/ingest` | Updates `runs` row | ✅ Works |
| Accumulates tokens/cost in memory | Written to `runs` on completion | ⚠️ Risk: null if crash before emit |
| NO writes to `agent_events` | `agent_events` stays empty | ❌ Observability gap |

### Orchestrator (`orchestrator.py`)

| Runtime behavior | Live schema impact | Status |
|---|---|---|
| Writes `agent_outputs` with `output_type='ui_components'` | Violates CHECK constraint | ❌ FAILS (constraint enforces specific values only) |
| `run_id` FK to `runs.id` | Valid if ingest succeeded first | ⚠️ Race condition risk |
| Writes `lp_blueprint` outputs | Works — exists in constraint | ✅ Works (19 rows observed) |

---

## Critical Drift

### 1. `001_initial_schema.sql` Entirely Absent — CRITICAL
All 10 foundational tables have no migration coverage. The platform cannot be reproduced from repo migrations. Remediation: create `001_initial_schema.sql` from live DB schema.

### 2. `agent_events` Has Zero Writes — CRITICAL
Table exists, is fully structured, but has zero rows. Ingest route never writes to it. All event-level observability is absent. The `agent_cost_summary` view's `last_event_at` column will always be null.

### 3. `agent_events` Live Schema Differs from Reconciliation Proposal — HIGH
The reconciliation strategy proposed `sequence`, `event_time`, and a simpler schema. Live DB has `occurred_at` (not `event_time`), no `sequence`, plus additional fields: `severity`, `depth`, `message`, `company_id`, `orchestrator_run_id`, `platform_run_id`, `triggered_by_agent_id`. The migration must match live, not the proposal.

### 4. `project_state` Has `id` UUID PK — MEDIUM
Reconciliation strategy incorrectly proposed `project_tag TEXT PRIMARY KEY`. Live has `id UUID PK` + `project_tag UNIQUE`. Both the API and the migration must reflect this correctly.

### 5. `agent_outputs.output_type` CHECK Constraint — MEDIUM
Allowed values: `marketing_brief`, `lp_blueprint`, `strategy_summary`, `context_snapshot`, `other`. `ui_components` not allowed. Orchestrator writes `ui_components` which fails at DB level. 19 live rows are all `lp_blueprint`.

### 6. `runs.created_at` Not in Reconciliation Contract — LOW
Live `runs` has `created_at TIMESTAMPTZ` as required. This was absent from the proposed contract. Must be included in `001_initial_schema.sql`.

### 7. `runs` Cost Data Universally Null — MEDIUM (operational)
51 runs in live DB. All have `cost_usd = null`, `tokens_in = null`, `tokens_out = null`. Cost observability views (agent_cost_summary etc.) show zero cost. Financial metrics are completely unreliable.

### 8. Zombie Runs Present — LOW (operational)
Multiple runs with `status='started'` and `completed_at=null` from 2026-03-21. No cleanup mechanism. These inflate "in-progress" counts.

### 9. `agents` has company `87fb6e0d` (Personal) not in companies seed rows — LOW
The `companies` table has 3 rows (ReformAI, AfterGlow, Personal). The `001_initial_schema.sql` seed must include all 3. The Codex concern about invalid UUID characters (`g`, `h`) appears not to have affected the live data — all UUIDs in live DB are valid. The invalid seed issue was in an uncommitted migration file.

---

## Migration Backfill Requirements

All required migrations to achieve a reproducible repo state:

### `001_initial_schema.sql` (CREATE — highest priority)
Must include:
- `companies` (id, name, slug, description, cost_limit_usd, cost_limit_period, created_at)
- `agent_definitions` (all 13 columns confirmed above)
- `agents` (all 25 columns confirmed above + all FKs)
- `projects` (id, company_id FK, name, description, status, orchestrator_id FK, created_at)
- `runs` (id, agent_id FK, status, started_at, completed_at, tokens_in, tokens_out, cost_usd, error, metadata, created_at)
- `project_state` (id, project_tag UNIQUE, current_state, todo, lessons, updated_at)
- Seed data: 3 companies (ReformAI, AfterGlow, Personal)
- Initial `project_state` rows: 5 tags
- RLS policies for each table

### `003_add_agent_events.sql` (CREATE)
Must match live schema exactly (17 columns listed above).
Add RLS: append-only (INSERT allowed, UPDATE/DELETE blocked for all roles).

### `004_add_governance_tables.sql` (CREATE)
- `policies` (12 columns)
- `audit_log` (6 columns + FK)
- `agent_qa_results` (10 columns + FK)

### `005_add_cost_views.sql` (CREATE)
- `agent_cost_summary` view
- `company_cost_summary` view
- `project_cost_summary` view

### `006_fix_agent_outputs_constraint.sql` (ALTER)
- Expand `output_type` CHECK to include `ui_components`, `code_artifact`, `research_report`, `eval_result`

### `007_runs_reconciliation.sql` (ALTER — proposed additions)
- `ADD COLUMN timeout_at TIMESTAMPTZ` for zombie run detection
- `ADD COLUMN cost_reported BOOLEAN NOT NULL DEFAULT false` for cost observability sentinel
- `ADD COLUMN parent_run_id UUID REFERENCES runs(id)` for retry chain linkage

---

## Open Questions

1. **`agent_events` CHECK constraint on `event_type`**: What values are currently allowed? The OpenAPI shows `text` (no constraint listed). What is the intended taxonomy? The reconciliation strategy proposed an explicit check constraint — should one be added?

2. **`agent_events.severity` allowed values**: What values does `severity` accept? (`info`, `warn`, `error`? or other?)

3. **`runs` CHECK on `status`**: Is there a check constraint on `status` in the live DB, or just application-level validation? Live data shows only `started/completed/failed`.

4. **`project_state` CHECK on `project_tag`**: Is there a check constraint on allowed project tags in the live DB, or only in the API Zod schema?

5. **`agents.agent_type` CHECK**: What values does `agent_type` allow? Observed: `worker`, `orchestrator`.

6. **Views SQL definition**: Cannot retrieve view SQL via PostgREST. What is the exact SQL for `agent_cost_summary`, `company_cost_summary`, `project_cost_summary`? Needed to write accurate migration files. Can only be retrieved via Supabase SQL editor or management API.

7. **RLS policies**: Which tables have RLS enabled? What are the exact policy expressions? Cannot verify via PostgREST (only presence/absence inferred from HTTP status codes). Needed for accurate migration coverage.

8. **`project_state` seed constraint**: Is there a CHECK constraint on `project_tag` in live DB, or only unique constraint? How should new project tags be added?

9. **`policies` scoping**: Policies table has no `company_id` FK — are policies global across all companies, or is scoping expected to be added later?

10. **Sequence for `agent_events` ordering**: Live schema has no `sequence` column. How should events within a run be ordered? By `occurred_at` only? Is monotonic ordering guaranteed if events are written at sub-millisecond intervals?

---

## Recommended Next Step

**Immediate priority: write `001_initial_schema.sql`** using the confirmed column definitions in this document.

Approach:
1. Use the table schemas listed in this document (confirmed from live data).
2. For any column where type precision is uncertain (check constraints, exact nullability), mark with a `-- TODO: confirm constraint` comment.
3. Apply migration to a local Supabase instance first to validate syntax.
4. The migration file should reproduce the live schema exactly — it is a documentation migration, not a schema change.

**Do NOT modify live DB** during migration creation. The goal of this phase is to document what exists, not to change it.

**Second priority**: Resolve the 10 open questions above (especially view SQL and RLS policy expressions) via the Supabase dashboard SQL editor before finalizing the migration files.
