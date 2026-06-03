# Codebase Context Agent -> BA Agent Interface (v1, FROZEN)

This is the binding commitment of the Codebase Context Agent: exactly what it
consumes, what it emits, and the rules that make the cbc <-> CON join stable.
It is the reciprocal of the BA Agent plan sections 2 and 11. Schema of record:
`docs/schemas/codebase-context.schema.json`. Canonical artifact body lives in
oversight `agent_outputs` (`output_type = 'codebase_context'`); `codebase-context.md`
is a human-only render. The BA reads the JSON, never the `.md`.

## Separation of authority

- Codebase Context Agent = describes WHAT IS. Owns `cbc:*` identities. Reads no product graph.
- BA Agent = scopes WHAT SHOULD BE. Owns `CON-*` Concepts. Holds the `CON-* -> [cbc:*]` join via `maps_to_codebase` (now `string[]`).
- This agent never names a product Concept. It emits code-side identities, glossary, signals, and existence resolutions; the BA does all Concept resolution.

## Inputs (this agent consumes)

| Field | Required | Notes |
|---|---|---|
| `target_key` | yes | Resolves to a repo URL + auth via the target registry. |
| `ref` | yes | Branch/tag/sha; resolved to a concrete `commit_sha` at run start and pinned. |
| `feature_intent` | yes | Drives existence-check coverage + the human brief. Does NOT narrow the entity/signal sweep. |
| `concepts_to_check[]` | no | Directed existence-check list. Plain nouns or `{noun, expected_kind}`. ADDITIVE ONLY (see invariant below). |

This agent does NOT consume the product graph. The glossary is produced from code, not consumed.

## Outputs (this agent emits) — see schema for full shape

- `entities[]` — comprehensive code-side inventory with `cbc:` ids, `exists`, `source`, `fields[]` (with `semantic_hint`), `relationships[]`. Includes `exists:false` negative findings.
- `actors[]`, `capabilities[]` — `cbc:actor:*`, `cbc:cap:*`.
- `domain_signals[]` — non-obvious cross-cutting facts + implication hints. Highest-value output.
- `glossary[]` — code terms with `aka[]`, mapping to `cbc:*`.
- `concept_resolution[]` — one entry per requested noun: `{requested_noun, cbc_ids[], exists}`. `cbc_ids` plural; empty = genuinely new.
- `registry_events[]` — identity transitions (mint / rename / implemented / collision / possible_realization).
- `coverage` — `scanned_paths`, `omitted`, `confidence`, `files_scanned/total`. Honest denominator.
- `repo`, `commit_sha`, `ref_requested`, `feature_intent`, `inputs` echo, `run_id`.

## Hard invariants

1. **`concepts_to_check` is additive, never narrowing.** It directs existence-checking only. The full unrequested `domain_signals` sweep and honest `coverage` always run. (The single most valuable simulation result -- market-scoping -- came from an unrequested signal.) A future optimization MUST NOT prune this.
2. **Comprehensive inventory; intent focuses, never filters.** `feature_intent` guarantees feature nouns get existence-checked and focuses the `.md` brief. The `entities`/`signals`/`glossary` sweep is app-wide so the BA graph seeds fully.
3. **Evidence or it is omitted.** Every entity/signal/actor claim cites `path` (+ optional `lines`) at `commit_sha`, or it is not emitted.
4. **Negative findings are explicit.** "Material does not exist" is an `entities[]` row with `exists:false` + a `concept_resolution` entry, never silence.

## cbc identity rules (FROZEN, BA-approved with amendments)

Format `cbc:{type}:{normalized_name}` is for MINTING ONLY. Identity is owned by a
persistent registry, not by the name.

- **Registry of record.** `cbc_identity_registry` persists `{cbc_id, current_name, aka[], first_seen_sha, status}`. The Codebase Context Agent is the sole writer. This makes the agent STATEFUL across runs (relevant to storage design).
- **Freeze at first mint.** The name derives the id only at first mint; thereafter the id is opaque and frozen for life.
- **Names follow CODE identifiers.** If code says `contractor`, the id is `cbc:actor:contractor`; the glossary maps `contractor <-> service_provider`; the BA's `CON-service-provider` maps onto it. Exception by necessity: an ABSENT entity has no code name, so its id is provisionally minted from the normalized requested noun and frozen on consumption.
- **Freeze on consumption, incl. `exists:false`.** Once the BA stores a cbc id into `maps_to_codebase`, it is authoritative. Later implementation binds the real table onto the pre-assigned id and emits an `implemented` event; it never mints a parallel id.
- **Normalization (deterministic, sole-minter):** `lowercase -> snake_case -> singularize -> strip non-alphanumerics`. Singularizer uses a fixed irregular-word table for reproducibility. Only this agent mints, so cross-thread divergence cannot occur.
- **Collision rule.** A mint candidate colliding with a different frozen identity gets a numeric disambiguator: `cbc:entity:vendor_2`.
- **Renames** update `current_name` + append old name to `aka[]` and emit a `rename` event. The id never changes (e.g. `cbc:entity:vendor` stays even after code renames to `supplier`: `current_name:"supplier", aka:["vendor"]`).

### Two micro-refinements pending BA ack (baked into the schema)

- **Divergent-name realization -> propose, do not silently auto-bind.** When an absent `cbc:entity:material` later ships as table `product_materials`: exact-or-alias match -> auto-bind + `implemented` event; no confident match -> mint a new id AND emit a `possible_realization` event referencing the still-absent id for BA/human merge confirmation. Prevents both silent Amendment-2 violations and wrong auto-binds.
- **Registry is durable cross-run state**, owned by this agent, to be designed alongside `graph_nodes`/`graph_edges` in the storage pass.

## First test case (materials catalogue) — expected resolution shape

`concept_resolution[]` answers the BA's existence questions directly, e.g.:

```json
[
  {"requested_noun": "Material",        "cbc_ids": [],                       "exists": false},
  {"requested_noun": "Catalogue",       "cbc_ids": [],                       "exists": false},
  {"requested_noun": "Supplier",        "cbc_ids": ["cbc:actor:supplier", "cbc:entity:vendor"], "exists": true},
  {"requested_noun": "ServiceProvider", "cbc_ids": ["cbc:actor:contractor"], "exists": true}
]
```

The Supplier/ServiceProvider/vendor unification surfaces as multiple `cbc_ids`
plus a `domain_signal` describing the `vendor_type` discriminator. This agent does
NOT decide whether they are "the same" -- that is a BA/human modeling decision.

## Version

v1 FROZEN pending BA ack of the two micro-refinements above. Both agents may build
to this contract without blocking each other.
