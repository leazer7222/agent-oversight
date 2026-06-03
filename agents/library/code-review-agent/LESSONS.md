# Lessons Learned — code-review-agent

Per-agent standing rules. Read at the start of every session involving this agent.

---

## v1 Scope Discipline

- This agent is **advisory only** in v1. It produces findings; it does not gate pushes.
- Do not add lifecycle state fields inside the output artifact — the artifact is immutable.
- `recommendation` must always be one of `approve | approve_with_warnings | review_required | block`.
  Never use the word `decision` or `verdict` — the agent advises, it does not decide.

## Output Contract

- Every run that produces findings MUST write an `agent_outputs` row with `output_type = 'code_review'`.
- The `finding_id` on each finding must be a fresh UUID — it is the stable handle for future
  lifecycle state tracking once that table is built.
- `blocking: true` on a finding means the agent recommends a gate. It does not gate anything in v1.

## Operational Neutrality

- Findings must cite `principles` (e.g. `["P5"]`) or `standards_refs` to anchor them to
  documented standards. A finding that cites no source cannot be contested. Unciteable findings
  are likely opinions, not findings — do not emit them.
- Do not include reasoning traces, chain-of-thought, or model deliberation in the artifact.
- Do not include automated code fixes. The agent finds and explains; the author fixes.
- Do not include author attribution. The finding is about the artifact, not its author.

## Differentiation from engineering-review-agent

- `engineering-review-agent`: strategic/design review, general quality and user feedback analysis.
- `code-review-agent`: structured pre-push safety check; specific output schema with severity
  taxonomy, confidence levels, principle references. output_type = `code_review`.
  These are distinct agents with distinct operational records in the ledger.

---

- [2026-06-03] | One uncited finding aborted the whole review (crashed the push gate) | `validate_artifact` treated an uncited/malformed finding as a hard error, so `write_code_review` raised and the run died - blocking every push, not just the bad finding. Fix: `sanitize_findings()` in output.py drops uncited/malformed findings (logged + recorded in `governance_flags`, no silent drops) inside `build_artifact` before validation. `validate_artifact` stays strict as the contract checker, but it now only ever sees emittable findings. A single bad finding must never abort the review.
- [2026-06-03] | The reviewer crashed on the empty-Bearer header inside Claude Code | Scrub empty `ANTHROPIC_AUTH_TOKEN`/`ANTHROPIC_CUSTOM_HEADERS` after load_dotenv and pass `api_key=` explicitly to `anthropic.Anthropic()` (same guard the BA/CCA agents use).
- [2026-06-03] | A runaway diff cost $5.58 on opus (350k tokens) and still failed | The reviewer had no cost awareness: chars/4 undercounted input ~2.3x, opus is default, and a failed run still bills. Fix (Phase 0): `preflight_cost_gate()` counts tokens EXACTLY via `client.messages.count_tokens` before the call and applies zones - auto-downgrade opus->sonnet above CODE_REVIEW_DOWNGRADE_TOKENS (60k), refuse (exit 1) above CODE_REVIEW_MAX_TOKENS (500k) or CODE_REVIEW_COST_CEILING_USD ($3). Runs before oversight.run() so a refusal wastes no run. `_build_review_kwargs` is shared by count_tokens and create so they can't drift. Full plan: docs/cost-guardrail-plan.md.
- [2026-06-03] | Scope commits; never git add -A | The bloated diff that caused the $5.58 run came from an over-broad add sweeping in experimental seller-test/seller-v7 pages. Stage only intended files.
