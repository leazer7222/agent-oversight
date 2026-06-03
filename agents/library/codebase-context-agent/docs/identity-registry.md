# Identity Registry - Codebase Context Agent

The CCA owns `cbc:*` code-side identities through a **frozen-ID registry**. This is the durable,
cross-run state that makes the `CON-* -> [cbc:*]` join stable for the BA Agent. Storage:
`supabase/migrations/025_cbc_identity_registry.sql` (**authored, NOT yet applied**).

## Why a registry and not just a naming convention

A name-derived ID is a natural key - by construction it is **not stable under rename**. When `vendor`
becomes `supplier` in code, a name-derived ID either lies (stays `vendor`) or dangles every BA
`maps_to_codebase[]` reference (becomes `supplier`). A naming convention alone cannot deliver stable
identity; only a registry can. So the convention is used **for minting only**, and the registry owns
identity for life.

## Tables (migration 025)

| Table | Mutability | Purpose |
|---|---|---|
| `platform.cbc_identity_registry` | hybrid (block DELETE; allow INSERT/UPDATE) | current identity state; `cbc_id`/`first_seen_sha` frozen, `current_name`/`aka`/`status`/`source` mutate |
| `platform.cbc_registry_events` | append-only | audit log of identity transitions |

Both are **platform-level and tenant-neutral** - a `cbc:*` identity is the same fact for every company
or product. This is the deliberate counterpart to `product_graph.graph_nodes` (migration 024), which
is tenant-scoped because Concepts/Decisions/Questions/Features are decisions. There is **no DB FK**
between the two; the join is application-level (`graph_nodes.maps_to_codebase[]`), so code renames and
concept re-mappings version independently.

A `BEFORE UPDATE` trigger (`platform.enforce_cbc_frozen_fields`) rejects any change to `cbc_id` or
`first_seen_sha`. The registry is **not** append-only, so it does NOT use `apply_append_only_rls()`
(that is only for `cbc_registry_events`). See LESSONS_LEARNED "apply_append_only_rls is NOT for
mixed-mutability tables".

## Identity rules (sealed BA/CCA contract)

1. **Minting / normalization.** `cbc:{entity|actor|capability}:{normalized_name}`, where
   normalization is `lowercase -> snake_case -> singularize -> strip non-alphanumerics`, in that
   order. The CCA is the **sole minter**, so cross-thread normalization divergence cannot occur. The
   singularizer uses a fixed irregular-word table for reproducibility.
2. **Frozen at first mint.** The name derives the ID only at first mint; thereafter the ID is opaque
   and frozen for life.
3. **Names follow CODE identifiers.** If code says `contractor`, the ID is `cbc:actor:contractor`; the
   glossary maps `contractor <-> service_provider`. Exception by necessity: an absent entity has no
   code name, so its ID is provisionally minted from the normalized requested noun.
4. **Frozen on consumption, incl. `exists:false`.** Once the BA stores a `cbc_id` into
   `maps_to_codebase[]`, it is authoritative. Later implementation binds the real table onto the
   pre-assigned ID (`cbc_implement`: `provisional -> active`); it never mints a parallel ID.
5. **Renames.** Update `current_name` + append old to `aka[]` + emit a `rename` event. The ID never
   changes (`cbc:entity:vendor` stays even after code renames to `supplier`:
   `current_name:"supplier", aka:["vendor"]`).
6. **Collisions.** A mint candidate colliding with a different frozen identity gets a numeric
   disambiguator: `cbc:entity:vendor_2`.
7. **Divergent-name realization -> candidate, not auto-bind.** When an absent `cbc:entity:material`
   later ships as `product_materials`: exact-or-alias match -> `cbc_implement`; no confident match ->
   mint a new active ID AND emit `cbc_propose_realization` (a `possible_realization` event referencing
   the still-absent ID) for BA/human merge confirmation. Never silently auto-bind across a divergence.
8. **Merge collapses toward the EARLIER (BA-consumed) ID.** `cbc_merge` enforces
   `survivor.created_at <= throwaway.created_at`. The survivor absorbs the throwaway's name + aka; the
   throwaway becomes `status='merged'` pointing at the survivor. A BA-consumed ID always survives, so
   `maps_to_codebase[]` never dangles.

## RPCs (public schema, SECURITY DEFINER)

PostgREST does not expose the `platform` schema, so all access is through `public.cbc_*`:

| RPC | Purpose |
|---|---|
| `public.cbc_register_or_get(cbc_id, type, name, sha, created_by, source, status)` | Mint a new identity or return the existing one (idempotent). Used for `provisional` and `active`. |
| `public.cbc_rename(cbc_id, new_name, sha, created_by)` | Frozen ID; append old name to `aka[]`; log `rename`. |
| `public.cbc_implement(cbc_id, source, sha, created_by)` | Confident-match realization: `provisional -> active`. |
| `public.cbc_propose_realization(new_cbc_id, candidate_for, sha, created_by)` | Record a divergent-name realization candidate (no auto-bind). |
| `public.cbc_merge(survivor_id, throwaway_id, created_by)` | Collapse toward the earlier ID; throwaway -> `merged`. |
| `public.cbc_resolve(noun)` | Resolve a code-side noun to live identities (matches `current_name` or `aka`). |

Never access the registry via `supabase.schema('platform').from(...)` - it silently returns null. Mint
and mutate only through these functions.

## Status lifecycle

```
provisional  (absent noun-mint; frozen on BA consumption)
   |  cbc_implement (confident realization)
   v
 active       (realized in code)
   |  cbc_merge (collapsed into an earlier id)
   v
 merged  -> merged_into = survivor

deprecated   (retired; reserved, not used in v1)
```

## What the BA relies on

The BA never mints or mutates `cbc:*`. It reads identities via `public.cbc_resolve` and from the
artifact's `concept_resolution[]`, and stores them in `concept.maps_to_codebase[]` (plural). Every
guarantee above exists so that a `maps_to_codebase[]` reference is permanently stable to join against.
