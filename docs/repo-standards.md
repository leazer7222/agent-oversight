# Agent Oversight — Repository Organization Standards

> **This is the authoritative standard for all agent projects under MasterAgenticFlow.**
> Every agent, script, output, and config MUST conform to this structure.
> The `optimization-agent` enforces these rules automatically on each run.

# Document Role
Source of truth for:
- repository-wide engineering and organization standards
- repo conventions and file-placement rules
- cross-repo hygiene and process expectations

Should live here:
- canonical repo structure and naming conventions
- rules for scripts/outputs/docs placement
- repository governance conventions that apply to all contributors/tools

Should NOT live here:
- strategic architecture evolution narratives
- active operational run-state/checkpoint logs

Related documents:
- Agent inventory/status snapshots: `docs/AGENTS.md`
- Agent implementation/runtime standards: `docs/agent-standards.md`
- Strategic architecture/tradeoffs: `docs/AI_AGENT_INFRASTRUCTURE_MASTER_DOCUMENT.md`
- Operational continuity state: `docs/HANDOFF_PROTOCOL.md`
- MVP implementation sequencing: `docs/MVP_IMPLEMENTATION_ROADMAP.md`
- Concise chronological lessons: `docs/LESSONS_LEARNED.md`
- Project entrypoint: `docs/README.md`

---

## 1. Canonical Directory Structure

```
agent-oversight/                      ← repo root
├── agents/
│   ├── library/                      ← REUSABLE agent definitions (not company-specific)
│   │   ├── _template/                ← copy this to create a new agent
│   │   │   ├── agent.json
│   │   │   ├── agent.py
│   │   │   ├── README.md
│   │   │   └── LESSONS.md
│   │   └── <agent-name>/             ← one folder per agent, kebab-case
│   │       ├── agent.json            ← REQUIRED
│   │       ├── agent.py              ← REQUIRED
│   │       ├── README.md             ← REQUIRED
│   │       ├── LESSONS.md            ← REQUIRED
│   │       └── prompt.md             ← optional, for LLM system prompts
│   └── instances/                    ← company-specific deployments
│       └── <company>/                ← reformai | afterglow | personal
│           ├── <agent>.config.json   ← instance config (agent_id, overrides)
│           ├── orchestrator.py       ← workflow coordinator for this company
│           └── outputs/              ← ALL run outputs for this company go HERE
│               ├── local_output_*.json
│               ├── team_strategy_*.md
│               └── <project>/        ← generated artifacts (e.g. seller_test/)
├── docs/                             ← standards, specs, architecture docs
│   ├── repo-standards.md             ← THIS FILE
│   └── agent-standards.md            ← agent runtime contract
├── python-sdk/                       ← shared Python SDK
│   └── oversight.py
├── scripts/                          ← all utility/registration/runner scripts
│   ├── register_<agent>.js           ← one per agent
│   └── run_<agent>.py                ← one per standalone runner
├── src/                              ← Next.js app (dashboard UI)
├── supabase/                         ← DB migrations
│   └── migrations/
├── sessions/                         ← current session logs (Claude session-logger)
├── session-logs/                     ← archived session logs
├── tasks/                            ← task management files (current-state, todo, lessons)
├── CLAUDE.md                         ← Claude Code instructions (must stay at root)
└── docs/                             ← ALL documentation lives here
    ├── AGENTS.md                     ← agent index + checklist
    ├── LESSONS_LEARNED.md            ← project-wide lessons
    ├── README.md                     ← project overview
    ├── agent-standards.md            ← agent runtime contract
    └── repo-standards.md             ← THIS FILE
```

---

## 2. What Does NOT Belong at the Repo Root

The following must NEVER be placed at the repo root:

