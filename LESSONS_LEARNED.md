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
