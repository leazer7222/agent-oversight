# Agent Agile Force - Full Lifecycle Design

Status: DESIGN (v1 implementation scope = Phase 2: PCA -> CCA -> BA -> Gate A)
Owner: `reformai`
Orchestrator: `agile-team-orchestrator` (`b2c3d4e5-f6a7-8901-bcde-f12345678901`)
Entry point: `agents/teams/agile/run.py`

## Purpose

The agile orchestrator is a **lifecycle coordinator for the entire product delivery
process** - idea to production - not just a scoping pipeline. It owns the finite state
machine (FSM), sequences agent stages, enforces human review gates, validates each stage
artifact against its schema, and threads upstream artifacts to downstream stages.

It makes no LLM calls itself. It is deterministic: load -> run stage -> validate ->
persist -> gate -> advance.

**Implementation is phased** (Section 14). The FSM and the storage spine are designed in
full now so later phases bolt on by appending a stage descriptor - no engine rewrite and
no schema redesign. v1 ships PCA -> CCA -> BA plus the first human gate (Gate A).

## Locked decisions (2026-06-02)

1. The **design** stage is owned by a **dedicated UX Design Agent** (`reformai.ux-design-agent`, NEW).
2. The existing **UI generation agent** (`reformai.ui-design-agent`, marketing-blueprint -> React code)
   **remains separate** and is NOT a lifecycle stage. It may later be invoked as a tool inside the
   Engineering stage, but it does not own the design gate.
3. **Design and implementation are distinct lifecycle stages** (UX Design -> Gate B -> Engineering).
4. `platform.feature_lifecycle` is introduced **now, in Phase 2**.
5. `platform.lifecycle_events` is **append-only**.
6. All stage artifacts remain **immutable** (in `agent_outputs`).
7. The lifecycle spine stores **state + references only** - never artifact bodies.

Target lifecycle (full):

```
Idea -> PCA -> [Persona Validation: optional] -> CCA -> BA -> [Gate A]
     -> [Sprint Planning Team] -> UX Design -> [Gate B]
     -> Engineering -> [Gate C] -> Code Review -> [Gate D] -> Release
```

v1 implements only: `Idea -> PCA -> CCA -> BA -> [Gate A]`.

Two stages are documented here as **future, not implemented**:
- **Persona Validation Agent** (after PCA, before CCA) - optional - **Phase 2.5**.
- **Sprint Planning Team** (after Gate A, before UX Design) - **Phase 3**.

Neither is required for the current Phase 2 implementation.

---

## 1. Full lifecycle states (idea -> production)

The unit of work is a **Feature** (one `feature_id`). It moves through an FSM. Each
delivery stage has a `*_running` state (agent working), an optional `*_blocked` state
(agent could not proceed - e.g. BA refusal, open questions), and a human `*_review` gate
state. Cross-cutting states (`changes_requested`, `abandoned`) are reachable from any gate.

| # | State | Kind | Owner | Phase | Meaning |
|---|---|---|---|---|---|
| 0  | `intake`                | entry      | orchestrator | 2   | Idea captured; raw goal recorded |
| 1  | `clarifying`            | agent      | PCA          | 2   | PCA running |
| 2  | `clarification_blocked` | agent-stop | human        | 2   | PCA could not clarify (insufficient context) |
| 3  | `persona_validating`    | agent (optional) | Persona Validation | **2.5 (future)** | Test clarified idea against personas; score desirability/frequency/pain/value/objections |
| 4  | `context_scanning`      | agent      | CCA          | 2   | CCA running (clone, pin SHA, extract) |
| 5  | `scoping`               | agent      | BA           | 2   | BA running |
| 6  | `scoping_blocked`       | agent-stop | human        | 2   | BA refused - ambiguity too high (the refusal is the product) |
| 7  | `scope_review`          | HUMAN GATE A | human      | 2   | Human Product Review of Feature Scope Brief |
| 8  | `sprint_planning`       | agent/team | Sprint Planning Team | **3 (future)** | Convert approved scope into delivery planning (epics/stories/deps/risk/sequencing) |
| 9  | `designing`             | agent      | UX Design    | 4 (future) | UX Design Agent running |
| 10 | `design_review`         | HUMAN GATE B | human      | 4 (future) | Human Design Review |
| 11 | `implementing`          | agent      | Engineering  | 5 (future) | Engineering Agent running |
| 12 | `implementation_review` | HUMAN GATE C | human      | 5 (future) | Human Engineering Review |
| 13 | `code_review`           | agent      | Code Review  | 6 (future) | Code Review Agent running |
| 14 | `final_approval`        | HUMAN GATE D | human      | 6 (future) | Human Final Approval (release decision) |
| 15 | `deploying`             | deterministic | Release   | 7 (future) | Release coordinator running |
| 16 | `released`              | terminal   | -            | 7 (future) | Deployed; release record written |
| -  | `changes_requested`     | loopback   | -            | 2   | A gate sent the feature back to an earlier stage |
| -  | `abandoned`             | terminal   | -            | 2   | Killed at any gate |

