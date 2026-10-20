# P0-0 Production Deployment Runbook

Migration: `supabase/migrations/047_p0_0_database_hardening.sql`
Target: Supabase project `hdhovyrlnfojtkqbcegh` (`leazer7222's Project`, us-west-2, PG 17.6)
Branch: `claude/agent-oversight-implementation-b25688`
Status: **PREPARED, NOT AUTHORIZED, NOT APPLIED.**

---

## A. Production Readiness Assessment

**Ready with conditions.** The conditions are in section E and all of them are satisfiable in
minutes; none requires a purchase.

Two findings from this preparation pass changed the migration, and the first one is the reason this
pass was worth doing:

1. **A critical defect in 047 was found and fixed.** The live ACL on every one of the 42 functions is
   `=X/postgres  postgres=X/postgres  anon=X/postgres  authenticated=X/postgres  service_role=X/postgres`.
   That leading `=X/postgres` is a grant of EXECUTE to **PUBLIC**, and PUBLIC includes `anon`. The
   committed migration revoked only the explicit `anon` and `authenticated` entries, so **anon would
   have retained EXECUTE through PUBLIC and the migration would have closed nothing** while reporting
   success. All 42 functions carry a PUBLIC grant (39 in `public`, 2 in `platform`, 1 in
   `product_graph`; 3 of those via a NULL `proacl`, whose built-in default for functions is also
   EXECUTE to PUBLIC). Section A now revokes `FROM PUBLIC, anon, authenticated` and re-grants
   `service_role` explicitly, and assertion **A1b** now fails loudly on any surviving PUBLIC grant.
   Tables were checked and are not affected: their `relacl` carries no PUBLIC entry.
2. **Three rollback defects were found and fixed** (section D).

**The project has no platform backups of any kind.** This does not block 047 specifically, for the
reason set out in section C, but it is a standing risk worth separate attention.

---

## B. Preflight Results (all executed this pass, read-only)

| Check | Result |
|---|---|
| Migration linter, `--from-migration 047` | **PASS** - 0 hard failures, 0 warnings on both SQL files. (14 repo-wide failures exist in 001-011, predate the linter, unrelated.) |
| Single transaction | **CONFIRMED** - one `BEGIN` ... `COMMIT`; any error aborts the whole migration and leaves production untouched. |
| 7 explicit `ALTER FUNCTION` signatures still resolve | **PASS** - all 7 resolved via `to_regprocedure`; this is the statement class most likely to fail and it is clean. |
| 3 cost views still exist as views | **PASS** - all `relkind = 'v'`. |
| Function count | **42**, matches audit exactly. |
| `authenticated_*` policy count | **36** across 9 tables, matches audit exactly. |
| Tables with RLS off in `public` | **8**, matches audit exactly. |
| `anon` table grants in `public` | **203**, matches audit exactly. |
| Drift since original audit | **NONE.** Every count and definition is identical. |
| Executing role | `postgres`, `session_user` = `postgres`, owner of all 42 functions and all 3 views -> has authority to REVOKE and ALTER. |
| `postgres` is superuser | **No** (`is_superuser = off`). |
| `postgres` member of `supabase_admin` | **No** - bounds the default-privileges change (see Remaining Risks). |
| Extension-owned functions in target schemas | **ZERO** - no REVOKE can abort on ownership. |
| `anon`/`authenticated` grants outside `public` | **NONE** - confirmed `platform`/`product_graph` have no table grants and anon holds no schema USAGE. This is what exposed rollback defect #2. |
| Public table ACL uniformity | **1 distinct pattern** across all 203 relations (`anon=arwdDxtm`, `authenticated=arwdDxtm`, no PUBLIC) -> the pre-image needs one blanket GRANT. |
| Secrets in migration output | **NONE.** The migration emits one `RAISE NOTICE` with a function count. No key, token, connection string or row data is read or printed. |
| Service-role paths still functional pre-change | **PASS** - 17/17 (8 table reads, 6 RPCs, 3 cost views) via `verify_p0_0_security.py` baseline. |

