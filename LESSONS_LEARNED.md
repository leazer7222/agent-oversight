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
 
 ### Python SDK (`oversight.py`)
 - The SDK is used for reporting run status and steps. 
 - Use `client.run()` as a context manager to ensure `run_completed` is emitted even if the script fails.
 - Add the `python-sdk` directory to `sys.path` to import `oversight` if the agent is in a deep subdirectory.

