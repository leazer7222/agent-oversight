# Output Contract - BA Scoping Agent

The agent produces one artifact conforming to `docs/schemas/product-graph.schema.json`
(`artifact_type: "product_graph_scope"`), plus the graph mutations applied via RPC.

## Artifact storage

Written to `agent_outputs.content` with `output_type = 'product_graph_scope'`. The artifact is the
on-disk mirror of the `product_graph.graph_nodes` / `graph_edges` rows produced this run. Treat the
written artifact as an immutable ledger entry - corrections are new runs/rows, never edits (same
append-only principle as `code_review` artifacts).

## What the agent produces

| Output | Form | Notes |
|---|---|---|
| Feature node | `FEAT-*`, `status: scoping \| ready` | Process plane; carries `scoped_against_commit` |
| Concept nodes | `CON-*`, `status: proposed` (until ratified) | `kind`, `aliases[]`, `maps_to_codebase[]` |
| Question nodes | `QST-*`, `status: open` | `blocking`, `divergence`; blocking+high only |
| Decision nodes | `DEC-*`, `status: proposed` (until ratified) | `rationale`, `implies_rules[]`, `implies_attributes[]` |
| Edges | `references` / `resolves` / `supersedes` / `derived_from` | endpoints by `node_key` |
| Readiness | `readiness` object | convenience echo of `graph_feature_readiness` (derived) |
| Feature Scope Brief | `brief_markdown` | projection; rendered only when `scope_ready` |

## What it must NOT produce (v1)

- No PRDs, user stories, or acceptance criteria.
- No `Rule` or `Attribute` nodes - captured as `implies_*` stubs inside Decisions instead.
- No `Assumption` nodes - low-divergence assumptions become `feature.node_attributes.notes[]`.
- No `cbc:*` identities - `maps_to_codebase[]` only references existing ones.

## Forward-compatibility stubs

Decisions MUST preserve, inside `node_attributes`:

- `implies_rules[]` - plain-language rule statements the decision establishes.
- `implies_attributes[]` - `{concept, fields[]}` field sets the decision implies.

These are unused by the v1 brief but make Phase 2 promotion (to `Rule` / `Attribute` nodes) a
migration, not a re-scoping. Omitting them loses knowledge that cannot be recovered without
re-litigating the decision.

## Readiness echo

`readiness` mirrors `public.graph_feature_readiness(tenant, product_key, feature_key)`. The DB function is
authoritative; the artifact field is a convenience snapshot. It always includes
`gate_contradiction_check: "deferred_v1"` so the known v1 gap is visible in the artifact.

```json
{
  "scope_ready": true,
  "gate_open_blocking_questions": 0,
  "gate_open_high_divergence": 0,
  "gate_unresolved_concepts": 0,
  "gate_contradiction_check": "deferred_v1"
}
```

## Brief rendering rule

`brief_markdown` is rendered **only** when `readiness.scope_ready` is `true`. When not ready, the
agent emits the open Questions and either omits the brief or marks it `PROVISIONAL`. The brief is a
disposable projection - every line traces to a node; nothing is asserted that is not in the graph.

## Telemetry on completion

`run.report(tokens_in, tokens_out, cost_usd)` before the context manager exits, so
`run_completed` carries cost data. A null `cost_usd` without reporting is indistinguishable from
"didn't report" - always report, even if zero.
