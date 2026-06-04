# P2 Build Plan - Rule/Attribute Promotion + Gate A Feature Spec Snapshot

Status: design (no code yet). Extends the shipped polymorphic graph; does not replace it.
Owner: reformai. Pairs with: docs/agent-agile-force-lifecycle.md, docs/cost-guardrail-plan.md.

Locked decisions (1-21) from the design session are treated as binding. This plan is the
migration-by-migration realization. Every change extends `product_graph.graph_nodes` /
`graph_edges` (migration 024) and the existing `graph_*` RPCs.

---

## 1. Executive summary

P2 makes the Gate A Feature Spec renderable from graph truth with zero prose leakage. It:

1. Promotes **Rule** and **Attribute** to first-class `node_type` values in the existing polymorphic
   `graph_nodes` table (no new entity tables).
2. Replaces the one-hop `graph_feature_detail` with a **bounded transitive** feature read.
3. Adds a **Feature Spec renderer** (read-time projection from the subgraph).
4. Adds **Gate A validation** that is strictly stronger than scope-readiness.
5. **Snapshots** the approved Feature Spec into an immutable `agent_outputs` row + the lifecycle spine.
6. Provides **read-time adapter RPCs** (UX / Engineering / QA) over the pinned snapshot.

It is additive: existing node types, RPCs, the immutability trigger, RLS, and the BA runtime keep
working. The only destructive operations are CHECK-constraint relaxations (drop+recreate), which do not
touch data.

---

## 2. Current-state assessment

Shipped (migrations 024, 029-038):
- `product_graph.graph_nodes` - polymorphic: `feature | concept | question | decision`. Columns:
  `id, tenant_id, product_key, node_type, node_key, title, status, kind, blocking, divergence,
  maps_to_codebase[], aliases[], node_attributes(jsonb), ratified_by, ratified_at, created_by,
  created_at, updated_at`.
- `product_graph.graph_edges` - `edge_type in (references, resolves, supersedes, derived_from)`,
  append-only, FK src/dst -> graph_nodes(id) RESTRICT, unique(edge_type,src,dst), no self-loop.
- Constraints (by name): `graph_nodes_node_type_check` (inline/auto-named), `ck_node_key_prefix`,
  `ck_node_status`, `ck_kind_concept_only`, `ck_blocking_question_only`, `ck_divergence_question_only`,
  `ck_mapping_concept_only`; `graph_edges_edge_type_check` (inline/auto-named).
- Immutability trigger `trg_node_immutability`: blocks content edits on
  accepted/handed_off/rejected/superseded/deprecated; allows accepted -> superseded/deprecated.
- RPCs: `graph_next_key`, `graph_upsert_node`, `graph_add_edge`, `graph_ratify_node`,
  `graph_resolve_concept`, `graph_feature_detail` (one-hop), `graph_feature_readiness`,
  `graph_backlog`, `graph_list_features`, `graph_set_maps_to_codebase`, `graph_node_epistemic_status`.
- `Decision.node_attributes.implies_rules[]` / `implies_attributes[]` exist as stubs.
- `agent_outputs.output_type` CHECK includes `product_graph_scope`, `codebase_context`, etc.
- Migration 026 (`platform.feature_lifecycle` / `lifecycle_events` / `gate_decisions`) is AUTHORED but
  NOT APPLIED.

Latent problems P2 must fix:
- **Decisions are 2 hops from Feature** (decision->concept; decision->question->feature) and are NOT
  returned by the one-hop `graph_feature_detail`. Rules will be 3 hops, Attributes via Concept. The
  current renderer cannot reliably assemble Gate A.
- Functional requirements + data specs live only as `implies_*` jsonb stubs (prose-adjacent, untraceable).
- `graph_feature_readiness` checks open blocking questions / unresolved concepts only - far weaker than
  a "ratified, internally-consistent, provenance-backed" gate.
- No snapshot mechanism; no immutable approved baseline.
- `ck_kind_concept_only` and `ck_mapping_concept_only` forbid `kind` / `maps_to_codebase` on non-concept
  nodes - they would block Rule/Attribute as designed.

---

## 3. Target architecture

```
Feature   --references-->        Concept            (existing)
Feature   <--derived_from--      Question           (existing)
Question  <--resolves--          Decision           (existing)
Decision  --references-->        Concept            (existing; citation)
Decision  --establishes-->       Rule | Attribute   (NEW; replaces implies_* stubs)
Rule      --references-->        Concept            (NEW; rule must cite >=1 concept)
Rule      --references[validates]--> Attribute      (NEW)
Concept   --owns-->              Attribute          (NEW; non-sovereign ownership, exactly one)
*         --supersedes-->        * (same type)      (existing)
```

