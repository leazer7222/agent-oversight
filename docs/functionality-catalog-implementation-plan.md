# Functionality Catalog / Reuse Radar - Implementation Plan (v1)

Status: APPROVED for implementation (design locked in the Dialogue Design passes).
Owner: reformai | Part of: Agent Agile Force, Codebase Context Agent (CCA).
This plan is the Codex handoff. It specifies WHAT to build, the contracts, the order, and the
acceptance criteria. Codex writes the code/SQL; this document does not.

---

## 0. Absolute rules (must hold at every step)

- The Functionality Catalog (a.k.a. Reuse Radar) is a SECOND, LOWER-TRUST plane on top of the CCA.
- It NEVER writes `maps_to_codebase`. It NEVER becomes existence truth. It is ADVISORY only.
- Deterministic CCA parse output stays authoritative; LLM output is interpretation, not truth.
- It must answer "unknown / indeterminate" when coverage is incomplete - NEVER "no such capability".
- An empty search result is NOT an absence claim.
- Grain (behavior seeds), actors, entities, evidence, confidence, and coverage are DETERMINISTIC.
  Only title/summary/intents/verbs/nouns/artifacts/limitations are LLM-generated (interpretation).

---

## 1. Preconditions (resolve before Step 0)

Blocking:
1. **Chain-resolution mechanism** (Q3): confirm regex-bounded extraction vs a light TS AST pass for
   `route -> controller.method -> this.service.method`. Recommendation: start regex-bounded; escalate to
   a tiny AST only if resolution rate on Reform-AI is < ~85%.
2. **Audit home** (Q1): `capability_reuse_decisions` dedicated table (recommended) vs a product_graph node.
3. **Threshold ownership** (Q6): who maintains the labeled acceptance matrix as the catalog grows.

Before Step 6 (hybrid search):
4. **pgvector**: confirm the extension is enabled on project `hdhovyrlnfojtkqbcegh` (apply via `scripts/apply_sql.py`).

Before Step 4 (storage):
5. **Migration number**: inspect `supabase/migrations/` and use the next free number. DO NOT assume 039.

---

## 2. Architecture + where it lives

The catalog is a NEW STAGE of the CCA pipeline (the CCA is the only code-reading authority). It consumes
the deterministic inventory the CCA already produces and emits a separate, lower-trust artifact + a
searchable table.

```
CCA deterministic inventory (routes, capabilities, actors, entities, coverage)   [EXISTS]
        |
        v
[NEW] behavior seeds (deterministic)  ->  evidence bundles (deterministic)
        |                                       |
        v                                       v
[NEW] LLM translation (bounded, label-only)  -> validation + derived confidence
        |
        v
[NEW] functionality_catalog rows + artifact (advisory)  ->  search_functionality RPC
        |
        v
[NEW] PCA/BA consume search before net-new classification (gate)  ->  capability_reuse_decisions (audit)
        |
        v (on accept/extend)
deterministic CCA resolver re-confirm  ->  reuse becomes a relied-upon scope fact
```

Module layout (new subpackage `agents/library/codebase-context-agent/catalog/`):
- `catalog/seeds.py`      - deterministic behavior-seed builder.
- `catalog/evidence.py`   - deterministic evidence-bundle builder (route->controller->service, 1-hop).
- `catalog/translate.py`  - LLM translation stage (bounded packet -> interpretation, forced tool).
- `catalog/validate.py`   - validation, evidence_valid, derived confidence, coverage-basis.
- `catalog/envelope.py`   - coverage-envelope builder.
- `catalog/store.py`      - upsert rows + publish artifact + is_active pointer.
- `catalog/client.py`     - thin Python client over search_functionality (for tests + BA/PCA).
- Wire as a `--catalog` stage in `pipeline.py` (after inventory + coverage; reuses the commit-keyed cache).

