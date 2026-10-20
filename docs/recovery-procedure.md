# Recovery Procedure

Backup taken and verified 2026-10-20T20:26:06Z against project
`hdhovyrlnfojtkqbcegh` (PostgreSQL 17.6).

| | |
|---|---|
| Location | `backups/full-20261020T202606Z/` (gitignored, **0 files tracked by Git**) |
| Size | 9.1 MB |
| Schemas | 7: `public`, `platform`, `product_graph`, `cost_intelligence`, `telemetry`, `runtime_governance`, `model_intelligence` |
| DDL objects | **2,110** - 45 tables, 618 columns, 171 constraints, 136 indexes, 42 functions, 3 views, 93 policies, 5 triggers, 924 table grants, 42 function ACLs, 24 default privileges |
| Data | **3,560 rows** across 42 tables, every count matching the server exactly |
| Verification | 0 failures. Every NDJSON line re-parsed; asserted >=40 functions and all 7 schemas present |

**Not included, by design:** `auth.*` (users), `storage.*` (objects),
extensions, roles, database-level settings.

## Why this backup is the one that matters

The 42 captured function definitions are the part **git cannot reproduce**:

- Migration `021_cost_risk_engine_public_rpc_wrappers` exists in the production
  migration ledger with **no file in this repository**.
- Migrations `022` and `041` were repaired in place with `CREATE OR REPLACE`
  after their original apply, so the files on disk are not what is running.

Spot-verified: both `write_run_started_artifacts` overloads captured at 7,438
and 8,477 characters with complete bodies; zero functions have an empty
definition.

## Recovery scenarios

### A. One of migrations 047-050 fails mid-apply
**No recovery needed.** Each file is wrapped in a single `BEGIN`/`COMMIT`, so a
failed statement rolls the whole file back and production is bit-for-bit
unchanged. Diagnose, correct, re-apply. Do not retry a failed statement blind.

### B. 047 committed but caused a regression
Use the privilege pre-image, not this backup. 047 changes only grants, policies,
`search_path` and view options - no data, no DDL - so restoring those is exact
and surgical:

```
scripts/tests/capture_047_preimage.sql      # re-capture current state first
supabase/migrations/047_rollback.sql        # or the captured pre-image
```

Prefer a **narrow forward GRANT** for a single broken object over running the
whole rollback, which re-opens every hole 047 closes.

### C. 048/049/050 committed but caused a regression
These create objects rather than modifying data, so reversal is a targeted drop:

```sql
-- 050: drop the swim_* functions
DROP FUNCTION IF EXISTS public.swim_claim_job(text, int, text[]);
-- ... (see the file for the full list)

-- 049: the schema owns all its objects
DROP SCHEMA IF EXISTS swim_sourcing CASCADE;

-- 048: drop in reverse dependency order
DROP TRIGGER IF EXISTS trg_agent_outputs_append_only ON public.agent_outputs;
DROP TRIGGER IF EXISTS trg_agent_events_append_only ON public.agent_events;
DROP TRIGGER IF EXISTS trg_privileged_action_log_append_only ON public.privileged_action_log;
DROP FUNCTION IF EXISTS public.forbid_mutation();
DROP FUNCTION IF EXISTS public.get_tenant_credential(uuid, text);
DROP FUNCTION IF EXISTS public.list_tenant_credentials(uuid);
DROP FUNCTION IF EXISTS public.check_tenant_budget(uuid, numeric);
DROP FUNCTION IF EXISTS public.current_user_companies();
DROP TABLE IF EXISTS platform.tenant_provider_credentials;
DROP TABLE IF EXISTS public.privileged_action_log;
DROP TABLE IF EXISTS public.company_members;
```

No existing row is touched by any of these, so no data restore is involved.

### D. Catastrophic loss - restore from this backup
The backup is logical (JSON), not a `pg_dump` custom archive, so restoration is
a scripted replay rather than `pg_restore`. Order matters:

1. Create the 7 schemas (`ddl/schemas.json`).
2. Create tables from `ddl/tables.json` + `ddl/columns.json`, **without**
   constraints.
3. Load data from `data/*.ndjson`. Without FK constraints in place, load order
   does not matter.
4. Apply constraints (`ddl/constraints.json`), then indexes
   (`ddl/indexes.json`).
5. Create functions from `ddl/functions.json` - the `definition` field is a
   complete, executable `CREATE OR REPLACE FUNCTION` statement.
6. Create views (`ddl/views.json`), then triggers (`ddl/triggers.json`).
7. Enable RLS per `ddl/tables.json.rls_enabled`, then create policies from
   `ddl/policies.json`.
8. Apply grants (`ddl/table_grants.json`, `ddl/function_acls.json`) and default
   privileges (`ddl/default_privileges.json`).
9. Recreate `auth.users` separately - **not in this backup**. Users must
   re-register, and `company_members.user_id` rows must be re-pointed.

## Honest limitation: the restore has NOT been rehearsed

I have verified the backup is **complete and internally valid** - every row
count matches the server, every JSON line re-parses, every function has a body.
I have **not** restored it into a live database, because that needs a second
Postgres instance to restore into, and provisioning one is either a paid
Supabase branch or a new project.

So: completeness is proven; the replay script in scenario D is written but
unexercised. For scenarios A, B and C - which are the realistic ones for
migrations 047-050, since none of them modifies a row - recovery does not depend
on that replay at all.

If you want scenario D rehearsed, the cheapest route is a second free Supabase
project used as a restore target, then thrown away. Say so and I will write the
replay script and run it.

## Re-taking the backup

```bash
python scripts/backup_full.py --out backups
python scripts/backup_full.py --verify backups/<dir>
```

Needs `SUPABASE_DB_URL` in `.env.local` (session pooler, port 5432 - transaction
mode breaks the server-side cursors). The password is never printed and is
redacted from the manifest.

**Re-take before each migration apply.** A backup from before 047 does not
reflect the state 048 is about to modify.
