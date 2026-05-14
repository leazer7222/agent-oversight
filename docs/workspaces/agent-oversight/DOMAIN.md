# Domain Glossary — Agent Oversight / Agent Agile Force

**Document type:** Canonical — workspace context  
**Owner:** Founder/Operator  
**Workspace:** agent-oversight  
**Update trigger:** New domain concepts introduced, existing definitions corrected, business rules changed  
**Consumed by:** Product Clarification Agent (primary), Story Structuring Agent (primary)

---

> If this document carries a staleness flag, agents reading it must surface that flag in their output and reduce their context integrity rating accordingly. Do not proceed as if the definitions are current.

---

## Defined Terms

### Agent

A stateless software process with a typed input/output schema that calls an LLM to perform one specific reasoning task. An agent receives pre-assembled context from an orchestrator, produces structured output conforming to a schema contract, and exits. It has no internal state between runs, calls no external tools directly, and has no knowledge of other agents.

### Run

A single invocation of an agent, identified by a UUID `run_id`. A run is bracketed by two telemetry events: `run_started` (emitted before any work begins) and `run_completed` or `run_failed` (emitted when the agent exits). The run record in Supabase is the authoritative record of what happened, including token usage, cost, duration, and the context bundle that was loaded.

### Team

A workflow definition: a named sequence of specialist agents with defined handoffs, quality gates, and shared workflow documents. The Agile Team is the sequence: Product Clarification Agent → Story Structuring Agent → Engineering Planning Agent → QA / Release Confidence Agent. A team is not a group of people — it is a reusable workflow template instantiated per workspace.

### Team Orchestrator

The deterministic controller that manages workflow state for one team invocation. It: loads the correct context bundle for the workspace, enforces the staleness gate before any agent runs, calls specialist agents in sequence, validates each agent's output against its schema contract, saves artifacts, and emits telemetry. It is a Python script, not an LLM agent. It makes no subjective decisions.

### Workspace

A context namespace: a scoped collection of canonical documents (PRODUCT.md, DOMAIN.md, KNOWN-RISKS.md, etc.) that define one product's reality. Identified by `workspace_id` (e.g., `agent-oversight`, `reformai`, `afterglow`). A workspace is a parameter passed to the team orchestrator at invocation time — it is not an agent layer, not an execution unit, and not a decision-maker.

### Canonical Document

A human-maintained, git-tracked file that agents receive as read-only context. Authoritative within its defined scope. Never written or modified by agents. Updated by the workspace owner within 48 hours of any trigger event. Examples: PRODUCT.md, DOMAIN.md, KNOWN-RISKS.md, STORY-READY.md.

### Context Bundle

A versioned manifest listing the exact canonical documents that a specific team + workspace combination loads per agent invocation. Stored as a JSON file at `docs/workspaces/{workspace_id}/context-bundles/{bundle-id}.json`. Each bundle has a `version` integer; when the doc set changes, the version increments. Every run record stores `context_bundle_id` and `context_bundle_version` so the exact context can be reconstructed.

### Clarification Brief

The structured output of the Product Clarification Agent. A JSON document conforming to `docs/schemas/clarification-brief.schema.json`. Contains: restated goal, problem statement, target user, proposed scope (in and out), success criteria, open questions, domain terms referenced, staleness flags, and a context integrity rating. The Brief is the input to the Story Structuring Agent after human review and approval.

### Definition of Ready

The ten-field standard a story must satisfy before engineering begins. Defined in `docs/teams/agile/STORY-READY.md`. The Product Clarification Agent's output must set up the Story Structuring Agent to produce stories meeting this standard without asking further clarifying questions.

### Context Integrity

The property that the canonical documents an agent receives accurately reflect the current state of the product. Rated by the Product Clarification Agent on every run: **Green** (all docs present, no staleness flags, all referenced concepts defined), **Yellow** (docs present but flagged, or goal references terms not in DOMAIN.md), **Red** (one or more required docs absent — output is best-effort and must not advance to the next stage without explicit human override).

### Staleness Flag

A marker prepended to a canonical document to signal that it may be outdated. Format:

```
> **STALE — as of YYYY-MM-DD:** [Brief description of what has changed. This document will be updated by YYYY-MM-DD.]
```

An agent that reads a staleness flag must include the flagged document name in its `staleness_flags` output field and adjust its context integrity rating to Yellow or Red.

### The Plausibility Trap

The primary failure mode of LLM-based agents: the model produces well-formatted, internally consistent output that is wrong because the context it read was stale, absent, or incomplete. The output looks correct on first read. It passes schema validation. It is still wrong. The mitigation is: every agent output is explicitly labeled a hypothesis; humans review against the quality rubric before any output advances to the next stage.

### Story

A unit of engineering work that satisfies the Definition of Ready — all ten fields populated, acceptance criteria testable and unambiguous, scope explicit on both sides. Stories are produced by the Story Structuring Agent and reviewed by a human before releasing to engineering. A document that does not meet all ten fields is not a story — it is a draft.

### Clarification Loop

The sequence of interactions between the Product Clarification Agent and the human before a Brief advances to Story Structuring. The PCA produces a Brief with open questions. The human answers those questions. If significant new information emerges, the PCA runs again with the updated context. The loop ends when the human approves the Brief — at which point all open questions are answered and the context integrity is Green or Yellow.

### Tier 1–4 (Source-of-Truth Hierarchy)

The four layers of information authority in this system:

- **Tier 1 — Ground Truth:** The codebase. What is actually running.
- **Tier 2 — Canonical Documents:** Human-maintained. Agents read these. PRODUCT.md, ARCHITECTURE.md, DOMAIN.md, KNOWN-RISKS.md, workflow docs.
- **Tier 3 — Derived Standards:** Documented patterns derived from Tier 2. Agent standards, coding standards, workflow definitions.
- **Tier 4 — Generated Outputs:** Agent artifacts — Clarification Briefs, Stories, Engineering Plans, Release Assessments. Always hypotheses. Require human approval before acting on them.

---

## Business Rules

These rules are invariants of the system. Agents must not violate them. Orchestrators must enforce them.

1. **Canonical documents are updated by humans only.** Agents read canonical documents. They never write, edit, or annotate them. If an agent output suggests a canonical document needs updating, a human makes that update.

2. **A stale document is worse than a missing document.** A missing document produces an explicit error. A stale document produces a confident wrong answer. When in doubt, flag as stale and require human review before proceeding.

3. **Every agent output is a hypothesis until a human approves it.** No agent output automatically advances to the next workflow stage. Human review is required at every quality gate. The quality rubric defines what "approved" means.

4. **The 48-hour update rule.** Canonical documents must be updated within 48 hours of a trigger event: architectural decision, product pivot, resolved risk, new constraint, changed goal. After 48 hours without an update following a trigger event, the document must be flagged as potentially stale.

5. **Stories must satisfy all ten Definition of Ready fields before engineering begins.** A story missing one field is not ready. The Story Structuring Agent refuses to produce incomplete stories. The human validates completeness before releasing to engineering.

6. **Specialist agents never call other agents directly.** All agent coordination flows through the team orchestrator. Specialist agents take typed input and produce typed output. They have no knowledge of other agents and call no external tools directly.
