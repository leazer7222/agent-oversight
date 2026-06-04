# Agile Team Orchestrator - Lessons

Standing rules for this package. Read before editing run.py / worker.py.

- **The orchestrator makes no LLM calls.** All model work belongs to the worker agents
  (PCA/CCA/BA). The orchestrator only sequences, validates, gates, and threads artifacts.

- **Every run emits orchestrator telemetry.** Both run.py and worker.py emit
  `run_started` / `run_completed` (or `run_failed`) under `AGILE_ORCHESTRATOR_AGENT_ID`
  (`b2c3d4e5-...`), and pass `parent_run_id` into `pca.run_intake`. Never call a worker agent
  without an enclosing orchestrator run - that creates an orphan child run in the ledger.

- **The worker is the orchestrator's execution arm, not a separate agent.** It runs under the
  orchestrator identity. Do not register it as its own agent; do not give it a separate
  agent_id. Local vs hosted is only *where* `worker.py` runs - same code, same contracts.

- **Supabase is the bus.** The dashboard enqueues `public.agile_intake_jobs`; the worker
  claims via `claim_intake_job()` (SKIP LOCKED) and writes result pointers back. The queue
  holds STATE + pointers only - artifact bodies stay in `agent_outputs`.

- **Artifact contracts are trigger-agnostic.** CLI and worker paths must produce identical
  `intake_assessment` / `clarification_brief` artifacts. If you change one path's output, change
  both (or, better, change only `pca.run_intake` which both call).

- **Reuse `pca.run_intake`, do not fork it.** run.py and worker.py both import the PCA module
  and call `run_intake`. Keep the pipeline single-sourced there.
