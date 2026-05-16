# Agent Standards

This document defines the standards every agent in the system must meet.
These rules apply to all agents across all companies (ReformAI, AfterGlow, Personal).

# Document Role
Source of truth for:
- individual agent implementation standards
- runtime contract requirements
- telemetry emission requirements
- agent lifecycle expectations

Should live here:
- required agent files/schema/contract rules
- run lifecycle event requirements
- agent-level naming and runtime conventions

Should NOT live here:
- live agent inventory/status tracking
- phased platform strategy and roadmap decisions

Related documents:
- Agent inventory/status snapshots: `docs/AGENTS.md`
- Repo-wide engineering standards: `docs/repo-standards.md`
- Strategic architecture/tradeoffs: `docs/AI_AGENT_INFRASTRUCTURE_MASTER_DOCUMENT.md`
- Operational continuity checkpointing: `docs/HANDOFF_PROTOCOL.md`
- MVP sequencing roadmap: `docs/MVP_IMPLEMENTATION_ROADMAP.md`
- Concise chronological lessons: `docs/LESSONS_LEARNED.md`
- Project entrypoint: `docs/README.md`

---

## 1. Identity

Every agent has a permanent, stable identity. These never change after registration.

| Field | Type | Description |
|---|---|---|
| `agent_id` | UUID | Stable identifier. Generated once, never changed. |
| `name` | string | Human-readable name. Snake case. e.g. `context_agent` |
| `description` | string | One sentence. What it does and why it exists. |
| `owner` | string | Which company/project owns it. e.g. `reformai`, `afterglow`, `personal` |
| `version` | semver | e.g. `1.0.0`. Bump minor for new capabilities, patch for fixes. |
| `mcp_dependencies` | string[] | List of MCP server names this agent requires. Empty array if none. |

---

## 2. Registration

Before an agent can run, it must be registered in Supabase.

### Steps
1. Copy `/agents/library/_template/` to the appropriate location:
   - Reusable/generic agent: `/agents/library/<name>/`
   - Company-specific deployment: `/agents/instances/<company>/<name>/`
2. Fill in `agent.json` with real values (generate a UUID for `agent_id`)
3. Write a clear `README.md`
4. Register in Supabase `agents` table — insert a row matching `agent.json`
5. Add the agent to the index below

### Agent Index

| Agent | Owner | agent_id (definition) | Location | Status |
|---|---|---|---|---|
| `context-agent` | `reformai` | `40b5e259-5b28-44fd-9c5b-e758093e5d3d` | `/agents/library/context-agent/` | Active |
| `marketing-agent` | `reformai` | `761c56f6-4de8-4859-974a-43d964de62f0` | `/agents/library/marketing-agent/` | Active |
| `ui-design-agent` | `reformai` | (see agent.json) | `/agents/library/ui-design-agent/` | Active |
| `audit-agent` | `reformai` | (see agent.json) | `/agents/library/audit-agent/` | Active |
| `optimization-agent` | `reformai` | (see agent.json) | `/agents/library/optimization-agent/` | Active |
| `code-review-agent` | `reformai` | `f9a8b7c6-d5e4-4f3a-8b2c-1d0e9f8a7b6c` | `/agents/library/code-review-agent/` | Active |



---

## 3. Runtime Contract

Every agent run must follow this contract exactly.

### On start
Emit `run_started` to the oversight API:
```
POST https://agent-oversight.vercel.app/api/ingest
x-agent-secret: <secret>
Content-Type: application/json

{
  "agent_id": "<agent_id>",
  "event": "run_started",
  "run_id": "<uuid>"
}
```

### On completion
Emit `run_completed` to the oversight API. Include cost data if available:
```json
{
  "agent_id": "<agent_id>",
  "event": "run_completed",
  "run_id": "<same uuid as run_started>",
  "tokens_in": 1200,
  "tokens_out": 340,
  "cost_usd": 0.0042
}
```

### run_id rules
- Generate a fresh UUID at the start of each run
- Use the same `run_id` for both `run_started` and `run_completed`
- Never reuse a `run_id` across runs

---

## 4. Required Files

Every agent directory must contain these files:

```
<agent-name>/
├── agent.json       # Identity manifest (see template)
├── README.md        # What it does, tools used, owner, setup instructions
└── LESSONS.md       # Standing rules specific to this agent (start empty)
```

---

## 5. agent.json Schema

```json
{
  "agent_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "name": "agent_name",
  "description": "One sentence describing what this agent does.",
  "owner": "reformai",
  "version": "1.0.0",
  "mcp_dependencies": []
}
```

---

## 6. Oversight API Reference

**Base URL (local):** `http://localhost:3000`
**Base URL (production):** `https://agent-oversight.vercel.app` (has Vercel SSO — use local for agent runs)
**Auth:** `x-agent-secret: <value of INGEST_SECRET in .env.local>`

