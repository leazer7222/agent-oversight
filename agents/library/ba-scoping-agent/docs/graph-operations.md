# Graph Operations - BA Scoping Agent

All graph access goes through `public.*` SECURITY DEFINER RPCs. PostgREST does not expose the
`product_graph` schema, so direct table access from the Supabase client is not available - RPCs are
the only path. Defined in `supabase/migrations/024_product_graph_phase1.sql`.

## Tenant context

`product_graph.graph_nodes` enforces tenant isolation RLS via `current_setting('app.current_tenant_id')`.

**v1 decision: session GUC path.** The agent resolves the company id and makes it visible to RLS via
`set_config('app.current_tenant_id', '<company-uuid>', ...)`.

**Caveat that determines HOW to set it:** PostgREST runs each RPC in its own transaction. A standalone
`set_config(..., is_local => true)` (transaction-local) call will NOT survive into a separate
following RPC call - the GUC resets when that transaction ends. Two correct ways to satisfy this:

- **Preferred - set inside each write RPC.** Each SECURITY DEFINER write RPC already receives
  `p_tenant`; have it run `PERFORM set_config('app.current_tenant_id', p_tenant::text, true)` at the
  top so the RLS `WITH CHECK` passes within the same transaction. This makes tenant context
  self-contained per call and removes the cross-call ordering hazard. **Requires a one-line amendment
  to migration 024 before it is applied** (tracked; 024 is not yet applied).
- **Alternative - pinned session.** On a single pinned connection, set
  `set_config('app.current_tenant_id', '<uuid>', false)` (session-level, `is_local=false`) once, then
  issue the RPCs on that same connection. Brittle with pooled connections; only use with an explicit
  dedicated connection.

Resolve the company by **name or explicit UUID** - never `LIMIT 1`. There are multiple companies
(ReformAI, AfterGlow, Personal) and creation order is not guaranteed.

```sql
-- correct
SELECT id FROM companies WHERE name = 'ReformAI';
-- WRONG - returns an arbitrary company
SELECT id FROM companies LIMIT 1;
```

## RPC reference

Every RPC takes `p_tenant` (UUID) except `graph_next_key` (product-scoped numbering) and
`graph_node_epistemic_status` (pure). Write RPCs `PERFORM set_config('app.current_tenant_id', ...)`
internally; read RPCs filter on `tenant_id = p_tenant` explicitly (SECURITY DEFINER bypasses RLS for
the owner, so explicit filtering - not RLS - is the real isolation).

### Key minting (Decision 1)

| RPC | Purpose |
|---|---|
| `graph_next_key(product, node_type)` | Mint the next opaque sequential key: `FEAT-0001`, `CON-0001`, `QST-0001`, `DEC-0001`. **The BA runtime never generates keys itself.** v1 uses `MAX(suffix)+1` (sole-writer assumption); the body can be swapped for a sequence table without changing the signature. Human-readable name lives in `title`. |

### Write

| RPC | Purpose | Key behavior |
|---|---|---|
| `graph_upsert_node(tenant, product, ...)` | Create/update a node | Upsert on `(product_key, node_key)`. Sets tenant context internally. Blocked by the immutability trigger on accepted nodes. |
| `graph_add_edge(tenant, product, edge_type, src_key, dst_key, ...)` | Add a typed edge | Endpoints resolved by `(product, node_key, tenant)`; idempotent on `(edge_type, src, dst)`; raises if an endpoint is missing. |
| `graph_ratify_node(tenant, product, node_key, new_status, ratified_by)` | Flip lifecycle state | Stamps `ratified_by`/`ratified_at` on accept/handed_off. Human action only. |

### Read

| RPC | Purpose |
|---|---|
| `graph_resolve_concept(tenant, product, noun)` | Find an existing Concept by canonical name or alias (anti-duplicate). Returns `node_key, title, status, kind, maps_to_codebase`. |
| `graph_feature_subgraph(tenant, product, feature_key)` | The feature + every one-hop linked node (questions, concepts, decisions) with derived epistemic status. Source for brief rendering. |
| `graph_feature_readiness(tenant, product, feature_key)` | The derived scope-readiness gate breakdown + `scope_ready` verdict. |
| `graph_node_epistemic_status(node_type, status)` | Pure function: `fact \| claim \| open \| process \| none`. No tenant param. |

### Cross-agent read (registry)

| RPC | Purpose |
|---|---|
| `cbc_resolve(noun)` | Read code-side identities from `platform.cbc_identity_registry` (skip `merged`/`deprecated`). **Read only** - the BA Agent never calls `cbc_register_or_get`, `cbc_rename`, `cbc_implement`, `cbc_merge`. |

## Typical call sequence (one pass)

```
tenant := resolve company by name or explicit id   # never LIMIT 1
fk := graph_next_key(product, 'feature')
graph_upsert_node(tenant, product, 'feature', fk, ...)        -> FEAT-0001
for each noun:
    graph_resolve_concept(tenant, product, noun)
      OR  ck := graph_next_key(product, 'concept'); upsert new CON-  (maps_to_codebase from concept_resolution[])
    graph_add_edge(tenant, product, 'references', fk, ck, {nature})
for each blocking high-divergence assumption:
    qk := graph_next_key(product, 'question')
    graph_upsert_node(tenant, product, 'question', qk, ...)   -> QST-0001
    graph_add_edge(tenant, product, 'derived_from', qk, fk)
graph_feature_readiness(tenant, product, fk)                  -> withhold or render
```

## Ratification pass (Pass B)

```
dk := graph_next_key(product, 'decision')
graph_upsert_node(tenant, product, 'decision', dk, status='proposed', ...)  -> DEC-0001 (+ implies_* stubs)
graph_add_edge(tenant, product, 'references', dk, ck)        (citation - required)
graph_add_edge(tenant, product, 'resolves',   dk, qk)
# human accepts:
graph_ratify_node(tenant, product, dk, 'accepted', '<operator>')
graph_ratify_node(tenant, product, qk, 'answered', '<operator>')   # if status-tracked
graph_feature_readiness(tenant, product, fk)                -> render brief when scope_ready
```

## Integrity guarantees (enforced in the DB, not the agent)

- **Immutability:** accepted/terminal nodes are content-frozen by trigger; only `accepted ->
  superseded/deprecated` status moves are allowed. Everything else must supersede.
- **Type hygiene:** `kind` only on Concepts; `blocking`/`divergence` only on Questions;
  `maps_to_codebase`/`aliases` only on Concepts; `node_key` prefix must match `node_type`.
- **Lifecycle:** per-type status CHECK constraints.
- **Edges:** append-only; FK-restricted endpoints; no self-loops; unique per `(type, src, dst)`.
- **Citation:** enforce in the agent - every `DEC-*` must have at least one `references` edge to a
  Concept before it is presented for ratification.
