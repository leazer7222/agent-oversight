<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

---

# Agent Standards — Mandatory Checklist

Every agent in this system MUST satisfy all of the following before it is considered real.
Full specification: `/docs/agent-standards.md`
Template to copy from: `/agents/library/_template/`

## Required to exist
- [ ] Registered in Supabase `agents` table with a stable UUID `agent_id`
- [ ] `README.md` — what it does, what tools/MCPs it uses, who owns it
- [ ] `agent.json` — machine-readable identity manifest (see template)

## Registered Agents (Library)

### Agile Team
- **agile-team-orchestrator** ([teams/agile](agents/teams/agile/run.py))
    - Purpose: **Lifecycle coordinator for the full product-delivery process (idea -> production)**, not just a scoping pipeline. Owns the lifecycle FSM, sequences agent stages, enforces human review gates, validates each stage artifact, threads upstream artifacts downstream. Makes no LLM calls. Phase 1 (current) is a single-worker (PCA) runner; the full design is the lifecycle coordinator below.
    - agent_id: `b2c3d4e5-f6a7-8901-bcde-f12345678901`
    - Status: Active | Owner: `reformai` | Type: `orchestrator`
    - **Design spec:** [docs/agent-agile-force-lifecycle.md](docs/agent-agile-force-lifecycle.md) (Agent Agile Force lifecycle)
    - **Lifecycle spine:** `platform.feature_lifecycle` / `lifecycle_events` / `gate_decisions` (migration 026 - **authored, NOT applied**); 19-state FSM + 4 human gates enumerated for no-later-DDL extensibility.
    - **Target lifecycle:** Idea -> PCA -> [Persona Validation: optional] -> CCA -> BA -> Gate A -> [Sprint Planning] -> UX Design -> Gate B -> Engineering -> Gate C -> Code Review -> Gate D -> Release.
    - **Implementation phasing:** P1 (done) PCA · **P2 (v1 target)** PCA->CCA->BA + Gate A + FSM spine · P2.5 Persona Validation (optional) · P3 Sprint Planning · P4 UX Design · P5 Engineering · P6 Code Review · P7 Release.
- **product-clarification-agent** ([library](agents/library/product-clarification-agent/))
    - Purpose: Converts fuzzy product goals into structured Clarification Briefs conforming to `docs/schemas/clarification-brief.schema.json`. Lifecycle stage 1 (`clarifying`).
    - agent_id: `a1b2c3d4-e5f6-7890-abcd-ef1234567890`
    - Status: Active | Owner: `reformai` | Type: `worker`
    - Run: `python agents/teams/agile/run.py --goal "your goal"`
- **Planned lifecycle agents** (design only - see lifecycle spec): `reformai.persona-validation-agent` (P2.5, NEW) · `reformai.sprint-planning-team` (P3, NEW team/sub-orchestrator) · `reformai.ux-design-agent` (P4, NEW dedicated; distinct from the existing marketing `ui-design-agent`) · `reformai.engineering-agent` (P5, NEW) · `reformai.code-review-agent` (P6, exists/operational) · `reformai.release-coordinator` (P7, NEW thin/deterministic over `scripts/push.ps1`).

### Contractor Pipeline
- **contractor-pipeline-orchestrator** (`ReformAI_Agents/Contractor_Orchestrator_Agent/run_contractor_pipeline.py`)
    - Purpose: Governed orchestrator for the ReformAI contractor discovery pipeline. Owns run lifecycle, stage sequencing (batch plan → research → extraction → catalog → sync), and telemetry. Phase 1 wraps existing scripts; Phase 2+ will own the full governed flow.
    - agent_id: `73de0fbc-3419-4f33-aac5-d79ebef25b59`
    - Status: Active | Owner: `reformai` | Type: `orchestrator` | Phase: HubSpot sync live
    - Run: `python run_contractor_pipeline.py --market-id co-renovation --label scheduled`
    - Markets: `co-renovation` (active) · `mx-renovation` · `pt-renovation` · `es-renovation` (inactive, greenfield)

### Workspace Team
- **workspace-orchestrator** (Supabase only — no run script yet)
    - Purpose: Orchestrator for the YouTube workspace pipeline (discovery → transcript → extraction of workspace setup videos).
    - agent_id: `e5f6a7b8-c9d0-5678-ef01-234567890123`
    - Status: Active | Owner: `reformai` | Type: `orchestrator` | Phase: stub
    - Workers: `reformai.workspace-discovery-agent` · `reformai.workspace-transcript-agent` · `reformai.workspace-extraction-agent`