Not executed, and not claimed: **047 has never been applied to any database.** There is no local
Postgres on this machine, Docker was ruled out, and branching requires Pro. The SQL is reviewed
statement-by-statement against the live catalog; it is not execution-tested.

---

## C. Backup and Recovery Assessment

Verified, not assumed. The stored `sbp_` management token in `~/.claude.json` is **invalid**
(`401 Invalid access token` on every Management API call), and the MCP server exposes no backup
endpoint, so the backups API could not be queried directly. Plan tier was established behaviourally
instead: `create_branch` returned *"Branching is supported only on the Pro plan or above"*, which
places the project **below Pro**.

| Question | Answer |
|---|---|
| 1. Automated backups enabled? | **No.** Supabase backs up "Pro, Team, and Enterprise Plan projects" only; the docs explicitly tell free-tier projects to export their own data. |
| 2. PITR available? | **No.** Pro/Team/Enterprise add-on, from ~$100/month for 7-day retention. |
| 3. Most recent usable backup? | **None exists.** |
| 4. Can a backup be restored? | **N/A** - there is nothing to restore. |
| 5. Expected recovery time? | **N/A** for platform restore. For the pre-image path below: seconds. |
| 6. Would restoring require a new project? | **N/A.** ("Restore to a new project" is the Pro clone-project feature.) |
| 7. Could restoration overwrite newer data? | **No** - the pre-image path touches no rows at all. |
| 8. Additional backup/export required first? | **Yes, and it is mandatory: capture the pre-image.** See below. |

**Why this is not a blocker for 047, stated plainly.** The generic demand for a database backup is
driven by migrations that mutate data or drop objects. 047 does neither: it changes privileges,
policies, function `search_path` settings and view options only - no rows, no DDL on tables, no
dropped objects. The recovery surface is therefore fully expressible as SQL, and
`scripts/tests/capture_047_preimage.sql` captures it exactly from the live catalog: all 42 function
grants and `search_path` settings, the uniform table/sequence grants, RLS state for every affected
table, every policy with its precise definition, the view options and the default privileges. For
this change that is **better** than a daily backup: no downtime, no data-loss window, and surgical.

**Standing risk, independent of P0-0 and not fixed by it:** this project holds the entire Agent
Oversight ledger and has no backups whatsoever. A `supabase db dump` to off-site storage is free and
should be scheduled regardless of this migration. Flagging, not actioning - out of P0-0 scope.

---

## D. Rollback Strategy Review

**Transaction rollback and post-deployment rollback are not the same thing** and must not be
conflated:

- **Transaction rollback** is automatic. 047 is one `BEGIN`/`COMMIT`; if any statement fails,
  Postgres reverts everything and production is bit-for-bit unchanged. No script, no decision, no
  risk. This is the likely failure mode and it is self-healing.
- **Post-deployment rollback** is deliberately reversing an already-committed 047. This is the
  dangerous path, because **it re-opens every hole P0-0 closes.** Treat it as last resort. For an
  isolated regression, prefer a narrow forward `GRANT` on the one object that broke.

Three defects were found in `047_rollback.sql` this pass and are fixed:

1. **It did not restore the PUBLIC grant.** It re-granted only `anon`/`authenticated`, so running it
   would not have returned the database to its prior state. Now grants `TO PUBLIC, anon, authenticated`.
2. **It over-granted.** It granted ALL on `platform` and `product_graph` tables to
   `anon`/`authenticated` - grants that **never existed** (confirmed `(none)` in the live catalog).
   A rollback that quietly escalates privilege is worse than no rollback. Removed.
3. **It could not cleanly reverse the view change.** `SET (security_invoker = off)` leaves an explicit
   `false` option where there was originally no option at all. Now uses `RESET (security_invoker)`.

Operations that **cannot** be reversed byte-exactly, now documented in the script itself:

| Operation | Reversibility |
|---|---|
| Function EXECUTE grants | Fully reversible. |
| Table/sequence privileges | Fully reversible (uniform pattern). |
| RLS policies | Fully reversible - exact definitions captured from `pg_policies`. |
| Function `search_path` | Fully reversible via `RESET`. |
| Security-invoker views | Reversible via `RESET`; original had no option row. |
| **NULL function ACLs (3 functions)** | **Not exactly.** Once an ACL materialises, "no ACL row" cannot be recreated. `GRANT ... TO PUBLIC` is functionally equivalent, catalog-visibly different. |
| **Default privileges for `platform`/`product_graph`** | **Not exactly.** No entry existed; restoration grants EXECUTE to PUBLIC, the built-in default, rather than removing the entry. |
| **`supabase_admin`-owned default privileges** | Never touched by 047; nothing to reverse. |

Prefer the captured pre-image (`047_preimage_<ts>.sql`) over `047_rollback.sql`: the pre-image is
derived from the live catalog, the rollback script is hand-written.

---

## E. Go / No-Go Checklist

Every box must be ticked before deployment is authorized.

- [ ] **Correct project confirmed:** `hdhovyrlnfojtkqbcegh`, name `leazer7222's Project`. (There are two projects on this account; the other is `Renovation WalkThrough`, which must not be touched.)
- [ ] **Pre-image captured and committed.** Run `scripts/tests/capture_047_preimage.sql`, save output to `supabase/migrations/047_preimage_<YYYYMMDDHHMM>.sql`, commit it. **This is the backup substitute and is non-optional given the Free plan.**
- [ ] **Preflight re-run and still clean.** Re-confirm the counts in section B (42 / 36 / 8 / 203) and that all 7 `ALTER FUNCTION` signatures still resolve. Any drift -> stop and re-review.
- [ ] **Advisor baseline captured.** Record current security-advisor output so post-deployment findings can be attributed.
- [ ] **Behaviour baseline captured.** `python scripts/verify_p0_0_security.py` (no flags; read-only). Expect 32 checks, 0 failed, with anon reachability recorded as the pre-fix state.
- [ ] **App health confirmed BEFORE the change.** Load `/dashboard`, `/dashboard/runs`, `/dashboard/costs`, `/dashboard/scoping`. **Note:** production `/api/agents` is currently returning `500 TypeError: fetch failed` - a pre-existing fault, unrelated to 047. Record it now so it is not later misattributed to the migration.
- [ ] **No agent run or agile worker in flight.** The migration takes brief locks on policies and functions.
- [ ] **Rollback assets to hand:** the captured pre-image, plus `047_rollback.sql` as a last resort.
- [ ] **Stop conditions agreed** (see below).
- [ ] **Ledger tracking decided:** apply via a path that records the migration (see section G).

**Stop conditions.** Halt and investigate; do not retry a failed statement:
1. Any statement error -> the transaction has already rolled back. Diagnose before any second attempt.
2. Any catalog assertion in `047_assertions.sql` fails.
3. Any `service_role` check in `verify_p0_0_security.py --expect-hardened` fails.
4. The dashboard loses data access, or an agent cannot emit `run_started`/`run_completed`.
5. A new ERROR-level advisor finding appears that is attributable to 047.

---

## F. Execution Procedure

### Before
1. Capture and commit the pre-image (checklist item 2).
2. Re-run preflight; confirm zero drift.
3. Capture advisor + behaviour baselines.
4. Confirm app health and record the pre-existing `/api/agents` 500.

### During
5. Apply `047_p0_0_database_hardening.sql` **as a single atomic transaction** - it already contains
   its own `BEGIN`/`COMMIT`; do not split it into statements.
6. Capture the full execution output, including the `[047A]` notice reporting the function count
   (expect 42).
7. Confirm explicitly whether it committed or rolled back. **Do not auto-retry on failure.**

