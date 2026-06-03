# Ratification Workflow - BA Scoping Agent

Ratification is the single human-owned gate that keeps the graph trustworthy. The agent proposes;
the human disposes. Designed for a two-person team - fast, batched, mandatory.

## Plane rule

| Plane | Nodes | Ratification |
|---|---|---|
| Process | `Feature`, `Question` | None - agent-owned, inherently provisional |
| Knowledge | `Concept`, `Decision` | **Required** to reach `accepted` (becomes `fact`) |

Process-plane nodes need no ratification - they are scaffolding, and the epistemic derivation rule
already prevents them from being mistaken for truth. Knowledge-plane nodes are **quarantined while
`proposed`**: they do not count as `fact`, do not appear in retrieval-as-truth, and a `proposed`
Concept must not be cited by an `accepted` Decision.

## What requires approval

Every transition *into* `accepted` on the knowledge plane:

- `Concept`: `proposed -> accepted` (or `rejected` / `deprecated`).
- `Decision`: `proposed -> accepted` (or `rejected`).

Nothing else needs a human: feature/question creation, alias matches above the confidence threshold
(folding `vendor` into `CON-supplier` is mechanical), and brief rendering are all automatic.

## Human action set

Per proposed node, one batch screen with three actions:

- **accept** - flips to `accepted`, stamps `ratified_by` / `ratified_at` (via `graph_ratify_node`).
- **reject(+reason)** - flips to `rejected`; the node is **retained** as the road-not-taken.
- **edit-then-accept** - human edits the still-mutable proposed node, then accepts.

## When the human disagrees

The human edits the proposed node before accepting, or rejects with a rationale. A rejected Decision
is not deleted - it is the documented alternative. Most systems throw away their most useful data
here; this one keeps it.

## When decisions conflict

The agent runs a contradiction check at proposal time (one-hop walk over shared Concept references -
**deferred in v1** as readiness gate 4, but the supersede mechanism exists now). Resolution is always
**supersede-and-retain**, never overwrite: the winning Decision gets a `supersedes` edge to the loser,
which becomes `superseded`. Accepted Decisions are content-frozen by trigger - you cannot edit one,
only supersede it.

## Immutability

- `accepted` Concepts/Decisions are content-frozen (migration 024 trigger).
- The only permitted move from `accepted` is `-> superseded` / `-> deprecated` (status only).
- To change ratified knowledge: mint a new node + `supersedes` edge. Never edit.

## Ratification backlog is a health metric

The failure mode that kills a two-person graph is becoming **write-only** - proposed nodes pile up
unratified, retrieval quality degrades, trust collapses. Controls:

- Track **count of `proposed` knowledge-plane nodes** and their **age** as a first-class metric.
- Keep proposed volume low: alias-resolve before minting Concepts; batch ratification.
- Surface backlog in the oversight dashboard alongside run health.

If the backlog grows monotonically, the system is dying regardless of schema quality. The ratification
UX is not deferrable - design it before the runtime.

## State transitions (reference)

```
Concept:   proposed --accept--> accepted --deprecate--> deprecated
                    \--reject--> rejected
Decision:  proposed --accept--> accepted --supersede--> superseded
                    \--reject--> rejected
Question:  open --answer--> answered          (resolved by a Decision)
                \--defer--> deferred
Feature:   scoping --(readiness passes)--> ready --handoff--> handed_off
                   \--shelve--> shelved
```
