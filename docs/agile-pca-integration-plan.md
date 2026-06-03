# PCA as the Agile Front Door - Intake Normalization (Implementation Plan)

Status: APPROVED design, build pending
Owner: `reformai`
Relates to: `docs/agent-agile-force-lifecycle.md` (implements its `clarifying` stage against
the LIVE product_graph model; forward-compatible with the deferred 026 spine).

## Locked principle

> **PCA does not always ask questions. PCA asks questions only when the intake package
> cannot confidently satisfy the Clarification Brief contract.**

PCA is the **Agile front door and intake-normalization agent**. Its job is to transform
arbitrary product intake - from a one-line idea to a near-complete multi-artifact spec -
into a complete, schema-valid Clarification Brief plus a downstream handoff. **Clarification
is conditional, not automatic.**

## Decision record (2026-06-03)

- **PCA = intake normalization**, not clarification. The invariant is the OUTPUT contract
  (the Brief + handoff); questioning is a conditional gap-filling tool.
- **Conditional clarification** driven by a classifier, not a fixed step.
- **Intake Classifier is its own LOGGED artifact** (`intake_assessment`) - the ask/skip/block
  decision must be auditable before the lifecycle advances.
- **Adapter / package / classifier / core** architecture (below).
- **Text-first** (Phase 1); **multimodal adapters deferred** (Phase 2).
- **Option A** retained - BA stamps the PCA->feature link; PCA never creates the `FEAT-*`
  node. No migration 026 required.

## Responsibility boundary (the guardrail)

PCA populates ONLY Clarification Brief contract fields + the handoff. Anything it extracts
that does not map to a contract field, it **references** (attachment/link); it does not
**re-model**. PCA captures what the intake ASSERTS (stated intent, even when that intent
arrives as a diagram or mockup).

PCA does NOT:
- read source code or scope against the codebase -> that is the **CCA**.
- produce Concepts / Decisions / Questions about the data model, or resolve `cbc:*` -> **BA**.
- author screens / flows / components / a design brief -> the **UX Design Agent**. (PCA may
  CAPTURE design intake and carry forward refs as `design_inputs`, never re-author it.)
- score personas -> the **Persona Validation Agent** (optional next stage).
- estimate effort / sequencing -> the **Sprint Planning Team**.

The contract is the governor: if a piece of extracted intent does not fill a Brief field or
the handoff, it is referenced, not authored into a downstream artifact.

## Architecture

```
raw intake (any form, one or many artifacts)
  -> INTAKE ADAPTERS        # per source_type; normalize raw -> package fragments
  -> INTAKE PACKAGE         # ONE canonical representation (intent-level)
  -> INTAKE CLASSIFIER      # score Brief-contract coverage; emit Intake Assessment ARTIFACT
  -> CONDITIONAL CLARIFY    # decision: proceed_direct | clarify | block
  -> BRIEF SYNTHESIS        # schema-valid Clarification Brief + handoff
  -> handoff to CCA / BA
```

Modes live at the **adapter boundary**, not in the reasoning core. Adding a new input form =
a new adapter; the package, classifier, and synthesis core never change. PCA "determines the
processing path itself" via the classifier (not via a mode flag).

PCA has TWO inputs, kept distinct:
1. **Intake** (variable) - what the user is asking for, via adapters.
2. **Product grounding** (stable per product) - `PRODUCT.md` / `DOMAIN.md` so `target_user`
   references real user definitions and `domain_terms` match the glossary.

## 1. Intake Package (canonical abstraction)

The single internal representation every adapter produces, regardless of source. Intent-level
only (no code reality, no design authoring):

```
intake_package {
  sources[]:          [{ source_type, origin_ref, content_hash, adapter, ingested_at }]
  normalized_text:    string                 # unified statement of intent across all sources
  extracted_signals: {                       # ASSERTED intent, used to fill Brief + handoff
    explicit_goals[]:   string,
    actors[]:           string,              # roles the intake mentions
    workflows[]:        string,              # flows/steps the intake describes
    states[]:           string,              # conditions/states the intake implies
    entities[]:         string,              # nouns/objects (-> handoff.concepts_to_check seeds)
    stated_rules[]:     string,              # business rules explicit in the intake
    constraints[]:      string
  }
  attachments[]:      [{ kind, ref }]        # figma/screenshot/loom refs (Phase 2 populated)
  provenance:         { source_count, modalities[], mixed: bool }
}
```

