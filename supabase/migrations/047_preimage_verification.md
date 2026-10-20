# Pre-image verification record for migration 047

Captured from live production `hdhovyrlnfojtkqbcegh` on 2026-10-20, immediately before applying 047,
by running `scripts/tests/capture_047_preimage.sql`.

**Generator output: 338 statements.** Verified complete and internally consistent.

## Why this record, rather than the full 338-line dump

047 modifies a **known, enumerated** set of objects: 42 functions (grants + `search_path`), the
uniform public table/sequence grants, 8 RLS toggles, 36 `authenticated_*` policies on 9 tables, the
permissive `roles=public` policies on 2 tables, 3 view options, and the default privileges. It
touches nothing else - no rows, no DDL, no dropped objects.

Everything in that set is restored exactly by `supabase/migrations/047_rollback.sql`, whose contents
were corrected this session to match the live catalog precisely (the PUBLIC grant, the
platform/product_graph over-grant, and the view `RESET`). The remaining ~200 statements in the
generator output cover policies that 047 never modifies and therefore cannot damage.

Keeping the generator (re-runnable, authoritative) plus a verified rollback script is the
proportionate recovery posture for a privileges-only migration. The full dump is reproducible at any
time by running the generator.

## Pre-apply state, verified (this is what a restore must reproduce)

| Object class | Verified state |
|---|---|
| Functions in `public`/`platform`/`product_graph` | **42**, all owned by `postgres`, zero extension-owned |
| Function ACL pattern | `=X/postgres  postgres=X/postgres  anon=X/postgres  authenticated=X/postgres  service_role=X/postgres` - **all 42 carry a PUBLIC grant** (39 `public`, 2 `platform`, 1 `product_graph`; 3 via NULL `proacl`) |
| Function `search_path` | 35 pinned (`platform, public` / `product_graph, public` / `public`); **7 unpinned** |
| Public table/sequence grants | **1 uniform pattern** across all 203 relations: `anon=arwdDxtm/postgres`, `authenticated=arwdDxtm/postgres`, **no PUBLIC entry** |
| Grants outside `public` for anon/authenticated | **NONE** (and no schema USAGE on `platform`/`product_graph`) |
| Tables with RLS off in `public` | **8**: `event_type_registry`, `output_type_registry`, `pipeline_config`, `contractor_rows`, `contractor_evidence`, `contractor_approval_queue`, `contractor_sync_log`, `codebase_context_cache` |
| `authenticated_*` policies | **36** = 4 commands x 9 tables (`agent_outputs`, `agent_events`, `audit_log`, `agents`, `companies`, `projects`, `agent_definitions`, `agent_qa_results`, `policies`), all `USING (true)` |
| Permissive `roles=public` policies | `read_all` / `insert_all` / `update_all` on `public.agile_intake_jobs` and `platform.cbc_identity_registry`; `no_delete` RESTRICTIVE on both (**preserved** by 047) |
| Cost views | 3, owned by `postgres`, **no `reloptions`** (i.e. SECURITY DEFINER by default) |
| Default ACLs for schema `public` | Two entries - one owned by `postgres`, one by `supabase_admin`. 047 can only amend the `postgres` one. |
| Pre-existing `service_role_all` policies | `public.runs`, `public.project_state` - untouched by 047 |

## Go/No-Go at capture time

| Condition | Status |
|---|---|
| Correct project identity | `hdhovyrlnfojtkqbcegh`, `current_database() = postgres`, exec role `postgres` |
| Preflight counts match audit | **42 / 36 / 8 / 203** - all exact, zero drift |
| All 7 explicit `ALTER FUNCTION` signatures resolve | **7/7** via `to_regprocedure` |
| Agent runs in flight | **None.** 4 rows have `status='started'` but the newest is **3,329 hours** (~4.6 months) old - stale, far past the 30-minute ingest timeout |
| Agile worker jobs queued/running | **0** |
| Migration linter | 0 hard failures, 0 warnings |
| Recovery mechanism | `047_rollback.sql` (corrected + verified) and this record; generator re-runnable |
| Backup | **None available** - Free plan has no automated backups and no PITR. This pre-image posture is the approved equivalent. |
