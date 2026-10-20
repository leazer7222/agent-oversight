# P0 Activation Plan - deployment and validation sequence

Date: 2026-10-20
Branch: `claude/agent-oversight-implementation-b25688`
Target: Supabase project `hdhovyrlnfojtkqbcegh` (`leazer7222's Project`, us-west-2, PG 17.6)

**Nothing in this document has been applied.** It is the operator-executable
sequence, prepared because the apply is permission-blocked in this session.

---

## 1. Committed migration state and dependencies

| Migration | Lines | SHA-256 (first 12) | Commit | Depends on | Applied? |
|---|---|---|---|---|---|
| `047_p0_0_database_hardening.sql` | 400 | `6f2ace26e3af` | `2a027a0` | 001-046 (applied) | **No** |
| `048_auth_and_tenant_credentials.sql` | 311 | `02e24af8917f` | `c36560b` | 001, 047 | **No** |
| `049_swim_sourcing_schema.sql` | 369 | `617249452732` | `c36560b` | 001, 047, 048 | **No** |
| `050_swim_sourcing_rpcs.sql` | 408 | `01874f2a69d7` | `9719aeb` | 049 | **No** |

Working tree clean; no uncommitted migration changes.

**Apply order is mandatory and not merely conventional:**
- 048 attaches triggers using `public.forbid_mutation()` and assumes 047's
  grant posture.
- 049's RLS policies reference `public.company_members`, created in 048.
- 049 attaches triggers to `swim_sourcing.approvals` using `forbid_mutation()`
  from 048.
- 050's functions query `swim_sourcing` tables created in 049.

### Drift re-check (just run, read-only)

| Check | Expected | Now | Verdict |
|---|---|---|---|
| Functions in public/platform/product_graph | 42 | **42** | match |
| Functions carrying a PUBLIC grant | 42 | **42** | match |
| `authenticated_*` policies | 36 | **36** | match |
| Tables with RLS off in `public` | 8 | **8** | match |
| `anon` table grants in `public` | 203 | **203** | match |
| The 7 explicit `ALTER FUNCTION` signatures resolve | 7 | **7** | match |
| Migration ledger high-water mark | - | `20260520001052` (023) | unchanged |

**Zero drift since the last preflight.** 047 remains valid as written.

### No partial apply

| Object | Exists? |
|---|---|
| `swim_sourcing` schema | No |
| `public.company_members` | No |
| `platform.tenant_provider_credentials` | No |
| `public.forbid_mutation()` | No |
| `auth.users` (048 FKs to it) | **Yes** - and it holds **0 users** |

That last row matters: `company_members.user_id` references `auth.users(id)`, so
no membership can be seeded until at least one account exists. The validation
sequence in section 5 creates throwaway users for exactly this reason.

---

## 2. Supported approval procedure

The apply was refused by the Claude Code auto-mode permission classifier:

```
Permission denied by the Claude Code auto mode classifier.
Reason: [Protected-Scope IaC Apply]
tool: mcp__749bda98-5039-4bd2-b996-f87889c72e86__apply_migration
```

I did not attempt `execute_sql` or any other tool to achieve the same effect.
There are three supported ways to authorize it. **Option C is the one I would
choose.**

### Option A - grant the tool a permission rule
Add to `.claude/settings.local.json` under `permissions.allow`:

```
"mcp__749bda98-5039-4bd2-b996-f87889c72e86__apply_migration"
```

Then re-run the apply in a session. This grants the capability for **all future
migrations**, not just these four, which is a broader grant than this task needs.

### Option B - interactive permission prompt
Run the work from an interactive `claude` terminal where the classifier can
prompt, and approve each apply individually. `/permissions` is a terminal-dialog
command and is **not available in this desktop session**.

### Option C - operator applies the SQL directly (recommended)
Use the Supabase dashboard SQL editor. This keeps the production DDL decision
with a human, needs no standing permission grant, and gives you the statement
output to read. The exact sequence is section 4.

Dashboard SQL editor:
`https://supabase.com/dashboard/project/hdhovyrlnfojtkqbcegh/sql/new`

---

## 3. Backup strategy

