# BA Handoff - Codebase Context Agent

The Codebase Context Agent (CCA) and the BA Scoping Agent are a paired system. This document is the
CCA-side mirror of the BA's `docs/codebase-context-handoff.md`. It defines the boundary and the join
from the producing side.

## Direction of truth

| | Codebase Context Agent | BA Scoping Agent |
|---|---|---|
| Produces | IS-state (codebase reality) | SHOULD-BE (scoping decisions) |
| Trust | advisory input, regenerable | ratified record |
| Reads source code | yes (the only agent that does) | **never** |
| Owns identities | `cbc:*` | `CON-*`, `FEAT-*`, `QST-*`, `DEC-*` |
| Writes | `platform.cbc_identity_registry`, `cbc_registry_events` | `product_graph.*` |

## The join

```
CON-* Concept  (product_graph.graph_nodes, owned by BA)
      |
      | maps_to_codebase TEXT[]        (owned by BA, populated from concept_resolution[])
      v
cbc:* identity (platform.cbc_identity_registry, owned by CCA)
```

- One-directional and **application-level**. **No DB foreign key** between `product_graph` and
  `platform.cbc_identity_registry` - by design, so a code rename (registry only) and a concept
  re-mapping (node only) version independently.
- `maps_to_codebase[]` is **plural**: one Concept may bind to multiple cbc:* identities (e.g. an actor
  backed by both an auth role `cbc:actor:contractor` and a table `cbc:entity:contractors`). The CCA
  may therefore return multiple `cbc_ids` per requested noun.

## Handoff mechanism (the resolver — part of the process)

The handoff is not a manual step. The CCA writes the artifact to `agent_outputs`
(`output_type='codebase_context'`), and the BA fetches the current one by reference through a
SECURITY DEFINER RPC (migration 028) — the same pattern as `cbc_resolve`:

- `public.get_latest_codebase_context(p_target_key)` -> the latest COMPLETE artifact (full `content`
  jsonb + `artifact_id`, `run_id`, `commit_sha`, `generated_at`).
- `public.get_latest_codebase_context_meta(p_target_key)` -> a cheap header (commit_sha, counts) for
  staleness checks before pulling the full payload.

"Complete" is enforced as a non-empty `concept_resolution`, so a truncated/partial run (e.g. one that
hit `max_tokens` before emitting `concept_resolution`) is deterministically skipped without mutating
the immutable `agent_outputs` ledger. The BA therefore never hand-queries `agent_outputs` and never
risks consuming a partial artifact.

```sql
-- BA load-context step:
select * from public.get_latest_codebase_context('reformai-product');
```

## Ownership rules

- CCA owns `cbc:*` and is the sole minter/mutator of the registry. It **never emits `CON-*`** or any
  product Concept/Decision/Question/Rule/recommendation.
- BA owns `CON-*` and holds the `CON-* -> [cbc:*]` mapping. It **never mints, renames, merges, or
  mutates `cbc:*`** - it reads them via `public.cbc_resolve` and from `concept_resolution[]`.
- The CCA registry never references `CON-*`. The BA node never stores a cbc row, only the id string.

## How the CCA closes the loop

The CCA emits `concept_resolution[]` so the BA populates `maps_to_codebase[]` deterministically rather
than inferring it:

```json
"concept_resolution": [
  {"requested_noun": "Material",        "cbc_ids": ["cbc:entity:material"],  "exists": false},
  {"requested_noun": "ServiceProvider", "cbc_ids": ["cbc:actor:contractor"], "exists": true},
  {"requested_noun": "Catalogue",       "cbc_ids": [],                       "exists": false}
]
```

For each resolved noun the BA sets the matching Concept's `maps_to_codebase[]` to `cbc_ids`. An empty
array means genuinely new - the Concept exists only in the product graph for now.

## Stability guarantees the BA depends on (migration 025)

- **Frozen on mint:** a `cbc_id` is name-derived only at first mint, then opaque and immutable for life.
- **Frozen on consumption:** once the BA stores a `cbc_id` in `maps_to_codebase[]` (including for an
  `exists:false` entity), it is authoritative; later implementation binds the real table onto the
  pre-assigned ID via `cbc_implement`.
- **Divergent-name realization is a candidate, not an auto-bind:** a non-matching realization emits a
  `possible_realization` event for BA/human confirmation.
- **Merge collapses toward the earlier (BA-consumed) id:** `cbc_merge` enforces
  `survivor.created_at <= throwaway.created_at`, so a BA-consumed id always survives and
  `maps_to_codebase[]` never dangles.

## What the CCA will NOT decide for the BA

- Whether Supplier and ServiceProvider are "the same" product Concept. The CCA reports the `vendor`
  unification as a `domain_signal` and returns multiple `cbc_ids`; the **BA/human** decides whether
  that is one Concept or two.
- Whether a Catalogue is an entity or a view. The CCA reports what exists in code (often: nothing yet);
  the BA decides the product shape.
- Any product intent. Code shows what IS, never what SHOULD BE.

## Names: code vs product

`cbc:*` names follow **code** identifiers (`cbc:actor:contractor` if the code says `contractor`).
`CON-*` titles follow **product** language (`CON-service-provider`). The CCA `glossary` (`aka`) and the
BA `aliases[]` bridge the two. Neither side assumes the cbc name equals the product noun.

## Staleness

The artifact is stamped with `commit_sha`. The BA records `scoped_against.commit_sha` in the feature
node and warns when a brief was scoped against a commit older than the latest available
`codebase-context.json`. Re-analyze against a fresh tree when this happens.