### After
8. `scripts/tests/047_assertions.sql` - 13 catalog invariants, read-only, safe on production.
9. `scripts/tests/047_behaviour_probes.sql` - impersonates anon/authenticated inside
   `BEGIN..ROLLBACK`, so its deliberate write attempts persist nothing even if one unexpectedly
   succeeds. This is the authorized form of write-oriented verification.
10. `python scripts/verify_p0_0_security.py --expect-hardened` - external HTTP probes with the public
    anon key, the actual threat model. Add `--include-write-probes` only once step 9 has passed; those
    probes attempt real forgery and job injection against production and are expected to be rejected.
11. Re-run the Supabase security advisors; compare against the step-3 baseline.
12. Service-role regression: dashboard pages, `/api/cost` (the 3 views changed), one full agent run
    emitting `run_started` + `run_completed`, and `agents/teams/agile/worker.py --once`.

---

## G. Migration Ledger Tracking

`scripts/apply_sql.py` executes raw SQL through the Management API and **does not write a migration
record** - which is exactly how 024-046 came to be missing from the ledger. Applying 047 the same way
would extend that drift.

**Recommendation:** apply 047 through a path that records it, so that `supabase_migrations.schema_migrations`
gains a `047_p0_0_database_hardening` row. The Supabase MCP `apply_migration` tool does this, as does
the Supabase CLI. If 047 is applied via `apply_sql.py` for any reason, insert the ledger row manually
in the same session and note it in the session log.

Do **not** replay missing historical migrations, rewrite history, or repair the ledger as part of
P0-0. The drift is tracked as separate technical debt; see the plan document.

---

## H. Remaining Risks

1. **047 is not execution-tested.** Mitigated by the single transaction (a failure changes nothing),
   by `DROP POLICY IF EXISTS` being a safe no-op, and by Section A's loop being generated from
   `pg_proc` at runtime so it cannot hold a stale signature. The residual exposure is the seven
   explicit `ALTER FUNCTION` statements, all verified to resolve as of this pass.
2. **No platform backups.** Mitigated for 047 by the pre-image; unmitigated as a standing project risk.
3. **Default-privileges coverage is partial.** `ALTER DEFAULT PRIVILEGES` only affects the executing
   role's entry. Schema `public` has two - one owned by `postgres`, one by `supabase_admin` - and
   `postgres` is not a member of `supabase_admin`, so the second cannot be amended. Objects created
   by `supabase_admin` would still inherit anon grants. Every object here is created by migrations
   running as `postgres`, so the gap is theoretical, but it is a gap and not a guarantee.
4. **Ledger immutability against the service-role key is NOT addressed.** RLS does not bind
   `service_role` (BYPASSRLS). 047 stops *authenticated* mutation of `agent_outputs` and `audit_log`;
   it cannot stop a holder of the service key. Needs triggers - proposed as P0-1g.
5. **Tenant identity is still caller-asserted** in the RPCs. After 047 only `service_role` can reach
   them, so the trust boundary moves into the app, which has no verified identity yet. P0-1e.
6. **Pre-existing, not caused by 047 and not fixed by it:** `/dashboard` is publicly readable (P0-1a);
   `ratified_by` is self-asserted (P0-1); production `/api/agents` returns `500 TypeError: fetch
   failed`; the repo cannot reproduce production (migration drift).
7. **Advisor findings P0-0 does not address:** the `function_search_path_mutable` warnings are fixed,
   but any advisor item arising from `auth.role()`-style policies on `provider_accounts` and the
   `recommendation_*` tables is untouched - 047 deliberately does not modify those policies.

---

## I. Implementation Status

- Branch: `claude/agent-oversight-implementation-b25688`
- Working tree: clean at commit time; all changes committed.
- Corrections committed this pass: the PUBLIC-grant defect in 047 Section A; three defects in
  `047_rollback.sql`; a new assertion A1b; the new pre-image capture script; this runbook.
- **047 has not been applied. No production object or row has been modified. Nothing merged.**