**The P0-0 privilege pre-image is not a backup.** It restores grants, policies,
`search_path` settings and view options. It contains no data and no DDL. It is
the correct recovery tool for 047 specifically, because 047 changes nothing else
- but 048, 049 and 050 **create tables, functions and triggers**, so they need a
real backup behind them.

### What I was able to take and verify

`scripts/backup_supabase.py` - a logical data export of the `public` schema.

```
python scripts/backup_supabase.py --out backups
python scripts/backup_supabase.py --verify backups/public-schema-<stamp>
```

**Executed and verified just now:** 29 objects, **2,485 rows**, every table's row
count matching PostgREST's exact count, every line valid JSON, **0 failures**.
Largest tables: `contractor_rows` 798, `agent_events` 749,
`provider_health_snapshots` 468, `runs` 181, `agent_outputs` 83.

Verification is not just "the file exists": it re-parses every line, because a
truncated write produces a file that looks fine until you try to restore from it.

### What that backup does NOT cover - and why

| Not covered | Why |
|---|---|
| `platform`, `product_graph`, `cost_intelligence`, `telemetry`, `runtime_governance`, `model_intelligence` | PostgREST exposes only `public`; no HTTP client can read them |
| Schema DDL, functions, policies, grants, triggers, sequences | Not retrievable over PostgREST |
| `auth.users`, `storage.objects` | Separate services |

Those six private schemas hold the cost artifacts, estimation history, product
graph and raw telemetry. **They are currently unbacked.**

### Completing the backup - needs you

A complete backup requires `pg_dump`, which requires a direct Postgres
connection string. There is none in `.env.local`, and the stored Supabase
management PAT is **invalid** (`401 Invalid access token` on every Management API
call), so one cannot be fetched programmatically.

Get the connection string from
`https://supabase.com/dashboard/project/hdhovyrlnfojtkqbcegh/settings/database`
then, with the Supabase CLI (`npm i -g supabase`):

```bash
supabase db dump --db-url "postgresql://postgres:<PASSWORD>@db.hdhovyrlnfojtkqbcegh.supabase.co:5432/postgres" -f backup-pre-047-schema.sql
supabase db dump --db-url "postgresql://..." --data-only -f backup-pre-047-data.sql
```

### Verifying the recovery procedure

A restore rehearsal needs a second database to restore *into*. The options are a
Supabase preview branch (Pro only - **paid, needs your authorization**), a second
free project, or a local Postgres. **I have not rehearsed a restore**, and I am
not going to describe the recovery procedure as verified on the strength of a
backup file existing.

What I did verify: the export is complete against exact server-side counts and
structurally valid line by line.

---

## 4. Operator-executable deployment sequence

Run in order. Stop at the first failure and do not retry a failed statement.

### Before
1. **Confirm the project.** `hdhovyrlnfojtkqbcegh` / `leazer7222's Project`. The
   other project on this account, `Renovation WalkThrough`, must not be touched.
2. **Take the pg_dump backup** (section 3). This is the step that makes 048-050
   reversible.
3. **Re-run the drift check.** Paste `scripts/tests/047_assertions.sql`'s
   precondition counts, or re-run section 1's table. Any change -> stop.
4. **Capture the pre-image for 047:** run `scripts/tests/capture_047_preimage.sql`,
   save the output to `supabase/migrations/047_preimage_<stamp>.sql`, commit it.
5. **Capture the advisor baseline:** Supabase dashboard -> Advisors -> Security.
6. **Capture the behaviour baseline:** `python scripts/verify_p0_0_security.py`
   (read-only). Expect 32 checks, 0 failed, with anon reachability recorded as
   the pre-fix state.
7. **Confirm nothing is in flight:** `swim`/`agile` workers stopped; no run with
   `status='started'` newer than a few minutes (the 4 existing ones are stale by
   4-7 months).

### Apply
Paste each file whole into the SQL editor, in this order, one at a time:

| Step | File | Expect |
|---|---|---|
| 8 | `supabase/migrations/047_p0_0_database_hardening.sql` | notice `[047A] ... on 42 function(s)` |
| 9 | `supabase/migrations/048_auth_and_tenant_credentials.sql` | success, no notices |
| 10 | `supabase/migrations/049_swim_sourcing_schema.sql` | success |
| 11 | `supabase/migrations/050_swim_sourcing_rpcs.sql` | success |

