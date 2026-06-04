# Codebase Context Agent - Codebase Truth Service Design

Status: DRAFT for implementation planning
Owner: `reformai`
Agent: `reformai.codebase-context-agent`
Relates to: `docs/codebase-context-interface.md`, `docs/agent-agile-force-lifecycle.md`, `docs/agile-pca-integration-plan.md`

---

## 0. Design lock

> CCA is not a summarizer. CCA is the codebase truth layer for the Agile workflow.
>
> Its job is to maintain a commit-keyed, deterministic, evidence-backed inventory of what exists in
> the ReformAI codebase, enrich that inventory semantically where useful, and provide cheap
> per-feature concept resolution to BA.
>
> The LLM is not responsible for discovering entities. Deterministic parsers discover entities,
> actors, routes, permissions, and integrations. The LLM only labels and interprets them.
>
> CCA must always report coverage. It must never present a partial sample as complete truth.

A context agent summarizes. A truth service inventories, proves, cites, caches, and resolves.

Core invariant:

> If CCA says a concept does not exist, a human and downstream agents should be able to trust that
> it does not exist within the analyzed codebase coverage. If coverage is incomplete, CCA must say
> so explicitly.

---

## 1. Problem statement

CCA is the IS-state foundation of the Agent Agile Force. It is the only agent that reads source
code, and it provides the product reality that downstream agents rely on.

```
PCA = what the product team wants
CCA = what the codebase already contains
BA  = what should change
UX  = what the experience should be
Eng = how to implement it
```

Because BA and Engineering depend on CCA, its accuracy and completeness set the ceiling for the
quality of the entire workflow.

Today CCA behaves too much like: `clone repo -> compact context -> one LLM call -> inferred
entities/actors/signals`. Five structural failure modes follow.

**1.1 Incompleteness.** The output is a sample, not the truth. A single LLM pass over a real
monorepo cannot reliably enumerate every entity, actor, route, permission, integration, and domain
object. The last live run surfaced only 18 entities for the whole product - implausibly low. Silent
omission is the most dangerous failure because the output still looks plausible.

**1.2 Confidently wrong downstream scope.** During Habi ingestion scoping, BA labeled Partner and
Admin as net-new even though both already existed in code. Not a BA reasoning failure - a CCA
architecture failure: those concepts were not in the inventory, so BA treated them as greenfield.
Result: duplicate builds, wrong estimates, missed reconciliation.

**1.3 Non-determinism.** An LLM-inferred inventory changes across runs (token budget, ordering,
truncation, generation variance). A truth layer cannot be based on non-reproducible structure.

**1.4 Cost and staleness.** A full repo sweep is expensive, so old context gets reused. The
materials-run context was reused for Habi, creating concept-resolution gaps. Today the system is
neither cheap nor correct.

**1.5 No incrementality and no reality layer.** No clean way to analyze only changed files, merge
updated inventory, or distinguish live from dead code. Static analysis is the first milestone;
future versions reconcile against product DB and runtime usage.

---

## 2. Success criteria

A trustworthy CCA provides: complete structural inventory (no silent omission); deterministic
results for the same commit + parser version; honest coverage reporting; freshness via commit-keyed
cache + incremental re-extraction; cheap per-feature concept resolution; evidence for every claim;
coverage-qualified statuses; compatibility with the existing BA-facing contract; and a future path
to runtime/DB reality reconciliation.

Most important practical rule:

> CCA can only say `not_found` when the relevant coverage is green. Otherwise it must return
> `indeterminate`.

---

## 3. Agent boundary

CCA owns IS-state questions only: what exists in the codebase; where it exists; how strongly a
feature concept matches existing code; what evidence supports the match; what was not analyzed.

CCA does not own: what to build; the business scope; the UX; how Engineering implements it.

CCA never emits product decisions, business scope, or implementation recommendations. Its strongest
verbs are: `exists`, `partially_exists`, `ambiguous`, `conflicts`, `not_found`, `indeterminate`. BA
decides what those mean for product scope.

---

## 4. Architectural separation

The most important change is separating commit-scoped truth from feature-scoped resolution.