### Context & Marketing
- **context-agent** ([library](agents/library/context-agent/))
    - Purpose: Retrieves project context from Google Drive.
    - Status: Active | Owner: `reformai`
- **marketing-agent** ([library](agents/library/marketing-agent/))
    - Purpose: Strategic marketing executive; produces UI-ready blueprints.
    - Status: Active | Owner: `reformai`

### Product Intelligence
- **ba-scoping-agent** ([library](agents/library/ba-scoping-agent/))
    - Purpose: Converts a feature idea into a scope-ready brief by resolving Concepts against product knowledge and codebase reality, surfacing high-divergence forks as blocking Questions, and capturing human answers as durable Decisions. Scoping and decision-extraction agent (NOT a PRD generator in v1).
    - agent_id (definition): `1232ef02-e83e-437a-a4a3-50b61090cb86` | Instance: `reformai.ba-scoping-agent` (`0cc9bf15-49a5-4667-9985-77c31877490b`)
    - Status: **Active** - instance `status=active`, `metadata.runtime_implemented=true`; runtime `agent.py` (Pass A scope) implemented and smoke-tested against `reformai-product` @ `d768f37` | Owner: `reformai` | Type: `worker`
    - Paired with: Codebase Context Agent. BA owns `CON-*`/`FEAT-*`/`QST-*`/`DEC-*` and `maps_to_codebase[]`; never reads source code or mutates `cbc:*`. Loads IS-state via `public.get_latest_codebase_context('reformai-product')`.
    - Run: `python agents/library/ba-scoping-agent/agent.py --feature-intent "..." --product-key reformai-product --tenant ReformAI`
    - Schemas: input `docs/schemas/ba-scoping-input.schema.json` -> consumes `docs/schemas/codebase-context.schema.json` -> output `docs/schemas/product-graph.schema.json`
    - Storage: `product_graph.graph_nodes` / `graph_edges` - migrations 024 (+ 029 output_type, 030 readiness fix) **APPLIED** to `hdhovyrlnfojtkqbcegh`
- **codebase-context-agent** ([library](agents/library/codebase-context-agent/))
    - Purpose: Analyzes an external target codebase read-only at a pinned commit and produces a structured `codebase-context.json` artifact describing code reality (entities, actors, capabilities, domain signals, glossary, coverage, evidence) for downstream BA scoping. Describes WHAT IS; never scopes WHAT SHOULD BE. Owns the `cbc:*` identity registry.
    - agent_id (definition): `93b45e81-a1e5-47d8-98b1-0575de49a21b` | Instance: `reformai.codebase-context-agent` (`b118d9e1-c3ff-49c3-bb8b-f3c1bb985d2a`)
    - Status: **Active** - instance `status=active`, `metadata.runtime_implemented=true`; runtime `agent.py` (LLM-assisted, v1 local-path mode) implemented and smoke-tested against ReformAI-Inc/Reform-AI @ `d768f37` | Owner: `reformai` | Type: `worker`
    - Paired with: BA Scoping Agent. CCA owns `cbc:*` / `cbc_identity_registry` and is the only agent that reads source code; never emits `CON-*`/Decisions/Questions/Rules/PRDs/recommendations.
    - Run: `python agents/library/codebase-context-agent/agent.py --repo-path <local clone> --target-key reformai-product --feature-intent "..." --concepts-to-check Material Supplier ...`
    - Schemas: input `agents/library/codebase-context-agent/docs/input-contract.md` -> output `docs/schemas/codebase-context.schema.json`
    - Storage: `platform.cbc_identity_registry` / `cbc_registry_events` (migration 025) + `agent_outputs.output_type='codebase_context'` (migration 027) - **APPLIED** to `hdhovyrlnfojtkqbcegh`


## Required at runtime

- [ ] Emits `run_started` to `/api/ingest` at the beginning of every run
- [ ] Emits `run_completed` to `/api/ingest` at the end of every run
- [ ] Each run has a unique `run_id` (UUID generated per invocation)

## Strongly recommended
- [ ] Reports `tokens_in`, `tokens_out`, `cost_usd` on `run_completed`
- [ ] Declares MCP dependencies in `agent.json`
- [ ] Includes a `LESSONS.md` for per-agent standing rules