| Violation | Correct Location |
|---|---|
| `run_seller_ui.py` | `scripts/run_seller_ui.py` |
| `register_marketing_agent.js` | `scripts/register_marketing_agent.js` |
| `run_agent.js` | `scripts/run_agent.js` |
| `outputs/` directory | `agents/instances/<company>/outputs/` |
| Duplicate output dirs | Only ONE canonical output dir per company instance |

**Rule:** The root contains only `CLAUDE.md`, config files (`package.json`, `next.config.ts`, `.env.local`), and top-level folders. All documentation (`AGENTS.md`, `LESSONS_LEARNED.md`, `README.md`) lives in `docs/`. No loose scripts, no generated output.

---

## 3. Required Files Per Agent

Every agent in `agents/library/<agent-name>/` MUST have all four files:

| File | Purpose | Required |
|---|---|---|
| `agent.json` | Machine-readable identity manifest | ✅ YES |
| `agent.py` | Core agent logic | ✅ YES |
| `README.md` | Human-readable: what it does, inputs, outputs, owner | ✅ YES |
| `LESSONS.md` | Per-agent standing rules (format: `[date] \| what went wrong \| rule`) | ✅ YES |
| `prompt.md` | LLM system prompt (if agent uses an LLM) | Recommended |

---

## 4. agent.json Schema

Every `agent.json` must contain:

```json
{
  "agent_id": "<UUID — must match Supabase agents.id>",
  "name": "<kebab-case-name>",
  "display_name": "<Human Readable Name>",
  "description": "<One sentence describing what this agent does.>",
  "owner": "<reformai | afterglow | personal>",
  "version": "<semver e.g. 1.0.0>",
  "model": "<default model e.g. gemini-2.5-flash>",
  "mcp_dependencies": []
}
```

Rules:
- `agent_id` must be a real UUID registered in the Supabase `agents` table
- `name` must be kebab-case and match the folder name
- `version` must follow semver (`MAJOR.MINOR.PATCH`)
- `model` must be a known, supported model string

---

## 5. Agent Runtime Contract (Non-Negotiable)

Every agent run MUST:

1. **Generate a unique `run_id`** (UUID) at the start of each invocation
2. **Emit `run_started`** to `/api/ingest` before any processing
3. **Emit `run_completed`** (or `run_failed`) to `/api/ingest` when done — even on error
4. **Report telemetry** on completion: `tokens_in`, `tokens_out`, `cost_usd`
5. **Use `OversightClient`** from `python-sdk/oversight.py` — do not hand-roll telemetry

Pattern:
```python
from oversight import OversightClient

client = OversightClient(url=os.environ["OVERSIGHT_URL"], secret=os.environ["OVERSIGHT_SECRET"])
with client.run(agent_id=self.agent_id, metadata={...}) as run:
    # do work
    run.report(tokens_in=..., tokens_out=..., cost_usd=...)
```

---

## 6. Naming Conventions

| Thing | Convention | Example |
|---|---|---|
| Agent library folder | `kebab-case` | `marketing-agent` |
| Agent instance config | `<agent-name>.config.json` | `marketing-agent.config.json` |
| Scripts | `<verb>_<subject>.py` or `.js` | `register_marketing_agent.js` |
| Output JSON files | `<type>_output_<run_id_short>.json` | `local_output_5fc97d3b.json` |
| Output Markdown files | `<type>_<run_id_short>.md` | `team_strategy_5fc97d3b.md` |
| Supabase agent name | `<company>.<agent-name>` | `reformai.marketing-agent` |

---

## 7. No Hardcoded Paths

**Rule:** Zero hardcoded absolute paths in agent code or scripts.

- All file paths must be derived from the script's `__file__` location or from environment variables
- Environment variables used for configurable paths: `OVERSIGHT_URL`, `OVERSIGHT_SECRET`, `GOOGLE_SERVICE_ACCOUNT_KEY`, `GDRIVE_FOLDER_ID`
- Use `os.path.abspath(os.path.join(os.path.dirname(__file__), "..."))` for relative imports

