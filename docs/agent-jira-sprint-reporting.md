# Jira Agent - Sprint Reporting Capability

Status: DESIGN (pre-build) | Owner: `reformai` | Type: capability within Agent Oversight
Last updated: 2026-06-09

This document specifies the Sprint Reporting capability of the ReformAI Jira Agent. It is a
capability inside the existing Agent Oversight framework, NOT new agent infrastructure. The
underlying orchestration, oversight, permissions, logging, and execution controls already exist.

This capability is unregistered as of this writing. Plan: build templates -> generate the first
real report -> register the agent properly via Agent Oversight (see "Registration - pending").

---

## 1. Purpose

Pull data from a completed sprint, the sprint retrospective, and the upcoming sprint, and assemble
it into two documents:

1. A comprehensive Sprint Review Analysis (internal source of truth, includes the retro).
2. A distilled Management Report (a subset of Doc 1 + the upcoming sprint preview), rendered to PDF
   for the management team.

Design priority for a two-person team: accurate, low-effort, count-based reporting. Avoid ceremony.
~95 percent agent-drafted; the human approves rather than authors.

---

## 2. Two-tier document architecture

```
        INPUTS (authored / Jira)                 OUTPUTS (agent-generated)

  Sprint N - Retro (Confluence page) --\
                                        \
  Jira - closed Sprint N (review data) --+--> DOC 1: SPRINT REVIEW ANALYSIS
                                        /      (comprehensive, internal, = review + retro)
                                       /       Audience: eng team. System of record.
                                      /              |
                                     /               |  SUBSET of Doc 1
                                    /                v
  Jira - future Sprint N+1 --------/----------> DOC 2: MANAGEMENT REPORT
  (upcoming sprint data)                         (distilled subset + next-sprint preview)
                                                 Audience: management. PDF / email.
```

Key principle: Doc 2 is a projection of Doc 1 plus the Sprint N+1 preview. The agent generates
Doc 1 fully, then derives Doc 2 from it. Single source of truth; the two never drift.

---

## 3. Inputs

| Input | Source | Notes |
|---|---|---|
| Retro | Confluence page `Sprint N - Retro` | Authored by humans from the template (Section 8). NOT a whiteboard - whiteboards are not API-readable. |
| Closed sprint | Jira (Agile) | Review metrics: completion, carryover, scope changes. |
| Upcoming sprint | Jira (Agile) | Next-sprint preview: goal, committed scope, readiness. |

Critical constraint discovered: the original retro was a Confluence WHITEBOARD. `getConfluencePage`
returns 404 for whiteboards and the sticky-note text is not retrievable via API. Resolution: retros
are captured on a normal Confluence PAGE using the template in Section 8.

---

## 4. Doc 1 - Sprint Review Analysis (section spec)

Source legend: AUTO = agent fills from Jira; RETRO = pulled from retro page; MANUAL = human writes;
DRAFT->OK = agent proposes, human confirms.

| # | Section | Source | Notes |
|---|---|---|---|
| - | Executive Summary | DRAFT->OK | Health, goal outcome, completion, carryover, scope delta, top risk, next-sprint focus. Management-first; at the top. |
| 1 | Sprint Information | AUTO | Name, dates, goal. Goal is stored in Jira sprint object. |
| 2 | Sprint Outcome | AUTO | Three non-summable axes (see below). |
| 3 | Capacity Analysis (T-shirt size) | AUTO (conditional) | Sprint 1: "sizing introduced Sprint 2 - not tracked." Sprint 2+: planned vs completed by size + coverage "N of M sized." |
| 4 | Scope Changes | AUTO | Added/removed mid-sprint, from changelog. |
| 5 | Throughput Trend | AUTO | This sprint vs prior 3-5 sprints. |
| 6 | Goal Assessment | AUTO (via convention) + MANUAL impact | Achieved/Partial/Not computed from goal-linked issues; LLM drafts impact line. |
| 7 | Work Completed + Highlights | AUTO | Features/Bugs/Tech Debt/Infra with links; 3-5 plain-English highlights. |
| 8 | Carry-Over | AUTO | Ticket, Type, Size, Status. Size populated Sprint 2+. |
| 9 | Risks & Blockers | DRAFT->OK | Agent flags `Blocked` status + aging WIP; LLM drafts impact. |
| 10 | Retro Summary | RETRO | Good/Bad/Actions pulled from retro page; linked, NOT re-authored. |
| 11 | Recommendations | DRAFT->OK | Rule-derived (Section 7) + LLM phrasing; human adds strategic ones. |
| 12 | Sprint Health | AUTO (formula) | Deterministic from metrics (Section 7). Human can override. |
| - | Cross-links | AUTO | Link to Retro page and Sprint N+1 Planning. |

