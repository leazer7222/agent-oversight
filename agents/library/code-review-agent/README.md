# Code Review Agent

Performs structured pre-push code review against documented architecture principles, governance
standards, and operational conventions. Produces an immutable `code_review` findings artifact
stored in `agent_outputs`.

**Advisory in v1** — recommendations guide human decisions; they are not automated gates.

---

## Owner

`reformai`

## Agent type

`worker` — leaf-level execution agent. Does not coordinate child agents.

## Registered instances

| Instance | Tenant | Parent | Source |
|---|---|---|---|
| `reformai.code-review-agent` | ReformAI | `claude-reformai` | this directory |

## Definition vs. instance

This directory is the **capability definition** (`agent_definitions` table). It is tenant-neutral
and versioned. Operational deployment lives in the `agents` table as
`reformai.code-review-agent` with ReformAI-specific jurisdiction and `config_overrides`.

See `docs/agent-standards.md` for the definition/instance naming convention.

---

## What it does

1. Receives a diff, commit SHA, and optional standards references as input.
2. Reviews the diff against:
   - `docs/PLATFORM_ARCHITECTURE.md` — architectural principles (P1–P10)
   - `docs/repo-standards.md` — repository engineering standards
   - `docs/agent-standards.md` — agent implementation contract
3. Produces a structured findings artifact with:
   - Per-finding: category, severity, confidence, blocking flag, explanation, remediation,
     affected files, line references, principle citations
   - Aggregate: severity counts, category counts, overall recommendation, governance flags
4. Writes the artifact to `agent_outputs` with `output_type = 'code_review'`.
5. Emits `run_started` and `run_completed` telemetry to `/api/ingest`.

## What it does NOT do

- Does not gate pushes automatically (advisory only in v1).
- Does not produce automated code fixes.
- Does not include reasoning traces or chain-of-thought in the artifact.
- Does not include author attribution.
- Does not read from Agent Oversight's governance tables to inform its findings (P5).
- Does not write to `agent_qa_results` — that table evaluates agent performance, not code artifacts.

---

## Findings taxonomy

### Severity

| Level | Meaning |
|---|---|
| `critical` | Operational risk, hard architectural violation, or security concern |
| `warning` | Pattern drift or governance debt; technically deployable but accumulates over time |
| `info` | Observational; no action required |

### Confidence

| Level | Meaning |
|---|---|
| `high` | Explicit pattern match against a documented standard |
| `medium` | Likely concern; human judgment warranted |
| `low` | Possible concern; may be a false positive |

### Categories

`architecture` · `observability` · `governance` · `schema` · `security` ·
`type_safety` · `operational_semantics` · `naming` · `documentation`

### Recommendations

| Value | Meaning |
|---|---|
| `approve` | No blocking findings |
| `approve_with_warnings` | Warning-level findings; acknowledge before pushing |
| `review_required` | Human judgment needed before decision |
| `block` | Clear architectural violation or safety risk — strong recommendation not to merge |

---

## Inputs

| Field | Type | Required | Description |
|---|---|---|---|
| `diff` | string | Yes | Unified diff of changes |
| `commit_sha` | string | Yes | Immutable provenance reference |
| `base_sha` | string | No | Base commit for the diff |
| `branch` | string | No | Branch being reviewed |
| `pr_number` | int\|null | No | PR number if available |
| `changed_files` | string[] | No | File paths that changed |
| `standards_refs` | string[] | No | Standards docs to apply |
| `review_mode` | enum | No | `pre-push` (default), `pr`, `commit`, `branch` |

## Outputs

Written to `agent_outputs.content` with `output_type = 'code_review'`.

Full output schema is defined in `agent_definitions.output_schema` for `code-review-agent`.
See `supabase/migrations/011_code_review_agent.sql` for the canonical schema.

Key top-level fields:

```json
{
  "schema_version": "1.0",
  "review_id": "<uuid>",
  "subject": { "type": "diff", "commit_sha": "...", ... },
  "context_applied": { "standards_refs": [...], "tenant": "reformai", ... },
  "findings": [ { "finding_id": "<uuid>", "severity": "critical", ... } ],
  "severity_counts": { "critical": 0, "warning": 0, "info": 0 },
  "category_counts": { ... },
  "recommendation": "approve | approve_with_warnings | review_required | block",
  "governance_flags": [],
  "summary": "..."
}
```

---

## MCP dependencies

None.

## Tools used

- `git diff` / `git show` for obtaining the diff
- Supabase REST API for writing `agent_outputs` and emitting telemetry

---

## Setup

Install dependencies (from the project root, or into your active venv):

```bash
pip install anthropic>=0.40.0 python-dotenv>=1.0.0 requests>=2.31.0
```

Add `ANTHROPIC_API_KEY` to `.env.local` in the project root (it is not included by default):

```
ANTHROPIC_API_KEY=sk-ant-api03-...
```

The agent also reads `NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and
`AGENT_OVERSIGHT_SECRET` from `.env.local`, which are already present for other agents.

## Running it

```bash
# From the project root — review the last commit
python agents/library/code-review-agent/agent.py \
  --commit-sha HEAD \
  --base-sha HEAD~1 \
  --branch <your-branch>

# Review a feature branch against main
python agents/library/code-review-agent/agent.py \
  --commit-sha HEAD \
  --base-sha origin/main \
  --branch feature/my-feature

# Use a cheaper/faster model (default is claude-opus-4-5)
CODE_REVIEW_MODEL=claude-sonnet-4-5 python agents/library/code-review-agent/agent.py \
  --commit-sha HEAD --base-sha HEAD~1 --branch main
```

Exit code `1` means recommendation is `block`. Use this in a git pre-push hook:

```bash
#!/bin/sh
# .git/hooks/pre-push
python agents/library/code-review-agent/agent.py \
  --commit-sha HEAD \
  --base-sha origin/main \
  --branch "$(git rev-parse --abbrev-ref HEAD)"
```

---

## Future roadmap (deferred from v1)

- Lifecycle state table (`code_review_finding_states`) for human workflow tracking
- CI integration: machine-readable findings consumed by GitHub Actions
- Trust accumulation: false positive rate, recommendation override rate, CI agreement rate
- Test generation agent as a sibling (`test-generation-agent`)
- Automated gating once trust is established through run history
