# Codebase Context Agent

Analyzes an external target codebase **read-only** at a pinned commit and produces a structured
`codebase-context.json` artifact describing code reality - entities, actors, capabilities, domain
signals, glossary, coverage, and evidence - for downstream BA scoping. It renders a human-only
`codebase-context.md` mirror and owns the `cbc:*` identity registry.

**Description agent, not a scoping agent.** It describes WHAT IS. It never produces Concepts,
Decisions, Questions, Rules, PRDs, user stories, acceptance criteria, or product recommendations.
Those belong to the BA Scoping Agent.

---

## Owner

`reformai`

## Agent type

`worker` - leaf-level execution agent. Does not coordinate child agents.

## Registered instances

| Instance | Tenant | Source |
|---|---|---|
| `reformai.codebase-context-agent` | ReformAI | this directory |

## Definition vs. instance

This directory is the **capability definition** (`agent_definitions` table). It is tenant-neutral and
versioned. Operational deployment lives in the `agents` table as `reformai.codebase-context-agent`
with ReformAI-specific configuration (`config_overrides.product_key = 'reformai-product'`). See
`docs/agent-standards.md` for the definition/instance naming convention.

Note: the `cbc:*` registry it owns is **platform-level and tenant-neutral** (code reality is the same
fact for every company), even though the *instance* is ReformAI-scoped. See
[docs/identity-registry.md](docs/identity-registry.md).

---

## Mission and boundaries

The Codebase Context Agent (CCA) and the BA Scoping Agent are a **paired system** split by direction
of truth:

| | Codebase Context Agent | BA Scoping Agent |
|---|---|---|
| Direction | **IS-state** (description) | **SHOULD-BE** (scoping) |
| Owns | `cbc:*`, `cbc_identity_registry` | `CON-*`, `FEAT-*`, `QST-*`, `DEC-*`, `maps_to_codebase[]` |
| Writes | `platform.cbc_identity_registry`, `cbc_registry_events` | `product_graph.*` |
| Reads code? | Yes - **the only agent that reads source** | Never - consumes validated `codebase-context.json` |

Hard boundaries (enforced, not aspirational):

- The CCA **only reads** the target repo. It never writes to the target and never writes its own host
  source. Its only write surfaces are the ephemeral clone workspace and the oversight artifact +
  registry.
- The CCA **never emits `CON-*`** or any product Concept, Decision, Question, Rule, or recommendation.
- The CCA **owns `cbc:*`**: it is the sole minter and the sole mutator of `cbc_identity_registry`.
- The join between the two agents is **application-level only** (`maps_to_codebase[]`, owned by the
  BA), with no DB foreign key.

See [docs/ba-handoff.md](docs/ba-handoff.md).

---

## What it does

1. Resolves `target_key` to a repo URL + read-only credential via the target registry.
2. Resolves `ref` (branch/tag/sha) to a concrete `commit_sha` and **clones read-only into an ephemeral
   workspace**, asserting `HEAD == commit_sha`.
3. Extracts code-side **entities**, **actors**, **capabilities** with evidence (file:line at the SHA).
4. Runs the full **`domain_signals` sweep** (market-scoping, multi-tenancy, currency/locale,
   soft-delete) - always, regardless of `concepts_to_check`.
5. Builds the code-derived **glossary** (`term`, `aka[]`, `maps_to` cbc:*).
6. Existence-checks the `feature_intent` nouns + `concepts_to_check[]`, emitting `exists:false`
   negative findings and a `concept_resolution[]` block.
7. **Mints / resolves `cbc:*` identities** through the registry (frozen-on-mint, frozen-on-consumption).
8. Reports honest **coverage** (`scanned_paths`, `omitted`, `files_scanned/total`, `confidence`).
9. Writes the `codebase_context` artifact to `agent_outputs`, renders `codebase-context.md`, tears
   down the clone, and emits telemetry.

## What it does NOT do (v1)

- Does not produce `CON-*`, Decisions, Questions, Rules, Attributes, PRDs, user stories, acceptance
  criteria, or product recommendations.
- Does not decide whether two code-side identities are "the same" product Concept (e.g.
  Supplier vs ServiceProvider vs `vendor`) - it reports the unification as a `domain_signal` and lets
  the BA/human decide.
- Does not map fields to `Attribute` nodes. It emits `fields[]` with `semantic_hint` as code reality;
  the BA owns Attributes.
- Does not read or consume the product graph (`CON-*`). The glossary is produced from code, not
  consumed.
- Does not narrow `domain_signals` or `coverage` based on `concepts_to_check` (additive-only invariant).
- Does not silently auto-bind a divergent-name realization - it emits a `possible_realization`
  candidate for confirmation.
- Does not resolve the tenant/company by `LIMIT 1` - always by name or explicit ID.

---

## Identity model (v1)

