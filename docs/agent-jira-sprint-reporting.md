# Jira Agent - Sprint Reporting Capability

Status: BUILT (first reports live, unregistered) | Owner: `reformai` | Type: capability within Agent Oversight
Last updated: 2026-06-10

This document specifies the Sprint Reporting capability of the ReformAI Jira Agent. It is a
capability inside the existing Agent Oversight framework, NOT new agent infrastructure. The
underlying orchestration, oversight, permissions, logging, and execution controls already exist.

First reports are built and live (see Section 14). The agent is still unregistered. Plan: prove
the reports over 1-2 sprints -> register the agent properly via Agent Oversight (Section 12).

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
- Infrastructure: `RAI-161` (Technical Infrastructure), `RAI-159` (Integrations - 3rd-party tools),
  plus other infra epics linked under 161/159.
- Business Design: `RAI-629` (Business Design) - design stories; broken out as its OWN group in
  planning, separate from Product (per Charles - these are design work he owns).
- Product: everything else (RAI-160 UI/UX, RAI-147 Distressed Assets, RAI-146 Admin Webpage,
  RAI-83 HomeOwner/HomeBuyer, RAI-1 Vendor Web App).
- New epics default to Product until classified. Agent reads issue parent epic to categorize.

### Confluence
- Space RAPD ("Reform AI Product Documentation"), id `38928388`. Home for these docs.
- Retro template page id `166297602`.
- Existing Sprint Review template page id `165904385` (superseded by Doc 1).
- LIVE pages built this session: Sprint 1 Review Analysis `166723587` · Sprint 2 Planning
  `166985730` · Sprint 1 Retro (filled from template) `166395905`.
- Naming convention: `Sprint N - Review Analysis`, `Sprint N - Retro`, `Sprint N - Planning`.
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

## 12. Registration - DONE (catalog) / runtime telemetry pending

Registered 2026-06-10 via `scripts/register_jira_sprint_agent.js`.
- [x] Registered in Supabase: definition `04c82526-fa49-4241-9bbf-674a0a64108a`
  (`jira-sprint-reporting-agent`) + instance `5544edd7-fe39-4340-9063-f9f71aef85b9`
  (`reformai.jira-sprint-reporting-agent`), company ReformAI, worker, trigger `manual`.
- [x] `agent.json` + `README.md` + `LESSONS.md` in `agents/library/jira-sprint-reporting-agent/`.
- [x] MCP/Jira dependencies declared in `agent.json` (Atlassian; Jira + Confluence scopes).
- [ ] Emit `run_started` / `run_completed` to `/api/ingest` with unique `run_id` - NOT done.
- [ ] Report `tokens_in` / `tokens_out` / `cost_usd` - NOT done.

Status is `paused` on purpose: the capability is proven and live, but there is no packaged
telemetry-emitting runtime yet (it is driven interactively via the Atlassian MCP). Flip the
instance to `active` only once a runtime that emits `run_started`/`run_completed` exists - ingest
returns 403 for non-active agents, so do not flip early. `metadata.runtime_implemented=false`.

Shape chosen: a standalone `worker` (definition + ReformAI instance). A future `reformai.jira-agent`
orchestrator could parent this and other Jira capabilities (backlog hygiene, config, dashboards).

---

## 13. Open decisions

1. Sprint-goal linkage: `sprint-goal` label vs designated goal epic. Leaning label (simpler at N=2).
2. Whether the agent should actively enforce the 5 data conventions as in-sprint hygiene nudges.
3. Confluence home: standardize all three artifacts in RAPD (current direction).

---

## 14. Implementation notes (Sprint 1/2 build, 2026-06-10)

