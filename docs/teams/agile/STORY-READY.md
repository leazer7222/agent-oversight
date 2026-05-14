# Definition of Ready — Agile Team

**Document type:** Canonical — team workflow standard  
**Owner:** Founder/Operator + Engineer  
**Team:** agile  
**Scope:** Applies to all workspaces using the Agile Team (agent-oversight, reformai, afterglow, personal)  
**Update trigger:** Definition of Ready criteria change, acceptance criteria standard changes, handoff process changes  
**Consumed by:** Product Clarification Agent (secondary — north star for Brief quality), Story Structuring Agent (primary — output standard)

---

## What This Document Is

This is the standard a story must meet before engineering begins. It is the downstream target that the Product Clarification Agent is trying to set up. A Clarification Brief is "good" if — and only if — the Story Structuring Agent can produce stories meeting this standard without asking any further clarifying questions.

The Story Structuring Agent treats this document as a hard constraint. It will not produce a story that is missing any of the ten fields. If a field cannot be populated from the available information, that gap must be surfaced as a blocker rather than left empty or filled with a placeholder.

---

## The Ten Fields

A story is ready for engineering when all ten fields are populated with non-placeholder content.

### 1. Title
One sentence. Verb-first. Describes the user action or system behavior being enabled.

**Pass:** "Export agent run history as a CSV file"  
**Fail:** "CSV export," "Fix the thing," "User story for exports"

---

### 2. Goal
What user outcome this story achieves. Not what gets built — what the user can do or know that they couldn't before.

**Pass:** "The founder can share a cost breakdown with stakeholders without manually recreating the data"  
**Fail:** "Add an export button," "Implement the CSV feature"

---

### 3. Context
Why this matters now. What triggered this story. What is happening in the product or business that makes this the right thing to build at this moment.

**Pass:** "The founder is preparing a monthly investor update and currently has to manually copy run costs from the dashboard into a spreadsheet. This story removes that manual step."  
**Fail:** "Needed for the product," "User requested this"

---

### 4. Acceptance Criteria
Numbered list. Each item must be testable by a human or automated test. No "works correctly," "feels good," "performs well" — these are not testable.

**Pass:**  
1. Clicking "Export" on the Runs page downloads a `.csv` file within 3 seconds  
2. The CSV contains columns: run_id, agent_name, status, started_at, completed_at, cost_usd, tokens_in, tokens_out  
3. Rows are ordered by started_at descending  
4. If no runs match the current filter, the CSV is empty except for the header row  

**Fail:** "The export works," "Data is correct," "No errors"

---

### 5. User-Facing Scope
What the user can see or do after this story ships that they could not do before. Describes the observable delta, not the implementation.

**Pass:** "An 'Export CSV' button appears on the Runs list page. Clicking it downloads a file named `runs-{date}.csv` with all currently filtered runs."  
**Fail:** "CSV endpoint added," "Backend changes only"

---

### 6. Out of Scope
What is explicitly excluded from this story. A story with no out-of-scope is incomplete — it is impossible to know where this story ends and the next one begins.

**Pass:**  
- Excel (.xlsx) export format  
- Scheduled / automated exports  
- Email delivery of the export  
- Export of agent_events (step traces) — runs table only  

**Fail:** (empty), "Nothing is out of scope," "TBD"

---

### 7. Domain Terms
Any domain-specific terms the engineer needs to understand to implement this story correctly. Each term must match its definition in the workspace's DOMAIN.md.

**Pass:**  
- **Run** — a single invocation of an agent, tracked by a UUID run_id in the `runs` Supabase table  
- **context_bundle_id** — the identifier of the context bundle loaded for a run; must be included in the export  

**Fail:** (empty when domain terms are referenced in acceptance criteria), generic definitions that contradict DOMAIN.md

---

### 8. Affected Components
Which system components are touched by this story. Engineers use this to plan their implementation approach and assess risk.

**Pass:**  
- `src/app/dashboard/runs/page.tsx` — add Export button to runs list  
- `src/app/api/runs/export/route.ts` — new API endpoint (create)  
- `src/lib/api/fetch.ts` — extend if needed for file download  

**Fail:** "The frontend," "Some backend files," (empty)

---

### 9. Known Risks or Constraints
Any relevant items from the workspace's KNOWN-RISKS.md, or implementation constraints discovered during story structuring.

**Pass:**  
- RISK-004 (LLM Cost Overrun): Not applicable — this story involves no LLM calls  
- Large run sets (>10,000 rows) may cause slow CSV generation — consider streaming or pagination if this is a concern  

**Fail:** (empty when KNOWN-RISKS.md has relevant items), "No risks"

---

### 10. Dependencies
What must be true before engineering starts. External systems, prior stories, decisions, approvals.

**Pass:**  
- Supabase `runs` table must include `context_bundle_id` and `context_bundle_version` columns (Migration 009 — already applied)  
- Design approval not required — this is a utility feature with no new UI patterns  

**Fail:** (empty), "None" when dependencies exist but weren't identified

---

## The Quality Gate

Before a story is released to engineering, the human reviewer must confirm:

- [ ] All ten fields are present and contain non-placeholder content
- [ ] Acceptance criteria are each individually testable — no criterion requires subjective judgment
- [ ] Out of scope has at least one item
- [ ] Domain terms match DOMAIN.md definitions
- [ ] Affected components are specific enough for the engineer to start without further discovery

A story that fails any of these checks is returned to the Story Structuring Agent with the specific failure noted.

---

## Definition of Done

A story is done when:

1. All acceptance criteria are met (verified by the engineer)
2. TypeScript compiles clean (`tsc --noEmit` exits 0)
3. Lint passes (`eslint` exits 0)
4. No new console errors in the browser during manual verification
5. The QA / Release Confidence Agent has run and returned a confidence rating of Green or Yellow with no blocking items

A story is not done because the code is merged. It is done when the above conditions are satisfied.

---

## Story Splitting Rules

When the Story Structuring Agent determines a Clarification Brief describes work too large for a single story, it must split. A story is too large when:

- It touches more than 4 distinct components
- It has more than 6 acceptance criteria
- It would take longer than 2 working days to implement
- It has more than 2 distinct user-facing behaviors

When splitting, each child story must independently meet all ten Definition of Ready fields. A parent story is never handed to engineering — only the children are.