### Sprint Outcome - three separate axes (never summed)
- Headline: Planned, Completed, Completion percent, Carried over, Added mid-sprint.
- By work type (issue type): Stories, Bugs, Tasks.
- By initiative (parent epic): Product, Tech Debt, Infrastructure, Uncategorized.

"By type" and "by initiative" are different axes. A Bug under the Tech Debt epic is both - listing
them in one summable list double-counts. Show separately. The Uncategorized row (issues with no
parent epic) doubles as an epic-linking hygiene signal.

---

## 5. Doc 2 - Management Report (subset + next sprint)

Layout (one page, PDF-friendly): Executive Summary -> Goal Outcome -> Work Completed (TOTAL) ->
Throughput -> Risks & Blockers -> How We're Self-Correcting -> Next Sprint Preview.

| Doc 1 section | In Mgmt Report | Depth |
|---|---|---|
| Executive Summary | Yes | Full (+ next-sprint focus line). |
| Goal Assessment | Yes | Outcome + 1-line impact. |
| Work Completed | Yes | TOTAL - full list by initiative + highlights. |
| Throughput | Yes | 1 line + mini trend. |
| Risks & Blockers | Yes | Top 2-3. |
| Retro Actions + Recommendations | Yes | Merged into "How We're Self-Correcting". |
| Sprint Health | Yes | Folded into Exec Summary. |
| Outcome sub-tables / Capacity / Scope detail | No | Doc 1 only. |
| Next Sprint Preview | New | Straight from Jira (goal, committed scope, size mix, readiness, overcommit vs throughput). |

"How We're Self-Correcting" merges retro action items (problems found) with process recommendations
(fixes being applied) into one narrative demonstrating active management. Intentional - this is the
management-skills story leadership should see.

Next Sprint Preview is pulled straight from Jira (no separate planning doc required for the report).

Generation order: build Doc 1 -> derive Doc 2 + append Sprint N+1 preview -> render Doc 2 to PDF.

---

## 6. PDF generation