### Ingestion (write path — agents use these)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/ingest` | POST | Emit run lifecycle events and step events |
| `/api/project-state/[tag]` | GET | Read project state (current_state, todo, lessons) |
| `/api/project-state` | PUT | Write project state |

#### Ingest event types

| Event | Writes to | Purpose |
|---|---|---|
| `run_started` | `runs` + `agent_events` | Begin a run; sets `timeout_at`, `parent_run_id` |
| `run_completed` | `runs` + `agent_events` | Mark run success; sets `cost_reported` |
| `run_failed` | `runs` + `agent_events` | Mark run failure with error category prefix |
| `run_step` | `agent_events` only | Mid-run trace point; does NOT touch `runs` |

#### run_step payload fields
```json
{
  "agent_id": "<uuid>",
  "event": "run_step",
  "run_id": "<uuid>",
  "message": "human readable description",
  "severity": "info | warning | error",
  "duration_ms": 1234,
  "tokens_in": 0,
  "tokens_out": 0,
  "cost_usd": 0.0
}
```

### Read APIs (dashboard uses these — no agent auth required, service-role only)

| Endpoint | Method | Filters | Purpose |
|---|---|---|---|
| `/api/agents` | GET | `status`, `company`, `limit`, `offset` | Agent list with cost summary |
| `/api/agents/[id]` | GET | — | Full agent detail + recent 10 runs |
| `/api/agents/[id]/runs` | GET | `status`, `limit`, `offset` | Paginated run history per agent |
| `/api/runs` | GET | `status`, `agent`, `errors_only`, `limit`, `offset` | Cross-agent run list |
| `/api/runs/[id]` | GET | — | Full run with events + outputs |
| `/api/runs/[id]/events` | GET | — | Chronological event trace + cumulative summary |
| `/api/cost` | GET | `group_by` (agent\|project), `company`, `limit` | Cost/token aggregates |
| `/api/errors` | GET | `agent`, `category`, `since`, `limit`, `offset` | Failed runs + error breakdown |

---

## 7. Naming Conventions

- Agent names: `snake_case` or `kebab-case` (e.g. `context-agent`, `marketing-agent`)
- Owner values: `reformai`, `afterglow`, `personal`
- Directory names match agent name exactly
- `run_id`: UUID v4, generated per run

---

## 8. Definition vs. Instance Pattern

Every agent is composed of two distinct registered entities:

**Capability definition** (`agent_definitions` table) — tenant-neutral, versioned library entry.
- Name: `{capability}` — no tenant prefix (e.g. `code-review-agent`, `marketing-agent`)
- Defines: `input_schema`, `output_schema`, `config_schema`, `capability_tags`, `version`
- Shared across all tenants that deploy this capability
- `agent.json` in the library directory stores the definition UUID

**Operational instance** (`agents` table) — tenant/project-scoped deployment.
- Name: `{tenant}.{capability}` (e.g. `reformai.code-review-agent`)
- Defines: `company_id`, `project_id`, `parent_agent_id`, governance params, `config_overrides`
- `config_overrides` holds instance-specific context: standards refs, jurisdiction, exclusions
- `can_be_triggered_by` enforces authorization — only listed parent agents may invoke

The **hierarchy page displays instances only**. Definitions are a library catalog, not
operational nodes. A definition has no run history, status, or hierarchy position.

### Instance config_overrides pattern

```json
{
  "tenant": "reformai",
  "project": "agent-oversight",
  "review_mode": "pre-push",
  "context_scope": {
    "standards_refs": ["docs/PLATFORM_ARCHITECTURE.md", "docs/repo-standards.md"],
    "architecture_docs": ["docs/PLATFORM_ARCHITECTURE.md"]
  },
  "review_scope": "agent-oversight repository",
  "exclusions": ["personal", "afterglow"]
}
```

---

## 9. Output Types

Agents write artifacts to `agent_outputs` with an `output_type` that identifies the artifact
kind. The CHECK constraint enforces the allowed set.

| output_type | Produced by | Description |
|---|---|---|
| `marketing_brief` | marketing-agent | Strategic brief and positioning |
| `lp_blueprint` | marketing-agent / orchestrator | Landing page structure |
| `strategy_summary` | marketing-agent | Executive strategy summary |
| `context_snapshot` | context-agent | Project context snapshot |
| `ui_components` | ui-design-agent | React component specifications |
| `code_review` | code-review-agent | Immutable findings artifact with severity taxonomy |
| `other` | any | Catch-all for non-standard outputs |

**Important semantic distinction:**
- `agent_outputs` (output_type = `code_review`) — artifacts produced BY an agent about
  code or other external subjects. The subject is a code diff.
- `agent_qa_results` — evaluations OF an agent's operational performance. The subject is
  an agent run. Do not use `agent_qa_results` for code review findings.