These 19 states are the **complete** set. Every future phase (2.5, 3-7) reaches states that
already exist in the FSM; no new state is introduced later. This is what lets later phases
attach without a schema redesign (the `current_state` CHECK enumerates all 19 - Section 15).

`persona_validating` is **optional**: the orchestrator may advance `clarifying ->
context_scanning` directly when persona validation is skipped, or route through
`persona_validating` when enabled. `sprint_planning` sits on the only path between Gate A
and UX Design once Phase 3 lands.

```
intake
  -> clarifying ----------(blocked)--> clarification_blocked --(answers)--> clarifying
  -> persona_validating  [optional; skippable -> context_scanning]   (Phase 2.5)
  -> context_scanning
  -> scoping -------------(blocked)--> scoping_blocked --(answers)--> scoping
  -> [GATE A] scope_review --(changes)--> back to clarifying|scoping
  -> sprint_planning      (Phase 3)
  -> designing
  -> [GATE B] design_review --(changes)--> back to designing|sprint_planning|scope_review
  -> implementing
  -> [GATE C] implementation_review --(changes)--> back to implementing|designing
  -> code_review
  -> [GATE D] final_approval --(changes)--> back to implementing
  -> deploying
  -> released
```

---

## 2. Stage ownership

| Stage | Owner agent | Type | Exists today? |
|---|---|---|---|
| Clarification | `reformai.product-clarification-agent` | worker | Yes (operational) |
| Persona Validation (Phase 2.5, optional) | `reformai.persona-validation-agent` (**NEW**) | worker | Does not exist |
| Codebase Context | `reformai.codebase-context-agent` | worker | Docs only - no `agent.py` |
| Scoping | `reformai.ba-scoping-agent` | worker | Docs only - no `agent.py` |
| Sprint Planning (Phase 3) | `reformai.sprint-planning-team` (**NEW, team/sub-orchestrator**) | orchestrator | Does not exist |
| UX Design | `reformai.ux-design-agent` (**NEW, dedicated**) | worker | Does not exist |
| Engineering | `reformai.engineering-agent` (**NEW**) | worker | Does not exist |
| Code Review | `reformai.code-review-agent` | worker | Yes (operational, advisory) |
| Release | `reformai.release-coordinator` (**NEW, thin/deterministic**) | orchestrator | Does not exist; wraps `scripts/push.ps1` |
| **Lifecycle coordination** | `agile-team-orchestrator` | orchestrator | Yes (Phase 1 single-worker; needs FSM refactor) |

Out of lifecycle: `reformai.ui-design-agent` (existing UI/React code generator) stays a
standalone tool. It is not a lifecycle stage and does not own a gate.

Human review gates are owned by **a human role**, not an agent. The orchestrator only
records the decision.

---

## 3. Artifact produced by each stage

Every agent artifact is written immutably to `agent_outputs` (`output_type` shown). Human
gate decisions are durable lifecycle state (Section 5), not artifacts.