| Layer | Question | Scope | Cardinality | Cache key | Cost |
|---|---|---|---|---|---|
| Global Codebase Inventory | What exists at this commit? | commit | one per commit + parser_version | `(commit_sha, parser_version)` | paid once |
| Coverage Report | What did CCA actually inspect? | commit | one per commit + parser_version | `(commit_sha, parser_version)` | paid once |
| Semantic Codebase Context | What does the inventory mean in product terms? | commit | one per commit + parser_version | `(commit_sha, parser_version)` | paid once |
| Concept Resolution | Do these feature concepts already exist? | feature | one per feature | `(feature_id, commit_sha, parser_version)` | cheap lookup |

The split is mandatory because the artifacts have different lifecycles. Commit-scoped artifacts are
reusable across every feature at the same commit; feature-scoped artifacts are derived from PCA's
handoff and should be cheap to generate.

---

## 5. Pipeline

```
Repository commit
  -> Source acquisition
  -> Deterministic structural extraction
  -> Canonical codebase inventory
  -> Coverage report
  -> Semantic enrichment
  -> Commit-scoped cache
  -> Per-feature concept resolution
  -> BA-facing composed context
```

1. **Source acquisition** - repo, branch, commit_sha, parser_version, changed files, feature_id (when resolving).
2. **Deterministic structural extraction** - Drizzle tables/columns/enums/relations/indexes; role/auth config; route/controller structure; service module boundaries; integration config (if in P1).
3. **Canonical codebase inventory** - entities, actors, permissions, routes, handlers, capabilities, integrations, cbc identities, evidence pointers.
4. **Coverage report** - files discovered/parsed/skipped; parser failures; coverage status by layer.
5. **Semantic enrichment** - LLM labels and groups deterministic objects. May label/group/explain/summarize. May not invent entities or become the source of existence truth.
6. **Per-feature concept resolution** - input: PCA `handoff.feature_intent` + `concepts_to_check` + commit-scoped inventory + coverage + semantic context.
7. **BA-facing composed context** - assemble the existing BA contract from cached artifacts; do not persist a second duplicate monolith unless required for provenance.

---

## 6. Deterministic extraction boundary

The deterministic parser extracts structure: table exists; column exists; enum exists; role exists;
route exists; handler exists; route calls handler; handler touches table; permission check exists;
external integration config exists.

The LLM labels semantics: "this group of routes supports project creation"; "this table likely
represents supplier inventory"; "this module belongs to marketplace capabilities"; "this integration
supports payment processing."

Hard rule: **Structure is parsed. Semantics are labeled. Never the reverse.** This avoids the current
failure where the LLM is responsible for discovering entities.

---

## 7. cbc:* identity minting

The deterministic parser becomes the primary `cbc:*` identity minter. Deterministic extraction =
stable names = reproducible identities = safe cross-run comparison.

The existing `platform.cbc_identity_registry` remains the source of record. The inventory does not
become a second registry - it populates and reconciles against the registry.

Suggested deterministic ID patterns:

```
cbc:entity:<canonical_table_or_domain_name>
cbc:actor:<role_name>
cbc:route:<method>:<normalized_path>
cbc:capability:<capability_slug>
cbc:integration:<integration_name>
cbc:enum:<enum_name>
cbc:permission:<permission_slug>
```

Examples: `cbc:entity:partner`, `cbc:actor:admin`, `cbc:route:post:api-properties`, `cbc:integration:wompi`.

---

## 8. Artifact model

Split internal artifacts; compose the BA-facing view externally.

### 8.1 `codebase_inventory` (commit-scoped, deterministic, evidence-backed)

Source of record for what exists at this commit.

```json
{
  "artifact_type": "codebase_inventory",
  "repo": "reformai", "branch": "main", "commit_sha": "abc123", "parser_version": "cca-parser-v1",
  "entities": [
    { "cbc_id": "cbc:entity:partner", "name": "Partner", "source": "drizzle_table",
      "table": "partners", "file_path": "apps/api/src/database/schema/partners.ts",
      "columns": [], "relations": [],
      "evidence": [ { "type": "source_file", "file_path": "apps/api/src/database/schema/partners.ts", "symbol": "partners" } ] }
  ],
  "actors": [ { "cbc_id": "cbc:actor:admin", "name": "Admin", "source": "auth_role", "file_path": "..." } ],
  "routes": [], "capabilities": [], "integrations": []
}
```

### 8.2 `codebase_coverage_report` (commit-scoped, REQUIRED)

Proves what was analyzed and what was not.

