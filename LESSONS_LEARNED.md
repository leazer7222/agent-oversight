# Lessons Learned

Read this file at the start of every session and apply these rules throughout.
Add new lessons at the end of each session.

---

## Next.js / React

### Server vs Client Components
- Components that use `onMouseEnter`, `onMouseLeave`, or any event handler MUST have `"use client"` at the top.
- Server components should use Tailwind hover classes (`hover:text-white/80`) instead of inline JS event handlers — no `"use client"` needed.
- `motion.a`, `motion.div` etc. from framer-motion require `"use client"` — framer-motion is a client-only library.
- All page sections using framer-motion animations must have `"use client"` as line 1.

### framer-motion (v12+)
- Import from `"framer-motion"` inside `"use client"` components — works fine.
- `whileHover` on `motion.a` internally generates `onMouseEnter`/`onMouseLeave` — these are fine inside client components but will error if the component lacks `"use client"`.

---

## Stitch MCP (Google)

### Auth
- `gcloud auth application-default print-access-token` **hangs silently** on this machine — never rely on it.
- Bypass: call the OAuth2 token endpoint directly via Python using the credentials at `C:\Users\cjlea\.stitch-mcp\config\application_default_credentials.json`.
- Token endpoint: `https://oauth2.googleapis.com/token` with `grant_type=refresh_token`.
- Always include `X-Goog-User-Project: reformai-stitch` header in Stitch API calls.

### API
- Stitch screens are generated via **JSON-RPC** to `https://stitch.googleapis.com/mcp`, NOT REST.
- The Stitch MCP tool itself doesn't pass `X-Goog-User-Project` correctly — use direct Python API calls as the workaround.
- ADC file at `C:\Users\cjlea\.stitch-mcp\config\application_default_credentials.json` must contain `"quota_project_id": "reformai-stitch"`.
- GCP project: `reformai-stitch`, numeric ID: `14670653347525671327`.
- Full troubleshooting log: `.claude/MCP_SETUP.md`.

---

## Nano Banana 2 MCP (Image Generation)

- Correct env var is `NANO_BANANA_MODEL` — NOT `GEMINI_MODEL` (wrong, will be ignored).
- Free-tier model: `gemini-2.0-flash-exp`.
- Model `gemini-3.1-flash-image-preview` requires billing — do not use without confirming billing is enabled.
- Registered at user level via `claude mcp add --scope user` — stored in `~/.claude.json`.
- Must set `NANO_BANANA_MODEL` in BOTH `.mcp.json` AND `~/.claude.json` (user-level MCP config).

---

## Google Service Account

- A ReformAI service account is available for Google API access (no OAuth browser flow needed).
- Email: `reformai-catalog-agent@reformai-agent.iam.gserviceaccount.com`
- GCP project: `reformai-agent`
- Key file: `C:\Users\cjlea\Key\reformai-agent-dd4d7e12c73f.json`
- Use `GOOGLE_SERVICE_ACCOUNT_KEY` env var (path to the key file) for MCPs that support it.
- For Google Drive: share the target Drive/folder with the service account email so it has access.

---

## Debugging Approach