Reachability: a feature's full subgraph is its transitive provenance component, depth <= 4
(feature -> concept -> attribute; feature -> question -> decision -> rule). Rendered + adapted from
that component. Gate A pins the accepted subset as an immutable manifest.

Node-type roles (knowledge plane): Concept, Decision, Rule, Attribute = durable truth.
Process plane: Feature, Question (+ Gate snapshots, agent_outputs) = scaffolding.

---

## 4. Migration plan (by migration)

### Migration 039 - promote Rule + Attribute (DDL, additive + constraint relaxation)

Node type + key + status:
- Drop `graph_nodes_node_type_check`; recreate with `node_type in
  ('feature','concept','question','decision','rule','attribute')`.
- `ck_node_key_prefix` (drop/recreate) add: `rule -> 'RULE-%'`, `attribute -> 'ATR-%'`.
- `ck_node_status` (drop/recreate) add:
  - `rule` status in `('proposed','accepted','rejected','superseded')`
  - `attribute` status in `('proposed','accepted','rejected','superseded','deprecated')`
  - (enumerate the FULL set now to avoid a later DDL; closed CHECK).

Constraint relaxations (drop/recreate):
- `ck_kind_concept_only` -> `kind IS NULL OR node_type IN ('concept','rule','attribute')`.
  (rule_type / attribute_type are open vocab in `kind`.)
- `ck_mapping_concept_only` -> allow `maps_to_codebase[]` on `concept | rule | attribute`; still forbid
  `aliases[]`/`maps_to_codebase[]` on `feature | question`. (Split the constraint: aliases stays
  concept-only; maps_to_codebase widens to concept/rule/attribute.)

Edges:
- Drop `graph_edges_edge_type_check`; recreate with
  `edge_type in ('references','resolves','supersedes','derived_from','establishes','owns')`.

RPC:
- `graph_next_key` (CREATE OR REPLACE): add CASE branches `rule -> 'RULE-'`, `attribute -> 'ATR-'`.

No data writes. Backward compatible (existing rows unaffected; existing edge/node types still valid).

### Migration 040 - transitive feature read

- New RPC `graph_feature_graph(p_tenant uuid, p_product text, p_feature_key text, p_max_depth int
  default 4) returns jsonb` = `{ feature, nodes[], edges[] }` over the feature's provenance component
  (bounded BFS from the feature across all edge types, both directions, depth-capped, distinct nodes).
- Keep `graph_feature_detail` as a thin wrapper (one-hop) for backward compat, or repoint the dashboard
  to `graph_feature_graph`. Recommend: repoint dashboard, deprecate detail.
- `graph_feature_readiness` / `graph_backlog` unchanged here.

### Migration 041 - Gate A spine + validation + output type

- **Apply migration 026** (feature_lifecycle / lifecycle_events / gate_decisions) - the lifecycle spine
  this gate plugs into. (It is authored; apply it now.)
- `agent_outputs.output_type` CHECK: add `'gate_a_feature_spec'` (same pattern as 029/037).
- New RPC `graph_gate_a_readiness(p_tenant, p_product, p_feature_key) returns jsonb` - the validation
  algorithm (section 9). Returns `{ status, gates[], hard_failures[], warnings[], deferrals[] }`.
- New RPC `graph_gate_a_snapshot(...)` OR app-side writer (section 11) - assembles manifest, freezes.

### Migration 042 - backfill stubs (data; one-time)

- Promote every `accepted` Decision's `node_attributes.implies_rules[]` -> `RULE-*` nodes (+ `establishes`
  edge from the Decision, + `references` edges to that Decision's referenced Concepts).
- Promote `implies_attributes[]` `{concept, fields[]}` -> `ATR-*` nodes (+ `owns` edge from the Concept,
  + `establishes` edge from the Decision).
- Never edits the frozen Decisions (creating new nodes that reference them is legal under the trigger).
- Idempotent: skip if a Rule/Attribute already establishes-linked to that Decision with the same title.
- Delivery: a Python backfill script using `graph_next_key` + `graph_upsert_node` + `graph_add_edge`
  (mirrors the runtime path), not raw SQL, so key minting + RLS + trigger behave identically.

---

## 5. Node model details

