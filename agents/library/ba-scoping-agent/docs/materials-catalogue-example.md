# Worked Example - Materials Catalogue

The first real feature, traced through the v1 graph. Assumes a `codebase-context.json` for
`reformai-product` (suppliers, service providers/contractors, geographic markets with currency/locale).

> Feature idea: **"Add a catalogue of materials for suppliers and service providers."**

## Step 1-2 - Intake + context

```
FEAT-catalogue-materials   status: scoping
  node_attributes.scoped_against_commit: <sha from codebase-context.json>
```

`codebase-context.json` confirms `suppliers`, `service_providers`/`contractors`, `markets` tables
exist; **no** `materials` or `catalogue` table; `markets` carries `currency` + `locale`
(`domain_signals[]`).

## Step 6-7 - Concept resolution + cbc mapping

```
RESOLVED (existing CON-*, accepted):
  CON-supplier           maps_to_codebase: ["cbc:entity:vendor"]        (alias: vendor)
  CON-service-provider   maps_to_codebase: ["cbc:actor:contractor"]     (alias: contractor)
  CON-market             maps_to_codebase: ["cbc:entity:market"]

PROPOSED (new CON-*, status: proposed):
  CON-material           kind: entity   maps_to_codebase: ["cbc:entity:material"]  (concept_resolution exists:false)
  CON-material-category  kind: entity   maps_to_codebase: []
  CON-catalogue          kind: ???      maps_to_codebase: []   <- entity vs view ambiguity flagged
```

`maps_to_codebase[]` is populated from `concept_resolution[]`, not inferred. `CON-catalogue` has an
unresolved `kind` - the agent does not guess whether a Catalogue is a first-class entity or a view
over Materials.

## Step 8 - Questions (blocking + high-divergence only)

The market-scoping signal (from `domain_signals[]`, never asked for) forces QST-02.

```
QST-01  "Who authors material listings: suppliers (UGC) or ReformAI-curated master?"   blocking, high
QST-02  "Is the catalogue market-scoped (per-market pricing in market currency)?"       blocking, high
QST-03  "Is pricing in scope, and transactional (checkout) or indicative (info only)?"  blocking, high
QST-04  "Who owns the category taxonomy: ReformAI-defined or supplier free-text?"       blocking, high
```

Each gets `derived_from FEAT-catalogue-materials`. Lower-divergence assumptions (bulk upload, units,
auth-gating) become `feature.node_attributes.notes[]`, not Questions.

## Step 11-12 (Pass A) - readiness withholds the brief

```
graph_feature_readiness -> { scope_ready: false,
  gate_open_blocking_questions: 4, gate_open_high_divergence: 4,
  gate_unresolved_concepts: 0, gate_contradiction_check: "deferred_v1" }
```

Not ready. The agent emits the four Questions and **does not render a brief**. This refusal is the
product.

## Step 9-10 (Pass B) - human answers -> Decisions

The human answers; note one sentence produces multiple Decisions (decomposed).

```
A1: "Suppliers manage their own listings; categories are ReformAI-defined."
  DEC-01  "Material listings are supplier-authored/owned (UGC). Curated-master rejected."  accepted
    references CON-supplier, CON-material | resolves QST-01
    implies_rules: ["exactly one owning supplier per listing"]
  DEC-02  "ReformAI owns the category taxonomy; suppliers map onto it. Free-text rejected." accepted
    references CON-material, CON-material-category | resolves QST-04
    implies_rules: ["a listing belongs to exactly one ReformAI category"]

A2: "Market-scoped; one listing per market, priced in market currency."
  DEC-03  accepted | references CON-material, CON-market | resolves QST-02
    implies_rules: ["a listing is scoped to one market", "price denominated in market currency"]
    implies_attributes: [{concept: "CON-material", fields: ["price", "currency"]}]

A3: "Pricing in scope, indicative only. No checkout."
  DEC-04  accepted | references CON-material | resolves QST-03
    implies_rules: ["a listing has indicative price + unit of measure"]
    implies_attributes: [{concept: "CON-material", fields: ["price","currency","unit_of_measure","sku","name","description","image"]}]
```

Confirmations (no Question needed): `CON-catalogue` resolved -> **rejected as an entity** (it is a
view over Materials filtered by market); service-provider read-only access captured in DEC-01 scope.

```
CON-material           accepted
CON-material-category  accepted
CON-catalogue          rejected   (catalogue is a projection, not a node)
```

## Step 11-12 (Pass B) - readiness passes, brief renders

```
graph_feature_readiness -> { scope_ready: true, gate_open_blocking_questions: 0,
  gate_open_high_divergence: 0, gate_unresolved_concepts: 0, gate_contradiction_check: "deferred_v1" }
FEAT-catalogue-materials: scoping -> ready
```

Now the Feature Scope Brief renders from `graph_feature_subgraph`. Every section traces to nodes:
problem (`FEAT` + concepts), decisions (`DEC-01..04`), rejected alternatives (curated master,
free-text tags), open assumptions (bulk upload note).

## What this example demonstrates

- **Market-scoping caught at intake** from a signal nobody asked for (the clearest win over a
  traditional BA workflow).
- **Concept reuse with zero duplication** - supplier/contractor already settled, resolved by alias.
- **The graph declined to mint a junk entity** (`CON-catalogue`).
- **Attribute leakage prevented** - field sets captured in `implies_attributes[]`, not brief prose.
- **The agent refused to produce a brief** until the four forks were decided.

## Known v1 limitations exposed here

- `implies_attributes[]` is a stub - Material's true field set has no first-class home until Attribute
  lands (Phase 2). This is the first feature that proves Attribute is the next primitive.
- Gate 4 (contradiction check) is `deferred_v1` - DEC-01..04 are not yet auto-checked against prior
  accepted decisions.
