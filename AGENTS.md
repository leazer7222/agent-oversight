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
    - Purpose: Deterministic Team Orchestrator for the Agile Team. Enforces staleness gate, assembles context bundle, calls specialist agents in sequence, validates schema, saves artifacts.
    - agent_id: `b2c3d4e5-f6a7-8901-bcde-f12345678901`
    - Status: Active | Owner: `reformai` | Type: `orchestrator`
- **product-clarification-agent** ([library](agents/library/product-clarification-agent/))
    - Purpose: Converts fuzzy product goals into structured Clarification Briefs conforming to `docs/schemas/clarification-brief.schema.json`.
    - agent_id: `a1b2c3d4-e5f6-7890-abcd-ef1234567890`
    - Status: Active | Owner: `reformai` | Type: `worker`
    - Run: `python agents/teams/agile/run.py --goal "your goal"`

### Contractor Pipeline
- **contractor-pipeline-orchestrator** (`ReformAI_Agents/Contractor_Orchestrator_Agent/run_contractor_pipeline.py`)
    - Purpose: Governed orchestrator for the ReformAI contractor discovery pipeline. Owns run lifecycle, stage sequencing (batch plan → research → extraction → catalog → sync), and telemetry. Phase 1 wraps existing scripts; Phase 2+ will own the full governed flow.
    - agent_id: `73de0fbc-3419-4f33-aac5-d79ebef25b59`
    - Status: Active | Owner: `reformai` | Type: `orchestrator` | Phase: 4 (in-repo extractor)
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


## Required at runtime

- [ ] Emits `run_started` to `/api/ingest` at the beginning of every run
- [ ] Emits `run_completed` to `/api/ingest` at the end of every run
- [ ] Each run has a unique `run_id` (UUID generated per invocation)

## Strongly recommended
- [ ] Reports `tokens_in`, `tokens_out`, `cost_usd` on `run_completed`
- [ ] Declares MCP dependencies in `agent.json`
- [ ] Includes a `LESSONS.md` for per-agent standing rules
