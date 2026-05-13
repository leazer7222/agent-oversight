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

| Agent | Owner | agent_id | Location |
|---|---|---|---|
| `context-agent` | `reformai` | `40b5e259-5b28-44fd-9c5b-e758093e5d3d` | `/agents/library/context-agent/` |
| `marketing-agent` | `reformai` | `761c56f6-4de8-4859-974a-43d964de62f0` | `/agents/library/marketing-agent/` |



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

**Base URL:** `https://agent-oversight.vercel.app`
**Auth:** `x-agent-secret: ChArles-Clint0n-Leazer-Jr.-1s-the-B3st`

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/ingest` | POST | Emit run events (`run_started`, `run_completed`) |
| `/api/project-state/[tag]` | GET | Read project state (current_state, todo, lessons) |
| `/api/project-state` | PUT | Write project state |

---

## 7. Naming Conventions

- Agent names: `snake_case` (e.g. `context_agent`, `email_summarizer`)
- Owner values: `reformai`, `afterglow`, `personal`
- Directory names match agent name exactly
- `run_id`: UUID v4, generated per run