Schema: `docs/schemas/intake-package.schema.json` (internal contract; embedded in the
Assessment artifact for audit rather than persisted on its own).

## 2. Intake Assessment (its own logged artifact)

Written to `agent_outputs` with `output_type = 'intake_assessment'` **before any Brief, on
every run, regardless of branch.** This is the auditable record of why PCA asked, skipped, or
blocked.

```
intake_assessment {
  schema_version, artifact_id, run_id, product_key, tenant_id, generated_at, generator
  intake_package: { ... }                    # embedded for full audit
  field_coverage: [                          # one row per required Brief field + handoff
    { field, covered: bool, confidence: 0..1, evidence, source_refs[] }
  ]
  scores:        { fidelity, completeness, ambiguity, context_confidence }   # 0..1
  blocking_gaps: [ { field, why } ]          # uncovered contract fields -> become questions
  decision:      "proceed_direct" | "clarify" | "block"
  rationale:     string
  draft_brief?:  { ... }                     # clarify branch only: provisional Brief for the
                                             #   dashboard while awaiting answers (NOT persisted
                                             #   as a clarification_brief artifact until final)
}
```

Decision semantics:
- **`proceed_direct`** - all required fields covered, no blocking forks -> synthesize a
  FINALIZED Brief in one pass, **zero questions**.
- **`clarify`** - one or more blocking gaps -> synthesize a PROVISIONAL Brief whose
  `open_questions` are exactly the `blocking_gaps`; await answers; run Pass B.
- **`block`** - intake too thin to form coherent intent -> no Brief; lifecycle enters
  `clarification_blocked`; the assessment explains what is missing.

Schema: `docs/schemas/intake-assessment.schema.json`.

## 3. Conditional clarification + Pass B (write ordering)

PCA writes the `intake_assessment` FIRST, on every run. It writes the `clarification_brief`
artifact ONLY when the Brief is FINAL - on `proceed_direct`, or after Pass B. This holds the
invariant: **a `clarification_brief` artifact is always the finalized contract, never a
provisional draft** (BA only ever stamps a final brief).

- **Pass 0 (always):** adapters -> package -> classifier -> write the `intake_assessment` artifact.
- **Pass A (synthesis), branched on the Assessment decision:**
  - `proceed_direct` -> synthesize the FINAL Brief (`open_questions: []`) -> write
    `clarification_brief`. Done; no Pass B.
  - `clarify` -> synthesize a DRAFT Brief whose `open_questions` are the blocking gaps, and
    carry it on the Assessment (`intake_assessment.draft_brief`) for dashboard display.
    **Do NOT write a `clarification_brief` artifact yet.**
  - `block` -> no Brief; lifecycle enters `clarification_blocked`; the Assessment explains the gap.
- **Pass B (clarify branch only):** ingest human answers -> re-synthesize the FINAL Brief and
  finalize the handoff -> write `clarification_brief`. **Pass B never runs on `proceed_direct`.**

A paragraph / PRD / well-formed ticket that already satisfies the contract flows straight to a
finalized Brief with no questions.

## 4. The dashboard contract this targets (already built - do not redesign)

- `src/app/api/scoping/[feature]/route.ts` reads the brief via
  `feature.node_attributes.clarification_brief_artifact_id` and returns `{ artifact_id, ...content }`.
- `src/components/dashboard/ScopingReview.tsx` renders it (Clarification Brief (PCA) panel).
- `agent_outputs.output_type` is a CHECK constraint (027/029 pattern) lacking both
  `clarification_brief` and `intake_assessment`.

PCA writes the `clarification_brief` artifact; BA stamps its id into
`node_attributes.clarification_brief_artifact_id`; the UI lights up with no frontend change.
The Brief carries `metadata.intake_assessment_artifact_id` so the Assessment is reachable for
audit (a dedicated Assessment panel is a small Phase-1.5 dashboard add).

## 5. Handoff to CCA / BA

`clarification-brief.schema.json` gains an optional `handoff`:
```
"handoff": { "feature_intent": string, "concepts_to_check": string[] }
```
- `feature_intent` = the finalized `restated_goal` -> CCA / BA `--feature-intent`.
- `concepts_to_check[]` = salient entity nouns (seeded from `extracted_signals.entities`,
  finalized after any Pass B) -> CCA `--concepts-to-check` (additive; never narrows CCA).

## Interaction surface & execution model (Phase 1a -> 1b)

