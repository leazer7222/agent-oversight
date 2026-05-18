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