Path A (chosen): the agent generates the management report as clean HTML/Markdown and renders the
PDF itself (full layout control; no dependency on Confluence's native export). The agent owns the
management-facing artifact so it looks deliberate.

---

## 7. Automation model (target ~95 percent)

The gap to full automation is a data-discipline problem, not a code problem. Two levers: convert
judgment into rules/data, and let the LLM draft soft narrative so the human only approves.

### Sprint Health formula (goal-aware)
Goal achievement is the PRIMARY signal and overrides the raw-completion formula. A sprint that
hits its committed goal is NOT red just because lower-priority stories were consciously deferred to
land that goal. Completion percent is secondary context, not the headline.
```
IF sprint goal achieved        -> GREEN (note any deliberate carryover as a trade-off)
ELSE IF no goal set / goal partial:
  GREEN  = completion >= 80%  AND scope-creep < 20%  AND 0 unresolved blockers
  YELLOW = completion 50-79%  OR  scope-creep 20-40% OR  1-2 blockers
  RED    = completion < 50%   OR  scope-creep > 40%  OR  >= 3 blockers / goal missed
```
Lesson (Sprint 1): a pure completion-% formula scored Sprint 1 RED (34% done, 3 blockers) when it
was actually GREEN - the infrastructure-transition goal was fully achieved, and low throughput on
other stories was the deliberate cost of landing it. This is why goal achievement must dominate.
This also requires the sprint goal to be recorded in Jira (Sprint 1's was not, in the sprint field).

### Goal Assessment (via convention)
Tag the issues/epic that deliver the sprint goal (label `sprint-goal` - decision pending).
```
Achieved = 100% of goal-linked issues Done
Partial  = some Done
Not      = none Done
```
LLM drafts the business-impact line from completed issue summaries.

### Auto-recommendation rules
| Detected pattern | Generated recommendation |
|---|---|
| Carryover > 30% | Reduce next-sprint commitment - over-committed. |
| Uncategorized epic-links > 15% | Link work to epics - N items had no initiative. |
| Unsized issues > 20% | Enforce t-shirt sizing - capacity data incomplete. |
| Same blocker 2+ sprints | Escalate recurring blocker. |
| One size class dominates carryover | Split L/XL items - they consistently slip. |

### The 5 data conventions that unlock 95 percent
1. Every issue has a parent epic (kills Uncategorized; enables initiative split + goal assessment).
2. Every issue is t-shirt sized (full Capacity coverage).
3. Sprint goal tied to issues/epic (auto Goal Assessment).
4. Consistent Definition of Done (trustworthy completion counts).
5. Blockers use `Blocked` status (already present; auto risk detection).

The agent can enforce these by flagging unsized/unparented/un-goaled issues during the sprint.

### The 5 percent that stays human (on purpose)
Final sign-off on the goal-impact line, any strategic recommendation, and confirming health before
the report goes to management. For a management-facing doc this human gate is a guardrail against an
over-automated, confidently-wrong report - not a limitation.

---

## 8. Retro page template (agent-readable contract)

Built and live: `SPRINT RETRO - TEMPLATE`, Confluence page id `166297602`, space RAPD.

Structure the agent parses:
- Metadata info panel: Sprint, Dates, Facilitator, Participants, Review page link, Planning link.
- Four fixed headings (do NOT rename): `Good`, `Bad / could be better`, `Ideas`, `Actions`.
- Actions as a TABLE with columns: `# | Action item | Jira item | Owner | Status | Notes`.
- Status values constrained to: To Do, In Progress, Done.

Usage: copy the template each sprint, rename `Sprint N - Retro`, fill in. Keep headings and the
Actions table structure - that is the parsing contract.

---

## 9. Jira / Confluence environment (live IDs)

Site: `reform-ai-team.atlassian.net` | cloudId: `6c97a9a2-291e-4c35-89da-b7c3d245e386`

### Jira
- Project: `RAI` ("Reform_AI"), classic software project, id `10003`. Board id `3`.
- Issue types: Story (10010), Bug (10014), Task (10012), Sub-task (10013), Epic (10000).
- Sprint field: `customfield_10020` (array of sprint objects; includes `goal`, `startDate`, `endDate`, `state`).
- T-Shirt Size field: `customfield_10225` (select). Options: XS, S, M, L, XL, XXL, Spike.
- Story Points (`customfield_10016`): NOT used (0 of issues populated). Reporting is count-based, not points.
- Epic link (classic): `customfield_10014` and/or `parent`.
- Sprint 1: closed, 2026-06-01 to 2026-06-05. Review target.
- Sprint 2: future, goal "Wompi Account Update and Dashboard Views". Planning/preview target.
- fixVersions/releases exist (e.g. "5.18") - feeds future release tracking.

### Epic -> initiative category mapping (maintained list)
- Tech Debt: `RAI-558` ([Tech Debt] System Stabilization, Observability, Architecture Remediation).
- Infrastructure: `RAI-161` (Technical Infrastructure), `RAI-159` (Integrations - 3rd-party tools).
- Product: everything else (RAI-160 UI/UX, RAI-147 Distressed Assets, RAI-146 Admin Webpage,
  RAI-83 HomeOwner/HomeBuyer, RAI-1 Vendor Web App).
- New epics default to Product until classified. Agent reads issue parent epic to categorize.

### Confluence
- Space RAPD ("Reform AI Product Documentation"), id `38928388`. Home for these docs.
- Retro template page id `166297602`.
- Existing Sprint Review template page id `165904385` (to be superseded by Doc 1 template).
- Naming convention: `Sprint N - Review`, `Sprint N - Retro`, `Sprint N - Mgmt Report`.
- Folders are created manually by the team; the agent writes pages into the designated location.

---

## 10. Permissions / autonomy (Jira-specific)

- Jira: READ-ONLY. The capability never writes to Jira. All sprint/issue data is read via REST/Agile.
- Confluence: WRITE pages only (create/update the review + report pages). Lowest-risk write; reversible.
- No deletes, no schema/permission changes, no sprint mutations.
- Auth scopes in use: `read:jira-work`, `write:jira-work` (unused by this capability),
  `read:page:confluence`, `write:page:confluence`, plus comment/space read.
- Recommendation for production: run the agent under its own Atlassian account for attribution.

---

## 11. Build sequence

1. Build Doc 1 template (Sprint Review Analysis) in RAPD - supersedes page 165904385.
2. Build Doc 2 template (Management Report).
3. Populate Sprint 1 live from Jira into Doc 1; derive Doc 2; render PDF.
4. Review output quality across 1-2 sprints.
5. Register the agent via Agent Oversight (Section 12).
6. Later: automate trigger on sprint close; layer in the 5 data-convention hygiene nudges.

---

## 12. Registration - pending (Agent Oversight committee)

To be completed AFTER the first report proves the pipeline. Per `AGENTS.md` standards:
- [ ] Register in Supabase `agents` table with stable UUID `agent_id`.
- [ ] `agent.json` identity manifest + `README.md`.
- [ ] Emit `run_started` / `run_completed` to `/api/ingest` with unique `run_id` per run.
- [ ] Report `tokens_in` / `tokens_out` / `cost_usd` on completion.
- [ ] Declare MCP/Jira dependencies in `agent.json`.

Likely shape: a `worker` capability, possibly under a Jira orchestrator instance
`reformai.jira-agent`. Decide definition-vs-instance split at registration time.

---

## 13. Open decisions

1. Sprint-goal linkage: `sprint-goal` label vs designated goal epic. Leaning label (simpler at N=2).
2. Whether the agent should actively enforce the 5 data conventions as in-sprint hygiene nudges.
3. Confluence home: standardize all three artifacts in RAPD (current direction).