The human and the agent never talk directly - they exchange artifacts through Supabase. The
dashboard is the human's window; the Python agent is the execution. The trigger model evolves
(1a -> 1b); the artifact contracts do not.

**1. Supabase is the structured communication bus.** Every exchange is a row, not a message:
PCA writes `intake_assessment` / `clarification_brief` to `agent_outputs`; the human writes
answers via the existing `scoping/[feature]/answer` route; the agent reads them back on Pass B.
There is no direct request/response between browser and agent.

**2. The dashboard is the human interaction surface.** In Phase 1a the human, entirely in the
app: submits intake -> views the Intake Assessment (coverage / scores / decision / rationale)
-> views the draft Clarification Brief -> answers blocking PCA questions -> views the finalized
Brief + handoff. Structured forms, not a chat.

**3. Python CLI is the Phase 1a execution mechanism.** PCA (and Pass B) run as a local
`python agent.py` against Supabase. The human experience is fully in-app; only execution is
operator-triggered CLI. No new infra required.

**4. Hosted worker / queued job is the Phase 1b target.** A `POST /api/agile/intake` route
enqueues a run; a hosted worker executes the agent and streams status back, so the human never
leaves the browser. Net-new infra (a runner for the Python agents), bounded and isolated to
execution.

**5. New UI pieces needed:**
- **New Feature / Intake submission form** - paste idea / paragraph / PRD / ticket text (Phase 2:
  attach Figma / screenshots / Loom). Net-new; today a feature only appears when BA runs.
- **Intake Assessment panel** - coverage table, scores, decision, rationale. The auditable view.
- **PCA clarification answer panel** - answer blocking questions; a copy of the BA answer pattern.

**6. Existing UI pieces we reuse:**
- The **BA-style answer route/pattern** (`scoping/[feature]/answer` + `/ratify`) - clone for PCA.
- The **PCA brief rendering panel** in `ScopingReview.tsx` (already reads
  `clarification_brief_artifact_id`).
- **Agent run + cost history** (`/api/agents`, `/api/runs`) - PCA runs appear automatically via
  oversight telemetry.

**7. The trigger model must not change the artifact contract.** Whether PCA is launched by CLI
(1a) or a hosted worker (1b), it writes the identical `intake_assessment` and
`clarification_brief` artifacts and reads the identical answer rows. The dashboard reads
artifacts, never the trigger. This is why 1a is the fastest correct path and 1b is a drop-in
execution upgrade with zero schema/UI churn.

## Build steps

### Step 1 - Migration `033_pca_intake_output_types.sql`
Copy the 029 pattern; add BOTH values to the `agent_outputs_output_type_check` array:
`'clarification_brief'` and `'intake_assessment'`. Lint
(`check_migrations.py --from-migration 033`) then `apply_sql.py`.