Schemas (new, under `docs/schemas/`):
- `functionality-catalog.schema.json`      - the catalog entry.
- `functionality-search-response.schema.json` - search response + coverage envelope.
- `capability-reuse-decision.schema.json`  - the BA/PCA audit record.

---

## 3. Data contracts

### 3.1 Catalog entry (`functionality-catalog.schema.json`)
Four trust tiers, structurally separated:

- `id` (req) - `fn:<capability-slug>:<resource>:<action>` (deterministic, stable).
- `source_capability_id` (req) - the PARENT capability cbc id (route-group), e.g. `cbc:capability:marketplace`.
- `grounded` (req, deterministic):
  - `evidence[]` (req, >=1): `{ type: route|symbol, route?, route_id?, file?, symbol?, line_start?, line_end? }` - POINTERS only, no excerpts.
  - `actors[]` (default []): cbc:actor ids, deterministic-or-omitted (from route auth).
  - `entities_touched[]` (default []): cbc:entity ids, deterministic-or-omitted.
  - `coverage_basis` (req): `{ layers[], status, known_gaps[] }`.
  - `evidence_bundle_hash` (req), `evidence_valid` (req bool).
- `interpretation` (req, LLM):
  - `title` (req), `summary` (req).
  - `user_intents[]` (req, >=1) - paraphrases.
  - `action_verbs[]` (req, >=1), `object_nouns[]` (req, >=1).
  - `input_artifacts[]`, `output_artifacts[]`, `limitations[]` (optional; limitations EVIDENCED-ONLY).
  - (NO `derived_search_terms`, NO `tags`.)
- `derived` (req, computed): `confidence`, `stale_status`.
- `provenance` (req): `commit_sha`, `parser_version`, `catalog_version`, `prompt_version`.

### 3.2 Search response (`functionality-search-response.schema.json`)
- `results[]`: `{ fn_id, source_capability_id, title, summary, confidence, score, strength: strong|medium|weak, match_explanation, grounded:{ evidence, actors, entities_touched, coverage_basis } }`
- `coverage_envelope` (ALWAYS present, incl. empty results): `{ catalog:{commit_sha,parser_version,catalog_version,generated_at,is_stale}, covered_layers[], uncovered_layers[], route_layer_complete, generator_failures[], no_result_means, absence_confidence: low|moderate }`
- `provenance`: `{ commit_sha, parser_version, catalog_version }`

### 3.3 Audit record (`capability-reuse-decision.schema.json`)
- `{ feature_key, concept_ref, query, candidate_ids[] (+scores), disposition: accept|reject|extend|proceed_net_new_with_rationale, rationale, decided_by, decided_at, catalog_provenance, reconfirmed bool, reconfirm_result }`

---

## 4. Database design (described, not SQL)

### 4.1 `public.functionality_catalog`
- Identity columns: `id`, `source_capability_id`, `product_key`, `repo`, `commit_sha`, `parser_version`, `catalog_version`, `prompt_version`.
- Grounded: `evidence jsonb`, `actors text[]`, `entities_touched text[]`, `coverage_basis jsonb`, `evidence_bundle_hash text`, `evidence_valid bool`.
- Interpretation (columns for search + jsonb for the rest): `title text`, `summary text`, `user_intents text[]`, `action_verbs text[]`, `object_nouns text[]`, `input_artifacts text[]`, `output_artifacts text[]`, `limitations text[]`, `interpretation_extra jsonb`.
- Derived/lifecycle: `confidence text`, `stale_status text`, `generated_at timestamptz`, `is_active bool`.
- Search: `search_doc tsvector` (GENERATED from title+summary+user_intents+action_verbs+object_nouns+artifacts, weighted), `embedding vector` (nullable; P2).
- Keys/indexes: UNIQUE(`product_key,repo,commit_sha,parser_version,catalog_version,id`); GIN(`search_doc`); GIN(`object_nouns`); partial index on `is_active`; ivfflat(`embedding`) in P2.
- Standard CCA conventions: `created_at timestamptz not null default now()`, TIMESTAMPTZ only, no SERIAL, no PG enums, no ON DELETE CASCADE on Class-I. Lint via `scripts/check_migrations.py`.