**Violation pattern to detect and fix:**
```python
# ❌ WRONG
path = "C:/Users/cjlea/AgentProjects/agent-oversight/.env.local"

# ✅ RIGHT
path = os.path.join(os.path.dirname(__file__), "../../../.env.local")
```

---

## 8. Output Management

**Rule:** All generated outputs go to `agents/instances/<company>/outputs/`.

- Root-level `outputs/` directory is a violation — delete it and move contents
- No agent or script writes directly to a user's Desktop or Downloads folder
- Output filenames must include the `run_id` (short UUID) for traceability

---

## 9. Secrets and Environment Variables

| Variable | Purpose |
|---|---|
| `OVERSIGHT_URL` | Base URL for the oversight ingest API |
| `OVERSIGHT_SECRET` | Auth secret for `/api/ingest` |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key (bypasses RLS) |
| `GEMINI_API_KEY` | Google Gemini API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `GOOGLE_SERVICE_ACCOUNT_KEY` | Path to GCP service account JSON key |

Rules:
- All secrets from environment variables — never hardcoded
- `.env.local` is in `.gitignore` — never committed
- Scripts load `.env.local` via `dotenv` or equivalent — no manual parsing

---

## 10. AGENTS.md Registration

Every agent that has a library folder and a Supabase registration MUST appear in `AGENTS.md` under "Registered Agents (Library)" with:
- Name (linked to its library folder)
- Purpose (one line)
- Status: `Active` | `Paused` | `Deprecated`
- Owner

The `optimization-agent` checks AGENTS.md against the disk and Supabase on every run and flags any gaps.

---

## 11. Supabase Registration Requirement

Every agent MUST be registered in both tables:

**`agent_definitions`** — the reusable blueprint:
- `id` (UUID), `name`, `display_name`, `description`, `capability_tags`, `instance_type`, `version`, `source_path`

**`agents`** — the company-specific instance:
- `id` (UUID), `name` (format: `<company>.<agent-name>`), `company_id`, `definition_id`, `agent_type`, `status`

The `agent_id` in `agent.json` must match the `agents.id` in Supabase.

---

## 12. Doc Maintenance — Agents Must Update Their Own Docs

`LESSONS.md` and `README.md` are living documents, not one-time artifacts.

**`LESSONS.md` rules:**
- Must be updated after any run where something went wrong or a non-obvious decision was made
- Format: `[YYYY-MM-DD] | what went wrong | rule going forward`
- If it still reads `_(none yet)_` after the agent has run more than once, it is being neglected

**`README.md` rules:**
- Must be customized beyond the template before the agent is considered production-ready
- Must accurately describe the agent's actual inputs, outputs, and behavior — not copy-paste from the template
- Must be updated if the agent's purpose, model, or output schema changes

**`docs/` updates:**
- If a new standard or convention is established during a session, it must be added to `docs/repo-standards.md` in the same session — not deferred
- `docs/AGENTS.md` must be updated the moment a new agent is added to `agents/library/`

---

## Enforcement

The `optimization-agent` runs these checks automatically:

| Check | What It Validates |
|---|---|
| `missing_files` | Every library agent has all 4 required files |
| `agent_json_schema` | agent.json has all required fields, valid UUID, semver version |
| `agents_md_sync` | AGENTS.md matches disk + Supabase |
| `runtime_contract` | agent.py imports and uses OversightClient |
| `hardcoded_paths` | No absolute paths in agent code |
| `root_clutter` | No scripts or output dirs at repo root |
| `output_location` | Outputs go to instances/<company>/outputs/ only |
| `supabase_sync` | Every disk agent has a Supabase registration |
| `doc_staleness` | LESSONS.md updated beyond placeholder; README.md customized past template |
| `run_activity` | Every active agent has a non-null `last_run_at` in Supabase (has actually run) |

Violations are scored by severity (critical / warning / info) and compiled into a prioritized report.