```json
{
  "artifact_type": "codebase_coverage_report",
  "repo": "reformai", "branch": "main", "commit_sha": "abc123", "parser_version": "cca-parser-v1",
  "coverage_status": "green",
  "layers": {
    "schema": { "status": "green", "files_discovered": 42, "files_parsed": 42, "files_failed": 0, "skipped_files": [] },
    "routes": { "status": "yellow", "files_discovered": 31, "files_parsed": 29, "files_failed": 2,
      "skipped_files": [ { "file_path": "apps/api/src/routes/legacy.ts", "reason": "unsupported dynamic export pattern" } ] },
    "auth":   { "status": "green", "files_discovered": 3, "files_parsed": 3, "files_failed": 0 }
  },
  "known_gaps": []
}
```

### 8.3 `semantic_codebase_context` (commit-scoped, LLM-enriched)

Explains the deterministic inventory in product/domain language: `domain_signals`, `capability_map`,
`glossary`, `module_summaries`, `entity_semantics`, `integration_semantics`. Rule: enriches
deterministic objects only; may not introduce unsupported entities.

### 8.4 `concept_resolution` (feature-scoped)

Resolves PCA handoff concepts against the current inventory.

Input:
```json
{ "feature_id": "FEAT-HABI-INGESTION", "feature_intent": "Integrate Habi property inventory into ReformAI",
  "concepts_to_check": ["Habi","Partner","Admin","Property","Listing","Inventory"],
  "commit_sha": "abc123", "parser_version": "cca-parser-v1" }
```

Output (abridged):
```json
{
  "artifact_type": "concept_resolution", "feature_id": "FEAT-HABI-INGESTION",
  "commit_sha": "abc123", "parser_version": "cca-parser-v1",
  "resolved_concepts": [
    { "concept": "Partner", "status": "exists", "matched_cbc_id": "cbc:entity:partner",
      "match_confidence": "high", "resolution_method": "deterministic_alias_match",
      "evidence": [ { "type": "table", "name": "partners", "file_path": "apps/api/src/database/schema/partners.ts" } ],
      "coverage_basis": { "layer": "schema", "coverage_status": "green" } },
    { "concept": "Inventory", "status": "ambiguous", "match_confidence": "medium",
      "resolution_method": "llm_ambiguous_tail",
      "possible_matches": ["cbc:entity:property","cbc:entity:material","cbc:entity:catalog_item"],
      "question_for_ba": "Does Habi inventory map to existing property listings, material catalogue items, or a new partner-owned inventory concept?",
      "coverage_basis": { "layer": "schema", "coverage_status": "green" } },
    { "concept": "Habi", "status": "not_found", "match_confidence": "high",
      "resolution_method": "deterministic_no_match", "evidence": [],
      "coverage_basis": { "layer": "schema_and_integrations", "coverage_status": "green" } }
  ]
}
```

Status vocabulary + definitions:
- `exists` - direct structural match with sufficient evidence.
- `partially_exists` - some parts exist, but not enough to treat the full concept as modeled.
- `ambiguous` - multiple plausible matches; BA decides product meaning.
- `conflicts` - appears to collide with an existing model/naming/permission/workflow.
- `not_found` - no match AND relevant coverage is green.
- `indeterminate` - no match, but coverage is insufficient to safely say it does not exist.

### 8.5 `codebase_context` (BA-facing composed view)

Preserves BA compatibility without storing a duplicate monolith. Assembled on demand from
`codebase_inventory` + `codebase_coverage_report` + `semantic_codebase_context` + `concept_resolution`.
BA-facing shape stays `{ entities, actors, domain_signals, concept_resolution, coverage, confidence }`.

Design rule: **store truth once; compose views many times.**

---

## 9. Concept resolution algorithm (two-tier)

**Tier 1 - deterministic (run first for every concept):** exact cbc_id match; exact table/entity
name match; singular/plural; snake_case/camelCase/PascalCase normalization; registered aliases; role
name; route path; enum value; integration name; known synonym table. (`Partner -> partners ->
cbc:entity:partner`; `Admin -> admin role -> cbc:actor:admin`.) If deterministic confidence is high,
do not call the LLM.

**Tier 2 - LLM ambiguous-tail (only for unresolved/ambiguous concepts):** receives the unresolved
concept, `feature_intent`, nearby deterministic matches, `semantic_codebase_context`, and coverage.
Outputs possible matches, ambiguity explanation, recommended BA question. The LLM still cannot create
existence truth - it only interprets ambiguity among extracted objects.