### 4.2 `public.search_functionality` RPC
- Signature: `(p_product_key text, p_query text, p_limit int=5, p_commit_sha text=null, p_mode text='catalog')`.
- Resolves to the active catalog (or `p_commit_sha`).
- v1: ts_rank over `search_doc` + verb/noun overlap boost.
- v2: RRF(full-text, vector) + object-noun boost/penalty (see Section 6).
- Returns the §3.2 response object. MUST include `coverage_envelope` + `provenance` even when `results=[]`.
- SECURITY DEFINER, public schema (PostgREST cannot reach private schemas).

### 4.3 `public.capability_reuse_decisions` (audit) - pending Q1
- Feature-scoped rows per §3.3. Append-only-ish; supports updating `reconfirmed`/`reconfirm_result`.
- Lives outside the cbc/graph trust tiers (advisory audit).

### 4.4 Latest-active pointer
- `is_active bool` + a partial unique index (one active catalog per `product_key,repo`). "Latest" = `is_active`.

---

## 5. Generation pipeline spec

### 5.1 Behavior seeds (`catalog/seeds.py`, deterministic, no LLM)
- Input: the deterministic inventory (routes + capabilities).
- Rules: one seed per MUTATING route (POST/PUT/PATCH/DELETE); GET/read routes collapse by `(capability, resource-noun)` into one `...:browse` seed.
- id: `fn:<capability-slug>:<resource>:<action>` from normalized method+path. `source_capability_id` = parent capability.
- Output: `list[BehaviorSeed{ id, source_capability_id, routes[], kind: action|browse }]`.
- Acceptance: deterministic + stable across runs; Reform-AI produces a `fn:marketplace:listings:bulk-import` seed.

### 5.2 Evidence bundle (`catalog/evidence.py`, deterministic)
- Per seed: resolve controller (from route handler arg + import) -> controller method -> service method(s) (1-hop) -> bounded service-method snippet; gather route auth roles (-> actors), referenced entities (best-effort -> entities_touched).
- Compute `evidence_bundle_hash` over the resolved pointers + snippet.
- Partial chain is allowed; record resolved `layers`. NEVER drop a seed for a partial chain.
- Output: `EvidenceBundle{ seed, route_evidence[], symbol_evidence[], actors[], entities[], layers[], snippet, hash }`.

### 5.3 LLM translation (`catalog/translate.py`, label-only, bounded)
- Input to the model = ONLY the evidence bundle (routes, method+path, auth roles, controller+service symbol names, capped snippet). No whole-repo context.
- Forced-tool output = interpretation fields ONLY (title, summary, user_intents, action_verbs, object_nouns, input/output_artifacts, evidenced limitations).
- Hard constraints in the prompt: invent nothing; reference only provided ids; omit when unsure; limitations only if shown in evidence.
- Reuse the existing env-scrub + provider pattern from `semantic.py`.

### 5.4 Validation + confidence (`catalog/validate.py`, deterministic)
- Drop entries with no evidence; drop any cbc id not in the inventory; verify cited file/symbol exists at commit (`evidence_valid`).
- Set `coverage_basis.layers` from the resolved chain; `known_gaps` = the standard non-route layer list.
- Derive confidence:
  - `indeterminate` if route-layer coverage red OR `evidence_valid=false`.
  - `high` if route+controller+service resolved AND evidence_valid AND route-layer coverage green.
  - `medium` if route+controller resolved, service unresolved/partial.
  - `low` if route only.
  - (Confidence does NOT depend on actor/entity resolution.)

