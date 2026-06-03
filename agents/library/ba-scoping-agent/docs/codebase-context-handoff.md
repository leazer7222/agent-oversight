# Codebase Context Handoff - BA Scoping Agent

The BA Scoping Agent and the Codebase Context Agent (CCA) are a paired system. This document defines
the boundary and the join.

## Direction of truth

| | BA Scoping Agent | Codebase Context Agent |
|---|---|---|
| Produces | SHOULD-BE (scoping decisions) | IS-state (codebase reality) |
| Trust | ratified record | advisory input, regenerable |
| Reads source code | **never** | yes (the only agent that does) |
| Owns identities | `CON-*`, `FEAT-*`, `QST-*`, `DEC-*` | `cbc:*` |
| Writes | `product_graph.*` | `platform.cbc_identity_registry`, `cbc_registry_events` |

## The join

```
CON-* Concept  (product_graph.graph_nodes, owned by BA)
      |
      | maps_to_codebase TEXT[]        (owned by BA, populated from concept_resolution[])
      v
cbc:* identity (platform.cbc_identity_registry, owned by CCA)
```

- The join is **one-directional and application-level.** There is **no DB foreign key** between
  `product_graph` and `platform.cbc_identity_registry` - by design, so a code rename (registry only)
  and a concept re-mapping (node only) version independently.
- `maps_to_codebase[]` is **plural**: one Concept may bind to multiple cbc:* identities (e.g. an actor
  backed by both an auth role `cbc:actor:contractor` and a table `cbc:entity:contractors`).

## Ownership rules

- BA owns `CON-*`. CCA **never emits `CON-*`** or any product Concept/Decision/Rule.
- CCA owns `cbc:*`. BA **never mints, renames, merges, or mutates `cbc:*`.** BA reads them via
  `public.cbc_resolve` and from the artifact's `concept_resolution[]`.
- BA holds the `CON-* -> [cbc:*]` mapping. CCA's registry never references `CON-*`.

## How the BA populates maps_to_codebase

The CCA's `concept_resolution[]` closes the loop deterministically - the BA does not infer:

```json
"concept_resolution": [
  {"requested_noun": "Material",        "cbc_ids": ["cbc:entity:material"],  "exists": false},
  {"requested_noun": "ServiceProvider", "cbc_ids": ["cbc:actor:contractor"], "exists": true},
  {"requested_noun": "Catalogue",       "cbc_ids": [],                       "exists": false}
]
```

For each resolved noun, set the matching Concept's `maps_to_codebase[]` to `cbc_ids`. An empty array
means genuinely new - the Concept exists only in the product graph for now.

## cbc identity stability (CCA-side, relied on by BA)

The BA depends on these CCA guarantees (migration 025):

- **Frozen on mint:** a `cbc_id` is name-derived only at first mint, then opaque and immutable for
  life. Renames update `current_name`/`aka[]` and emit a `rename` event; the ID never changes.
- **Frozen on consumption:** once the BA stores a `cbc_id` in `maps_to_codebase[]` (including for an
  `exists:false` entity), it is authoritative. Later implementation binds the real table onto the
  pre-assigned ID.
- **Divergent-name realization is a candidate, not an auto-bind:** if an absent id later ships under a
  non-matching code name, the CCA emits a `possible_realization` event for BA/human confirmation.
- **Merge collapses toward the earlier (BA-consumed) id:** `cbc_merge` enforces
  `survivor.created_at <= throwaway.created_at`, so a BA-consumed id always survives and the BA's
  `maps_to_codebase[]` reference never dangles.

## Staleness

The BA records `scoped_against.commit_sha` in the feature node. If a brief was scoped against a commit
older than the latest available `codebase-context.json`, warn - the SHOULD-BE may contradict current
IS-state. Re-scope against a fresh artifact when this happens.

## Names: code vs product

`cbc:*` names follow **code** identifiers (`cbc:actor:contractor` if the code says `contractor`).
`CON-*` titles follow **product** language (`CON-service-provider`). The CCA `glossary` (`aka`) and the
BA `aliases[]` bridge the two. The BA must not assume the cbc name equals the product noun.