### Rule (node_type='rule')
- `node_key` `RULE-NNNN`; `title` = short name; `status` proposed|accepted|rejected|superseded;
  `kind` = open rule-type vocab (`workflow|validation|permission|state_transition|calculation|
  integration|notification|exception|ux_behavior|business_logic`); `maps_to_codebase[]` allowed.
- `node_attributes`:
  ```
  { statement: string,                     # the normative requirement text
    normative_force: must|should|may|must_not,
    rationale: string,
    acceptance_criteria: [                  # AUTHORED AC only; derived AC are rendered, not stored
      { ac_key, given, when, then } ] }
  ```
- Edges: `Decision --establishes--> Rule`; `Rule --references--> Concept` (>=1 required);
  `Rule --references[nature=validates]--> Attribute`; `Rule --supersedes--> Rule`.

### Attribute (node_type='attribute')
- `node_key` `ATR-NNNN`; `title` = field name; `status` follows owning Concept; `kind` = open
  attribute-type vocab (`field|state|enum|relationship|computed|input|output`); `maps_to_codebase[]`
  allowed.
- `node_attributes`:
  ```
  { data_type: string|number|boolean|date|datetime|enum|object|array|reference,
    required: bool,
    allowed_values: [],
    codebase_status: exists|modify|net_new|unknown,
    pii: none|low|sensitive|restricted,
    display_label: string,
    description: string }
  ```
- Edges: `Concept --owns--> Attribute` (exactly one); `Decision --establishes--> Attribute`;
  `Rule --references[nature=validates]--> Attribute`; `Attribute --supersedes--> Attribute`.
- Governance invariants (enforced in BA + Gate validation, NOT DDL):
  G1 exactly one `owns` edge; G2 owning Concept is the only Concept that references it; G3 status mirrors
  owning Concept; G4 never re-pointed to a second Concept (supersede instead).

### Acceptance Criteria
- Derived at render time from each Rule (>=1 given/when/then), stable derived id `AC-<rule>-N`.
- Human-authored AC stored in `Rule.node_attributes.acceptance_criteria[]`.
- Promote to a `node_type='acceptance_criterion'` only when QA (Gate C/D) needs to version/test them.
  The derived-id convention makes that promotion non-breaking.

---

## 6. Edge model

| edge_type | from -> to | meaning | status |
|---|---|---|---|
| references | any -> concept; rule -> attribute | citation / linkage (nature: touches/creates/modifies/validates) | existing |
| resolves | decision -> question | answer | existing |
| supersedes | node -> same-type node | versioning | existing |
| derived_from | question -> feature; node -> node | provenance | existing |
| **establishes** | decision -> rule \| attribute | a decision creates a rule/attribute (replaces implies_* stubs) | NEW |
| **owns** | concept -> attribute | non-sovereign ownership (exactly one) | NEW |

Total: 6 edge types. No further edge types needed for P2.

---

## 7. Traversal RPC

`graph_feature_graph(tenant, product, feature_key, max_depth=4)`:
- BFS from the feature node across `graph_edges` (both directions), collecting distinct nodes/edges
  within depth; SECURITY DEFINER + explicit `tenant_id` filter (RLS-bypass rule).
- Returns `{ feature, nodes:[full rows], edges:[{edge_type,src_key,dst_key,edge_attributes}] }`.
- Cost guard: depth cap 4; rely on `ix_graph_edges_src/dst`. Watch fan-out on heavily-shared Concepts
  (a shared Concept pulls in its other features' attributes - filter attributes to those `owns`-reachable
  from concepts the feature references, not all concepts globally).
- Renderer + adapters + Gate validation all read this one RPC.

---

## 8. BA runtime changes (promotion step)