---

## 10. Coverage and trust

Coverage levels: `green` (all required structural sources discovered + parsed), `yellow` (some
non-critical files skipped/failed, core parsed), `red` (key sources missing/unavailable/failed).

Layer-specific coverage: `schema`, `auth`, `routes`, `controllers`, `services`, `integrations`,
`frontend_routes`, `server_actions`, `runtime_reality`.

Hard contract rule: `not_found` requires green coverage for the relevant layer; non-green => `indeterminate`.

BA enforcement (recommended split):
- **Entity existence** - hard-block net-new classification unless schema coverage is green.
- **Actor existence** - hard-block net-new classification unless auth coverage is green.
- **Capability/workflow** - allow a high-divergence question on yellow; hard-block on red.
- **Critical route/auth/integration claims** - hard-block if the relevant layer is red.

BA must not classify a concept as net-new when CCA status is `indeterminate`.

---

## 11. Storage model

`agent_outputs` is not the cache layer. Use:
- `agent_outputs` - published CCA artifacts + handoff provenance.
- `codebase_context_cache` - reusable commit-scoped inventory, semantic context, coverage.
- `concept_resolution` - feature-scoped, its own table or a typed agent_output.

### 11.1 Lightweight v1 cache table
```
codebase_context_cache
  id, tenant_id, product_key, repo, branch, commit_sha, parser_version,
  inventory_json, semantic_context_json, coverage_report_json, created_at, updated_at
  UNIQUE (tenant_id, product_key, repo, commit_sha, parser_version)
```

### 11.2 Future normalized cache tables
`codebase_context_runs`, `codebase_inventory_modules`, `codebase_entities`, `codebase_actors`,
`codebase_routes`, `codebase_capabilities`, `codebase_integrations`, `codebase_coverage_reports`,
`codebase_semantic_contexts`, `codebase_concept_resolutions`. Normalized is better long-term because
incremental re-extraction needs per-file/per-module merge.

### 11.3 Cache key
`(commit_sha, parser_version)` - not `commit_sha` alone. A parser improvement changes extracted truth
even if the commit is unchanged.

---

## 12. BA-facing composed view

- **Option A - SECURITY DEFINER RPC** `public.get_codebase_context(commit_sha, parser_version, feature_id)`:
  centralized, consistent, multi-agent, can enforce tenant/product boundaries; but more SQL, harder to
  evolve early.
- **Option B - CCA runtime assembler:** simpler to iterate, logic in Python, easy local CLI testing;
  but potential duplication if other agents need it.

Recommendation: **start with the application-layer assembler in P1; move to an RPC once the view
stabilizes.** P1 is about proving extraction, coverage, and resolution - do not slow it with an RPC
abstraction too early.

---

## 13. Execution model

CLI-triggered worker, designed as a service.
- **Phase 1a (CLI):** operator runs CCA against repo + commit; CCA writes cache + artifacts to
  Supabase; dashboard reads published artifacts; BA consumes composed view.
- **Phase 1b (hosted worker):** a web action queues a CCA job; worker pulls repo at commit, updates
  cache, writes coverage/inventory/semantic/resolution; dashboard shows status + output.

Rule: trigger mechanism must not change the artifact contract.

---

## 14. PCA to CCA handoff

PCA hands CCA: `feature_intent`, `concepts_to_check`, `clarification_brief_artifact_id`,
`intake_assessment_artifact_id`, `feature_id`, `product_key`, `tenant_id`.

CCA adds codebase truth: `commit_sha`, `parser_version`, `concept_resolution_artifact_id`,
`coverage_status`, `codebase_context_view`.

BA receives: PCA final brief; CCA composed codebase context; CCA concept resolution; CCA
coverage/confidence.

---

## 15. Telemetry and reality layer (deferred to P4)

Static analysis answers "what does the code say exists?" Runtime/DB reality answers "is it used /
populated / active / dead? what is the real cardinality?" Potential inputs: Postgres catalog, row
counts, real FKs/indexes, APM traces, route usage, feature flags, logs, cron/job execution.

Rules: runtime reality augments static truth, does not replace it; CCA must never require telemetry to
know that a table/route/actor/integration exists in code.

---

## 16. P1 implementation scope