Each file carries its own `BEGIN`/`COMMIT`, so a failure rolls that file back
whole and leaves the database as it was.

### Record them in the ledger
`scripts/apply_sql.py` and the SQL editor do **not** write migration records -
that is how 024-046 went missing from the ledger. After a successful apply:

```sql
insert into supabase_migrations.schema_migrations (version, name) values
  ('20261020120000', '047_p0_0_database_hardening'),
  ('20261020120001', '048_auth_and_tenant_credentials'),
  ('20261020120002', '049_swim_sourcing_schema'),
  ('20261020120003', '050_swim_sourcing_rpcs');
```

### Stop conditions
Any statement error; any assertion failure; any `service_role` check failing;
the dashboard losing data access; an agent unable to emit `run_started`; a new
ERROR-level advisor finding attributable to these migrations.

---

## 5. Post-apply validation sequence

Run in this order. Steps 12-14 are read-only; 15 writes throwaway fixtures.

| Step | Command | Proves |
|---|---|---|
| 12 | `scripts/tests/047_assertions.sql` | 14 catalog invariants, incl. A1b (no surviving PUBLIC grant) and F1b (global default privileges) |
| 13 | `scripts/tests/047_behaviour_probes.sql` | anon/authenticated denial, behaviourally, inside `BEGIN..ROLLBACK` |
| 14 | `python scripts/verify_p0_0_security.py --expect-hardened` | external HTTP probes with the **public anon key** - the real threat model |
| 15 | `python scripts/tests/test_tenant_isolation_live.py --i-understand-this-writes-to-production` | **the cross-tenant test** - see below |
| 16 | Supabase Advisors -> Security | zero ERROR-level lints |
| 17 | `python scripts/backup_supabase.py --out backups` | post-apply backup; also confirms service-role reads still work |
| 18 | Load `/dashboard`, `/dashboard/runs`, `/dashboard/costs`, `/dashboard/scoping`, `/dashboard/sourcing` | no regression; the 3 cost views changed |
| 19 | Run one agent end to end | `run_started` + `run_completed` still persist |
| 20 | `python agents/teams/agile/worker.py --once` | the existing queue still drains |

### What step 15 actually proves

`scripts/tests/test_tenant_isolation_live.py` creates two throwaway companies,
two throwaway `auth.users`, signs in as each, and asserts across five layers:

1. **RLS on `company_members`** - user A sees exactly one membership, it is
   company A's, and B's is invisible.
2. **`swim_*` RPCs reject authenticated callers** - they are `service_role` only,
   so a browser session cannot reach them whatever company id it passes.
3. **anon denial after 047** - `agents`, `agent_outputs`, `contractor_rows`,
   `agile_intake_jobs` and two SECURITY DEFINER RPCs.
4. **Ledger immutability binds `service_role`** - an UPDATE and a DELETE on
   `agent_outputs` through the service role must both be refused by the 048
   trigger. This is the one thing RLS cannot do.
5. App-layer `?company=` mismatch -> 403. Needs a browser session, so it is a
   manual step (below).

It gives company A a real facility first, so "cannot see B's rows" is a genuine
claim rather than an artefact of both tenants being empty, and it deletes
everything it created. It refuses to run when the migrations are absent -
**verified: it currently exits 2 and names the three missing objects**, rather
than reporting a meaningless pass.

### Manual app-layer check (step 5 above)
1. Sign in at `/login` as the user you added to Cameron's company.
2. `GET /api/sourcing/facilities` -> 200, scoped to her company.
3. `GET /api/sourcing/facilities?company=<ReformAI's uuid>` -> **403**.
4. Sign out. `GET /api/sourcing/facilities` -> **401**. `GET /dashboard` -> **302 to /login**.

---

## 6. `/api/agents` 500 - root cause found

**It was not a standing fault, and my earlier diagnosis was wrong.** It does not
reproduce: `/api/agents`, `/api/runs` and `/api/cost` all return **200 with real
data** right now.

Evidence from the project's own edge logs for 2026-10-20:

