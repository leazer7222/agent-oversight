<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

---

# Document Role
Source of truth for:
- agent inventory in this repository
- agent operational status snapshots (active/paused/deprecated intent)
- agent ownership and quick compliance checklist visibility

Should live here:
- registered agent list and ownership
- high-level runtime/compliance checklist references
- links to where each agent lives

Should NOT live here:
- deep implementation/runtime contract specifications
- strategic architecture evolution and roadmap reasoning

Related documents:
- Agent implementation contract: `docs/agent-standards.md`
- Repo-wide standards: `docs/repo-standards.md`
- Strategic architecture/tradeoffs: `docs/AI_AGENT_INFRASTRUCTURE_MASTER_DOCUMENT.md`
- Operational continuity state: `docs/HANDOFF_PROTOCOL.md`
- MVP sequencing roadmap: `docs/MVP_IMPLEMENTATION_ROADMAP.md`
- Concise chronological lessons: `docs/LESSONS_LEARNED.md`
- Project entrypoint: `docs/README.md`

# Agent Standards — Mandatory Checklist

Every agent in this system MUST satisfy all of the following before it is considered real.
Full specification: `/docs/agent-standards.md`
Repo organization standard: `/docs/repo-standards.md`
Template to copy from: `/agents/library/_template/`

## Required to exist
- [ ] Registered in Supabase `agents` table with a stable UUID `agent_id`
- [ ] `agent.json` — machine-readable identity manifest (see template)
- [ ] `agent.py` — core agent logic using OversightClient
- [ ] `README.md` — what it does, what tools/MCPs it uses, who owns it
- [ ] `LESSONS.md` — per-agent standing rules

## Registered Agents (Library)
- **context-agent** ([library](agents/library/context-agent/))
    - Purpose: Retrieves project context from Google Drive.
    - Status: Active
    - Owner: `reformai`
- **marketing-agent** ([library](agents/library/marketing-agent/))
    - Purpose: Strategic marketing executive; produces UI-ready blueprints.
    - Status: Active
    - Owner: `reformai`
- **ui-design-agent** ([library](agents/library/ui-design-agent/))
    - Purpose: High-fidelity UI/UX and Frontend Agent; builds landing pages.
    - Status: Active
    - Owner: `reformai`
- **audit-agent** ([library](agents/library/audit-agent/))
    - Purpose: Quality assurance validator; scores context relevance (1–10) and passes/fails it for downstream agents.
    - Status: Active
    - Owner: `reformai`
- **optimization-agent** ([library](agents/library/optimization-agent/))
    - Purpose: Scans the repo for standards compliance and organizational gaps; produces a prioritized improvement report via LLM.
    - Status: Active
    - Owner: `reformai`


## Required at runtime

- [ ] Emits `run_started` to `/api/ingest` at the beginning of every run
- [ ] Emits `run_completed` to `/api/ingest` at the end of every run
- [ ] Each run has a unique `run_id` (UUID generated per invocation)

## Strongly recommended
- [ ] Reports `tokens_in`, `tokens_out`, `cost_usd` on `run_completed`
- [ ] Declares MCP dependencies in `agent.json`
- [ ] Includes `prompt.md` alongside `agent.py` if the agent uses an LLM system prompt

## Enforcement
Run `python agents/library/optimization-agent/agent.py` to scan the entire repo for violations of the above standards. Output is saved to `agents/instances/reformai/outputs/`.

---

# Hierarchy Metadata

The dashboard `/dashboard/hierarchy` page renders the operational topology of all registered agents, grouped by tenant. It is a governance topology view — an org chart for AI operations — not a runtime execution graph.

## Fields used by the hierarchy page

Every registered agent should have the following fields populated in the `agents` table for correct topology rendering:

| Field | Required | Purpose |
|---|---|---|
| `company_id` | Yes | Assigns the agent to a tenant. Agents without `company_id` are grouped under an unassigned section. |
| `agent_type` | Yes | Controls visual weight and badge color. See types below. |
| `status` | Yes | Operational health indicator (`active`, `paused`, `deprecated`). |
| `name` | Yes | Primary display label. |
| `parent_agent_id` | Recommended | UUID of the parent agent in the hierarchy. Null means root (appears at the top of the tenant section). |
| `depth` | Recommended | Integer depth in the hierarchy: `0` = orchestrator, `1` = team or direct agent, `2` = agent within a team. |
| `display_name` | Optional | Human-readable override for `name`. Displayed instead of `name` if present. |
| `model` | Optional | Model identifier shown as a small metadata badge on the node. |

## Agent types and their hierarchy semantics

| `agent_type` value | Visual treatment | Meaning |
|---|---|---|
| `orchestrator` | Violet badge, full weight | Root of the hierarchy for a tenant. Governs which agents run and in what sequence. |
| `team` | Blue badge, medium weight | Organizational grouping. A team is an agent node with children, not a separate database entity. |
| `worker` (default) | Zinc badge, standard weight | A leaf-level execution agent. Most agents are this type. |

**Important: `agent_type = team` is a visual and organizational grouping only.** It does not imply a separate runtime coordination entity, a shared context scope, a task queue, or any coordination semantics. Teams are agent nodes with children in the `parent_agent_id` graph. The team abstraction exists to make the hierarchy page legible. It does not imply execution dependency or runtime coupling between the team node and its children.

## What parent/child hierarchy does NOT imply

The `parent_agent_id` relationship represents **organizational membership**, not execution dependency.

- A parent agent does not necessarily execute before its children.
- Children do not inherit context, memory, or state from their parent through the hierarchy metadata.
- The hierarchy page will look identical whether all agents are idle or actively running — it shows structure, not activity.
- Execution sequences, data flows, and orchestration logic live in agent code and run records, not in the hierarchy graph.

## Example registration shape (ReformAI)

```
ReformAI Orchestrator       agent_type=orchestrator  parent_agent_id=null      depth=0
└── Context Agent           agent_type=worker        parent_agent_id=<orch_id>  depth=1
└── Marketing Team          agent_type=team          parent_agent_id=<orch_id>  depth=1
    └── Marketing Strategist agent_type=worker       parent_agent_id=<team_id>  depth=2
└── Engineering Team        agent_type=team          parent_agent_id=<orch_id>  depth=1
    └── Engineering Agent   agent_type=worker        parent_agent_id=<team_id>  depth=2
```

## Canonical reference

For the full architectural reasoning behind these design choices — including why teams are not a separate database entity, why hierarchy does not imply execution dependency, and why the hierarchy page intentionally excludes runtime state — see `docs/PLATFORM_ARCHITECTURE.md`.
