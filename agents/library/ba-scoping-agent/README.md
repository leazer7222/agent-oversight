# BA Scoping Agent

Converts a feature idea into a scope-ready brief by resolving Concepts against existing product
knowledge and codebase reality, surfacing high-divergence forks as blocking Questions, and capturing
human answers as durable Decisions. Produces a `product_graph_scope` artifact and renders a Feature
Scope Brief.

**Scoping and decision-extraction agent in v1 - NOT a PRD generator.** It may decline to produce a
brief when ambiguity is too high. The refusal is the product.

---

## Owner

`reformai`

## Agent type

`worker` - leaf-level execution agent. Does not coordinate child agents.

## Registered instances

| Instance | Tenant | Source |
|---|---|---|
| `reformai.ba-scoping-agent` | ReformAI | this directory |

## Definition vs. instance

This directory is the **capability definition** (`agent_definitions` table). It is tenant-neutral and
versioned. Operational deployment lives in the `agents` table as `reformai.ba-scoping-agent` with
ReformAI-specific jurisdiction and `config_overrides`. See `docs/agent-standards.md` for the
definition/instance naming convention.

---

## Mission and boundaries

The BA Scoping Agent and the Codebase Context Agent are a **paired system** split by direction of truth:

| | BA Scoping Agent | Codebase Context Agent |
|---|---|---|
| Direction | **SHOULD-BE** (scoping) | **IS-state** (description) |
| Owns | `CON-*`, `FEAT-*`, `QST-*`, `DEC-*`, `maps_to_codebase[]` | `cbc:*`, `cbc_identity_registry` |
| Writes | `product_graph.*` | `platform.cbc_identity_registry`, `cbc_registry_events` |
| Reads code? | **Never** - consumes validated `codebase-context.json` | Yes - the only agent that reads source |

Hard boundaries (enforced, not aspirational):

- The BA Agent **never reads source code directly.** It consumes a validated `codebase-context.json`.
- The BA Agent **never mints or mutates `cbc:*` identities.** It reads them via `public.cbc_resolve`
  and stores them in `concept.maps_to_codebase[]`.
- The Codebase Context Agent **never emits `CON-*`** or any product Concept/Decision/Rule.
- The join between the two is **application-level only** (`maps_to_codebase[]`), with no DB FK.

See [docs/codebase-context-handoff.md](docs/codebase-context-handoff.md).

---

## What it does

1. Validates the feature intent + tenant context + `codebase-context.json` (against
   `docs/schemas/codebase-context.schema.json`).
2. Resolves the tenant/company and sets `app.current_tenant_id`.
3. Creates or upserts the `FEAT-*` node (process plane).
4. Resolves Concepts: matches nouns against existing `CON-*` (canonical name + aliases) and the
   codebase `concept_resolution[]`; proposes new Concepts; records `maps_to_codebase[]`.
5. Detects assumptions, ranks by divergence, and emits **blocking + high-divergence** ones as `QST-*`.
6. Captures human answers as `DEC-*` Decisions (with `implies_rules[]` / `implies_attributes[]` stubs).
7. Adds graph edges (`references` / `resolves` / `supersedes` / `derived_from`).
8. Runs `public.graph_feature_readiness`.
9. Renders the Feature Scope Brief **only when readiness passes** (else emits the open Questions).
10. Writes the `product_graph_scope` artifact to `agent_outputs` and emits telemetry.

## What it does NOT do (v1)

- Does not generate PRDs, user stories, or acceptance criteria (Phase 2 projections).
- Does not create `Rule` or `Attribute` nodes (deferred; pre-stubbed inside Decisions).
- Does not persist `Assumption` nodes (collapsed into Questions + feature notes).
- Does not read source code or any repository (consumes `codebase-context.json` only).
- Does not mint, rename, merge, or otherwise mutate `cbc:*` identities.
- Does not auto-ratify - Concepts and Decisions are `proposed` until a human accepts.
- Does not run the contradiction-detection gate (gate 4 is `deferred_v1`).
- Does not resolve the tenant/company by `LIMIT 1` - always by name or explicit ID.

---

## Graph model (v1)

**Process plane:** `Feature` (FEAT-), `Question` (QST-)
**Knowledge plane:** `Concept` (CON-), `Decision` (DEC-)

Deferred: `Rule`, `Attribute`, `Assumption`. Decisions preserve `implies_rules[]` and
`implies_attributes[]` so Phase 2 promotion is a migration, not a rescoping.