| Stage | Artifact | `output_type` | Schema |
|---|---|---|---|
| PCA | Clarification Brief | `clarification_brief` | `docs/schemas/clarification-brief.schema.json` |
| Persona Validation (future) | Persona Validation Report - desirability/frequency/pain/strategic value/objections scores + proceed signal | `persona_validation_report` (NEW) | `docs/schemas/persona-validation-report.schema.json` (TBD) |
| CCA | `codebase-context.json` (+ `.md` render) | `codebase_context` | `docs/schemas/codebase-context.schema.json` |
| BA | Feature Scope Brief + graph mutations + Questions + Decisions + readiness | `product_graph_scope` | `docs/schemas/product-graph.schema.json` |
| Gate A | approve / changes | - | lifecycle state |
| Sprint Planning (future) | Sprint Planning Brief - epics, stories, dependencies, risk, sequencing, sprint fit | `sprint_planning_brief` (NEW) | `docs/schemas/sprint-planning-brief.schema.json` (TBD) |
| UX Design | UX flow + screen requirements + wireframe/design brief (+ optional Figma link) | `ux_design_brief` (NEW) | `docs/schemas/ux-design-brief.schema.json` (TBD) |
| Gate B | approve / changes | - | lifecycle state |
| Engineering | implementation plan + code changes (branch/commit + diff) + tests | `engineering_change` (NEW) | `docs/schemas/engineering-change.schema.json` (TBD) |
| Gate C | approve / changes | - | lifecycle state |
| Code Review | findings + severity counts + recommendation + risk | `code_review` | `agent_definitions.output_schema` (migration 011) |
| Gate D | release approval | - | lifecycle state |
| Release | release record + deploy artifact + post-release checks | `release_record` (NEW) | `docs/schemas/release-record.schema.json` (TBD) |

---

## 4. Human review gates

Four hard gates. Each is a state the FSM rests in until a human records a decision.

| Gate | After stage | Reviews | Decision |
|---|---|---|---|
| **A - Product** | BA Scoping | Feature Scope Brief, open `QST-*`, proposed `CON-*`/`DEC-*`, readiness | approve / request changes |
| **B - Design** | UX Design | UX flow, screen requirements, wireframe brief | approve / request changes |
| **C - Engineering** | Engineering | implementation plan, diff, tests | approve / request changes |
| **D - Final** | Code Review | code review findings + full lineage | approve / request changes / hold |

Two **soft** agent-stop gates also require a human but are not approval gates: PCA
`clarification_blocked` and BA `scoping_blocked`. The human answers; the same stage re-runs.

**Gate A is the only gate implemented in v1.** B-D are defined in the FSM and storage but
not exercised until Phases 3-5.

---

## 5. Durable state (the lifecycle spine)

Net-new storage owned by the orchestrator (migration 026, Section 15). Matches platform
RLS conventions: hybrid table blocks DELETE only; log tables are append-only via
`platform.apply_append_only_rls`; all cross-schema access goes through `public.lifecycle_*`
`SECURITY DEFINER` RPCs (PostgREST does not expose the `platform` schema).

**`platform.feature_lifecycle`** - one row per Feature (the FSM instance; hybrid mutability):
- `feature_id` (uuid pk), `tenant_id` (uuid, by name/id - never `LIMIT 1`), `product_key`
- `title`, `raw_goal`
- `current_state` (text + CHECK over all 19 states)
- `artifact_pointers` (jsonb) - `{ <output_type>: <agent_output_id> }` for each stage
- `created_at`, `updated_at` (TIMESTAMPTZ)

**`platform.lifecycle_events`** - append-only audit of every transition:
- `id` (uuid pk), `feature_id` (fk), `from_state`, `to_state`, `actor`
  (`agent:<id>` | `human:<email>` | `system`), `decision`
  (`create|advance|approve|request_changes|blocked|answers|abandon`), `target_state`
  (loopbacks), `run_id` (driving agent run, nullable), `note`, `created_at`

