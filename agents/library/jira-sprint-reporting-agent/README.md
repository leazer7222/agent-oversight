# Jira Sprint Reporting Agent

**Definition UUID:** `04c82526-fa49-4241-9bbf-674a0a64108a`
**Instance:** `reformai.jira-sprint-reporting-agent` (`5544edd7-fe39-4340-9063-f9f71aef85b9`)
**Owner:** `reformai` | **Type:** `worker` | **Status:** registered (capability proven; telemetry runtime pending)

The first capability of the ReformAI Jira Agent. Turns Jira + Confluence data into two
sprint artifacts, with a human-gated write-back for t-shirt sizing.

Full design: [`docs/agent-jira-sprint-reporting.md`](../../../docs/agent-jira-sprint-reporting.md)

---

## What it does

Each sprint it pulls three sources and produces two documents:

| Input | Source |
|---|---|
| Completed sprint (review data) | Jira (Agile) |
| Retrospective | Confluence page (`Sprint N - Retro`, structured page - NOT a whiteboard) |
| Upcoming sprint (planning data) | Jira (Agile) |

| Output | Surface |
|---|---|
| Sprint Review Analysis (comprehensive, internal) | Confluence page in space RAPD |
| Sprint Planning (readiness gate + full scope) | Confluence page in space RAPD |
| Management Report (distilled, brand-styled) | PDF (`reports/sprint-1-review.pdf`) via Edge headless |

Key design choices:
- **Count-based**, not story points (the team does not estimate in points).
- **Goal-aware health:** a sprint that hits its committed goal is GREEN even if raw completion
  is low - low throughput on deprioritized work is a deliberate trade-off, not a miss.
- **Two teals + semantic palette** and the real `logo_en.png` from the `reformai-design-system`
  skill (reconciled against product source `d768f37`).

## Tools / MCPs used

- **Atlassian MCP** (Jira + Confluence Cloud) - reads sprints/issues/epics/retro; writes
  Confluence pages; writes the t-shirt size field (human-gated).
- **Edge headless** (`msedge --headless --print-to-pdf`) - renders the management PDF locally.
- Scopes: `read:jira-work`, `write:jira-work`, `read:page:confluence`, `write:page:confluence`.

## Permissions / autonomy

- **Auto:** read-only metrics, Confluence page generation.
- **Human-gated:** t-shirt size write-back to Jira (`customfield_10225`). The human chooses the
  value (via a "Set Size" column on the planning page); the agent only transcribes it.
- **Prohibited / not possible here:** moving issues between or out of sprints (needs the Agile
  board API, which the integration does not expose); deletes; schema/permission changes;
  accepting or closing work.

## Run (current state)

There is no packaged autonomous runtime (`agent.py`) yet. The capability is currently driven
interactively through the Atlassian MCP. First reports are live in Confluence space RAPD:
- Sprint 1 - Review Analysis (page `166723587`)
- Sprint 2 - Planning (page `166985730`)
- Management PDF: `reports/sprint-1-review.pdf`

## Registration status

Registered in Supabase for catalog/identity (`agent_definitions` + `agents`). Status is
`paused` until a telemetry-emitting runtime (emits `run_started`/`run_completed` to `/api/ingest`
per Agent Standards) is built. The capability itself is proven and producing real artifacts.
