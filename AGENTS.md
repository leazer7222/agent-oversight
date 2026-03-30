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
- **context-agent** ([library](file:///c:/Users/cjlea/AgentProjects/agent-oversight/agents/library/context-agent/))
    - Purpose: Retrieves project context from Google Drive.
    - Status: Active
    - Owner: `reformai`
- **marketing-agent** ([library](file:///c:/Users/cjlea/AgentProjects/agent-oversight/agents/library/marketing-agent/))
    - Purpose: Strategic marketing executive; produces UI-ready blueprints.
    - Status: Active
    - Owner: `reformai`
- **audit-agent** ([library](file:///c:/Users/cjlea/AgentProjects/agent-oversight/agents/library/audit-agent/))
    - Purpose: Quality gate; evaluates context relevance against a goal via LLM scoring.
    - Status: Active (bypassed in orchestrator pending re-enable)
    - Owner: `reformai`
- **optimization-agent** ([library](file:///c:/Users/cjlea/AgentProjects/agent-oversight/agents/library/optimization-agent/))
    - Purpose: Scans agent library for standards compliance, code issues, and gaps; synthesizes improvement report.
    - Status: Active
    - Owner: `reformai`


## Required at runtime

- [ ] Emits `run_started` to `/api/ingest` at the beginning of every run
- [ ] Emits `run_completed` to `/api/ingest` at the end of every run
- [ ] Each run has a unique `run_id` (UUID generated per invocation)

## Strongly recommended
- [ ] Reports `tokens_in`, `tokens_out`, `cost_usd` on `run_completed`
- [ ] Declares MCP dependencies in `agent.json`
- [ ] Includes a `LESSONS.md` for per-agent standing rules
