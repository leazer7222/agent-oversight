# Output Contract - Codebase Context Agent

The agent produces one artifact conforming to `docs/schemas/codebase-context.schema.json`
(`artifact_type: "codebase_context"`), plus any `cbc_identity_registry` mutations, plus a human-only
`codebase-context.md` render.

## Artifact storage

Written to `agent_outputs.content` with `output_type = 'codebase_context'`. The canonical body is the
JSON; `codebase-context.md` is a human-readable mirror. **The BA never reads the `.md`** - it consumes
the validated JSON. Treat the written artifact as an immutable ledger entry: a re-analysis at a new
SHA is a new row, never an edit (same append-only principle as `code_review` artifacts).

## What the agent produces

| Output | Form | Notes |
|---|---|---|
| Entities | `entities[]` | `cbc:entity:*`, `exists`, `source`, `fields[]` (+`semantic_hint`), `relationships[]`, evidence |
| Actors | `actors[]` | `cbc:actor:*`, `auth_role`, evidence |
| Capabilities | `capabilities[]` | `cbc:cap:*`, member `entities[]`, evidence |
| Domain signals | `domain_signals[]` | Cross-cutting facts + `implication_hint`; always swept in full |
| Glossary | `glossary[]` | `term`, `aka[]`, `maps_to` cbc:* |
| Concept resolution | `concept_resolution[]` | One per requested noun: `{requested_noun, cbc_ids[], exists}` |
| Registry events | `registry_events[]` | `minted` / `rename` / `implemented` / `collision` / `possible_realization` |
| Coverage | `coverage` | `scanned_paths`, `omitted`, `files_scanned/total`, `confidence` |
| Provenance | top-level | `repo`, `commit_sha`, `ref_requested`, `feature_intent`, `inputs` echo, `run_id` |

## What it must NOT produce (v1)

- No `CON-*`, Decisions, Questions, Rules, Attributes, PRDs, user stories, acceptance criteria, or
  product recommendations.
- No decision about whether two code-side identities are "the same" product Concept. The
  Supplier/ServiceProvider/`vendor` unification is reported as a `domain_signal` + multiple `cbc_ids`
  in `concept_resolution[]`; the BA/human decides.
- No `Attribute` nodes. `fields[]` carries `semantic_hint` (code reality only); the BA owns Attributes.

## concept_resolution[] (the loop-closer)

Every requested noun comes back resolved or explicitly unresolved - the BA never infers:

```json
"concept_resolution": [
  {"requested_noun": "Material",        "cbc_ids": ["cbc:entity:material"],  "exists": false},
  {"requested_noun": "ServiceProvider", "cbc_ids": ["cbc:actor:contractor"], "exists": true},
  {"requested_noun": "Catalogue",       "cbc_ids": [],                       "exists": false}
]
```

`cbc_ids` is **plural** - one noun may resolve to multiple code-side identities (an actor backed by
both a role and a table). An empty array means genuinely new (no code-side identity).

## Evidence or it is omitted

Every entity/actor/capability/signal claim cites at least one `evidence` (`path` + optional `lines`)
at `commit_sha`, or it is not emitted. Unciteable claims are opinions and are dropped (mirrors the
code-review-agent rule).

## Negative findings and coverage are data-integrity controls

- "Material does not exist" is an `entities[]` row with `exists:false` plus a `concept_resolution[]`
  entry - never the absence of a row.
- `coverage` always shows the denominator (`files_scanned / files_total`) and `omitted[]`. A low
  scan ratio (e.g. a truncated clone) surfaces as low confidence instead of a confident-but-empty
  artifact.

## Registry side effects

Artifact emission and registry mutation are coupled: each `cbc:*` returned in the artifact is backed
by a `platform.cbc_identity_registry` row (minted or pre-existing), and each transition is logged to
`platform.cbc_registry_events` and echoed in `registry_events[]`. See
[identity-registry.md](identity-registry.md).

## Telemetry on completion

`run.report(tokens_in, tokens_out, cost_usd)` before the context manager exits, so `run_completed`
carries cost data. Always report, even if zero.
