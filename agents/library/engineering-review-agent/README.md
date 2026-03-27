# Engineering Review Agent

> Staff-level engineering review agent that connects user feedback to code-level root causes and produces prioritized, evidence-based improvement recommendations.

## Owner
`reformai`

## What it does
Takes a GitHub repository (with an optional scoped path) and one or more user feedback documents, then produces a structured engineering review. It traces recurring user pain to likely implementation causes, ranks findings by impact-to-effort ratio, and outputs concrete, actionable recommendations — not generic code style notes.

The review covers:
1. Feedback themes — grouped recurring pain points
2. Code-level root causes — implementation diagnosis per theme
3. Prioritized recommendations — P0/P1/P2 with effort and confidence ratings
4. Quick wins vs structural improvements
5. Risks, assumptions, and open questions

## Tools & MCP Dependencies
| Tool/MCP | Purpose |
|---|---|
| GitHub REST API | Fetch code files from the target repository |
| Google Drive (service account) | Read user feedback documents |
| Gemini / OpenAI | LLM synthesis of the review |
| OversightClient | Emit run lifecycle events to the oversight API |

## Setup

1. Set environment variables:
   - `OVERSIGHT_URL` — oversight ingest endpoint
   - `OVERSIGHT_SECRET` — oversight API secret
   - `GITHUB_TOKEN` — personal access token with `repo` read scope
   - `GEMINI_API_KEY` or `OPENAI_API_KEY` — LLM provider key
   - `GOOGLE_SERVICE_ACCOUNT_KEY` — path to service account JSON (for GDrive feedback docs)
2. Run `register_engineering_review_agent.js` once to register in Supabase.

## Running it

```python
from agents.library.engineering_review_agent.agent import EngineeringReviewAgent

agent = EngineeringReviewAgent(agent_id="e6229606-78b9-4fd7-9424-6a62eb574255")
result = agent.run(
    repo="leazer7222/agent-oversight",    # GitHub owner/repo
    scope="src/app/",                     # Optional: limit to this path
    feedback_folder_id="<gdrive-folder-id>",  # GDrive folder with feedback docs
    # OR:
    feedback_text="User complaint 1...\nUser complaint 2..."  # Inline feedback
)
print(result["review"])
```

Or via CLI:
```bash
GITHUB_REPO=leazer7222/agent-oversight \
GITHUB_SCOPE=src/app/ \
FEEDBACK_FOLDER_ID=<folder-id> \
python agents/library/engineering-review-agent/agent.py
```

## Inputs
| Input | Source | Description |
|---|---|---|
| `repo` | arg / `GITHUB_REPO` env | GitHub `owner/repo` |
| `scope` | arg / `GITHUB_SCOPE` env | Subdirectory path to limit code review (optional) |
| `feedback_folder_id` | arg / `FEEDBACK_FOLDER_ID` env | GDrive folder ID containing feedback docs |
| `feedback_text` | arg | Inline feedback text (alternative to GDrive) |

## Outputs
```json
{
  "status": "success",
  "review": {
    "feedback_themes": [...],
    "root_causes": [...],
    "recommendations": [...],
    "quick_wins": [...],
    "structural_improvements": [...],
    "risks_and_open_questions": [...]
  },
  "files_reviewed": ["src/app/api/ingest/route.ts", "..."],
  "feedback_docs": ["User Feedback Q1.pdf", "..."]
}
```

## Notes
- Code is fetched via GitHub API — no local checkout required.
- Files in `node_modules/`, `.git/`, `dist/`, `build/`, `__pycache__/` are automatically excluded.
- Default max chars per file: 20,000 (configurable via `REVIEW_MAX_CHARS_PER_FILE`).
- Default max files: 60 (configurable via `REVIEW_MAX_FILES`).
- LLM provider defaults to Gemini; set `REVIEW_LLM_PROVIDER=openai` to switch.
