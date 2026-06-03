# Feature Scope Brief - Format Spec

Defines the structure of `brief_markdown` in the `product_graph_scope` artifact. The brief is a
**projection over the graph**, not a source of truth. Every line must trace to a node or edge; the
renderer asserts nothing that is not in `graph_feature_subgraph`.

## Rendering preconditions

- Rendered in full **only** when `graph_feature_readiness(...).scope_ready == true`.
- When not ready, the renderer either omits the brief or emits a PROVISIONAL brief that contains
  **only** the Open Questions section plus a banner. It never renders Decisions/Scope as settled when
  forks are open.
- The brief is regenerable at any time from the graph. Never hand-edit it; change the graph and
  re-render.

## Banner (conditional)

If not scope-ready, the first line is:

```
> PROVISIONAL - NOT SCOPE READY. N blocking question(s) open. Decisions below are not final.
```

## Section order and sources

| # | Section | Source nodes/edges | Omit when |
|---|---|---|---|
| 1 | Title + status | `FEAT-*` title, status; `scoped_against_commit` | never |
| 2 | Problem | `FEAT.intent` + referenced Concepts | never |
| 3 | Actors | Concepts `kind: actor` referenced by the feature | no actor concepts |
| 4 | In scope | `accepted` Decisions defining inclusions | not ready |
| 5 | Out of scope / non-goals | Decisions with explicit exclusions; deferred notes | empty |
| 6 | Key decisions | `accepted` `DEC-*` (statement + rationale) with cited Concepts | not ready |
| 7 | Rejected alternatives | `rejected` `DEC-*` (the road not taken) | none rejected |
| 8 | Entities touched | Concepts via `references` edges, with `nature` and `maps_to_codebase[]` | no concepts |
| 9 | Open questions | `open` `QST-*` (blocking flagged) | none open |
| 10 | Open assumptions | `feature.node_attributes.notes[]` (low-divergence) | empty |
| 11 | Readiness | `graph_feature_readiness` gate breakdown + verdict | never |
| 12 | Traceability footer | node/edge counts; artifact_id; commit_sha | never |

## Traceability rule

Each decision and scope line cites the node it derives from, inline:

```
- Material listings are supplier-authored and supplier-owned. (DEC-01; refs CON-supplier, CON-material)
```

A scope/decision line with no citation is a rendering bug - it means the brief is asserting something
not in the graph. Fail the render rather than emit an uncited claim.

## Skeleton

```markdown
# Feature Scope Brief: <FEAT title>
Status: <scoping|ready>  |  Scoped against: <commit_sha>  |  Artifact: <artifact_id>

## Problem
<intent restated as a user problem; refs the actor/entity concepts>

## Actors
- <Actor concept> (CON-...; maps_to_codebase: [...])

## In scope
- <inclusion> (DEC-..; refs CON-..)

## Out of scope
- <exclusion> (DEC-..)

## Key decisions
- <decision statement>
  Rationale: <why>. (DEC-..; refs CON-..)

## Rejected alternatives
- <alternative> - rejected. (DEC-..(rejected))

## Entities touched
- CON-material (nature: creates; maps_to_codebase: [cbc:entity:material])

## Open questions
- [BLOCKING] <question> (QST-..)

## Open assumptions
- <low-divergence assumption captured as a note>

## Readiness
scope_ready: <bool> | blocking_questions: N | high_divergence: N | unresolved_concepts: N | contradiction_check: deferred_v1

---
Traceability: <X> nodes, <Y> edges. Generated from graph_feature_subgraph.
```

## What the brief must never contain (v1)

- PRD/user-story/acceptance-criteria content (Phase 2).
- Field-level entity schemas as prose - field sets live in `DEC-*` `implies_attributes[]`, surfaced
  only as a decision reference, not a spec table.
- Any claim without a node citation.