- After Decisions are created, add a **promotion pass**: for each `implies_rules[]` entry mint a proposed
  `RULE-*` (statement = entry; `establishes` from the decision; `references` to the decision's concepts);
  for each `implies_attributes[]` `{concept, fields[]}` mint proposed `ATR-*` per field (`owns` from the
  concept; `establishes` from the decision). New BA runs therefore never leave stubs un-promoted.
- Optional LLM-assist: draft `normative_force` + clean `statement` + `data_type`/`required` for human
  ratification. Keep nodes `proposed`; humans ratify at Gate A.
- Citation enforcement stays: a Rule with no `references->Concept` is invalid at write time.
- `node_attributes` JSON-schema validation added to the BA write path (jsonb is not Postgres-checkable).

---

## 9. Gate A validation algorithm

`graph_gate_a_readiness` returns `{ status: ready|blocked|warn, hard_failures[], warnings[], deferrals[] }`.
Status = `blocked` if any hard failure; else `warn` if warnings/deferrals; else `ready`.

Hard failures (block snapshot):
- H1 an open Question with `blocking=true`.
- H2 a Concept referenced by the feature with `status != 'accepted'` (Gate A requires ratified knowledge).
- H3 an `accepted` Decision with a non-empty `implies_rules`/`implies_attributes` stub NOT promoted to nodes.
- H4 a Rule in the subgraph with zero `references->Concept` (uncited requirement).
- H5 an Attribute with `owns` count != 1, or owning Concept not `accepted`.
- H6 any `maps_to_codebase` value with no matching `cbc:*` in the referenced CCA artifact (provenance).
- H7 missing provenance (`codebase_context_artifact_id` / `commit_sha`) on the feature.
- H8 a Rule or Attribute in the subgraph with `status != 'accepted'` (gate pins fact only).

Warnings (pass, surfaced):
- W1 node with `confidence=low`. W2 CCA `commit_sha` older than latest published CCA artifact (stale).
- W3 net-new Rule with no `maps_to_codebase` anchor. W4 non-blocking open Questions remain.

Deferrals (explicit human ack, not auto):
- D1 PM priority added or deferred. D2 success metric added or deferred. D3 `ratified_by` recorded.
- D4 contradiction check (`gate_contradiction_check`) = `deferred_v1` until the engine exists.

Completeness ("is anything missing") is NOT machine-gated - it is the human reviewer's responsibility.
Error messages name the offending node_key + the fix (e.g. "RULE-0007 cites no Concept; add a
references edge or reject it").

---

## 10. Feature Spec renderer model

- Pure function of `graph_feature_graph` output -> markdown. Each section is a node query; an empty
  section renders "none", never free prose. Orphan prose is impossible by construction.
- Sections: Snapshot metadata / Problem (feature+concepts) / Actors (kind=actor) / Scope in+out
  (accepted+rejected decisions) / Codebase reconciliation (maps_to_codebase) / Concepts+entities /
  Key decisions / Functional requirements (rules) / Data spec (attributes) / Acceptance criteria
  (derived from rules + authored) / Open questions (blocking|non-blocking) / Assumptions (notes) /
  Risks+constraints / PM layer (from snapshot record) / Provenance appendix (node ids, CCA id, commit,
  parser version, supersession) + a footer with node counts by type and the content hash.
- Implementation: TS module in the dashboard (`src/lib/scoping/render-feature-spec.ts`), read-time for
  preview; the same function output is frozen into the snapshot at Gate A.

---

## 11. Snapshot / agent_outputs model

Gate A approval writes ONE immutable `agent_outputs` row:
```
output_type: 'gate_a_feature_spec'
content: {
  manifest: { node_uuids[], node_keys[], edge_ids[], content_hash },   # machine snapshot
  rendered_markdown: "...",                                            # human artifact
  provenance: { codebase_context_artifact_id, commit_sha, parser_version,
                accepted_decisions[], included_rules[], included_attributes[] },
  pm_layer: { priority, success_metrics, go_no_go, target_release, notes },   # human-added
  supersedes: <prior gate_a_feature_spec id | null> }
```
Decision on storage shape (Fork): **full JSON in `content` + `content_hash`; no external URIs.** No blob
store exists; jsonb keeps row + payload consistent and queryable. Immutability is already enforced
(`agent_outputs` append-only). A scope change post-approval = a NEW row with `supersedes` set + a new
`gate_decisions` entry; never an edit.

Manifest = node UUIDs. Because `accepted` nodes are already frozen by `trg_node_immutability`, pinning
UUIDs is a sufficient snapshot - no separate node-versioning system. `content_hash` lets any consumer
verify integrity.

Lifecycle wiring: `gate_decisions` row (gate='A', decision='approved', feature_id, output_id,
ratified_by, ratified_at); `feature_lifecycle.artifact_pointers += {gate_a_feature_spec: output_id}`;
feature node status `scoping -> ready` (or `handed_off`).

---

## 12. Downstream adapters

Read-time `SECURITY DEFINER` RPCs over a snapshot manifest (post-gate) or live graph (pre-gate preview):
- `graph_adapter_ux(feature|snapshot)` -> actors, user-facing concepts, `kind=ux_behavior` rules, UI
  attributes, UX-affecting decisions, open UX questions, out-of-scope UX boundaries.
- `graph_adapter_eng(feature|snapshot)` -> all rules + attributes + maps_to_codebase + cbc refs + AC +
  rejected alternatives + snapshot id.
- `graph_adapter_qa(feature|snapshot)` -> rules + derived AC + validation rules + state-transition rules
  + risks + rejected alternatives.
Adapters never parse rendered markdown. Persist nothing but the gate snapshot (Fork 5). Post-gate,
adapters resolve against the pinned manifest UUIDs so a downstream stage sees the version it was
dispatched against.

---

## 13. Backfill / migration of stubs

- Python script `scripts/backfill_rules_attributes.py`: iterate features; for each `accepted` Decision
  read `implies_rules`/`implies_attributes`; mint proposed Rule/Attribute nodes + edges via RPCs;
  idempotent (skip if an `establishes`-linked node with the same title exists).
- Historically-accepted nodes that are wrong (e.g. Habi CON-0011/0012 with empty maps) are corrected via
  SUPERSESSION when those features are next worked - never by editing frozen nodes.
- Stubs remain in the Decisions as historical provenance (not deleted).

---

## 14. Test plan

- Constraint: rule/attr insert with wrong prefix/status rejected; kind/maps allowed on rule/attr,
  rejected on feature/question; establishes/owns edges accepted, others still valid.
- Promotion/backfill: 1 Rule per implies_rules entry with establishes + >=1 references-concept; 1
  Attribute per field with owns; frozen Decisions untouched; idempotent re-run is a no-op.
- Traversal: `graph_feature_graph` returns Decisions (2-hop), Rules (3-hop), Attributes (via concept);
  no cross-feature bleed through shared Concepts; depth cap honored.
- Renderer: every section maps to a node query; empty sections say "none"; content hash stable for
  identical graph state; all rendered ids resolve to manifest UUIDs.
- Validation: each H1-H8 triggers on a crafted graph; W/D do not block; messages name the node.
- Snapshot: one immutable gate_a_feature_spec row; second approval sets supersedes; all manifest UUIDs
  are `accepted`; gate_decisions + feature_lifecycle updated; feature -> ready.
- Adapters: UX excludes eng-only rules; eng includes AC; post-gate adapters read the pinned manifest.

---

## 15. Implementation sequence (smallest clean increments)

1. **039** node/edge types + constraint relaxations + `graph_next_key` (ship; nothing breaks).
2. **042 backfill + BA promotion step** (stubs -> nodes; new runs stop creating stubs).
3. **040 transitive read + renderer** (Feature Spec previews from graph; repoint dashboard).
4. **026 apply + 041 Gate A** (validation RPC + snapshot writer + output_type + lifecycle wiring +
   dashboard "Approve Gate A" action).
5. **Adapter RPCs** (UX/Eng/QA) over the snapshot.

Each step is independently shippable and reversible; none paints us into a corner. Steps 1-3 deliver a
renderable Feature Spec; step 4 delivers the immutable gate; step 5 unlocks downstream stages.

---

## 16. Risks, tradeoffs, open questions

- `node_attributes` jsonb is load-bearing (statements, data types) and not Postgres-checkable - mitigate
  with a JSON-schema check in the BA write path + Gate validation.
- Transitive traversal fan-out via shared Concepts - mitigate with depth cap + attribute scoping to the
  feature's referenced concepts; revisit if graphs grow large.
- Shared-concept supersession ripples to all referencing features; approved snapshots are insulated
  (pinned UUIDs), live previews shift. Open question: per-feature attribute overrides vs canonical
  concept definition (lean canonical).
- AC promotion timing (Gate C/D) is a known future migration; derived-id convention de-risks it.
- Closed lifecycle CHECKs for rule/attribute - enumerate full status set now (done in 039).
- Open: does the PM layer ever become a reusable strategy plane? Defer until a second feature references
  shared metrics.

---

## 17. P2 acceptance criteria

- Rule + Attribute exist as node types; constraints relaxed; `graph_next_key` mints RULE-/ATR-.
- Backfill promotes all accepted-Decision stubs to nodes; new BA runs emit nodes, not stubs.
- `graph_feature_graph` returns the full transitive subgraph; renderer produces a complete Feature Spec
  with zero prose leakage and a verifiable content hash.
- `graph_gate_a_readiness` blocks on H1-H8; surfaces W/D; messages name nodes.
- Gate A writes one immutable `gate_a_feature_spec` row (manifest + markdown + provenance + pm_layer +
  hash), records gate_decisions, updates feature_lifecycle, flips the feature to ready.
- UX/Eng/QA adapters project from the pinned snapshot; no agent parses markdown.
- The polymorphic store's shape is unchanged except constraint relaxations + two edge types.
