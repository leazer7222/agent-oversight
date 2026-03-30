# audit-agent

## What it does
Quality gate for the agent pipeline. Given a `goal` and a block of `context`, asks Gemini to evaluate whether the context is substantive enough to fulfill the goal. Returns `passed: bool`, `score: 1-10`, and `reasoning`.

Fails context that is empty, thin, mocked, or relies heavily on hallucination. Used by the orchestrator between context retrieval and generation.

## Tools / dependencies
- Google Gemini API (`google-genai`) — model: `gemini-2.5-flash`
- `python-sdk/oversight.py`

## Owner
`reformai`

## Setup
```bash
export OVERSIGHT_URL=https://agent-oversight.vercel.app
export OVERSIGHT_SECRET=<secret>
export GEMINI_API_KEY=<key>
```

## Output schema
```json
{ "passed": true, "score": 8, "reasoning": "Context contains..." }
```

## Notes
Currently bypassed in the orchestrator (Step 2 commented out). Re-enable when context quality issues arise.
