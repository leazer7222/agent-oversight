# Agent Oversight - Platform Handoff Summary

Purpose: start a new development thread for a business agent **without repeating
the architecture audit**. Read this plus the file paths it names.

Branch: `claude/agent-oversight-implementation-b25688`
As of: 2026-10-20

> **Deployment state in one line:** **DEPLOYED AND VERIFIED** as of 2026-10-20.
> Migrations 047-052 applied; the secured application is live at
> `agent-oversight.vercel.app` (merge `e7f7cbf`). Anonymous callers get 401, the
> ledger is append-only even against the service-role key, and the cross-tenant
> 403 is proven against the deployed app, not just the database.

---

## 1. Current architecture

```
                     Cameron / operator (browser)
                                |  authenticated session
                                v
  +---------------------------------------------------------------+
  |  Next.js on Vercel                                            |
  |                                                               |
  |  src/middleware.ts        session gate. Pages -> /login,      |
  |                           APIs -> 401. Exempts ONLY            |
  |                           /api/ingest + /api/telemetry/ingest  |
  |                           (they use x-agent-secret instead).   |
  |         |                                                      |
  |         v                                                      |
  |  requireTenant()          company from the SESSION via         |
  |  src/lib/auth/            company_members. A disagreeing       |
  |  require-tenant.ts        ?company= is a 403, never an         |
  |                           override. Admin cross-tenant reads   |
  |                           are audited.                         |
  |         |                                                      |
  |  /api/sourcing/*  (tenant-scoped, new)                         |
  |  /api/* (26 legacy ReformAI routes, NOT yet retrofitted)       |
  |  /api/ingest      (agent telemetry, shared secret)             |
  +--------------------------+------------------------------------+
                             | service-role client (bypasses RLS)
                             v
  +---------------------------------------------------------------+
  |  Supabase Postgres 17.6  (hdhovyrlnfojtkqbcegh)               |
  |                                                               |
  |  CONTROL PLANE (shared)            DOMAIN (per business)      |
  |   public.companies                  swim_sourcing.*           |
  |   public.projects                   (9 tables + job queue)    |
  |   public.agent_definitions   <- shared capability library      |
  |   public.agents              <- tenant-scoped instances        |
  |   public.runs / agent_events / agent_outputs   (the ledger)   |
  |   public.company_members     <- RBAC (048)                    |
  |   public.privileged_action_log  <- audit (048)                |
  |   platform.tenant_provider_credentials <- per-tenant LLM keys |
  |   cost_intelligence.* / runtime_governance.* / telemetry.*    |
  |   product_graph.* / model_intelligence.*                      |
  +--------------------------+------------------------------------+
                             ^
                             | swim_* RPCs (service_role only)
  +--------------------------+------------------------------------+
  |  Python worker  (agents/teams/swim-sourcing/worker.py)        |
  |  lease + heartbeat + bounded retry + cancellation             |
  |  preflight fails closed: agent active? budget? tenant key?    |
  |  Railway config written; NOT provisioned                      |
  +---------------------------------------------------------------+
```

**The architectural rule to preserve: shared capabilities, separate business
data.** Agent code is tenant-agnostic and takes `(company_id, config)`. Business
rows live in that business's own schema. `swim_sourcing` is also the extraction
seam - if a business outgrows the control plane it lifts out without touching
`public`/`platform`.

Note this deviates from `docs/PLATFORM_ARCHITECTURE.md`, which positions Agent
Oversight as a pure control plane that holds no domain content. The deviation
was approved deliberately; `product_graph`, `feature_lifecycle` and
`agile_intake_jobs` had already set the precedent.

---

## 2. Deployment state - read before trusting anything below

| Migration | File | Status |
|---|---|---|
| 047 | `047_p0_0_database_hardening.sql` | **Applied + verified** |
| 048 | `048_auth_and_tenant_credentials.sql` | **Applied + verified** |
| 049 | `049_swim_sourcing_schema.sql` | **Applied + verified** |
| 050 | `050_swim_sourcing_rpcs.sql` | **Applied + verified** |
| 051 | `051_activate_rls_defense_in_depth.sql` | **Applied** - fixes a dead-RLS defect the live test caught |
| 052 | `052_current_user_companies_security_invoker.sql` | **Applied** - clears the last advisor WARN |

