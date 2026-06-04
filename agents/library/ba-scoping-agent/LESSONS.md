# Lessons - BA Scoping Agent

Standing rules specific to this agent. Add entries after corrections or discoveries.
Format: `[YYYY-MM-DD] | what went wrong or was discovered | rule to apply going forward`

These seed entries are the design decisions sealed during the BA/CCA architecture threads. They are
binding from day one.

---

- [2026-06-02] | The graph, not the documents, is the source of truth | Documents (Feature Brief, later PRD/stories/AC) are disposable projections over the graph. Never edit a brief to change a decision - change the `DEC-*` node and re-render. Nothing of record lives only in a document.

- [2026-06-02] | Epistemic status and scope readiness drift if stored | Both are DERIVED, never columns. Use `public.graph_node_epistemic_status` and `public.graph_feature_readiness`. A proposed Concept/Decision is `claim`, accepted is `fact`. Do not add an `epistemic` or `ready` column.

- [2026-06-02] | The tenant/company can be resolved wrong by `LIMIT 1` | There are multiple companies (ReformAI, AfterGlow, Personal). Resolve the tenant by name or explicit UUID and set `app.current_tenant_id`. Never `SELECT ... LIMIT 1`. (Mirrors the quota-sync provider_accounts split bug.)

- [2026-06-02] | cbc:* identities belong to the Codebase Context Agent | The BA Agent reads them via `public.cbc_resolve` and stores them in `concept.maps_to_codebase[]`. It NEVER mints, renames, merges, or mutates `cbc:*`. The join is application-level (no DB FK), so it must be populated deterministically from `concept_resolution[]`, not inferred.

- [2026-06-02] | Accepted Decisions are immutable | Once a `DEC-*` is `accepted` it is content-frozen by trigger (migration 024). To change a decision, supersede it with a new `DEC-*` and a `supersedes` edge. Rejected Decisions are retained as the road-not-taken, never deleted.

- [2026-06-02] | A requirement/rule that cites no Concept is an opinion | Every `DEC-*` must have at least one `references` edge to a Concept. Uncited decisions are not contestable. (Mirrors the code-review-agent "findings must cite sources" rule.)

- [2026-06-02] | Asking twenty questions defeats the purpose | Only BLOCKING + HIGH-divergence assumptions become `QST-*`. Divergence = how much the answer changes the data model/workflow. Low-divergence assumptions become feature notes, not questions. Mis-calibrated divergence (burying a real fork, or escalating trivia) is the agent's main quality risk.

- [2026-06-02] | One human answer can resolve multiple forks | A single sentence may produce several `DEC-*` nodes (e.g. authorship + taxonomy). Decompose the answer - each decision has an independent supersede future. Do not fuse two forks into one decision.

- [2026-06-02] | The agent must be able to refuse | If `graph_feature_readiness` returns `scope_ready=false`, emit the open Questions and do NOT render a final brief. Refusal-to-proceed is a feature, not an error.

- [2026-06-02] | Attribute leakage corrupts the source-of-truth claim | Attribute is deferred in v1, but field sets (name, sku, price, ...) must be captured inside a `DEC-*` `implies_attributes[]` stub - never only in brief prose. Same for rule statements in `implies_rules[]`. This keeps Phase 2 promotion a migration, not a re-scoping.

- [2026-06-02] | The system dies write-only | Proposed nodes piling up unratified is the failure mode that kills a two-person graph. Track ratification backlog as a health metric. Keep proposed volume low: alias-resolve before minting a Concept, batch ratification.

- [2026-06-02] | Production telemetry uses the production secret and URL | `AGENT_OVERSIGHT_SECRET` (not `OVERSIGHT_SECRET`/`INGEST_SECRET`) and `OVERSIGHT_URL=https://agent-oversight.vercel.app` (not the old Netlify URL). The dev-server secret silently fails against production.

- [2026-06-02] | Stale codebase context produces contradictory scope | Record `scoped_against.commit_sha` in the feature node. Warn when the brief is scoped against a commit older than the latest available `codebase-context.json`.

- [2026-06-03] | Readiness/subgraph must traverse edges in BOTH directions | Questions link via `derived_from` with the QUESTION as source (`QST -> FEAT`), so the feature is the edge DESTINATION. The original `graph_feature_readiness`/`graph_feature_subgraph` only followed feature-as-source edges (`references -> concepts`), so open blocking questions were invisible and `scope_ready` returned true with real forks open. Fixed in migration 030; 024 source patched. Any feature-anchored traversal must union both directions.

- [2026-06-03] | maps_to_codebase comes from `concept_resolution[].cbc_ids`, never LLM-guessed code names | The first runtime had the LLM emit `cbc_refs` by code name; they did not match the artifact's code identifiers, so every concept mapped to `[]`. Authoritative source is the artifact's `concept_resolution`, matched by `requested_noun` against the concept title/aliases. LLM `cbc_refs` are a fallback only. This is the CCA/BA join; getting it from the LLM breaks it.

- [2026-06-03] | `agent_outputs.run_id` is NOT NULL and FKs to `runs` | A paused agent degrades telemetry to a no-op, so no `runs` row exists, so the artifact write fails the FK. Prove logic while paused with graph-only/`--no-persist`; activate the instance BEFORE the authoritative persisting run.

- [2026-06-03] | The handoff resolver param is `p_target_key` | `public.get_latest_codebase_context(p_target_key text)` (not `p_product_key`). Returns the latest COMPLETE artifact (non-empty `concept_resolution`); columns include `content` (jsonb), `commit_sha`, `artifact_id`.

- [2026-06-03] | First real scope proved the model | Against live ReformAI data the agent correctly: bound Material->room_material_option/project_room_material (a material catalog ALREADY EXISTS -> reconciliation, not greenfield), treated Supplier/Market as net-new, recorded single-market Colombia as a confirmed constraint (refuting the market-scoping assumption), raised 3 blocking high-divergence questions, and WITHHELD the brief. Cost ~$0.12/run, claude-opus-4-5.

- [2026-06-04] | maps_to_codebase was LLM-guessed and missed existing code (Partner/Admin shipped as net-new) | Populate maps_to_codebase DETERMINISTICALLY: concept_resolution[noun] (authoritative) -> ELSE exact normalized name-match (`_norm`) of the title/aliases against entities[]/actors[] -> ELSE LLM cbc_refs (last resort). The CCA artifact carries the answer; never rely on the LLM to map a concept to existing code. concept_resolution only covers nouns that were in concepts_to_check at CCA-run time, so the name-match fallback is essential.
- [2026-06-04] | Reused (resolved) concepts kept their old empty maps_to_codebase | When graph_resolve_concept returns an existing concept with empty maps_to_codebase and we now have a deterministic match, backfill via public.graph_set_maps_to_codebase (migration 038). Only when currently empty (never overwrite); accepted/frozen concepts are immutable (trg_node_immutability) - correct those via supersession, not backfill.