**`platform.gate_decisions`** - append-only record of human gate outcomes:
- `id` (uuid pk), `feature_id` (fk), `gate` (`A|B|C|D`), `decision`
  (`approve|request_changes|hold`), `reviewer`, `change_requests` (jsonb), `note`,
  `created_at`

Rationale for the split: the FSM **state** must be durable and queryable ("show me every
feature stuck at Gate B"); the agent **artifacts** stay immutable in `agent_outputs`; the
lifecycle row holds only state + pointers. Never copy an artifact body into the spine.

---

## 6. What stays as agent output artifacts

Immutable ledger in `agent_outputs`, referenced by id from
`feature_lifecycle.artifact_pointers`: `clarification_brief`, `codebase_context`,
`product_graph_scope`, `ux_design_brief`, `engineering_change`, `code_review`,
`release_record`.

Agent-owned domain state (distinct from the spine): BA writes `product_graph.graph_nodes`
/ `graph_edges` (024); CCA mints `platform.cbc_identity_registry` (025).

Boundary: the orchestrator never mutates an artifact. It reads, validates, stores a
pointer. Human gate outcomes are lifecycle state, not artifacts.

---

## 7. Implement now vs deferred

| Item | Now (Phase 2) | Deferred |
|---|---|---|
| FSM engine + stage registry (Section 12) | yes (supports all stages) | - |
| `feature_lifecycle` + `lifecycle_events` + `gate_decisions` (migration 026) | yes (full schema) | - |
| PCA stage | yes (exists) | - |
| CCA stage (`agent.py` + migration 025 applied) | yes | - |
| BA stage (`agent.py` + migration 024 applied) | yes | - |
| Human Gate A (decision recorded via `public.lifecycle_record_gate`) | yes | rich review UI |
| Persona Validation stage (`persona-validation-agent` NEW) + schema | - | Phase 2.5 (optional) |
| Sprint Planning Team (`sprint-planning-team` NEW) + schema | - | Phase 3 |
| UX Design stage + `ux-design-brief` schema | - | Phase 4 |
| Engineering stage (`engineering-agent` NEW) | - | Phase 5 |
| Code Review stage wiring (agent exists) | - | Phase 6 |
| Release coordinator + gating | - | Phase 7 |

---

## 8. BA output -> Sprint Planning -> UX Design Agent input

Once Phase 3 lands, the path from approved scope to UX runs **through Sprint Planning**:
`scope_review (Gate A approve) -> sprint_planning -> designing`. Both the BA scope and the
Sprint Planning brief feed UX Design.

A **dedicated** `ux-design-agent` consumes the *approved* Feature Scope Brief (and, once it
exists, the Sprint Planning brief) and emits a UX/design brief (no code). The orchestrator
builds `design_input`:
- `feature_id`, `feature_intent` (FEAT-* title + restated goal)
- `actors[]` (BA Concepts mapped to `cbc:actor:*`)
- `capabilities[]` (in-scope) from the Feature Scope Brief `in_scope`
- `decisions[]` (DEC-*) that constrain UX (multi-tenant, locale, soft-delete, etc.)
- `success_criteria[]` (threaded from the PCA brief)
- `domain_terms[]` (glossary subset relevant to screens)
- `sprint_planning_brief` (future) - story breakdown + sequencing that bounds the screens

UX Design emits `ux_design_brief`: `screens[]` (each with states, fields, actions),
`flows[]` (actor -> screen sequences), `components[]`, design-token reference, optional
Figma link. The existing `ui-design-agent` (React code-gen) is not used here; if code-level
mockups are wanted they belong to Engineering.

### 8a. Future-stage handoffs (Persona Validation, Sprint Planning)

**Persona Validation (Phase 2.5, optional) - PCA -> Persona Validation -> CCA.**
Consumes the Clarification Brief and the ReformAI persona library. Scores the clarified
idea on desirability, frequency, pain intensity, strategic value, and objections, and emits
a **proceed signal** to help decide whether the idea is worth deeper scoping. Adapter
`persona_input`: `feature_id`, `clarification_brief` (restated goal, problem, target user,
success criteria), `personas[]` (ReformAI persona set). Output `persona_validation_report`.
It is **advisory**, not a hard gate in this roadmap: a weak proceed signal can route the
feature to `abandoned` / `changes_requested`, but a human still owns that call. Skippable -
when disabled the orchestrator advances `clarifying -> context_scanning` directly.

**Sprint Planning Team (Phase 3) - Gate A -> Sprint Planning -> UX Design.**
A **team / sub-orchestrator**, not a single worker. Consumes three approved/derived
artifacts (mirrors the Engineering fan-in, Section 9): `product_graph_scope` (approved),
the product graph (`CON-*`/`FEAT-*`/`DEC-*`), and `codebase_context` (code reality /
effort signal). Produces `sprint_planning_brief`: `epics[]`, `stories[]`, `dependencies[]`,
`risks[]`, `sequencing`, `sprint_fit`. This brief informs UX Design **before** design work
begins (story breakdown bounds the screen set) and later seeds the Engineering stage.

---

## 9. UX Design output -> Engineering Agent input

Engineering (NEW) needs **three** upstream artifacts - which is why the spine carries
pointers to all prior artifacts, not just the previous one:
- `ux_design_brief` (approved) - what to build
- `product_graph_scope` (approved) - data model, Concepts, Decisions
- `codebase_context` - code reality (where to add it; existing entities; `cbc:*`)

Adapter (`-> engineering_input`): `feature_id`, `design_brief`, `scope`,
`codebase_context`, `target_repo` + `base_ref` (reuse the CCA `commit_sha` as base).

Engineering emits `engineering_change`: implementation plan, a concrete branch +
`commit_sha`, unified `diff`, tests. A real `commit_sha` + `diff` is the contract that
makes Stage 10 trivial.

---

## 10. Engineering output -> Code Review Agent

**Cleanest seam in the pipeline.** The Code Review Agent already consumes exactly
`diff` + `commit_sha` + `base_sha` + `branch` + `changed_files`. `engineering_change`
carries precisely those, so the adapter is near-identity:

```
engineering_change.{branch, commit_sha, base_sha, diff, changed_files}
   -> code-review-agent inputs (1:1)
```

Code Review emits its existing immutable `code_review` artifact with
`recommendation in {approve, approve_with_warnings, review_required, block}`. Advisory in
v1.

---

## 11. Production deployment gating

A **conjunction** the orchestrator evaluates before entering `deploying`:
1. Gates A, B, C recorded `approve` in `gate_decisions`.
2. Latest `code_review.recommendation != 'block'` - OR a human override recorded at Gate D
   with an explicit reason in `lifecycle_events`.
3. Gate D recorded `approve`.

Then a **thin deterministic Release Coordinator** (not an LLM agent) runs: wraps
`scripts/push.ps1` (already does linter + doc sync + push), writes a `release_record`
artifact (commit, branch, target, timestamp, gate lineage), runs post-release checks.

Future hardening: once Code Review accrues trust (false-positive / override rates),
promote `block` from advisory to a hard gate that cannot be silently bypassed.

---

## 12. Orchestrator architecture - no-rewrite extensibility

Phases 2.5-7 add stages by **appending a descriptor**, never editing the loop.

**Stage descriptor (declarative):**
```
Stage = {
  id,                 # FSM state id, e.g. "scoping"
  agent_id,           # Supabase agent uuid (None for human gates / deterministic)
  kind,               # "agent" | "human_gate" | "deterministic"
  input_adapter,      # fn(lifecycle_row, artifacts) -> stage input dict
  output_type,        # agent_outputs.output_type to expect
  output_schema,      # JSON schema path for validation
  on_block,           # state to enter on agent block/refusal
  next,               # next state on success/approve
  gate,               # None | "A".."D"
}
```

**Engine loop (generic, stage-agnostic):**
```
load feature_lifecycle row (public.lifecycle_get)
while current_state not terminal:
    stage = REGISTRY[current_state]
    if stage.kind == "human_gate":
        decision = read recorded gate decision (block until present)
        public.lifecycle_record_gate(...); advance or loopback
    elif stage.kind == "agent":
        input = stage.input_adapter(row, artifacts)      # pulls upstream artifacts
        run_id = emit run_started(parent_run_id = orchestrator_run_id)
        artifact = call agent(input)
        if blocked/refusal: public.lifecycle_transition(-> on_block); stop
        validate artifact against stage.output_schema     # the contract seam
        public.lifecycle_transition(-> next, artifact_type, artifact_id)
        emit run_completed
    elif stage.kind == "deterministic":
        run release coordinator / etc.; lifecycle_transition(-> next)
```

**Why this avoids a rewrite / redesign:**
- New stage = append a `Stage` descriptor + one pure `input_adapter` + (for new artifacts)
  a JSON schema. The loop and the FSM states are untouched.
- `input_adapter` is the **only** place that knows how to turn upstream artifacts into a
  stage input - exactly the BA->UX, UX->Eng, Eng->Review transforms (Sections 8-10).
- Schema validation at every seam enforces the frozen contracts uniformly.
- `parent_run_id` threading (SDK already supports it) renders the lifecycle as one tree.
- All 19 states + 4 gates are enumerated in migration 026 now, so Phases 2.5-7 add zero DDL.

**Migration of the current `run.py`:** the Phase 1 single-worker script becomes the
`clarifying` stage descriptor + the generic engine. PCA-specific concerns (doc bundle, 48h
staleness gate) move *into the PCA stage's `input_adapter`*, so they do not leak into
CCA/BA (which pin a `commit_sha` instead of checking doc mtimes).

---

## 13. Future agents needed (summary)

| Agent | Status | Action required |
|---|---|---|
| **Persona Validation Agent** (`reformai.persona-validation-agent`) | Does not exist | Net-new, optional; consumes Clarification Brief + persona library, emits `persona_validation_report` (scores + proceed signal); define schema (Phase 2.5) |
| **Sprint Planning Team** (`reformai.sprint-planning-team`) | Does not exist | Net-new team/sub-orchestrator; consumes scope + product graph + codebase context, emits `sprint_planning_brief`; define schema (Phase 3) |
| **UX Design Agent** (`reformai.ux-design-agent`) | Does not exist (dedicated) | Net-new; consumes Feature Scope Brief + Sprint Planning brief, emits `ux_design_brief`; define `ux-design-brief` schema (Phase 4) |
| **Engineering Agent** (`reformai.engineering-agent`) | Does not exist | Net-new - largest effort; consumes design + scope + codebase context; emits diff/commit/tests (Phase 5) |
| **Code Review Agent** (`reformai.code-review-agent`) | Exists, operational, advisory | Wire `engineering_change` -> existing inputs (near-identity); optionally promote `block` to a hard gate later (Phase 6) |
| **Release Coordinator** (`reformai.release-coordinator`) | Does not exist | Thin deterministic coordinator over `scripts/push.ps1` + `release_record`; not a full LLM agent (Phase 7) |
| `reformai.ui-design-agent` (existing) | Exists | Stays separate; out of lifecycle. Optional code-gen tool inside Engineering later |

---

## 14. Phased implementation roadmap

| Phase | Adds | Gate added | New build |
|---|---|---|---|
| 1 (done) | PCA | - | - |
| **2 (v1 target)** | CCA, BA + FSM engine + lifecycle spine | Gate A | CCA/BA `agent.py`, migrations 024/025 applied, migration 026 (spine), FSM refactor of `run.py` |
| 2.5 (optional) | Persona Validation | - | `persona-validation-agent` (new) + `persona-validation-report` schema |
| 3 | Sprint Planning Team | - | `sprint-planning-team` (new) + `sprint-planning-brief` schema |
| 4 | UX Design | Gate B | `ux-design-agent` (new) + `ux-design-brief` schema |
| 5 | Engineering | Gate C | `engineering-agent` (new) + `engineering-change` schema |
| 6 | Code Review | Gate D | Eng->review adapter (agent already built) |
| 7 | Release | deploy conjunction | release coordinator + `release-record` schema |

Note: Sprint Planning is inserted as Phase 3; UX/Engineering/Code Review/Release each
shifted +1 from the prior numbering to accommodate it. Persona Validation is Phase 2.5
(optional, advisory) and not on the critical path.

v1 scope is **Phase 2**: `Idea -> PCA -> CCA -> BA -> Gate A`, with the FSM/storage spine
built to full shape so Phases 2.5-7 are additive.

---

## 15. Minimum migration 026 (lifecycle spine)

`supabase/migrations/026_feature_lifecycle.sql` - **authored, NOT applied** (same status as
024/025). Depends on 012 (platform schema + `apply_append_only_rls`). Must pass
`python scripts/check_migrations.py --from-migration 026` before applying.

Minimum scope kept lightweight for Phase 2:

**3 tables**
- `platform.feature_lifecycle` - hybrid mutability (state/pointers/updated_at mutate;
  feature_id/tenant_id/created_at frozen). RLS: enable + restrictive `no_delete` +
  permissive SELECT/INSERT/UPDATE. `current_state` CHECK enumerates **all 19 states now**
  (incl. the future `persona_validating` and `sprint_planning`).
- `platform.lifecycle_events` - append-only (`apply_append_only_rls`). `decision` CHECK
  covers create/advance/approve/request_changes/blocked/answers/abandon.
- `platform.gate_decisions` - append-only (`apply_append_only_rls`). `gate` CHECK
  `A|B|C|D` (**all four now**); `decision` CHECK approve/request_changes/hold.

**4 public RPCs** (SECURITY DEFINER, `SET search_path = platform, public`) - the only
surface the orchestrator calls:
- `public.lifecycle_create_feature(tenant_id, product_key, title, raw_goal, created_by) -> uuid`
  inserts the feature at `intake` and logs the `create` event.
- `public.lifecycle_transition(feature_id, to_state, actor, decision, run_id?, artifact_type?, artifact_id?, target_state?, note?)`
  atomically updates state, merges an artifact pointer (if given), appends an event.
- `public.lifecycle_record_gate(feature_id, gate, decision, reviewer, to_state, change_requests?, target_state?, note?)`
  inserts the gate decision, transitions state, appends an event.
- `public.lifecycle_get(feature_id) -> jsonb` returns the feature row (incl. pointers).

**1 trigger** - `feature_lifecycle` BEFORE UPDATE: freeze `feature_id`/`tenant_id`/
`created_at`, refresh `updated_at`.

**Governance** - register both log tables + the hybrid table in
`platform.schema_registry` (RFC-AAF-001).

What is deliberately deferred (not needed for Phase 2, addable without schema change):
- tenant-isolation RLS via `app.current_tenant_id` (Phase 2 relies on service-role +
  explicit `tenant_id` passed to the RPC; isolation policy is additive later).
- a richer list/query RPC for the review dashboard (`lifecycle_list_by_state`).
- materialized views over events.

### 15a. Amendment for Persona Validation + Sprint Planning (2026-06-02)

Adding these two future stages required a **minimal** amendment to 026: two values
(`persona_validating`, `sprint_planning`) added to the `feature_lifecycle.current_state`
CHECK enumeration. This was unavoidable - the CHECK is a closed list, so a transition into
a state not enumerated would raise a constraint violation. The amendment is zero-cost
because 026 is authored-NOT-applied; it simply completes the enumeration before first
apply, preserving the "all states enumerated now, zero later DDL" invariant.

No other part of 026 changed: no new tables, no new gates (`gate_decisions.gate` stays
`A|B|C|D`), no new `lifecycle_events.decision` values (both stages use `advance`/`blocked`),
no RPC signature changes. `persona_validation_report` and `sprint_planning_brief` are stored
as ordinary `artifact_pointers` jsonb keys, which need no schema change.

Phase 2 only ever drives states `intake -> clarifying -> context_scanning -> scoping ->
scope_review` and Gate `A`; the remaining states/gates sit unused in the same tables until
their phase lands.