### 5.5 Caching + incremental + stale
- Cache key: `evidence_bundle_hash + prompt_version (+ catalog_version)`. Unchanged bundle -> reuse stored interpretation (NO LLM call). Reuse the commit-keyed cache pattern from `cache.py`.
- Incremental regen: only seeds whose bundle hash changed since the last catalog.
- Stale: on a new commit, re-check `evidence_valid` for carried entries; flag moved/removed symbols.

### 5.6 Publication + failure handling (`catalog/store.py`)
- Upsert rows; publish a `functionality_catalog` artifact to `agent_outputs` (NEW output_type -> migration must extend the CHECK constraint, preserving all existing values); set `is_active`.
- LLM/bundle failure for a seed -> record in `generator_failures` (coverage envelope), NO catalog entry, set `route_layer_complete=false`. Never silently drop from coverage accounting.

---

## 6. Search + ranking spec

- Searchable doc: title, summary, user_intents, action_verbs, object_nouns, input/output_artifacts (NOT evidence/file/symbol).
- Embedding text (v2): `title + ". " + summary + " Intents: " + join(user_intents)`. Embed entry at generation, query at search.
- v1 keyword: ts_rank (weighted) + exact verb/noun overlap boost.
- v2 hybrid (the gate bar):
  - RRF(full-text_rank, vector_cosine).
  - object-noun AGREEMENT boost.
  - object-noun CROSS-OBJECT penalty (the precision mechanism): build an object-noun lexicon = union of all entries' `object_nouns`; if the query contains a lexicon object NOT in the matched entry's object_nouns, apply a strong penalty. This is what makes negatives ("bulk import users") fail.
- Thresholds (`strong`/`medium`/`weak`) calibrated on the acceptance matrix; `strong` requires object agreement (vector similarity alone never reaches strong).
- `match_explanation` per result: matched intent string + object/verb agreement + vector_sim.

---

## 7. BA/PCA integration spec

- PCA (intake): after extracting behavior phrases, call `search_functionality(intent + phrases)`; surface candidates in `intake_assessment` (advisory; may raise a clarifying question). PCA never blocks.
- BA (scoping): for each candidate net-new CAPABILITY/WORKFLOW/BEHAVIOR concept (NOT entities/actors), call search; record a `capability_reuse_decision`.
- Hard block: (a) net-new capability/workflow classification WITHOUT a recorded search; (b) proceeding net-new while a STRONG candidate is UN-dispositioned.
- Warning-only: medium candidates. Weak: not surfaced.
- Human override (recorded): `proceed_net_new_with_rationale` despite a strong candidate.
- Re-confirm loop: on accept/extend, re-check the candidate's grounded evidence (route_id, symbol) against the deterministic CCA resolver at the current commit. Pass -> reuse is a relied-upon scope fact; fail -> stale -> indeterminate.
- Boundary: capability-reuse is a SEPARATE link from `maps_to_codebase`. The cbc join still comes only from the deterministic entity/actor `concept_resolution`.

---

## 8. Acceptance test suite

- Unit (no LLM): seed builder (mutating->seed, GET-collapse, id naming + stability); chain resolver (full + partial); confidence derivation; evidence_valid; coverage-envelope builder; object-noun lexicon builder.
- Generation/validation: unevidenced dropped; non-inventory cbc dropped; missing-symbol -> evidence_valid=false; cache hit -> no LLM call.
- Search ranking: POSITIVE recall (the 10 queries) -> importer top-3; NEGATIVE precision (the 7 queries) -> importer NOT strong; cross-object penalty fires; match_explanation present.
- Trust-boundary: no path writes maps_to_codebase; empty search returns envelope; all actors/entities in inventory; LLM-asserted confidence ignored (derived used).
- Coverage-honesty: script-only behavior absent AND `scripts` in uncovered_layers; generator failure -> route_layer_complete=false.
- BA/PCA gate: net-new blocked without recorded search; strong+undispositioned blocks; override+rationale recorded; accept -> deterministic re-confirm runs.
- Drift: move a cited symbol -> entry stale next run; accepted-reuse re-confirm fails -> flagged.
- Migration/RPC: table+RPC created; response always includes coverage_envelope.