- When an issue recurs across restarts, stop guessing and **read the source** — find the actual config/env var the package uses before changing anything.
- For persistent auth errors: test the API call directly via Python/curl before touching config files.
- Stale server logs will show old errors even after they are fixed — check browser console logs separately.
---
 
 ## Agent Foundation & Supabase Schema
 
 ### Database Naming Conventions
 - The production Supabase schema (project `hdhovyrlnfojtkqbcegh`) uses `id` as the primary key for most tables (`companies`, `agents`, `agent_definitions`).
 - The `agents` table uses `definition_id` as the foreign key to `agent_definitions.id` (contrary to some early planning docs that suggested `agent_definition_id`).
 - Always verify column names via the OpenAPI spec (`/rest/v1/`) or a browser query before writing registration scripts.
 
 ### Agent Registration
 - **Instance Type**: Default value is `stateless` in the primary schema.
 - **Agent Type**: Default value is `worker` for sub-agents; `orchestrator` is used for master agents.
 - **Required Headers**: Direct REST API calls to Supabase MUST include both `apikey` and `Authorization: Bearer [apikey]` headers.
 - **`agent_definitions` has no owner/company column** — it is a shared library. Company association is handled exclusively in the `agents` table via `company_id`.
 - **`agent_definitions` real columns**: `id, name, display_name, description, capability_tags, instance_type, default_model, input_schema, output_schema, config_schema, version, source_path, created_at`
 - **`agents` real columns**: `id, name, company_id, project_id, definition_id, agent_type, parent_agent_id, depth, platform, model, trigger_type, trigger_config, status, cost_limit_usd, cost_limit_period, max_errors_per_hour, priority, tags, can_trigger, can_be_triggered_by, config_overrides, registered_at, last_run_at, paused_at, paused_reason, metadata`
 - **DB-first inspection**: Always run a quick `SELECT * LIMIT 1` against the live table before writing registration scripts — avoids column name guessing.
 - **Run scripts from the project directory**: Node.js resolves `node_modules` relative to CWD. Run scripts from `c:\Users\cjlea\AgentProjects\agent-oversight\` using `powershell -Command "Set-Location '...'; node script.js"`.

 
 ### Python SDK (`oversight.py`)
 - The SDK is used for reporting run status and steps. 
 - Use `client.run()` as a context manager to ensure `run_completed` is emitted even if the script fails.
 - Add the `python-sdk` directory to `sys.path` to import `oversight` if the agent is in a deep subdirectory.

 ### Agent Prompt Management
 - Agent system prompts and instructions (e.g. Elite v4 prompt) should be stored directly alongside the agent's code in its library folder (e.g. `agents/library/marketing-agent/prompt.md`) instead of keeping them in external directories like Downloads. This keeps context tightly coupled to the agent logic.

---

## Supabase MCP Setup (Windows)

- `claude mcp add` with the `-y` flag fails silently or errors in PowerShell — edit `~/.claude.json` directly to add MCP server entries.
- After adding the Supabase MCP entry to `~/.claude.json`, restart Claude Code; the MCP tools become available in the next session.
- Supabase MCP access token: stored in `~/.claude.json` under the supabase server entry. Project ID: `hdhovyrlnfojtkqbcegh`.

---

## Git Worktrees on Windows

- `node_modules` are NOT present in git worktrees by default — Next.js and TypeScript will fail to run.
- Fix: `cmd /c mklink /J node_modules ..\node_modules` in the worktree root creates a directory junction to the main project's `node_modules`.
- This is safe for read-only use (running tsc, starting dev server) — do not run `npm install` from the worktree as it may corrupt the main node_modules.

---

## Supabase TypeScript Types

- Supabase's `createClient<Database>()` generic requires a generated `Database` type. Without it, `.from('table').select(...)` returns `GenericStringError` for the data type instead of the actual row shape.
- Short-term fix: cast `data as any[]` and map items as `(item: any)`.
- Long-term fix: run `mcp__supabase__generate_typescript_types` for project `hdhovyrlnfojtkqbcegh` → save to `src/lib/supabase/types.ts` → pass as generic to `createClient`.

---

## Python Agent Telemetry Patterns

### Cost reporting
- Agents must explicitly capture `response.usage` (OpenAI) or `resp.usage_metadata` (Gemini) after every LLM call and pass `tokens_in`, `tokens_out`, `cost_usd` to `run_completed`.
- A null `cost_usd` without `cost_reported=True` is indistinguishable from "agent didn't report" vs "agent had zero cost". The `cost_reported` boolean sentinel on `runs` resolves this.
- Per-model cost estimation: maintain a pricing dict in the agent; multiply tokens × per-token rate.

### Step events
- Call `ctx.step("step_name", metadata={...}, duration_ms=timer.ms)` after each meaningful unit of work. Steps write directly to `agent_events` and do not affect `runs` lifecycle.
- `StepTimer` context manager measures wall-clock time: `with client.timer() as t: ... t.ms` gives elapsed milliseconds.
- Steps are non-fatal — wrap in try/except and never let step emission block the agent's core work.

### Error taxonomy
- `categorize_error(exc)` in the SDK returns one of: `quota_exceeded`, `auth_error`, `network_error`, `llm_error`, `validation_error`.
- Errors are stored on `runs.error` as `[category] original message`.
- `GET /api/errors` uses regex `^\[([^\]]+)\]` to extract the category for grouping/filtering.

---

## Netlify Deployment (Next.js)

- Next.js server components and API routes require `@netlify/plugin-nextjs` — without it the site deploys as static and API routes return 404.
- Add `[[plugins]] package = "@netlify/plugin-nextjs"` to `netlify.toml` and install the package as a dev dependency.
- `NEXT_PUBLIC_SITE_URL` must be set in Netlify env vars after the first deploy — the URL is only known after Netlify assigns it.
- Git worktrees in `.claude/worktrees/` are tracked as gitlinks (mode 160000) if accidentally staged — Netlify treats them as submodules and fails checkout. Fix: `git rm --cached .claude/worktrees/*` and add `.claude/worktrees/` to `.gitignore`.
- shadcn/ui dependencies (`@base-ui/react`, `class-variance-authority`, `clsx`, `tailwind-merge`) must be installed in the main project root — worktree node_modules junctions don't carry over to CI builds.

---

## Agile Team / Agent Architecture

### Python module imports from hyphenated directories
- Python cannot import modules from directories with hyphens in the name (e.g., `product-clarification-agent`).
- Use `importlib.util.spec_from_file_location("alias", Path("agents/library/product-clarification-agent/agent.py"))` to load the module dynamically.

### Environment variables for Python agents vs Next.js dev server
- `INGEST_SECRET` and `OVERSIGHT_SECRET` in `.env.local` are the local Next.js dev server secrets — they do NOT match the production Vercel deployment.
- Python agents calling the production Vercel endpoint need `AGENT_OVERSIGHT_SECRET=ChArles-Clint0n-Leazer-Jr.-1s-the-B3st`.
- In the `OversightClient` init, check `AGENT_OVERSIGHT_SECRET` first, then fall back to `OVERSIGHT_SECRET`/`INGEST_SECRET`.

### Bash env var scoping on Windows
- `set VAR=val` in the Bash tool does NOT export to child processes — the variable is set for the current shell process only.
- Use the `VAR=val python script.py` prefix syntax to pass env vars to child processes.

### dotenv in worktrees
- `find_dotenv(".env.local", usecwd=True)` correctly walks up from CWD and finds `.env.local` in the main repo root, even when a script runs from a worktree subdirectory.

### Supabase agents table insert order
- Register parent/orchestrator agents in Supabase BEFORE worker agents that reference them via `parent_agent_id` — the FK constraint fires on insert.

### Supabase trigger_type constraint
- The `trigger_type` check constraint on the `agents` table does NOT accept `"orchestrator"` as a value.
- Use `"manual"` for orchestrator agents; `"manual"` is also correct for agents invoked by script or CLI.

### oversight.py SDK — extending for new run fields
- `emit()` and `run()` now accept `team_id`, `context_bundle_id`, `context_bundle_version`, `parent_run_id` as optional kwargs.
- These flow through to the `/api/ingest` payload and populate the matching columns in the `runs` table.
- When adding new DB columns that agents should populate, update the SDK in the same PR — not separately.

---

## Windows Environment Variables

### Machine env vars not visible to running processes
- Windows user env vars set via `[System.Environment]::SetEnvironmentVariable(... 'User')` are NOT inherited by already-running processes — only by processes started after the change.
- Always restart Claude Code after adding new machine env vars to ensure they're inherited.
- Workaround in current session: `$env:VAR = [System.Environment]::GetEnvironmentVariable('VAR', 'User')`.

### Machine env can silently hold the wrong value
- The machine env `SUPABASE_SERVICE_ROLE_KEY` held the 105-char anon key instead of the 219-char service role key — both are JWTs starting with `eyJ` so visually similar.
- Before trusting machine env for Supabase auth, verify key length: anon ≈ 105 chars, service_role ≈ 219 chars.
- Canonical source of truth is always `.env.local` — cross-check machine env against it.

---

## Dashboard / Next.js

### Server-rendered timestamps always need explicit timezone
- `new Date(...).toLocaleString()` with no options uses the runtime's timezone. On Vercel this is UTC, which looks correct locally (dev machine matches user's TZ) but shows UTC in production.
- Always pass `{ timeZone: 'America/Chicago' }` (or use the shared `formatDateTime`/`formatTime` helpers in `src/lib/utils.ts`) for any date displayed in the dashboard.

---

## AI Ops / Recommendation Engine

### Quota score requires both pct AND reset hours — easy to accidentally neuter
- `scoreProvider()` originally only ran quota logic when BOTH `quota_remaining_pct` AND `hours_until_reset` were non-null. Providers with no reset schedule configured always got the neutral 0.5 score, ignoring actual quota.
- Fix: evaluate quota pct independently; only use `hours_until_reset` for the "use-it-or-lose-it" bonus. A provider at 0% must score 0 regardless of reset schedule.

---

## Quota-Sync Agent

### Claude OAuth token vs Anthropic API key — completely separate systems
- The Anthropic API key (`ANTHROPIC_API_KEY`, starts `sk-ant-api03-`) is for API access.
- The Claude OAuth token in `~/.claude/.credentials.json` (`claudeAiOauth.accessToken`, starts `sk-ant-oat01-`) is for the claude.ai subscription quota API (`api.anthropic.com/api/oauth/usage`).
- Claude Desktop does NOT refresh the credentials file — that file is managed by the Claude Code CLI (`claude login`). Using Claude Desktop does not keep the token fresh.
- Token lasts ~2 days. To refresh: open a standalone cmd/PowerShell window (NOT inside Claude Code or Claude Desktop) and run `claude login`. It opens a browser OAuth flow.

### Claude OAuth refresh URL changed
- `https://claude.ai/api/oauth/token` now returns 404 — do not rely on in-script token refresh.
- Delegate token management entirely to `claude login`; the script should read whatever is in the credentials file and fail gracefully if the API returns 401.

### Oversight secret env var naming
- Python agents must check `AGENT_OVERSIGHT_SECRET` first, then fall back to `OVERSIGHT_SECRET`, then `INGEST_SECRET`.
- `OVERSIGHT_SECRET` in `.env.local` is the local dev server secret and does NOT work against the production Vercel endpoint.
- Production secret: `AGENT_OVERSIGHT_SECRET`.

### Two provider_accounts for the same provider — data split between companies
- `quota_sync.py` hardcodes `COMPANY_ID = "87fb6e0d"` (Personal). The quota-snapshot API route used `SELECT id FROM companies LIMIT 1` which returned "ReformAI" (first created, different ID). Each wrote to a different `provider_accounts` row. `assembleSignals` picked up whichever account came last in the iteration — always the wrong one.
- **Rule:** any code that looks up a company to write quota/provider data must use `.eq('name', 'Personal')`, not `LIMIT 1`. There are multiple companies in the DB (ReformAI, AfterGlow, Personal) and order is not guaranteed.
- **Diagnostic query:** when quota bars are blank/stale, run this before touching code: `SELECT pa.id, pa.company_id, COUNT(pqs.id) AS snapshots FROM provider_accounts pa LEFT JOIN provider_quota_snapshots pqs ON pqs.provider_account_id = pa.id GROUP BY pa.id` — if snapshot counts are split across multiple rows for the same provider, that's the bug.

### Oversight URL — Netlify vs Vercel
- The production oversight dashboard moved from `https://agentoversight.netlify.app` to `https://agent-oversight.vercel.app`.
- Any script with the Netlify URL hardcoded as a default will silently fail telemetry. Audit all agent scripts for this.

---

## Chrome Cookie Extraction (Gemini Quota)

### File locking issues
- Chrome keeps an exclusive lock on the `Cookies` SQLite database while it is running.
- Traditional `shutil.copyfile` or PowerShell `Copy-Item` will fail with "Permission denied".
- Current strategy: `quota_sync.py` will retry automatically. Manual sync requires closing Chrome temporarily.
- Future improvement: use Volume Shadow Copy (VSS) if admin privileges are available, or wait for Chrome to release the lock.

### DPAPI Decryption
- Chrome cookies on Windows are encrypted using DPAPI.
- The decryption key is stored in `Local State` (JSON), itself encrypted with DPAPI.
- Requires `pypiwin32` (for `win32crypt`) and `pycryptodome` (for AES-GCM decryption).
- Cookie format: `v10` or `v11` prefix followed by nonce and ciphertext.

---

## Agent Definition / Instance Architecture

### Definitions are tenant-neutral; instances are tenant-scoped
- `agent_definitions` table = reusable capability contract. Name convention: `{capability}` (no tenant prefix).
- `agents` table = operational deployment. Name convention: `{tenant}.{capability}` (e.g. `reformai.code-review-agent`).
- The schema already had this split (`definition_id` FK on `agents`) — but the naming convention was not enforced until 2026-05-15.
- `agent.json` in the library directory stores the **definition UUID** (not the instance UUID).
- Instance-specific jurisdiction lives in `agents.config_overrides` as JSONB. No formal `context_packages` table yet — prove the pattern before building the abstraction.

### Hierarchy page displays instances only
- Definitions are a library catalog. They have no run history, no operational status, no hierarchy position.
- Showing definitions in the hierarchy would create phantom nodes with no operational semantics. Keep the surfaces separate.

### agent_outputs vs agent_qa_results — do not conflate
- `agent_outputs` with `output_type = 'code_review'` = artifact produced by the code-review-agent ABOUT a code diff. Subject is a code change.
- `agent_qa_results` = evaluation OF an agent's operational performance. Subject is an agent run.
- A code review finding does NOT belong in `agent_qa_results`. If you are evaluating whether the code-review-agent itself performed well, THAT goes in `agent_qa_results`.

### code_review artifact is immutable — lifecycle state is a separate table
- The findings artifact written to `agent_outputs` must never be modified after write. It is a ledger entry.
- Human workflow (acknowledged / resolved / false positive / accepted risk) belongs in a separate `code_review_finding_states` table. That table is deferred from v1.
- Design `finding_id` as a stable UUID per finding NOW so the lifecycle table can reference it later without a schema change.

### load_dotenv requires override=True inside Claude Code sessions
- Claude Code injects some env vars as empty strings (`''`) into child processes — including `ANTHROPIC_API_KEY`.
- `load_dotenv` defaults to `override=False`, so it silently skips a key that already exists in `os.environ`, even if the existing value is empty.
- Fix: always use `load_dotenv(find_dotenv(...), override=True)` in agent scripts that need `.env.local` values to win over the Claude Code process environment.
- Diagnosis: if `os.environ.get('KEY')` returns `''` before any dotenv load, this is the issue.

### Findings must cite sources or they are opinions
- Every finding in a code_review artifact MUST populate at least one of: `principles`, `standards_refs`, `lessons_refs`.
- A finding that cites no source is not contestable by the author. Unciteable findings are likely opinions — do not emit them.
- `validate_artifact()` in `output.py` enforces this at write time.

---

## Adaptive Cost Risk Engine (Phase 1)

### Migration numbering and linter
- Migrations 013–020 are the Phase 1 Cost Risk Engine migrations. All must pass `python3 scripts/check_migrations.py --from-migration 013` with zero hard failures before applying.
- The linter enforces: no TIMESTAMP without TZ, no SERIAL, no ON DELETE CASCADE on Class I tables, no PostgreSQL ENUM types, every CREATE TABLE has `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
- Migration 012 (phase0 — platform schema + apply_append_only_rls function) was authored in the `funny-heisenberg` worktree and applied directly to Supabase. Apply migrations 013–020 after 012.

### Non-public schema access from Supabase JS client
- Tables in schemas other than `public` require `supabase.schema('schema_name').from('table_name')`.
- Functions in `public` schema are callable via `supabase.rpc('function_name')`. Functions in other schemas are NOT directly callable via `.rpc()` without schema prefix — always define monitoring/utility functions in `public`.

### budget_periods UNIQUE constraint with nullable cost_center_id
- `UNIQUE (tenant_id, cost_center_id, period_key)` does NOT enforce uniqueness when `cost_center_id IS NULL` because NULL ≠ NULL in PostgreSQL.
- Fix: use two partial unique indexes: one `WHERE cost_center_id IS NULL` on `(tenant_id, period_key)`, and one `WHERE cost_center_id IS NOT NULL` on `(tenant_id, cost_center_id, period_key)`.

### apply_append_only_rls() is NOT for mixed-mutability tables
- `platform.apply_append_only_rls()` creates restrictive UPDATE and DELETE policies. Do not call it on tables where any field must be updatable (e.g., `budget_reservations.status`, `budget_periods.reserved_usd`).
- For hybrid tables: create custom RLS — block DELETE with a restrictive policy, allow INSERT + UPDATE, add tenant isolation SELECT policy manually.

### Turbopack + Windows directory junctions (node_modules in worktrees)
- The LESSONS_LEARNED workaround `cmd /c mklink /J node_modules ..\node_modules` works for webpack-based `next dev` but Turbopack (Next.js 16 default) panics with "Symlink points out of filesystem root" on Windows junctions that traverse deep paths.
- Workaround: run `next dev --no-turbo` (webpack mode) in the launch.json `runtimeArgs` when using worktrees on Windows.
- Or: copy the files being developed to the main repo temporarily for preview validation.

### Artifact tables and the settlement_records / evaluation_artifacts sequential dependency
- `settlement_records.reservation_id` FKs to `budget_reservations.id` — budget_reservations must exist before settlements.
- `evaluation_artifacts.estimate_id` FKs to `estimate_artifacts.id` — estimates must exist before evaluations.
- Ingest flow for run_started: (1) task type lookup → (2) run INSERT → (3) fire-and-forget: recommendation artifact → estimate artifact → budget period upsert → reservation.
- Ingest flow for run_completed: fire-and-forget: evaluation artifact → settle reservation. Order matters: evaluation reads estimate FK first.

### estimate_artifacts.run_request_id vs runs.id
- In Phase 1, there is no `run_requests` table. `estimate_artifacts.run_request_id` is an application-level reference to `runs.id`.
- The DB FK to `run_requests.id` is intentionally deferred to Phase 3. Do not add it until that table exists.
- The UNIQUE index `ON estimate_artifacts(run_request_id)` enforces one estimate per run without needing the FK.

### Supabase JS v2 — insert() vs upsert() for onConflict
- `supabase.from('table').insert({...}, { onConflict: '...' })` causes a TypeScript compile error — the `options` type for `insert()` only accepts `{ count }`.
- `onConflict` and `ignoreDuplicates` are options on `upsert()` only.
- Correct pattern for "create if not exists": `supabase.from('table').upsert({...}, { onConflict: 'col1,col2', ignoreDuplicates: true })`.
- This generates `INSERT ... ON CONFLICT (col1, col2) DO NOTHING` — safe to call concurrently.

### ROUND(float8, int) does not exist in Postgres — always cast to ::numeric
- `AVG()`, `PERCENTILE_CONT()`, and arithmetic on `NUMERIC` columns often returns `double precision` (float8).
- `ROUND(double precision, integer)` does not exist in Postgres — calling it gives: `function round(double precision, integer) does not exist`.
- `ROUND(numeric, integer)` does exist. Fix: wrap the entire aggregate+FILTER expression in parentheses and cast: `ROUND((AVG(...) FILTER (...))::numeric, 1)`.
- Migration 020 (`invariant_report`) already uses `::numeric` — apply the same pattern everywhere. Migration 022 had this bug; fixed via `CREATE OR REPLACE`.
- The FILTER clause is part of the aggregate call and must sit inside the cast parentheses: `(AVG(x) FILTER (WHERE ...))::numeric`, not `AVG(x)::numeric FILTER (WHERE ...)`.

### PostgREST only exposes the public schema by default
- `supabase.schema('cost_intelligence').from('task_types')` silently returns `{ data: null }` at runtime — PostgREST does not expose non-public schemas unless explicitly configured.
- The `authenticator` role is reserved in Supabase and cannot be altered to expose schemas via SQL.
- Fix: create `SECURITY DEFINER` functions in the `public` schema that internally query the private schemas. Call them via `supabase.rpc('fn_name', args)`. This is the same mechanism `invariant_report()` uses.
- Pattern: one public function per cross-schema operation (`get_task_type_id`, `write_run_started_artifacts`, `ingest_telemetry_event`, etc.). Functions own the cross-schema logic; TypeScript just calls them.
- Never fall back to a sentinel UUID (`000...000`) when a tenant/company ID is missing — skip the write instead and log clearly.

### Code review agent findings triage (Phase 1 review)
- The code review agent flagged 9 findings on the Phase 1 diff. Key dispositions:
  - Sentinel tenant UUID (`000...000` fallback for null `company_id`) — always a real finding; fix immediately.
  - Non-serializable financial updates — acceptable in Phase 1 dark launch; Phase 3 gate item.
  - Fire-and-forget failure invisibility — Phase 2 observability work.
  - Double-EXECUTE pattern in `apply_append_only_rls()` — verify in DB rather than changing the already-applied migration; it worked correctly.
  - `any` casts on RPC responses — easy fix, address with the tenant UUID fix in the same commit.

---

## Estimation Dashboard Architecture

### Three truth surfaces — never mix
- `estimate_artifacts` = decision truth (what the estimator said before the run)
- `evaluation_artifacts` = outcome truth (what actually happened)
- `runs` + `agent_events` + `telemetry.raw_events` = execution truth
- Never blend estimate and actual into a single "representative cost" figure in the UI.
- Never exclude incomplete telemetry silently — always show the denominator ("N of M complete evaluations").

### Canonical metric location split
- **SQL-derived metrics** → `SECURITY DEFINER` functions in `public` schema (migration 022). Bucket status logic, calibration readiness, accuracy aggregates — all owned by the DB function.
- **TypeScript-derived metrics** → `src/lib/cost-intelligence/estimation-metrics.ts`. Failure mode classification, signed error, band containment, replayability — all owned by this module.
- **Never implement metric logic inline in a dashboard component.** If a component needs a derived value, it imports from `estimation-metrics.ts` or reads a SQL function result. This is the only protection against dashboard logic drift.

### Dashboard logic drift — the primary long-term UI risk
- TS-derived calculations, SQL-derived calculations, and artifact semantics can diverge gradually if metric logic is scattered.
- Prevention: one module owns TS metrics (`estimation-metrics.ts`), one migration owns SQL metrics (022). If you add a metric, add it in exactly one place and import everywhere else.
- `estimation-metrics.ts` is the single source of truth for: failure mode, signed error, band containment, token error %, replayability, error severity thresholds, failure mode labels, estimate explanation lines.

### Failure mode is derived, never stored
- `EstimationFailureMode` is computed at API response time from stored artifacts. It is never a DB column.
- Phase 1 canonical failure modes: `context_size_unknown`, `output_expansion`, `complexity_mismatch`, `pricing_table_stale`, `context_window_pressure`, `within_tolerance`, `insufficient_data`, `unknown`.
- The most common Phase 1 failure mode is `context_size_unknown`: `prompt_chars = 0` in the feature snapshot because the ingest endpoint cannot observe actual prompt content at `run_started` time. The estimator defaults to 250-token system overhead, which is catastrophically wrong for large-context tasks (e.g., a 365KB code diff = ~91,250 actual input tokens).

### Telemetry completeness must be visible above the fold
- Accuracy metrics computed on incomplete telemetry are worse than no metrics — they silently miscalibrate the system.
- Always filter accuracy aggregates with `WHERE telemetry_status = 'complete'`.
- Always show the completeness denominator: "Based on N complete evaluations of M total."
- The telemetry completeness panel is not optional UX — it is a data integrity control.

### Schema freeze gate logic
- Schema freeze must be a deliberate manual declaration, not an automatic threshold crossing.
- The gate checklist (in `public.get_calibration_readiness()`): missing_features = 0, all_recomputable, incomplete < 10%, no unevaluated estimates, ≥1 eligible bucket.
- Showing a bucket as "eligible" in the UI does not trigger calibration. Phase 2 is a deliberate decision.

### Counterfactual replay — do not build yet
- "What would the estimate be using today's calibration?" is the most valuable future component.
- Do not build until: ≥30 complete observations per bucket, stable calibration exists, and drift is measurable.
- `is_recomputable = true` on evaluation artifacts is the precondition that makes replay possible when the time comes.

### Smart push script — never do bare git push from this repo
- `scripts/push.ps1` is the canonical push path. It: (1) runs the migration linter if new migrations are in the diff, (2) stages and commits all modified doc files (sessions/, docs/, LESSONS_LEARNED.md, AGENTS.md), (3) runs git push. One workflow, one push.
- A Claude Code PreToolUse hook (`scripts/hooks/check-git-push.py`) intercepts bare `git push` Bash calls and blocks them, redirecting to `push.ps1`. The hook outputs `{"decision":"block","reason":"..."}` JSON to stdout; Claude Code parses this and shows the reason text to Claude.
- A git pre-push hook (`.githooks/pre-push`) blocks manual CLI pushes with the same redirect. Activated by `git config core.hooksPath .githooks`.
- `PUSH_SCRIPT_RUNNING=1` env var signals to the git hook that it's being called from inside `push.ps1` — allows the internal `git push` through without recursion.
- Bypass: `pwsh scripts/push.ps1 --no-doc-check` (emergencies) or `git push --no-verify` (skips git hook only).
- PreToolUse hook fires on EVERY Bash call — the script exits 0 immediately if the command isn't a git push, so overhead is negligible.

### Build order for estimation dashboard (vertical slices)
1. Single run drilldown (`/dashboard/estimation/runs/[id]`) — build first, debug the live miss.
2. Overview with headline metrics + biggest misses table — build second.
3. Bucket accuracy table — build third.
4. Calibration readiness page — build at Phase 2 gate.
