# Lessons Learned

Read this file at the start of every session and apply these rules throughout.
Add new lessons at the end of each session.

# Document Role
Source of truth for:
- concise chronological lesson log
- dated operational discoveries and practical corrections

Should live here:
- short, direct lessons tied to real incidents/decisions
- actionable rules derived from debugging and execution experience

Should NOT live here:
- deep architecture strategy essays
- phased roadmap sequencing details
- tactical current-session checkpoint state

Related documents:
- Strategic architecture and deep tradeoffs: `docs/AI_AGENT_INFRASTRUCTURE_MASTER_DOCUMENT.md`
- Operational continuity checkpoints: `docs/HANDOFF_PROTOCOL.md`
- MVP sequencing roadmap: `docs/MVP_IMPLEMENTATION_ROADMAP.md`
- Agent inventory/status: `docs/AGENTS.md`
- Agent implementation/runtime standards: `docs/agent-standards.md`
- Repo-wide engineering standards: `docs/repo-standards.md`
- Project entrypoint: `docs/README.md`

---

## Next.js / React

### Server vs Client Components
- Components that use `onMouseEnter`, `onMouseLeave`, or any event handler MUST have `"use client"` at the top.
- Server components should use Tailwind hover classes (`hover:text-white/80`) instead of inline JS event handlers — no `"use client"` needed.
- `motion.a`, `motion.div` etc. from framer-motion require `"use client"` — framer-motion is a client-only library.
- All page sections using framer-motion animations must have `"use client"` as line 1.

### framer-motion (v12+)
 
 ## Next.js 15 Performance, Security & Stability
 
 - **Avoid Experimental Versions**: Next.js `16.x` or other unreleased versions can cause massive build-time overhead and memory leaks on Windows. Use stable versions (e.g., **`15.5.14`**) for reliable local development.
 - **Security Patches**: Always check for critical vulnerabilities (like CVE-2025-66478). Version **`15.5.14`** is the recommended stable and patched release for the 15.x branch.
 - **Disable Experimental Compiler**: The `reactCompiler: true` flag in `next.config.ts` is experimental and can significantly increase RAM usage and compile times in complex projects. Only enable it if truly needed for performance optimization.
 - **Memory Usage**: Next.js dev servers can easily consume 4GB+ of RAM. If the system is slowing down, consider increasing the Node.js memory limit via `NODE_OPTIONS=--max-old-space-size=4096`.
 
 ---
 
 ## Development Environment (Windows)
 
 - **PowerShell Execution Policy**: If `npm` scripts are blocked, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` to permit local script execution.
 - **Missing Dependencies**: When migrating components between projects, always ensure `framer-motion` is explicitly added to `package.json` if animations are used.
 
 ---
 
 ## Framer Motion Optimization
 
 - **Avoid Heavy Effects per Component**: 6+ cards all using `backdrop-filter: blur`, 3D transforms (`rotateX`, `rotateY`), and `whileInView` observers can lag the browser, especially on higher resolutions or lower-end GPUs.
 - **Correct Text Animation**: Do NOT use `spring.get()` directly in the JSX render function. It won't trigger re-renders and is inefficient. Use `useTransform(spring, (v) => ...)` and pass the resulting `MotionValue` to a `motion.span` for smooth, efficient text updates.
 - **Infinite Animations**: Be careful with `repeat: Infinity` on many elements. If the page re-renders frequently (e.g., during HMR), ensure animations are properly cleaned up or don't trigger unnecessary layout shifts.
- **Large Assets**: Avoid using massive raw images (>5MB) in `img` tags. Use Next.js `<Image />` component or optimize the source files to prevent browser tab crashes.
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
### UI Design & Generation (2026-03-24)

- **Direct Generation Fallback**: When external API quotas (Gemini/OpenAI) are hit by agent scripts, the orchestrator/agent can directly generate high-fidelity UI code manually as a fallback. This maintains velocity without sacrificing design standards.
- **Icon Dependencies**: The `ui-design-agent` standard components rely heavily on `lucide-react`. This MUST be included in the project's `dependencies` to avoid build errors.
- **Port Management**: If Next.js detects port 3000 is in use (e.g., by a previous failed run or other processes), it will increment to 3001. Local previews should check the terminal output for the correct port.
- **Workspace Conflicts**: Next.js may issue warnings about inferred workspace roots if multiple lockfiles are present (e.g., in `C:\Users\cjlea\` and `C:\Users\cjlea\AgentProjects\agent-oversight\`). Removing the root-level lockfile (`C:\Users\cjlea\package-lock.json`) is the recommended cleanup.
- **Responsive Animations**: Always use `whileInView` in Framer Motion for scroll-triggered reveal animations on landing pages to ensure smooth delivery.

---

## Agent Oversight & OversightClient (2026-03-30)

- **OversightClient URL**: Pass the base domain only (e.g. `http://localhost:3000`) — the SDK appends `/api/ingest` automatically. Never pass the full endpoint path or it doubles up and 404s.
- **Env var name**: The secret is stored as `INGEST_SECRET` in `.env.local`, not `OVERSIGHT_SECRET`. Always fall back to both: `os.environ.get("OVERSIGHT_SECRET") or os.environ.get("INGEST_SECRET")`.
- **Windows stdout encoding**: Unicode characters (`→`, `—`) in `print()` statements crash on Windows with cp1252 encoding. Add `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` at the top of any agent that prints non-ASCII output.
- **Vercel SSO protection**: The preview deployment URL has Vercel SSO — Python agents cannot POST to `/api/ingest` without a bypass token. Default `OVERSIGHT_URL` to `http://localhost:3000` for local runs.
- **Oversight as non-fatal**: Wrap `OversightClient` usage in `try/except` so that telemetry failures never block the agent's actual work.

