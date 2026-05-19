#!/usr/bin/env python3
"""
Claude Code PreToolUse hook — intercepts bare 'git push' commands.

When Claude runs a Bash tool call containing 'git push', this hook fires.
If the command is a bare git push (not routed through scripts/push.ps1),
it blocks the call and tells Claude to use the smart push script instead.

This ensures docs are always updated in the same push as the code change.

Hook contract (Claude Code SDK):
  - Input:  JSON on stdin  { tool_name, tool_input: { command } }
  - Output: JSON on stdout { decision: "block"|"approve", reason? }
  - Exit:   0 always (decision is communicated via stdout JSON)

RFC reference: LESSONS_LEARNED.md — "Documentation sync must happen before push"
"""

import json
import sys


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        # Can't parse input — let it through, don't block
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    command   = data.get("tool_input", {}).get("command", "")

    # Only care about Bash calls
    if tool_name != "Bash":
        sys.exit(0)

    # Check for bare git push
    is_git_push = "git push" in command

    # These are allowed through:
    #   - Our own push script (it calls git push internally)
    #   - Explicit bypass flag
    #   - Force-push (developer knows what they're doing)
    is_via_push_script = "scripts/push" in command
    is_bypassed        = "--no-verify" in command or "--no-doc-check" in command
    is_force_only      = command.strip() in (
        "git push --force", "git push --force-with-lease"
    )

    if is_git_push and not is_via_push_script and not is_bypassed:
        reason = (
            "Documentation must be synced before pushing.\n\n"
            "Use the smart push script instead:\n\n"
            "    pwsh scripts/push.ps1\n\n"
            "It will:\n"
            "  1. Run the migration linter if new migrations exist\n"
            "  2. Stage and commit any updated docs (sessions/, docs/, LESSONS_LEARNED.md)\n"
            "  3. Push everything in one shot — no second push needed\n\n"
            "To bypass in an emergency:\n"
            "    pwsh scripts/push.ps1 --no-doc-check\n"
            "    git push --no-verify  (skips git hook only, not this check)"
        )
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(0)

    # All other cases — approve
    sys.exit(0)


if __name__ == "__main__":
    main()