### Step 2 - Schemas
- New `docs/schemas/intake-package.schema.json` and `docs/schemas/intake-assessment.schema.json`.
- Edit `docs/schemas/clarification-brief.schema.json`:
  - add optional `handoff` (above);
  - **relax `open_questions` to `minItems: 0`** (a fully-covered intake yields zero questions -
    today's `minItems: 1` would reject a `proceed_direct` Brief);
  - add optional `metadata.intake_assessment_artifact_id`;
  - add optional `design_inputs[]` (carried-forward refs; Phase 2 populated).

### Step 3 - PCA runtime (`agents/library/product-clarification-agent/agent.py`)
Restructure into the four-stage core (text adapters in Phase 1):
- **Adapters:** `--intake-file <path> --intake-type <idea|paragraph|prd|jira_text|customer_feedback|bug_enhancement|text_workflow>`, repeatable; or an intake manifest for mixed. Each adapter normalizes its source into package fragments and tags provenance.
- **Package assembly:** merge fragments into one `intake_package`.
- **Classifier:** LLM pass scoring per-field coverage -> write the `intake_assessment` artifact (always) -> decision.
- **Synthesis:** produce the Brief (final or provisional per decision) + `handoff`; validate against schema; write `clarification_brief` artifact (unless `block`).
- Align with BA/CCA: `--product-key`/`--tenant` + `resolve_tenant()` (never `LIMIT 1`);
  `write_agent_output(...)`; `load_dotenv(override=True)`; scrub empty `ANTHROPIC_AUTH_TOKEN`/
  `ANTHROPIC_CUSTOM_HEADERS`; report `tokens_in_hint`/`model`/`provider`.
- `--no-persist` and a `--pass b --answers <file>` path for the clarify branch.
- PCA touches NO product_graph / cbc / feature nodes (guardrail).

### Step 4 - Product grounding bundle `docs/workspaces/reformai-product/context-bundles/agile-v1.json`
`PRODUCT.md` (roles: admin, home_owner, home_buyer, service_provider, seller; what exists -
room-scoped material catalogue is product selection, not supplier inventory), `DOMAIN.md`
(Colombia single-market: COP, NIT, IVA, Wompi; glossary), `STORY-READY.md`, manifest.

### Step 5 - BA stamps the link (`agents/library/ba-scoping-agent/agent.py`)
Add `--clarification-artifact-id`; in `scope_to_graph`, set
`feat_attrs["clarification_brief_artifact_id"]`. One field; no frontend change. BA keeps sole
ownership of the `FEAT-*` node.

### Step 6 - Orchestrator threading (`agents/teams/agile/run.py`)
Run PCA -> read the Assessment decision:
- `proceed_direct` -> emit handoff, advance.
- `clarify` -> surface blocking-gap questions (soft gate), collect answers, Pass B, then advance.
- `block` -> stop at `clarification_blocked`; surface the Assessment rationale.
Emit `{clarification_artifact_id, intake_assessment_artifact_id, handoff}` for CCA/BA (auto-chain
is the next increment). Keep the doc-bundle staleness gate scoped to PCA grounding only.

## Phasing

**Phase 1 - text intake only:** idea, paragraph, PRD, Jira ticket text, customer feedback,
bug/enhancement request, text-described workflow. Exercises the ENTIRE architecture (adapters
-> package -> classifier -> conditional clarify -> synthesis) with no vision dependency.

**Phase 2 - multimodal adapters (deferred):** Figma, screenshots, Loom/video transcript,
workflow diagrams. Pure additions: new adapters populate `attachments[]` + `extracted_signals`
into the SAME package and core. The classifier and synthesis are unchanged. Requires vision /
transcription / Figma-Jira API plumbing - that is the only net-new capability, isolated to
adapters.

## Build order

1. Step 1 (migration 033) - unblocks both artifact writes.
2. Step 2 (schemas) - defines package, assessment, handoff; relaxes `open_questions`.
3. Step 3 (PCA runtime, text adapters) - the core repurpose.
4. Step 4 (reformai-product grounding) - needed to run against the real target.
5. Step 5 (BA stamp) - one line.
6. Step 6 (orchestrator threading) - ties it together.

## Acceptance tests (all three branches must work)

1. **proceed_direct:** feed a complete paragraph/PRD for the materials feature ->
   `intake_assessment` artifact written with `decision=proceed_direct`, coverage all-true ->
   finalized Brief with `open_questions: []` and a populated `handoff` -> no Pass B.
2. **clarify:** feed the one-line idea -> assessment `decision=clarify` with `blocking_gaps`
   and a `draft_brief` (NO `clarification_brief` artifact yet) -> supply answers -> Pass B
   writes the finalized `clarification_brief`.
3. **block:** feed a near-empty intake -> assessment `decision=block`, no Brief, lifecycle
   `clarification_blocked`, rationale explains the missing fields.
4. In all cases the `intake_assessment` artifact exists and is inspectable BEFORE any advance.
5. After CCA + BA (with `--clarification-artifact-id`), `/dashboard/scoping/<feature>` shows
   the real Clarification Brief panel.

## Forward-compatibility with migration 026 (the spine)

When `feature_lifecycle` lands: `clarification_brief_artifact_id` and
`intake_assessment_artifact_id` become `artifact_pointers` entries; the Assessment `decision`
maps to the `clarifying` -> `clarification_blocked` / `context_scanning` transitions; the
`handoff` feeds the stage input_adapter unchanged. This plan is a strict subset of the spine.

## Caveats / non-goals

- Phase 2 multimodal is design-reserved, not built; only text adapters ship in Phase 1.
- Pass B (answer ingestion) is operator-driven (CLI) in Phase 1; the dashboard answer panel for
  PCA is a small follow-on, mirroring the BA ratification UI.
- No auto-flip of feature status; contradiction gate `deferred_v1` (both unchanged).
- PCA grounding is curated `PRODUCT.md`/`DOMAIN.md`, NOT code - PCA runs before CCA by design.
