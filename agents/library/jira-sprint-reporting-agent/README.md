# Jira Sprint Reporting Agent

**Definition UUID:** `04c82526-fa49-4241-9bbf-674a0a64108a`
**Instance:** `reformai.jira-sprint-reporting-agent` (`5544edd7-fe39-4340-9063-f9f71aef85b9`)
**Owner:** `reformai` | **Type:** `worker` | **Status:** ACTIVE (registered; runtime emits telemetry)

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

## Run

```
python agents/library/jira-sprint-reporting-agent/agent.py --smoke   # telemetry + config only
python agents/library/jira-sprint-reporting-agent/agent.py           # live: pull latest closed sprint
```
`agent.py` emits `run_started`/`run_completed` via the `oversight` SDK (no LLM calls -> reports
`cost_usd=0`, `cost_reported=true`). Live mode needs `ATLASSIAN_EMAIL` + `ATLASSIAN_API_TOKEN` in
`.env.local`; `--smoke` runs without them.

First reports are live in Confluence space RAPD:
- Sprint 1 - Review Analysis (page `166723587`)
- Sprint 2 - Planning (page `166985730`)
- Management PDF: `reports/sprint-1-review.pdf`

## Cycle kickoff (start of each review/planning session)

Run this first each cycle. It does the three session-opening steps in one shot:
1. Copies `SPRINT RETRO - TEMPLATE` into `<review sprint> Retro` under **RAPD > Reform AI Product
   Documentation > Sprint Reviews** (idempotent - skips if it already exists), and **pre-fills from
   Jira**: Sprint name, Dates, Review + Planning page links, and one Sprint Goal table row per goal
   component (split on `+`). Facilitator / Participants stay blank for the humans.
2. Copies over the Jira sprint info (runs the gather -> `reports/cycle_data.json` + prints the summary).
3. Prints the 1-hour-before pre-meeting checklist (`PRE_MEETING_CHECKLIST.md`).

```
python agents/library/jira-sprint-reporting-agent/kickoff.py              # auto: latest closed sprint
python agents/library/jira-sprint-reporting-agent/kickoff.py --sprint "Sprint 4"
python agents/library/jira-sprint-reporting-agent/kickoff.py --dry-run    # validate, no writes
```

Order: run kickoff **while the sprint is still OPEN** (do NOT close it first). Review = the active
sprint, so the retro is created and pre-filled before the review meeting. After the meeting fills
the retro page and it is re-published, run `cycle.py` -> `author.py` -> `pdf.py` to produce the
review/planning pages + management PDF. Close the sprint in Jira after the review, not before.

## Registration status

ACTIVE. Registered in Supabase (`agent_definitions` + `agents`); `metadata.runtime_implemented=true`.
Telemetry smoke-tested (run `51a54fba-1b8e-4747-9d61-f563c12538ce`, `status=completed`).

**The live runtime is TOKEN-based REST, NOT the Atlassian MCP.** Every real cycle (Sprint 1/2,
Sprint 2/3) ran through `cycle.py` -> `author.py` -> `pdf.py` using the Atlassian API token
(HTTP Basic auth): Jira REST reads, Confluence REST read+write, and Agile-API sprint-goal writes.
The MCP OAuth broke on 2026-06-18 and is not used. See root `LESSONS_LEARNED.md` ("Jira Sprint
Reporting Agent — the runtime is TOKEN-based REST"). Requires `ATLASSIAN_EMAIL` +
`ATLASSIAN_API_TOKEN` in `.env.local`. Flip status with
`node scripts/set_jira_agent_status.js <active|paused>`.