All six are recorded in `supabase_migrations.schema_migrations`.

**Verified in production:** anon-executable functions 42 -> 0; functions
granting PUBLIC 42 -> 0; tables with RLS off 8 -> 0; `authenticated_*` policies
36 -> 0; anon table grants 203 -> 0; security advisor lints **46 -> 0**.
Anonymous ledger forgery and job injection both return 401. Service-role
UPDATE and DELETE on `agent_outputs` are refused by trigger with `42501`.

Apply sequence, preconditions and post-apply validation:
**`docs/p0-activation-plan.md`** sections 4 and 5. Apply one at a time via the
Supabase SQL editor and verify before continuing.

---

## 3. Verified operational capabilities

Honest split. "Verified" means a test ran and passed.

| Capability | State | Evidence |
|---|---|---|
| Telemetry ingest (`run_started`/`run_completed`) | **Operational** (pre-existing) | 181 runs, 749 events in production |
| Agent registry + hierarchy | **Operational** (pre-existing) | 25 agents, 18 definitions |
| Cost attribution | **Operational** (pre-existing) | `/dashboard/costs`, cost views |
| Agent status kill switch | **Operational** | `/api/ingest` 403s a non-active agent |
| Dashboard read APIs | **Operational** | `/api/agents`, `/api/runs`, `/api/cost` all 200 |
| Credential vault | **Verified live, 13/13** | `scripts/tests/validate_credential_vault_live.py` against applied 048, plus 17/17 unit tests |
| Qualification scoring | **Code verified, 19/19** | deterministic, no live dependency |
| Discovery | **Fixtures only** | no `GOOGLE_PLACES_API_KEY` |
| Outreach safety + exactly-once send | **Code verified, 30/30** | mock transport |
| Authentication | **Live** | anon 401, `/dashboard` 307 -> `/login`, admin 200 on all surfaces |
| Tenant isolation | **Verified live, both layers** | database 23/23; application 13/13 incl. the cross-tenant 403 |
| Durable worker | **Schema live, worker unrun** | `swim_*` RPCs applied; worker not yet executed against the queue |
| Backup | **Complete, verified** | 7 schemas, 2,110 DDL objects, 3,560 rows, 0 failures |

---

## 4. Authentication and authorization model

Four layers. Each holds if the others fail:

1. **`src/middleware.ts`** - no session, no access. Matches broadly and exempts
   explicitly, so a new route is protected unless someone deliberately exempts it.
2. **`requireTenant()`** - the company comes from `company_members` keyed on
   `auth.uid()`. A caller-supplied `?company=` is validated against the session
   and rejected on mismatch. This is the fix for query-param tenancy.
3. **RLS** - `swim_sourcing` policies bind to `company_members` via `auth.uid()`,
   not to a session GUC set from a parameter. The `swim_*` RPCs are
   `service_role` only, so a browser session cannot reach them at all.
4. **Triggers** - `public.forbid_mutation()` on `agent_outputs`, `agent_events`
   and `privileged_action_log`. RLS does **not** bind `service_role`
   (BYPASSRLS), so a trigger is the only thing that makes the ledger
   append-only against the service key.

Roles: `owner`, `operator`, `admin`. `admin` may act cross-tenant and every such
access writes `privileged_action_log`.

**Closed 2026-10-20:** the 26 legacy ReformAI routes previously had no
authorization at all. They now require a platform administrator via
`requireAdminOrDeny` (`src/lib/auth/require-admin.ts`). Tenant-scoping them
would have been the wrong fix - aggregating across companies IS their purpose
(`/api/hierarchy` walks every company, `/api/cost` aggregates all spend) - and no
tenant user should call them, because tenant data is served by
`/api/sourcing/*`. A non-admin gets 403 and the denial is written to
`privileged_action_log`.

This required one supporting change: `apiFetch` now forwards the caller's
session cookie on the server-to-server hop. Dashboard pages are server
components that re-enter the app over HTTP, so without cookie forwarding every
page would have rendered as a convincing empty state once the routes started
requiring auth.

CI enforces it: `check_route_authorization.py` asserts every route in
`ADMIN_ONLY` calls the guard, that the guard runs BEFORE any database client is
constructed, and that no route anywhere has zero authorization.