P1 goal: **kill the Partner/Admin class of error.**

P1 includes deterministic extraction for: Drizzle tables/columns/enums/relations (where parseable);
role/auth config; basic API route/controller structure; basic integration config (if easily
parseable); coverage report; deterministic cbc identity minting; BA-facing composed view.

P1 can defer: full service dependency tracing; deep business-logic understanding; runtime DB catalog;
APM usage; frontend component mapping; full server-action parsing (if not straightforward); LLM
map-reduce semantic depth; incremental merge.

P1 output must let BA know: does this entity already exist? does this actor already exist? does this
basic route/capability appear to exist? can I trust `not_found`? what coverage limits should I respect?

---

## 17. P1 acceptance criteria

**17.1 Partner/Admin regression.** Given handoff `{ feature_intent: "Integrate Habi property
inventory into ReformAI", concepts_to_check: ["Partner","Admin","Habi","Property","Inventory"] }`, CCA
must return: Partner -> `exists`/`partially_exists` (with evidence); Admin -> `exists` (with
evidence); Habi -> `not_found` only if relevant coverage is green; Inventory -> `exists`/
`partially_exists`/`ambiguous`/`not_found` (with evidence + coverage basis). **Hard fail:** Partner or
Admin -> `not_found`, or net-new without evidence.

**17.2 Coverage honesty.** If any schema files fail parsing, CCA must not report green schema
coverage. If schema coverage is not green, CCA must not emit `not_found` for schema-backed entity
concepts.

**17.3 Determinism.** Same commit + parser version produces identical structural inventory.

**17.4 Evidence.** Every `exists`/`partially_exists`/`conflicts` status includes evidence (at least
one of: file_path, symbol, table, route, role, enum, integration config).

**17.5 No LLM-created entities.** Any entity in `codebase_inventory.entities` traces to deterministic
evidence. LLM-only entities are invalid.

**17.6 BA compatibility.** BA consumes the composed `codebase_context` without changing its high-level
contract.

---

## 18. Phasing

- **P1 - Determinism, completeness, coverage:** deterministic parser; coverage report; cbc minting;
  lightweight cache; composed BA view; basic concept resolution. Outcome: CCA stops missing obvious
  existing entities/actors.
- **P2 - Cache, incremental, cheap resolution:** `(commit_sha, parser_version)` cache; changed-file
  detection; per-file/per-module merge; dedicated concept-resolution artifact; alias registry; two-tier
  resolver. Outcome: feature resolution is cheap and current.
- **P3 - Semantic depth:** LLM map-reduce over modules; capability map; domain signals; glossary;
  module summaries; semantic clustering. Outcome: richer context without losing deterministic truth.
- **P4 - Reality layer:** Postgres catalog reconciliation; row counts; APM/usage; dead-code + route
  usage signals. Outcome: CCA distinguishes coded existence from actual product usage.

---

## 19. Recommended answers to open questions

1. **P1 parser surface** - Drizzle + enums + role/auth + basic route/controller structure; integration
   config if straightforward. Defer deep server actions + service dependency tracing to P2.
2. **Composed view mechanism** - application-layer assembler in P1; SECURITY DEFINER RPC once stable.
3. **Incremental merge unit** - per-file first; per-module once boundaries are proven.
4. **Parser reuse** - investigate Drizzle schema AST / drizzle-kit introspection first; fall back to a
   TypeScript AST parser only if existing tooling is insufficient.
5. **Coverage -> BA enforcement** - hard-block entity net-new on non-green schema coverage; hard-block
   actor net-new on non-green auth coverage; for capability/workflow, allow a high-divergence question
   on yellow, block on red.

---

## 20. Build order discipline

Do not add more LLM intelligence before P1 deterministic extraction + coverage work. The Partner/Admin
miss is an architecture problem, not a prompt problem.

```
1. Deterministic extraction
2. Coverage report
3. cbc identity minting
4. Lightweight cache
5. Deterministic concept resolution
6. BA-facing composed view
7. LLM ambiguous-tail resolver
8. Semantic enrichment
9. Incremental merge
10. Runtime reality layer
```

---

## 21. Final design principle

CCA should become boring in the places where truth matters. The parser does factual discovery; the
LLM does semantic interpretation; BA does product scoping; Engineering does implementation planning.
That separation is what makes the Agile workflow trustworthy.
