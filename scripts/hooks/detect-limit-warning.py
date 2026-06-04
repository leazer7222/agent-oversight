#!/usr/bin/env python3
"""
Claude Code PreToolUse hook — detects "approaching limit" language in context
and immediately triggers a checkpoint before Claude does anything else.

When the user sends a message containing limit-warning keywords, this hook
fires on the FIRST tool call Claude attempts in that response and runs
checkpoint.ps1 before anything else happens.

This ensures that even if Claude is cut off mid-response, the work from
all previous turns is committed and pushed before Claude starts new work.

Hook contract:
  - Input:  JSON on stdin
  - Output: Nothing (just runs the checkpoint side-effectfully)
  - Exit:   Always 0 (never blocks tool calls)
"""

import json
import os
import subprocess
import sys


LIMIT_KEYWORDS = [
    "approaching limit",
    "approaching the limit",
    "5 hour limit",
    "five hour limit",
    "usage limit",
    "hitting the limit",
    "close to the limit",
    "token limit",
    "context limit",
    "running out",
    "limit soon",
    "save progress",
    "checkpoint",
    "save and push",
    "document progress",
]

CHECKPOINT_SENTINEL = ".claude/.limit_checkpoint_done"


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    # Read the transcript to check if recent user messages contain limit keywords
    transcript_path = data.get("transcript_path", "")
    if not transcript_path or not os.path.exists(transcript_path):
        sys.exit(0)

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript = f.read()[-4000:]  # Check last 4000 chars only (recent messages)
    except OSError:
        sys.exit(0)

    transcript_lower = transcript.lower()
    triggered = any(kw in transcript_lower for kw in LIMIT_KEYWORDS)

    if not triggered:
        sys.exit(0)

    # Check sentinel — only run checkpoint once per limit-warning event
    # (not on every subsequent tool call in the same response)
    sentinel = CHECKPOINT_SENTINEL
    if os.path.exists(sentinel):
        # Check if sentinel is fresh (< 60 seconds old)
        import time
        if time.time() - os.path.getmtime(sentinel) < 60:
            sys.exit(0)

    # Write sentinel before running checkpoint
    try:
        with open(sentinel, "w") as f:
            f.write("1")
    except OSError:
        pass

    # Run checkpoint immediately — before Claude does any other work
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    checkpoint = os.path.join(script_dir, "checkpoint.ps1")

    # Prefer pwsh (PowerShell Core) if installed; fall back to Windows PowerShell (always present
    # on Windows). pwsh is NOT installed on every machine — hard-coding it silently no-ops the
    # checkpoint (see LESSONS_LEARNED: the whole checkpoint system was dead on this machine).
    import shutil
    ps_exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell"

    subprocess.run(
        [ps_exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", checkpoint, "-Reason", "limit-warning"],
        capture_output=True,
        timeout=30,
    )

    sys.exit(0)


if __name__ == "__main__":
    main()
