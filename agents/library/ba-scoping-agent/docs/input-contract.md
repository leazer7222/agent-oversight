# Input Contract - BA Scoping Agent

## Invocation inputs

| Field | Type | Required | Notes |
|---|---|---|---|
| `feature_intent` | string | Yes | The raw feature idea. Becomes the `FEAT-*` node title. |
| `product_key` | string | Yes | Product/repo scope, e.g. `reformai-product`. Mirrors codebase-context `target_key`. |
| `tenant` | string | Yes | Company **name or explicit UUID**. Resolved to `app.current_tenant_id`. Never `LIMIT 1`. |
| `codebase_context` | object | Yes | A validated `codebase-context.json` instance (see below). |
| `concepts_to_check` | string[] \| object[] | No | Directed existence-check list passed *to* the Codebase Context Agent. Additive only. |
| `human_answers` | object[] | No | Supplied in the ratification pass: `{question_key, answer_text, ratified_by}`. |

## Mandatory vs optional

- **Mandatory grounding:** `feature_intent`, `product_key`, `tenant`, `codebase_context`, plus the
  existing product graph (read implicitly via RPCs). These shape truth.
- **Optional signal:** `concepts_to_check` (a relevance hint, never a filter), `human_answers`
  (present only in Pass B).

## codebase-context.json

The BA Agent consumes a **validated** `codebase-context.json` and never reads source code. Validate
against `docs/schemas/codebase-context.schema.json` before use. Key consumed fields:

| Field | Used for |
|---|---|
| `commit_sha` | Recorded in `feature.node_attributes.scoped_against_commit` for staleness detection |
| `entities[]`, `actors[]` | Concept resolution (existing code-side reality) |
| `concept_resolution[]` | The authoritative `requested_noun -> cbc_ids[]` map; populates `maps_to_codebase[]` |
| `glossary[]` (`aka`) | Alias resolution - prevents duplicate Concepts |
| `domain_signals[]` | High-divergence assumption detection (market-scoping, multi-tenancy, currency/locale) |
| `coverage` | Confidence down-ranking - a Concept derived from an unscanned path is lower-confidence |

If `codebase_context` fails schema validation, abort with `validation_error`. Do not proceed on a
malformed or partial artifact.

## concepts_to_check semantics

`concepts_to_check` is **additive only**: it directs the Codebase Context Agent's existence-checking,
it never narrows the `domain_signals` sweep or `coverage`. The single most valuable signal in
practice (market-scoping) came from a signal the BA did not ask about - so the BA must consume the
full `domain_signals[]`, not just the resolutions for nouns it requested.

Entries may be plain strings (`"Material"`) or typed (`{"noun": "Supplier", "expected_kind": "actor"}`).

## Tenant context

Tenant resolution and `app.current_tenant_id` are a hard precondition for any graph write - RLS on
`product_graph.graph_nodes` denies writes without it. See
[graph-operations.md](graph-operations.md#tenant-context). Resolve by name (`.eq('name', 'ReformAI')`)
or explicit UUID; multiple companies exist and order is not guaranteed.

## No silent assumptions

Every input the agent treats as true must be either (a) present in `codebase_context` as IS-state
fact, (b) an `accepted` graph node, or (c) explicitly recorded as an Assumption-derived Question or a
low-divergence feature note. The agent never silently fills a gap - it surfaces it.
