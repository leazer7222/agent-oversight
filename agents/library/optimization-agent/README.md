# optimization-agent

## What it does
Scans every agent in `agents/library/` and `agents/instances/` against the [Agent Standards](../../../docs/agent-standards.md), identifies structural gaps and code quality issues, then uses an LLM to synthesize a prioritized improvement report.

## What it checks
- **Structural compliance** — `agent.json`, `README.md`, `LESSONS.md` present
- **agent.json validity** — all required fields (`agent_id`, `name`, `description`, `owner`, `version`, `mcp_dependencies`)
- **Oversight integration** — `OversightClient` imported, `run_started`/`run_completed` emitted
- **Token reporting** — `run.report(tokens_in=..., tokens_out=..., cost_usd=...)` called after LLM calls
- **Hardcoded secrets/IDs** — placeholder UUIDs, hardcoded file paths, raw secrets in code
- **Bypassed steps** — commented-out logic (e.g. audit step skipped)

## Output
Returns a JSON report with:
- `summary` — one-line status
- `agents` — per-agent findings with `issues[]` and `severity` (critical / warning / info)
- `recommendations` — LLM-synthesized prioritized action list

## Tools / dependencies
- Google Gemini API (`google-genai`)
- `python-sdk/oversight.py`

## Owner
`reformai`

## Setup
```bash
export OVERSIGHT_URL=https://agent-oversight.vercel.app
export OVERSIGHT_SECRET=<secret>
export GEMINI_API_KEY=<key>
```

Run:
```bash
python agents/library/optimization-agent/agent.py
```