Epistemic status (`fact | claim | assumption`) and scope readiness are **derived, never stored**
(`public.graph_node_epistemic_status`, `public.graph_feature_readiness`). See
[docs/graph-operations.md](docs/graph-operations.md).

---

## Inputs

| Field | Type | Required | Description |
|---|---|---|---|
| `feature_intent` | string | Yes | The raw feature idea |
| `product_key` | string | Yes | Product/repo scope, e.g. `reformai-product` |
| `tenant` | string | Yes | Company **name or explicit UUID** (never `LIMIT 1`) |
| `codebase_context` | object | Yes | Validated `codebase-context.json` instance |
| `concepts_to_check` | string[] | No | Directed existence-check list (additive only) |
| `human_answers` | object[] | No | Provided during the ratification pass |

Full contract: [docs/input-contract.md](docs/input-contract.md).

## Outputs

A `product_graph_scope` artifact conforming to `docs/schemas/product-graph.schema.json`, written to
`agent_outputs.content` with `output_type = 'product_graph_scope'`, plus the graph mutations applied
via RPC and a rendered `brief_markdown`. Full contract: [docs/output-contract.md](docs/output-contract.md).

---

## MCP dependencies

None.

## Tools used

- Supabase REST + `public.graph_*` / `public.cbc_resolve` RPCs (graph read/write)
- An LLM provider (Anthropic default) for concept resolution, divergence ranking, brief rendering
- Oversight SDK (`python-sdk/oversight.py`) for run lifecycle telemetry

## Setup

```bash
pip install anthropic>=0.40.0 python-dotenv>=1.0.0 requests>=2.31.0 jsonschema>=4.0.0
```

Required env (in `.env.local`):

```
OVERSIGHT_URL=https://agent-oversight.vercel.app
AGENT_OVERSIGHT_SECRET=<production oversight secret>
BA_SCOPING_AGENT_ID=1232ef02-e83e-437a-a4a3-50b61090cb86
NEXT_PUBLIC_SUPABASE_URL=<supabase url>
SUPABASE_SERVICE_ROLE_KEY=<service role key - verify length ~219 chars, not the anon key>
ANTHROPIC_API_KEY=sk-ant-api03-...
```

## Running it

**Status: operational.** Runtime implemented (`agent.py`, Pass A scope) and smoke-tested against
`reformai-product`. The agent loads IS-state itself via `public.get_latest_codebase_context` - you do
not pass a context file.

```bash
python agents/library/ba-scoping-agent/agent.py \
  --feature-intent "Add a catalogue of materials for suppliers and service providers" \
  --product-key reformai-product \
  --tenant ReformAI
```

Pass A proposes Concepts + Questions and computes readiness; if blocking questions are open it
withholds the brief. **Pass B (answer questions -> Decisions, ratify, render brief) is done through
the Scoping dashboard**, not the CLI:

- `/dashboard/scoping` - feature list + ratification backlog
- `/dashboard/scoping/[feature]` - answer questions, accept/reject Concepts/Decisions, upstream
  context (CCA populated; PCA when linked), and the live brief once scope-ready

Dashboard API: `src/app/api/scoping/*`; UI: `src/app/dashboard/scoping/*` + `ScopingReview.tsx`.

## Telemetry

Emits `run_started` / `run_completed` / `run_failed` to `/api/ingest` with a unique `run_id`.
Step events: see [docs/runtime-workflow.md](docs/runtime-workflow.md).

## Documentation set

- [docs/runtime-workflow.md](docs/runtime-workflow.md) - the 13-step run flow + telemetry
- [docs/input-contract.md](docs/input-contract.md)
- [docs/output-contract.md](docs/output-contract.md)
- [docs/graph-operations.md](docs/graph-operations.md) - RPC usage + tenant context
- [docs/ratification-workflow.md](docs/ratification-workflow.md)
- [docs/codebase-context-handoff.md](docs/codebase-context-handoff.md)
- [docs/materials-catalogue-example.md](docs/materials-catalogue-example.md)

## Future roadmap (deferred from v1)

- Phase 2: promote `implies_rules[]` / `implies_attributes[]` to `Rule` / `Attribute` nodes
- Phase 2: PRD, user story, and acceptance-criteria projections
- Phase 3: drift detection (join `maps_to_codebase[]` against a fresh `codebase-context.json`)
- Contradiction-detection readiness gate (gate 4)
- `Assumption` as a first-class node (audit trail of agent reasoning)