## Repo Organization (2026-03-30)

- **All docs in docs/**: `AGENTS.md`, `LESSONS_LEARNED.md`, `README.md` belong in `docs/`. Only `CLAUDE.md` stays at root (Claude Code requires it there).
- **Session state must be updated every session**: `tasks/current-state.md`, `tasks/todo.md`, `tasks/lessons.md` are not optional. Going stale (as happened between 2026-03-21 and 2026-03-30) means the next session starts blind.
- **Single session log dir**: Use `session-logs/YYYY-MM-DD_<project>.md`. Do not create a separate `sessions/` directory.
- **No __init__.py in agent dirs**: Agents are run as scripts, not imported as packages. `__init__.py` in `agents/` and `agents/library/` serves no purpose and should not exist.
- **optimization-agent is the enforcement mechanism**: Run `python agents/library/optimization-agent/agent.py` any time structural changes are made to verify compliance.

## Documentation Governance (2026-05-12)

- Assign clear source-of-truth ownership per document type to reduce duplication drift.
- Keep strategic reasoning in `AI_AGENT_INFRASTRUCTURE_MASTER_DOCUMENT.md`; keep this file concise and chronological.
- Keep tactical continuity and active blockers in `HANDOFF_PROTOCOL.md`, not in standards documents.

## Live Schema Verification (2026-05-12)

- PostgREST OpenAPI spec (`GET /rest/v1/`) is sufficient for table/column/FK discovery but cannot expose CHECK constraint values, view SQL bodies, or RLS policy expressions — use Supabase SQL editor for those.
- `information_schema` and `pg_catalog` are not accessible via PostgREST by default; direct DB access or Supabase SQL editor required for constraint details.
- Querying `?limit=0&select=*` returns an empty array `[]` for empty tables — column names cannot be derived from empty row responses; OpenAPI spec is the fallback for empty tables.
- Live data reveals operational truth: all 51 run rows had null cost_usd — financial dashboards would show zero even with a working UI. Schema fields and operational discipline are separate concerns.
- `agent_events` existing live with zero rows is categorically different from `agent_events` not existing — a write path must be added to the ingest route to activate observability.
- When a reconciliation strategy is drafted without live DB verification, schema details can diverge significantly from reality — always verify live before writing migrations.

## Phase 1 Reconciliation Review (2026-05-12)

- Always verify referenced files exist before treating an audit as authoritative — Codex analyzed `001_initial_schema.sql` but this file was never committed to the repo.
- Table existence in live DB does not equal observability — `agent_events` can exist live and receive zero writes because the ingest route never inserts to it.
- `null cost_usd` is ambiguous without a `cost_reported BOOLEAN` sentinel; treat nullable numeric fields as unreliable for dashboard aggregation unless a sentinel confirms reporting occurred.
- Source-of-truth governance is a design decision: migrations + documented contracts are canonical (what the system *should* be); live DB is operational reality (what it *is*). Never reverse these.
- `runs.id` is already the canonical identifier in the ingest route — no dual-identifier issue exists at the runtime level; the confusion was introduced by an inferred migration file.
- Zombie runs (stuck in `started` forever) are a silent reliability risk; `timeout_at` field on `runs` is required to support future detection/cleanup.

## Reconciliation Implementation Planning (2026-05-13)

- Live verification can invalidate architecture assumptions; reconciliation strategy must follow verified operational reality while migrations remain the governance source of truth.
- PostgREST introspection has a hard ceiling: view SQL bodies, CHECK constraint expressions, and RLS policies require Supabase SQL editor access — document this dependency before writing a migration plan.
- Zero cost observability despite schema support is an agent discipline problem; agents must explicitly call `ctx.report()` after LLM calls for cost data to appear in runs rows.
- TypeScript interface mismatches with live DB column names are a silent UI correctness risk — validate interface field names against live OpenAPI spec before beginning dashboard work.
- `agent_events` ingest write must guard on `company_id` non-null; agents without company association must be handled as a conditional, not an error.

## Schema Contract Stabilization (2026-05-13)

- Ingest/API code can become a hidden schema contract; migrations must be reconciled immediately when API column assumptions diverge.
- Treat `runs` as lifecycle summary records and `agent_events` as append-only traces; blending the two semantics causes observability ambiguity.
- `project_state` must have one explicit contract shape (typed columns vs JSON envelope); dual assumptions create guaranteed drift.
- Output taxonomies (`agent_outputs.output_type`) need governance; runtime-emitted values must be represented in DB constraints before adoption.
- Source-of-truth ambiguity is an infrastructure risk category and should block Phase 2 feature expansion until resolved.

## Platform Architecture & Hierarchy UI (2026-05-13)

### Control-plane philosophy
- Agent Oversight is best understood as an **operational ledger with a governance enforcement surface** — not a context broker, memory system, orchestration engine, or cognitive architecture. Neutrality is the source of its authority.
- The key boundary: Agent Oversight records what happened and enforces operational rules. It does not participate in domain decisions, store content, or implement intelligence semantics.
- Personal, After Glow, and ReformAI are **isolated tenants** sharing governance infrastructure, not a context hierarchy. Resist any architecture or UI feature that implies cross-tenant semantic sharing.
- Canonical reference: `docs/PLATFORM_ARCHITECTURE.md`.

### Visual semantics for hierarchy views
- **Indentation, not edges.** The hierarchy page uses an indented tree (file-browser / org-chart register) instead of edges with directionality. This is a deliberate choice: graph edges imply execution direction or data flow. Indentation communicates containment without that implication.
- **Structure views must not become runtime views.** The single design constraint for a topology page: it should answer "what is the operational structure?" not "what is currently running?" These are separate concerns and must live on separate pages.
- **The idle-test invariant.** If a topology view would look different when agents are actively running versus idle, it has execution-state elements that do not belong on a structure page.
- **Status color semantics matter.** Use blue for "active/healthy" (not green). Green in operational interfaces implies "currently running." Blue implies "operational and healthy." The distinction prevents the topology view from being misread as a live execution monitor.
- **Node type reflects governance role, not execution capability.** Orchestrator, team, and worker badges communicate organizational authority, not execution order or data flow.

### Avoiding execution-semantic drift in dashboards
- Graph rendering libraries (React Flow, Dagre, vis.js) bring execution-graph metaphors into the component tree and signal to future contributors that directed edges are appropriate. Use a recursive tree renderer with Tailwind indentation instead.
- Do not add polling or live-state indicators to topology views. Once a topology page begins showing live execution state, it will be treated as a real-time monitor and its structural purpose will be lost.
- The hierarchy page has no "run" or "connect" actions. Actions with governance implications (restructuring the hierarchy) must not be added until their governance semantics are fully defined.

## Phase 1–3 Execution (2026-05-12)

- **Supabase MCP on Windows**: `claude mcp add` with `-y` fails in PowerShell. Edit `~/.claude.json` directly to add MCP server entries; restart Claude Code to activate.
- **Git worktree node_modules**: Worktrees don't inherit node_modules from the main checkout. Create a directory junction: `cmd /c mklink /J node_modules ..\node_modules`. Never run `npm install` from within the worktree.
- **Supabase GenericStringError**: Without generated TypeScript types, `supabase.from('table').select(...)` returns `GenericStringError` as the data type. Cast as `any[]` short-term; generate types via `mcp__supabase__generate_typescript_types` long-term.
- **cost_reported sentinel pattern**: `runs.cost_reported BOOLEAN NOT NULL DEFAULT false` distinguishes "agent completed but never reported cost" from "agent reported zero cost". Set `cost_reported = true` only when `cost_usd` is explicitly included in a terminal event payload.
- **agent_events non-fatal write discipline**: Wrap the agent_events INSERT in a non-fatal try/catch block. Guard on `company_id !== null` before inserting — agents without company association must not crash the run. Telemetry failure must never block agent execution.
- **Error taxonomy bracket prefix**: Python SDK categorizes errors as `[quota_exceeded]`, `[auth_error]`, `[network_error]`, `[llm_error]`, `[validation_error]`. Stored in `runs.error`. The `/api/errors` endpoint extracts the category via regex `^\[([^\]]+)\]` for grouping/filtering.
- **LLM token capture**: OpenAI usage is in `response.usage.prompt_tokens` / `completion_tokens`. Gemini usage is in `resp.usage_metadata.prompt_token_count` / `candidates_token_count`. Always capture after the LLM call; pass to `run_completed` as `tokens_in`, `tokens_out`.
- **Windows stdout emoji crash**: Unicode characters in `print()` crash on Windows cp1252. Add `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` as the first statement in every agent script.
- **run_step event bypasses runs table**: `run_step` events write only to `agent_events`. The ingest route returns early after the insert without touching the `runs` table. This is intentional — steps are traces, not lifecycle state transitions.
- **Pagination helper pattern**: `parsePagination(url)` extracts `limit` (capped at 200) and `offset` from URL query params. `paginationMeta({limit, offset}, returnedCount)` computes `has_more`. Both live in `src/lib/api/pagination.ts`.

## Agent Backfill + Dev Environment Fix (2026-05-13, continued)

- **Never use HTTP round-trips from server components to own API routes.** `apiFetch` calls `localhost:PORT` — if the port is wrong (auto-assigned by preview tool, not matching the `BASE` constant), all server component pages silently return empty data. Solution: call Supabase directly from server components, or set `PORT` in `.env.local` to match the fixed dev port.
- **`PORT` env var fixes `apiFetch` fallback.** `apiFetch` falls back to `http://localhost:${process.env.PORT ?? 3000}`. Set `PORT=3002` in `.env.local` and use port 3002 in `launch.json` so dev always binds to the same port.
- **`.env.local` corruption pattern.** Multiple append operations without newlines produce a single-line file that Next.js cannot parse. All env vars become undefined. Symptom: all Supabase queries fail silently, dashboard shows zeros. Rewrite the file with one key=value per line.
- **Verify schema columns before writing queries.** The `agents` table has no `display_name` column — only `name`. Always run `SELECT column_name FROM information_schema.columns WHERE table_name = '...'` before writing a SELECT with assumed columns.
- **Inspect run history before deleting duplicate agent rows.** Keep the row with real run history even if its UUID looks manually generated. Delete the one with zero runs.
