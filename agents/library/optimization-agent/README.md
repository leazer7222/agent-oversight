# Optimization Agent

**Owner:** reformai
**Status:** Active
**Agent ID:** `1ba970fb-caba-4c4d-9e91-0f07135c1a70`
**Model:** gemini-2.5-flash (fallback: gpt-4o-mini)

---

## What it does

The Optimization Agent is the system's self-improvement loop. It scans the entire agent-oversight repo against the standards defined in `docs/repo-standards.md` and produces a prioritized action plan.

**Problem it solves:** As more agents are built across multiple projects, the repo drifts — missing files, unregistered agents, scattered scripts, hardcoded paths, and gaps between disk and Supabase. This agent catches all of that automatically.

**Output:** A JSON findings file + a Markdown improvement report, both saved to `agents/instances/reformai/outputs/`.

---

## Checks Performed

| Check | What It Validates |
|---|---|
| `missing_files` | Every library agent has `agent.json`, `agent.py`, `README.md`, `LESSONS.md` |
| `agent_json_schema` | `agent.json` has all required fields, valid UUID, semver version |
| `agents_md_sync` | `AGENTS.md` lists every agent that exists on disk |
| `runtime_contract` | `agent.py` imports and uses `OversightClient` |
| `hardcoded_paths` | No absolute paths in agent code, scripts, or instance files |
| `root_clutter` | No scripts or output dirs floating at repo root |
| `output_location` | Outputs go to `agents/instances/<company>/outputs/` only |
| `supabase_sync` | Every disk agent has a matching Supabase registration |

---

## Tools & Dependencies

| Tool | Purpose |
|---|---|
| `python-sdk/oversight.py` | Emits run lifecycle events |
| Gemini 2.5 Flash | LLM synthesis of findings into a report |
| OpenAI gpt-4o-mini | Fallback if Gemini is unavailable |
| Supabase REST API | Reads `agents` table for registration sync check |

---

## Setup

Requires these environment variables (loaded from `.env.local`):

```
OVERSIGHT_URL=https://agent-oversight.vercel.app/api/ingest
OVERSIGHT_SECRET=<secret>
NEXT_PUBLIC_SUPABASE_URL=https://hdhovyrlnfojtkqbcegh.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<key>
GEMINI_API_KEY=<key>          # primary LLM
OPENAI_API_KEY=<key>          # fallback LLM
```

---

## Running

```bash
python agents/library/optimization-agent/agent.py
```

Run from the repo root. The agent resolves all paths relative to its own location.

---

## Inputs

| Input | Source | Description |
|---|---|---|
| `repo_root` | auto-detected | Resolved from `__file__` — no config needed |
| Supabase credentials | env vars | Used for registration sync check |
| LLM API key | env vars | Used for report synthesis |

---

## Outputs

| File | Location | Description |
|---|---|---|
| `optimization_output_<run_id>.json` | `agents/instances/reformai/outputs/` | Raw findings + stats as JSON |
| `optimization_report_<run_id>.md` | `agents/instances/reformai/outputs/` | LLM-synthesized prioritized report |

---

## Standards Reference

This agent enforces: [`docs/repo-standards.md`](../../../docs/repo-standards.md)

Every other agent project should be measured against the same standard.
