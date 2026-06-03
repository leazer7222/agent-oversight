# Runtime Workflow - BA Scoping Agent

The complete run flow from feature idea to scope-ready brief. The agent is stateless per run; all
durable state lives in `product_graph.*`. Wrap the whole run in `OversightClient.run(...)` so
`run_started` / `run_completed` / `run_failed` are emitted with a single `run_id`.

## Flow

| # | Step | Action | Telemetry step | Failure mode |
|---|---|---|---|---|
| 1 | Validate input | Check `feature_intent`, `product_key`, `tenant` present | `input_validated` | `validation_error` -> abort |
| 2 | Validate codebase context | Validate `codebase_context` against `codebase-context.schema.json`; check `commit_sha`, `coverage.confidence` | `codebase_context_validated` | `validation_error` -> abort |
| 3 | Resolve tenant | Resolve company by **name or explicit UUID** (never `LIMIT 1`) | `tenant_resolved` | abort if ambiguous/missing |
| 4 | Set tenant context | Make the resolved company id visible to RLS via `set_config('app.current_tenant_id', ...)`. v1 = session GUC path, preferably set INSIDE each write RPC (PostgREST per-call transaction caveat - see graph-operations.md) | `tenant_context_set` | abort if unset (RLS would deny) |
| 5 | Upsert Feature | `graph_upsert_node(node_type='feature', status='scoping', node_attributes.scoped_against_commit=<sha>)` | `feature_upserted` | non-fatal retry |
| 6 | Resolve Concepts | For each noun: `graph_resolve_concept` (existing CON-*?) + `codebase_context.concept_resolution[]` (cbc match?); propose new CON- as needed | `concepts_resolved` | - |
| 7 | Map to cbc:* | Set `concept.maps_to_codebase[]` from `concept_resolution[].cbc_ids` (plural). Confirm via `public.cbc_resolve` if needed. Never mint cbc:* | `concepts_mapped` | - |
| 8 | Generate Questions | Detect assumptions, rank by divergence; emit `QST-*` for **blocking + high-divergence** only; `derived_from` edges | `questions_generated` | - |
| 9 | Capture Decisions | (Ratification pass) human answers -> `DEC-*` (proposed), decompose multi-fork answers, fill `implies_rules[]`/`implies_attributes[]` | `decisions_captured` | - |
| 10 | Add edges | `references` (decision/feature -> concept), `resolves` (decision -> question), `supersedes`, `derived_from` | `edges_added` | - |
| 11 | Run readiness | `graph_feature_readiness(product_key, feature_key)` | `readiness_evaluated` | - |
| 12 | Render brief | If `scope_ready`: render `brief_markdown` from the subgraph (`graph_feature_subgraph`). Else: emit open Questions, mark PROVISIONAL, stop | `brief_rendered` / `brief_withheld` | - |
| 13 | Emit artifact + telemetry | Write `product_graph_scope` to `agent_outputs`; `run.report(tokens_in, tokens_out, cost_usd)` | (run_completed) | telemetry non-fatal |

**Node-key minting (Decision 1):** before every `graph_upsert_node` for a NEW node (steps 5, 8, 9),
call `graph_next_key(product, node_type)` to mint the opaque sequential key (`FEAT-0001`, `CON-0001`,
`QST-0001`, `DEC-0001`). The runtime never generates keys itself. The human-readable name goes in
`title`.

## Two-pass shape

The run is naturally two passes around the human:

- **Pass A (steps 1-8, 11-12):** scope, propose, generate Questions, compute readiness. If not ready,
  render the open Questions and stop. The graph now holds `proposed` nodes awaiting ratification.
- **Pass B (steps 9-13):** after human answers + ratification, capture Decisions, add `resolves`
  edges, recompute readiness, render the brief, write the artifact.

A fully unambiguous feature (rare) collapses to one pass.

## Telemetry rules

- Every meaningful step emits `run.step(name, message=..., duration_ms=t.ms, payload={...})`.
- Step emission is non-fatal - wrap in try/except, never let it block scoping.
- On completion report `tokens_in`, `tokens_out`, `cost_usd` (per the LLM provider usage object).
- Errors are categorized by the SDK (`quota_exceeded | auth_error | network_error | llm_error |
  validation_error`) and stored on `runs.error` as `[category] message`.

## Idempotency

- `graph_upsert_node` is upsert-on-`(product_key, node_key)`; re-running a pass updates still-mutable
  nodes and is blocked by the immutability trigger on accepted ones.
- `graph_add_edge` is idempotent on `(edge_type, src, dst)`.
- The BA Agent owns `node_key` minting; keys must be stable across passes for the same feature.