---

## 5. Onboarding a new company

1. `node scripts/register_swim_sourcing.js --dry-run` - copy it as a template.
   Register the company with a **real `cost_limit_usd`**; every pre-existing
   company has it NULL, so the cap is both unenforced and unpopulated.
2. Create the user through Supabase Auth (magic link at `/login`, or the Admin
   API).
3. Insert `company_members (user_id, company_id, role)`.
4. Store the tenant's provider key (section 6).
5. Create the business's own schema, modelled on `049_swim_sourcing_schema.sql`.
   **Copy its default-privilege preamble** - a new schema otherwise inherits
   PostgreSQL's built-in EXECUTE-to-PUBLIC for new functions and silently
   reopens the hole 047 closes.
6. Register agent definitions (tenant-neutral) and instances (`{tenant}.{capability}`).

---

## 6. Per-company Anthropic credentials

Storage: `platform.tenant_provider_credentials` - AES-256-GCM ciphertext, nonce,
SHA-256 fingerprint, last4. **No function returns a decrypted key.**
Runtime: `agents/lib/credentials.py`.

```python
from agents.lib import credentials as CRED
cred = CRED.resolve_tenant_api_key(company_id, "anthropic")   # raises if absent
env  = CRED.tenant_llm_env(cred)                              # SCRUBBED env
```

Three rules that make billing isolation real rather than aspirational:

- `resolve_tenant_api_key` **raises** `MissingTenantCredential`. There is no
  fallback to a platform key under any failure mode.
- `tenant_llm_env()` **scrubs** `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
  `ANTHROPIC_BASE_URL`, `OPENAI_API_KEY` and friends before injecting the tenant
  key. Without the scrub the SDK falls back to the inherited platform key, the
  agent still works, and the billing leak is invisible. This is the single most
  important line of code in the vault.
- Requires `CREDENTIAL_ENCRYPTION_KEY` (base64 32 bytes) in the deployment env,
  never in the repo.

Rotation: insert a new row, mark the old `revoked`. A partial unique index
enforces one active credential per (company, provider).

**Internal cost attribution is not provider billing isolation.** `runs.cost_usd`
is bookkeeping. Billing isolation comes solely from the key belonging to the
tenant.

---

## 7. Registering agents, and how they reach telemetry/governance

Definitions are tenant-neutral; instances are `{tenant}.{capability}`. Template:
`scripts/register_swim_sourcing.js`. Register the orchestrator **before** the
workers (`parent_agent_id` FK), and use `trigger_type='manual'` - the CHECK
constraint rejects `'orchestrator'`. Register new agents **paused**.

Telemetry, unchanged and reusable as-is:

```python
from oversight import OversightClient          # python-sdk/oversight.py
client = OversightClient()                     # OVERSIGHT_URL + AGENT_OVERSIGHT_SECRET
with client.run(agent_id=AGENT_ID, run_id=run_id) as ctx:
    ctx.step("did_a_thing", metadata={...})
    ctx.report(tokens_in=..., tokens_out=..., cost_usd=...)
