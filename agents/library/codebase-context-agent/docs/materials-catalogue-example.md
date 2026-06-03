# Worked Example - Materials Catalogue (CCA side)

The first real feature, traced through the Codebase Context Agent. This is the producing side of the
BA's `docs/materials-catalogue-example.md` - it shows the `codebase-context.json` the CCA emits, which
the BA then consumes. Assumes the `reformai-product` repo contains suppliers, service
providers/contractors, and geographic markets with currency/locale.

> Feature intent: **"Add a catalogue of materials for suppliers and service providers."**
> `concepts_to_check`: `["Material", "Catalogue", "Supplier", "ServiceProvider", "Market"]`

## Step 2-4 - Resolve + clone + pin

```
target_key: reformai-product  ->  repo_url + read-only token (target registry)
ref: main  ->  commit_sha: <sha>   (git ls-remote)
clone .workspace/reformai-product@<sha>/   ;   assert HEAD == <sha>   [OK]
```

## Step 6-9 - Extract code reality

```
entities[]
  cbc:entity:vendor    exists:true   source: table:public.vendors
     fields: [{vendor_type, enum}, {name, text}, {region_id, foreign_key}]
     relationships: [{to: cbc:entity:market, many-to-one, via: region_id}]
     evidence: supabase/migrations/004_vendors.sql:12-40
  cbc:entity:market    exists:true   source: table:public.markets
     fields: [{currency, text}, {locale, text}]
     evidence: supabase/migrations/006_markets.sql:8-22
  cbc:entity:material  exists:false  source: none      <- negative finding
  cbc:entity:catalogue exists:false  source: none      <- negative finding

actors[]
  cbc:actor:supplier    exists:true  auth_role: supplier
  cbc:actor:contractor  exists:true  auth_role: contractor

domain_signals[]
  "markets carry currency and locale columns"
     entities: [cbc:entity:market]   implication_hint: "data may be market-scoped"   confidence: high
     evidence: supabase/migrations/006_markets.sql:8-22
  "vendor table unifies supplier + service provider via a vendor_type discriminator"
     entities: [cbc:entity:vendor]   implication_hint: "Supplier and ServiceProvider may be one model in code"
     confidence: high

glossary[]
  {term: "vendor",     aka: ["supplier"],          maps_to: cbc:entity:vendor}
  {term: "contractor", aka: ["service provider"],  maps_to: cbc:actor:contractor}
```

The CCA does **not** decide whether Supplier and ServiceProvider are the same Concept. It reports the
`vendor_type` unification as a `domain_signal` and lets the BA/human decide. That single unrequested
signal (market-scoping) is the highest-value output - it is swept regardless of `concepts_to_check`.

## Step 10 - concept_resolution (the loop-closer)

```json
"concept_resolution": [
  {"requested_noun": "Material",        "cbc_ids": [],                                             "exists": false},
  {"requested_noun": "Catalogue",       "cbc_ids": [],                                             "exists": false},
  {"requested_noun": "Supplier",        "cbc_ids": ["cbc:actor:supplier", "cbc:entity:vendor"],    "exists": true},
  {"requested_noun": "ServiceProvider", "cbc_ids": ["cbc:actor:contractor"],                       "exists": true},
  {"requested_noun": "Market",          "cbc_ids": ["cbc:entity:market"],                          "exists": true}
]
```

`cbc_ids` is plural: "Supplier" resolves to both an actor (auth role) and an entity (table). "Material"
and "Catalogue" come back `exists:false` with empty arrays - genuinely new.

## Step 11 - Registry reconciliation

```
cbc_register_or_get(cbc:entity:vendor,   ..., status=active)        -> existing
cbc_register_or_get(cbc:entity:market,   ..., status=active)        -> existing
cbc_register_or_get(cbc:actor:supplier,  ..., status=active)        -> existing
cbc_register_or_get(cbc:actor:contractor,..., status=active)        -> existing
cbc_register_or_get(cbc:entity:material, ..., status=provisional)   -> minted   (absent noun-mint)
cbc_register_or_get(cbc:entity:catalogue,..., status=provisional)   -> minted   (absent noun-mint)

registry_events[]: minted cbc:entity:material, minted cbc:entity:catalogue
```

`material` and `catalogue` are minted `provisional` from the normalized requested nouns. They become
authoritative the moment the BA stores them in `maps_to_codebase[]`. If they later ship as, say,
`product_materials`, the CCA emits `cbc_implement` on a name match, or a `possible_realization`
candidate on a divergence - never a silent parallel mint.

## Step 12-13 - Coverage + emit

```
coverage: { files_scanned: 240, files_total: 1830, confidence: high,
            scanned_paths: ["supabase/migrations/**", "src/**"],
            omitted: ["background jobs", "webhook handlers"] }
artifact -> agent_outputs (output_type='codebase_context')   ;   render codebase-context.md   ;   teardown clone
```

## What the BA does next (for reference, not CCA work)

The BA consumes this artifact and produces `CON-material`, `CON-catalogue` (proposed), maps them via
`concept_resolution[]`, and - critically - raises a blocking Question about market-scoping that came
entirely from the CCA's unrequested `domain_signal`. See the BA's
`agents/library/ba-scoping-agent/docs/materials-catalogue-example.md`.

## What this example demonstrates (CCA side)

- **Negative findings are explicit** - Material/Catalogue come back `exists:false`, not as missing rows.
- **The unrequested signal is the win** - market-scoping is swept even though it was not in
  `concepts_to_check`.
- **The CCA refuses to resolve product ambiguity** - it reports the `vendor` unification, it does not
  decide Supplier == ServiceProvider.
- **Plural `cbc_ids`** - one noun ("Supplier") legitimately maps to a role + a table.
- **Provisional minting** - absent nouns get a frozen ID now, stable for when they ship later.
