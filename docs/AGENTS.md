<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

---

# Agent Standards — Mandatory Checklist

Every agent in this system MUST satisfy all of the following before it is considered real.
Full specification: `/docs/agent-standards.md`
Repo organization standard: `/docs/repo-standards.md`
Template to copy from: `/agents/library/_template/`

## Required to exist
- [ ] Registered in Supabase `agents` table with a stable UUID `agent_id`
- [ ] `agent.json` — machine-readable identity manifest (see template)
- [ ] `agent.py` — core agent logic using OversightClient
- [ ] `README.md` — what it does, what tools/MCPs it uses, who owns it
- [ ] `LESSONS.md` — per-agent standing rules

## Registered Agents (Library)
- **context-agent** ([library](agents/library/context-agent/))
    - Purpose: Retrieves project context from Google Drive.
    - Status: Active
    - Owner: `reformai`
- **marketing-agent** ([library](agents/library/marketing-agent/))
    - Purpose: Strategic marketing executive; produces UI-ready blueprints.
    - Status: Active
    - Owner: `reformai`
- **ui-design-agent** ([library](agents/library/ui-design-agent/))
    - Purpose: High-fidelity UI/UX and Frontend Agent; builds landing pages.
    - Status: Active
    - Owner: `reformai`
- **audit-agent** ([library](agents/library/audit-agent/))
    - Purpose: Quality assurance validator; scores context relevance (1–10) and passes/fails it for downstream agents.
    - Status: Active
    - Owner: `reformai`
- **optimization-agent** ([library](agents/library/optimization-agent/))
    - Purpose: Scans the repo for standards compliance and organizational gaps; produces a prioritized improvement report via LLM.
    - Status: Active
    - Owner: `reformai`


## Required at runtime

- [ ] Emits `run_started` to `/api/ingest` at the beginning of every run
- [ ] Emits `run_completed` to `/api/ingest` at the end of every run
- [ ] Each run has a unique `run_id` (UUID generated per invocation)

## Strongly recommended
- [ ] Reports `tokens_in`, `tokens_out`, `cost_usd` on `run_completed`
- [ ] Declares MCP dependencies in `agent.json`
- [ ] Includes `prompt.md` alongside `agent.py` if the agent uses an LLM system prompt

## Enforcement
Run `python agents/library/optimization-agent/agent.py` to scan the entire repo for violations of the above standards. Output is saved to `agents/instances/reformai/outputs/`.