The CCA owns `cbc:*` code-side identities through a **frozen-ID registry**
(`platform.cbc_identity_registry`, migration 025):

- `cbc:{entity|actor|capability}:{normalized_name}` - the name derives the ID **only at first mint**,
  then the ID is opaque and frozen for life.
- Renames update `current_name` + `aka[]` and emit a `rename` event; the ID never changes.
- Absent (`exists:false`) entities are minted `provisional` from the normalized requested noun and
  become authoritative on BA consumption.
- Normalization: `lowercase -> snake_case -> singularize -> strip non-alphanumerics`; collisions get a
  numeric disambiguator (`cbc:entity:vendor_2`).

Full rules: [docs/identity-registry.md](docs/identity-registry.md).

---

## Inputs

| Field | Type | Required | Description |
|---|---|---|---|
| `target_key` | string | Yes | Resolves to repo URL + read-only auth via the target registry |
| `ref` | string | Yes | Branch/tag/sha; resolved to a concrete `commit_sha` and pinned |
| `feature_intent` | string | Yes | Drives existence-check coverage + the human brief; never narrows the sweep |
| `concepts_to_check` | string[] \| object[] | No | Directed existence-check list (additive only) |

Full contract: [docs/input-contract.md](docs/input-contract.md).

## Outputs

A `codebase_context` artifact conforming to `docs/schemas/codebase-context.schema.json`, written to
`agent_outputs.content` with `output_type = 'codebase_context'`, plus a human-only `codebase-context.md`
render and any `cbc_identity_registry` mutations. Full contract:
[docs/output-contract.md](docs/output-contract.md).

---

## MCP dependencies

None.

## Tools used

- Git (read-only clone of the external target into an ephemeral workspace)
- Supabase REST + `public.cbc_*` RPCs (registry mint/rename/implement/merge/resolve)
- An LLM provider (Anthropic default) for `domain_signal` and `glossary` extraction
- Oversight SDK (`python-sdk/oversight.py`) for run lifecycle telemetry

## Setup

```bash
pip install anthropic>=0.40.0 python-dotenv>=1.0.0 requests>=2.31.0 jsonschema>=4.0.0
```

Required env (in `.env.local`):

```
OVERSIGHT_URL=https://agent-oversight.vercel.app
AGENT_OVERSIGHT_SECRET=<production oversight secret>
CODEBASE_CONTEXT_AGENT_ID=93b45e81-a1e5-47d8-98b1-0575de49a21b
NEXT_PUBLIC_SUPABASE_URL=<supabase url>
SUPABASE_SERVICE_ROLE_KEY=<service role key - verify length ~219 chars, not the anon key>
GITHUB_CODEBASE_AGENT_TOKEN=<read-only, single-repo-scoped token for the target repo>
ANTHROPIC_API_KEY=sk-ant-api03-...
```

## Running it

Runtime is not implemented yet (this is the documentation + registration package). The intended
invocation:

```bash
python agents/library/codebase-context-agent/agent.py \
  --target-key reformai-product \
  --ref main \
  --feature-intent "Add a catalogue of materials for suppliers and service providers" \
  --concepts-to-check Material Catalogue Supplier ServiceProvider Market
```

## Telemetry

Emits `run_started` / `run_completed` / `run_failed` to `/api/ingest` with a unique `run_id`.
Step events: see [docs/runtime-workflow.md](docs/runtime-workflow.md).

## Documentation set

- [docs/runtime-workflow.md](docs/runtime-workflow.md) - the resolve -> clone -> pin -> extract ->
  store run flow + telemetry
- [docs/input-contract.md](docs/input-contract.md)
- [docs/output-contract.md](docs/output-contract.md)
- [docs/identity-registry.md](docs/identity-registry.md) - cbc:* rules + RPC usage
- [docs/ba-handoff.md](docs/ba-handoff.md) - the boundary and the join
- [docs/materials-catalogue-example.md](docs/materials-catalogue-example.md)

## Schemas and storage

- Output schema: `docs/schemas/codebase-context.schema.json`
- Registry storage: `supabase/migrations/025_cbc_identity_registry.sql` (**authored, NOT yet applied**)

## Status

**Registered (DB), runtime pending.** Instance `reformai.codebase-context-agent` is registered with
`status = paused` and `metadata.runtime_implemented = false`. `agent.py` does not exist yet and
migration 025 is not applied. Not operationally active. See
[Remaining steps](docs/runtime-workflow.md#remaining-steps-before-activation).

## Future roadmap (deferred from v1)

- Selective field -> `Attribute` candidate mapping (keys/enums/FKs/intent-relevant only)
- Cross-SHA diffing (drift between two `codebase-context.json` artifacts)
- Multi-target support beyond `reformai-product`
- LRU clone cache keyed by immutable `commit_sha`