### What was built
- Sprint 1 Review Analysis (Confluence `166723587`) - full internal doc, brand-styled.
- Sprint 2 Planning (Confluence `166985730`) - redesigned planning page (below).
- Management report PDF: `reports/sprint-1-review.html` -> `reports/sprint-1-review.pdf`, rendered
  via Edge headless (`msedge --headless --print-to-pdf`). 4 pages: (1) Sprint 1 Review,
  (2) Shipped + Self-Correcting + Risk, (3) Sprint 2 Planning summary, (4) Sprint 2 Full Scope.

### Write capabilities - PROVEN and BOUNDED
- IMPLEMENTED write-back: t-shirt sizing from Confluence. A fillable "Set Size" column on the
  planning page -> human types sizes -> agent parses the published page -> writes each via
  `editJiraIssue` setting `customfield_10225` to `{value: "<size>"}`. Guardrail held: the agent
  only transcribes the size the HUMAN chose; it never estimates. This is the first Jira write.
- WRITE-BOUNDARY (hard limit of this integration): the agent can set issue FIELDS but CANNOT move
  issues between/out of sprints. `editJiraIssue` on `customfield_10020` rejects arrays
  ("The Sprint id must be a number") - it only accepts a single sprint to move INTO, which would
  wipe an issue's whole sprint history. Removing from a sprint (esp. a CLOSED one) needs the Agile
  board API (`/rest/agile/1.0/backlog/issue`), which this MCP does not expose. Consequence: items
  wrongly tagged to a sprint are handled by REPORT-LEVEL EXCLUSION, not Jira edits.
- Worked example: RAI-201/228/67 were UAT items completed pre-Sprint-1 but tagged to Sprint 1+2.
  They are excluded from all report metrics/scope with a note; Jira tags left as-is (closed-sprint
  membership is effectively locked).

### Confluence rendering ceiling (verified)
- Cell background colors via `data-highlight-colour` are STRIPPED by the HTML->ADF converter
  (confirmed by reading back ADF). Brand color on tables is only reliable via status lozenges
  (green/yellow/blue/neutral/purple) + panels. True brand-colored tables live in the PDF.
- Whiteboards are not API-readable (404). Retro MUST be a page (Section 8), not a whiteboard.
- Drafts are invisible to the API - a page must be PUBLISHED before the agent can read edits
  (matters for the Set-Size write-back flow).

### Redesigned Sprint 2 Planning page structure
Goal + success criteria -> Snapshot KPIs (Committed / Sized / Carryover / Owners) -> Readiness Gate
(epics linked / sized / owners -> READY verdict) -> Committed Scope (by initiative + by size) ->
Full Committed Scope (Business Design broken out first, then Product / Tech Debt / Infrastructure,
all expanded, carryover-tagged) -> Action Worklist (editable write-back; "all clear" when empty) ->
Risks & Dependencies. NO points/capacity model yet (count-based by decision; revisit after seeing
throughput). Carryover detection: item is in BOTH sprint 540 and 573 (`sprint in (540) AND
sprint in (573)`).

### Branding (reconciled against source)
- The `reformai-design-system` skill was reconciled against `ReformAI-Inc/Reform-AI @ d768f37`.
  Real logo ships as PNGs (no SVG): `logo_en.png` bundled in the skill `assets/` (copied to
  `reports/logo_en.png`). Two teals: `#00ADB5` primary, `#3B8AA2` system. Semantic palette:
  success `#27AE60`, info `#2D9CDB`, accent `#F5A623`, warning `#F2C94C`, danger `#EB5757`.
  Chart hexes from the old QA scrape are stale - use the semantic tokens. The earlier
  `docs/ref-logo-branding-thread.md` is now superseded by this skill reconciliation.

### Data-handling gotchas
- Query Sprint membership by sprint ID (`sprint = 540`), NOT name (`sprint = "Sprint 1"`) - the
  name matches other boards' identically-named sprints and over-returns.
- Exclude sub-tasks from work-item counts (`issuetype != Sub-task`).
- Large JQL results exceed the tool token cap - they save to a file; parse with PowerShell
  (`ConvertFrom-Json`), not inline. `jq` is not installed on this machine.