```

Governance available to any new agent:
- `public.check_tenant_budget(company_id, estimate_usd)` - fail-closed spend ceiling (048)
- agent `status != 'active'` -> `/api/ingest` returns 403 (kill switch, live today)
- `public.privileged_action_log` - audit sink for privileged operations
- `cost_intelligence.*` estimate/evaluation artifacts, written by the ingest path

---

## 8. Worker and execution infrastructure

| | `agents/teams/agile/worker.py` | `agents/teams/swim-sourcing/worker.py` |
|---|---|---|
| Claim | atomic, `SKIP LOCKED` | same |
| Lease / heartbeat | **none** | yes |
| Crash recovery | **none** - job stuck `running` forever | `swim_reap_expired_jobs` |
| Retry / backoff | none | bounded, exponential |
| Cancellation | none | cooperative via heartbeat |
| Preflight | none | agent active + budget + tenant credential |
| Hosting | "run locally per work session" | Railway config written, **not provisioned** |

**Build new workers on the swim-sourcing pattern, not the agile one.** The
`swim_*` RPCs in migration 050 are a generic queue; a second business reuses
them by adding job types.

---

## 9. Shared components available for reuse

| Path | What it gives you |
|---|---|
| `python-sdk/oversight.py` | telemetry client, step timing, error taxonomy |
| `agents/lib/credentials.py` | tenant credential vault, env scrubbing, budget check |
| `agents/library/facility-qualification-agent/scoring.py` | deterministic weighted scoring; weights are config, so reuse rather than fork |
| `agents/library/outreach-agent/safety.py` | injection fencing, commitment escalation, anti-fabrication |
| `agents/library/outreach-agent/send.py` | exactly-once send protocol with reconciliation |
| `src/lib/auth/require-tenant.ts` | verified tenant context + audit helper |
| `src/lib/api/fetch.ts` | server fetch with cold-start retry |
| `scripts/check_migrations.py` | migration linter (RFC-009 rules) |
| `scripts/backup_supabase.py` / `backup_full.py` | logical backup + verification |
| `src/lib/auth/require-admin.ts` | admin-only guard for platform-oversight routes |
| `scripts/tests/check_route_authorization.py` | API authorization regression gate (499 checks) |
| `scripts/tests/check_no_secrets.py` | self-tested credential scanner |
| `scripts/tests/test_tenant_isolation_live.py` | five-layer live isolation test |

---

## 10. Limitations and risks

**Resolved since the last revision:** migrations applied; full backup taken and
verified; the 26 legacy routes are admin-only; cross-tenant isolation proven live.

**Remaining:**
1. **Restore never rehearsed.** The backup is complete and internally valid, but
   replaying it needs a second Postgres instance.

**Significant:**
4. **Free-tier auto-pause.** Root-caused from edge logs: the project slept and
   returned 502/521 for ~1 minute, which surfaced as
   `/api/agents -> TypeError: fetch failed`. `apiFetch` now retries, but a
   queue-polling worker on a sleeping database will still fail intermittently
   and it will look like application bugs. Pro tier or a keep-warm ping. Paid -
   needs authorization.
5. **CI does not run on GitHub.** The workflow is complete at
   `ci/github-workflow-ci.yml` but cannot sit under `.github/workflows/` without
   a token carrying the `workflow` scope - `leazer7222` can push but lacks the
   scope, `reformai-admin` has the scope but no push access, and the SSH key
   authenticates as `reformai-admin` too. See `ci/README.md`. Every check it
   defines passes locally.
6. **Service-role key is the main boundary** after 047, and it sits in Vercel
   env vars, on any agent host, and in plaintext in
   `.claude/settings.local.json` (gitignored, never committed - verified).
   Rotation unaddressed.
7. **Repo cannot reproduce production** - the ledger records a `021` with no
   file; 024-046 are unrecorded because they were applied out-of-band. Blocks
   any replay-built environment.

**Accepted:**
9. `public.audit_log` has no append-only trigger: zero writers, so attaching one
   risks breaking a caller found later. `privileged_action_log` is the audited
   surface going forward.
10. `public.runs` is excluded from immutability triggers - ingest legitimately
    updates `started` -> `completed`.

---

## 11. Next recommended entry point

Do these in order, then start the business-agent thread:

1. **Add `SUPABASE_DB_URL` to `.env.local`**, run
   `python scripts/backup_full.py`. Gates everything else.
2. **Apply 047**, then run `scripts/tests/047_assertions.sql`,
   `047_behaviour_probes.sql` and
   `python scripts/verify_p0_0_security.py --expect-hardened`. Verify before continuing.
3. **Apply 048, 049, 050** one at a time, verifying each.
4. **Create the admin account** at `/login`, insert `company_members` with
   `role='admin'`, then run
   `python scripts/tests/test_tenant_isolation_live.py --i-understand-this-writes-to-production`.
   **This is the step that converts "isolation implemented" into "isolation proven".**
5. Record the four migrations in `supabase_migrations.schema_migrations` (the SQL
   editor does not do it, which is how 024-046 went missing).
6. Then begin the next business agent: new schema from the 049 template, agents
   from the `scripts/register_*.js` template, worker from the swim-sourcing
   pattern.

CI runs on every push (`.github/workflows/ci.yml`): migration lint, 88 Python
tests, TypeScript compile, API authorization gate, self-tested secret scan.
Live-service tests are deliberately excluded and listed in that file.
