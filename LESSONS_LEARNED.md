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
