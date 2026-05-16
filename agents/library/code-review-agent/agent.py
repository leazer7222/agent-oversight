"""
code-review-agent — v1 stub

Registration, output contract, and output.py utility are complete.
Full LLM invocation wiring is deferred from v1.

When wiring:
  1. Accept --commit-sha, --base-sha, --branch args (or env vars)
  2. Run `git diff <base_sha> <commit_sha>` to obtain the diff
  3. Load standards docs from config_overrides.context_scope.standards_refs
  4. Call the LLM with prompt.md as system prompt + diff as user input
  5. Parse response into findings list
  6. Call output.build_artifact() and output.write_code_review()
  7. OversightClient handles run_started / run_completed telemetry

Operational instance:
  agent_id  : a0b9c8d7-e6f5-4a4b-9c3d-2e1f0a9b8c7d  (reformai.code-review-agent)
  parent    : f239fe0a-2134-489d-b13a-6bcf2aaf1ef5  (claude-reformai)
  company   : 1021c018-fe0e-4ae8-a972-7487521cc3d9  (ReformAI)
"""

AGENT_ID = "a0b9c8d7-e6f5-4a4b-9c3d-2e1f0a9b8c7d"
DEFINITION_VERSION = "1.0.0"

if __name__ == "__main__":
    print(f"code-review-agent v{DEFINITION_VERSION} — invocation not yet wired (v1 stub)")
    print(f"agent_id: {AGENT_ID}")
    print("See output.py for the artifact write path and prompt.md for review instructions.")
