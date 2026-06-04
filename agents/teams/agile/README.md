# Agile Team Orchestrator

Lifecycle coordinator for the Agile Team (Agent Agile Force). Coordinates the
product-delivery lifecycle from idea to production. Phase 2 (current) runs the **clarifying**
stage: it drives the Product Clarification Agent (intake normalization) and threads the
handoff (`feature_intent` + `concepts_to_check` + `clarification_brief_artifact_id`) to the
downstream CCA/BA stages.

It makes **no LLM calls** itself. Per stage it: load -> run the worker agent -> validate the
artifact -> persist a pointer -> gate -> advance.

- agent_id: `b2c3d4e5-f6a7-8901-bcde-f12345678901`
- Owner: `reformai` | Type: `orchestrator`
- Design spec: [docs/agent-agile-force-lifecycle.md](../../../docs/agent-agile-force-lifecycle.md)
- Integration plan: [docs/agile-pca-integration-plan.md](../../../docs/agile-pca-integration-plan.md)

## Directory layout note

This package lives under `agents/teams/<team>/` (not `agents/library/` or
`agents/instances/`). `teams/` is the established home for team **orchestrators** - a stage
sequencer that coordinates library agents, distinct from a reusable leaf agent (library) or a
company deployment (instances). The worker agents it drives (PCA, CCA, BA) live in
`agents/library/`.

## Two execution paths (same artifact contracts)

| Path | File | Trigger | Use |
|---|---|---|---|
| CLI | `run.py` | terminal | operator-driven runs |
| Worker | `worker.py` | `public.agile_intake_jobs` queue | the dashboard's in-app trigger (Phase 1b) |

Both run `pca.run_intake` and produce the same `intake_assessment` / `clarification_brief`
artifacts. Both emit an **orchestrator run** (`run_started`/`run_completed`/`run_failed`) under
this agent_id and thread `parent_run_id` into the PCA child run, so every run - CLI or
dashboard-triggered - is a linked tree in the oversight ledger.

## Running it

```bash
# CLI: clarify a goal / paragraph / PRD / ticket directly
python agents/teams/agile/run.py --goal "Add a materials catalogue for suppliers"
python agents/teams/agile/run.py --intake "prd:docs/features/materials.md"

# In-app trigger: start the worker once per session; submit intake from /dashboard/agile
python agents/teams/agile/worker.py            # poll loop (Ctrl-C to stop)
python agents/teams/agile/worker.py --once     # process one queued job, then exit
```

The worker is the orchestrator's execution arm for the queue. To move from a local worker to
a hosted always-on worker later, run `worker.py` on a server/cron - no code change; the queue
+ artifact contracts are identical.

## Decision routing (clarifying stage)

The PCA Intake Assessment decides the next lifecycle state:

| Decision | Job status | Lifecycle next state |
|---|---|---|
| `proceed_direct` | `done` (brief written) | `context_scanning` (CCA) |
| `clarify` | `clarify` (draft + questions) | `clarification_blocked` -> answer -> Pass B |
| `block` | `blocked` | `clarification_blocked` |

## Storage

- Queue: `public.agile_intake_jobs` (migration 034) + `public.claim_intake_job()`.
- Artifacts (immutable): `agent_outputs` (`intake_assessment`, `clarification_brief`).
- Output types registered in migration 033.

## Telemetry

Emits `run_started` / `run_completed` / `run_failed` to `/api/ingest` with a unique `run_id`
per job, under `agent_id = b2c3d4e5-...`. The PCA child run links via `parent_run_id`.