Acceptance matrices (calibration set):
- POSITIVE (top-3 must contain the importer): bulk ingest property listings; upload Excel file of properties;
  import listings from CSV; create many property listings from spreadsheet; mass upload marketplace properties;
  admin spreadsheet upload for listings; batch create property records; onboard properties from a sheet;
  upload a file to create listings in batches; mass-create marketplace inventory from an Excel template.
- NEGATIVE (importer must NOT be strong): bulk import users; upload investor contacts from spreadsheet;
  import financial transactions; create many partners from CSV; sync listings from MLS feed;
  import employee directory; upload invoices from spreadsheet.

---

## 9. Implementation sequence (for Codex)

| Step | Builds | Acceptance | Pause |
|---|---|---|---|
| 0. Contracts | the 4 schemas (3.1-3.3) + label the acceptance matrix | schemas reviewed; matrix labeled | YES |
| 1. Seeds + evidence bundle (deterministic, no LLM) | `seeds.py` + `evidence.py` | unit tests; Reform-AI yields the bulk-import seed with full chain | |
| 2. Confidence + evidence_valid + coverage envelope | `validate.py` + `envelope.py` | confidence matrix; envelope shape | |
| 3. LLM translation + validation + caching | `translate.py` wired into `pipeline.py --catalog` | generation/validation tests; bulk-import entry (grounded/interpretation split); cache hit -> no LLM | |
| 4. Storage + artifact + is_active | migration (NEXT FREE number) + output_type extension + `store.py` | migration/RPC tests; persisted + published; latest-active resolves | |
| 5. Keyword search RPC + envelope + match_explanation | `search_functionality` v1 | positive recall via keyword; envelope on empty | YES (calibrate) |
| 6. Embeddings + hybrid RRF + object-noun boost/penalty + thresholds | search v2 | FULL positive recall + negative precision pass; thresholds recorded | |
| 7. Raw-evidence fallback (P2.5) | fallback index + 'both' mode | un-catalogued behavior surfaces, lower-trust marked | |
| 8. BA/PCA wiring + audit + gate + re-confirm | BA/PCA agent changes + `capability_reuse_decisions` | gate tests; PCA hints; BA blocks per rules; accept -> re-confirm | YES |
| 9. Dashboard browser + why-it-matched | UI | optional/last | |

Do NOT build in v1: workflow-merge grain (multi-route->one behavior); one-route->multi-behavior;
non-route coverage (scripts/jobs/queues/cron/webhooks); learned ranking; raw-fallback before hybrid.

---

## 10. Risks + mitigations
- Enumeration incompleteness (LLM misses a behavior) -> coverage envelope keeps trust; raw fallback (Step 7) improves recall.
- Over-claiming summaries -> grounded/interpretation split + claim-vs-evidence verification before reuse; evidenced-only limitations.
- Precision false-positives -> object-noun lexicon + cross-object penalty; negative matrix is the true bar.
- Empty=absence -> coverage envelope on every response; BA treats empty-under-incomplete as indeterminate.
- Staleness -> evidence_bundle_hash + drift flags + per-commit regen.
- Cost -> cache by bundle hash; incremental; bounded packets.
- Trust creep -> never writes maps_to_codebase; accepted reuse re-confirmed against the deterministic resolver.

---

## 11. Open questions to settle before Step 0
1. Audit home: `capability_reuse_decisions` table (recommended) vs product_graph node.
2. pgvector enabled on the project? (before Step 6)
3. Chain-resolution mechanism: regex-bounded vs light TS AST.
4. Query-side object-noun extraction: heuristic-only in v1; pre-authorize a tiny extractor only if the negative matrix fails.
5. Regeneration trigger: per CCA run / per commit / manual.
6. Threshold ownership for the acceptance matrix.
7. Next free migration number (verify; 039/040 may be taken).
