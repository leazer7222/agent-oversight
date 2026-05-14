# Product Clarification Agent

> Converts fuzzy product goals into structured Clarification Briefs the Story Structuring Agent can act on without further clarification.

## Owner
`reformai`

## Team
`agile` — first agent in the Agile Team workflow (PCA → SSA → EPA → QA/RCA)

## What It Does

The Product Clarification Agent receives a raw product goal alongside pre-loaded workspace canonical documents (PRODUCT.md, DOMAIN.md, STORY-READY.md). It:

1. Checks context integrity (are all docs present? are any stale?)
2. Extracts the underlying user problem from the stated goal
3. Bounds scope explicitly on both sides (in and out)
4. Identifies missing information as open questions
5. Drafts measurable success criteria
6. References domain terms from DOMAIN.md
7. Produces a Clarification Brief conforming to `docs/schemas/clarification-brief.schema.json`

The Brief is reviewed and approved by the human. Unanswered open questions must be resolved before the Brief advances to the Story Structuring Agent.

## Key Design Decisions

- **Stateless pure function.** The PCA receives pre-loaded doc content from the orchestrator. It reads no files and calls no external tools.
- **Problem-not-solution framing.** The PCA always restates the goal as a user problem, never as a proposed solution.
- **Schema-first output.** Output is JSON conforming to `clarification-brief.schema.json`. Schema validation is enforced by the Team Orchestrator.
- **Context integrity is always rated.** Every Brief includes a Green / Yellow / Red rating with reasoning.

## Inputs

Provided by the Team Orchestrator — the PCA never reads files directly.

| Input | Type | Required |
|---|---|---|
| `product_md` | str | Yes — content of PRODUCT.md |
| `domain_md` | str | Yes — content of DOMAIN.md |
| `story_ready_md` | str | Yes — content of STORY-READY.md |
| `goal` | str | Yes — the human's raw goal |
| `context_notes` | str | No — supplementary framing |
| `target_user` | str | No — named user segment |
| `urgency` | str | No — priority signal |
| `context_bundle_id` | str | Yes — for Brief metadata |
| `context_bundle_version` | int | Yes — for Brief metadata |
| `workspace_id` | str | Yes — for Brief metadata |
| `agent_id` | str | Yes — for telemetry |
| `run_id` | str | Yes — for telemetry (provided by orchestrator) |

## Outputs

A dict matching `docs/schemas/clarification-brief.schema.json`, saved by the orchestrator as:
- `outputs/clarification-briefs/{date}-{run_id}.json` — machine-readable
- `outputs/clarification-briefs/{date}-{run_id}.md` — human-readable

## Quality Rubric

| Check | Pass | Fail |
|---|---|---|
| Restated goal accuracy | Captures intent without adding or losing scope | Adds implied scope or misses key nuance |
| Problem statement | States a user problem ("users cannot X") | States a solution ("build X" / "add Y") |
| Open questions | Non-obvious, each unlocks a decision, 1–5 total | Trivially answerable from input; vague; >5 |
| Success criteria | Each is measurable and observable | Uses "works correctly," "feels good," etc. |
| Scope | Both in-scope and out-of-scope populated | Either side missing |
| Domain terms | Match DOMAIN.md exactly | Contradict or extend DOMAIN.md |
| Context integrity | Accurately reflects what docs were found | Rates Green when docs are missing or stale |
| Story Structuring readiness | SSA could produce DoR stories from this Brief alone | Open questions unanswered; scope unclear |

## Setup

1. Install dependencies: `pip install anthropic openai python-dotenv jsonschema` (add `google-generativeai` for Gemini)
2. Copy `.env.example` to `.env.local` and fill in required vars
3. Ensure the Team Orchestrator (`agents/teams/agile/run.py`) is configured for your workspace
4. Run via the orchestrator: `python agents/teams/agile/run.py --goal "your goal here"`

## Environment Variables

```
OVERSIGHT_URL=https://agent-oversight.vercel.app
OVERSIGHT_SECRET=ChArles-Clint0n-Leazer-Jr.-1s-the-B3st
PCA_AGENT_ID=a1b2c3d4-e5f6-7890-abcd-ef1234567890
AGILE_ORCHESTRATOR_AGENT_ID=<orchestrator uuid>

# LLM provider — pick one
AGILE_LLM_PROVIDER=anthropic   # or openai or gemini
ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# OPENAI_MODEL=gpt-4o
# GEMINI_API_KEY=...
# GEMINI_MODEL=gemini-2.0-flash-exp
```

## Telemetry

The PCA emits these step events during a run:

| Step | When |
|---|---|
| `context_check` | After receiving docs — reports presence, staleness flags found, total chars |
| `goal_analysis` | After parsing the goal — reports identified user problem and gap count |
| `brief_generation` | After LLM call completes — reports token usage |
| `quality_self_check` | After self-evaluation — reports any fields revised |
| `schema_validation` | After schema check — pass/fail and any validation errors |

## Notes

- The PCA does not create or update Jira/Linear tickets. That is deferred to v2.
- The PCA does not read from Google Drive, Slack, GitHub, Figma, or any external system. Context is provided by the orchestrator from canonical docs.
- If `context_integrity.rating` is `red`, the Brief must not advance to Story Structuring without explicit human override.
