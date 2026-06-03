# Agent Cost Guardrail - Plan

Origin: a single code-review run cost **$5.58** (350,422 input tokens on claude-opus-4-5) and still
failed. Root causes: an over-broad `git add -A` produced a huge diff; the `chars/4` token estimate
undercounted ~2.3x; opus is the default model; the Cost Risk Engine is observe-only and its pre-run
estimate is blind to prompt size (`context_size_unknown`); a failed run still bills the LLM call.

The cost gate must live in the agent's **pre-flight** (the only place that can stop before spending),
with thresholds ideally owned by the Cost Risk Engine (one source of truth).

## Phase 0 - Agent pre-flight cost gate (DONE)

Implemented in `agents/library/code-review-agent/agent.py`:
- **Exact token count** via `client.messages.count_tokens(...)` before the call (replaces `chars/4`).
- **Zones** (env-tunable):
  - `> CODE_REVIEW_DOWNGRADE_TOKENS` (default 60k) and model is opus -> auto-route to
    `CODE_REVIEW_DOWNGRADE_MODEL` (default `claude-sonnet-4-5`, ~5x cheaper).
  - `> CODE_REVIEW_MAX_TOKENS` (default 500k) OR est cost `> CODE_REVIEW_COST_CEILING_USD`
    (default $3.00) -> **refuse** (exit 1) unless `CODE_REVIEW_ALLOW_LARGE=1`.
- Runs **before** `oversight.run()` so a refusal creates no wasted run record.
- Single request builder (`_build_review_kwargs`) shared by `count_tokens` and `create` (no drift).
- The exact count is also passed as `tokens_in_hint` -> the Cost Risk Engine estimate for this agent
  is no longer blind (a Phase 1 benefit, for free).

Effect on the original incident: 350k tokens would downgrade to sonnet (~$1.10) and complete, instead
of $5.58 on opus and failing.

Also fixed (separate but related): the reviewer no longer aborts the whole run on a single uncited or
malformed finding (`sanitize_findings` in `output.py`), and scrubs the empty `ANTHROPIC_AUTH_TOKEN`.

## Phase 1 - Shared pre-flight + accurate hints (PLANNED)

- Extract count -> estimate -> zone-check into a reusable helper in `python-sdk/oversight.py`
  (e.g. `preflight_cost(client, request) -> {tokens, est_cost, zone}`).
- Have BA, CCA, and code-review all call it and emit the **exact** `tokens_in_hint` at `run_started`.
  This fixes the `context_size_unknown` estimation failure mode for these agents platform-wide.

## Phase 2 - Centralize zones in the Cost Risk Engine (PLANNED)

- Add `public.cost_preflight(task_type_code, tokens_in, model)` (SECURITY DEFINER) returning
  `{zone, ceiling_usd, recommended_model, allow}` from engine config (per task type / budget period).
- Agents consult it instead of local env thresholds -> one source of truth, centrally tunable, and the
  decision is recorded alongside the estimate artifact. This is the real "estimation-step gate".

## Phase 3 - Budget enforcement (PLANNED; the originally-deferred gate)

- Make `budget_reservations` actually block when a period budget is exhausted (RFC Phase 3 gate item).
  Zones now include period-level spend, not just per-run size.

## Operational rules

- Never `git add -A` for commits - scope to intended files; a bloated diff is the most common cost spike.
- A failed run still bills for the LLM call - the pre-flight gate is the protection, not post-hoc review.