| Minute | Method | Status | Count |
|---|---|---|---|
| 17:03 | GET | 401 | 3 |
| 17:05 | GET | **502** | 3 |
| 17:05 | GET | **521** | 3 |
| 17:05 | GET | 200 | 2 |
| 17:06 onward | GET/POST | 200/201/206 | all |

**Root cause: the Supabase project was cold-starting from Free-tier auto-pause.**
Every one of the seven log sources in this project begins at 17:02-17:06 with
nothing before it, which is the signature of an instance that had just started.
HTTP 521 is "web server is down". Vercel's serverless function hit the origin
during that window and surfaced the connection failure as
`TypeError: fetch failed`.

**Correction to something I asserted twice.** I reported that "Supabase itself is
up" because `/rest/v1/` answered `401`. That inference was wrong: PostgREST
rejects a missing `apikey` at the edge **before touching Postgres**, so a 401
proves reachability, not database health. Those three 401s at 17:03 are my own
probes. The same cold start also explains the two `supabase` MCP
`CONNECTION_CLOSED` failures earlier in the session.

**Consequence that matters for Cameron, and it is not small:** a Free-tier
project that auto-pauses after inactivity is a poor backend for an unattended
worker polling a queue. Her agents will intermittently fail against a sleeping
database, and those failures will look like application bugs. Options: accept it
and make the worker tolerate cold starts with retry/backoff (it already has
bounded retry, so this is mostly a matter of not treating the first failure as
terminal); keep the project warm with a cheap periodic query; or move to Pro
(**paid - needs your authorization**).

No Vercel environment variable is at fault, and no code change is needed.

---

## 7. Remaining steps for Cameron to source real pools

Ordered. Items 1-3 are yours; 4-8 are hers.

| # | Owner | Step | Blocks |
|---|---|---|---|
| 1 | You | Authorize the apply (section 2, Option C) and run sections 4-5 | everything |
| 2 | You | Generate `CREDENTIAL_ENCRYPTION_KEY` (base64 32 bytes) into the deployment env | credential vault |
| 3 | You | `node scripts/register_swim_sourcing.js`, then add Cameron to `company_members` as `owner` | her sign-in |
| 4 | Cameron | Her own Anthropic account + API key, stored via the credentials route | her agents running at all |
| 5 | You/Cameron | `GOOGLE_PLACES_API_KEY` + GCP billing | **live** discovery (fixtures work today) |
| 6 | Cameron | Google **Workspace** domain + mailbox | any real email |
| 7 | Cameron | Gmail + Calendar OAuth (internal app, or service account with domain-wide delegation) | send, inbox, scheduling |
| 8 | Cameron | Business identity: legal name, **physical postal address** (CAN-SPAM), phone; qualification preferences; negotiation ceilings; pre-approved FAQ | compliant outreach |

Then, in order: activate the agents (they register `paused` deliberately),
enqueue a `discover` job, review the qualified list, approve the first campaign
in the dashboard, and only then connect the live mailbox.

Unchanged and still the schedule driver: Gmail's `gmail.send`/`gmail.readonly`
are **restricted scopes**. Both fast paths need Google Workspace. Consumer Gmail
in OAuth "Testing" mode expires refresh tokens every 7 days, which would break
the agent weekly.

---

## 8. Status of the six requested report items

| # | Item | Status |
|---|---|---|
| 1 | Migrations applied and verified | **None applied.** Permission-blocked; drift re-checked as zero; sequence prepared |
| 2 | Authentication and tenant isolation results | **Not run.** Test written and verified to refuse pre-apply |
| 3 | Anthropic credential isolation results | **Code proven: 17/17 tests**, incl. fail-closed with a platform key present. Live validation pending Cameron's key |
| 4 | Real vs mocked capabilities | Qualification **real**; discovery **fixtures** (no Places key); email/calendar **mocked**; worker unrun against a DB |
| 5 | Production API health | **Healthy.** 500 was Free-tier cold start, root-caused from edge logs; no code or env fix needed |
| 6 | Remaining steps for Cameron | Section 7 |

Nothing was applied, no external email was sent, no autonomous job was activated,
and no paid resource was provisioned.
