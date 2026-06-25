@AGENTS.md
@LESSONS_LEARNED.md

# Session Protocol

## Before starting ANY session
1. Read the most recent file in `sessions/` to understand exactly where we left off.
2. Read `LESSONS_LEARNED.md` and apply every rule — do not repeat past mistakes.
3. If no session file exists yet, create one before doing any work.
4. **Start the session guardian:** `powershell -ExecutionPolicy Bypass -File scripts/start-guardian.ps1`
   This runs a background checkpoint every 20 minutes. If the 5-hour limit hits
   mid-response, at most 20 minutes of work is at risk. Without it, the entire
   session's uncommitted work can be lost.

## At the start of every session
Create a new session file: `sessions/YYYY-MM-DD.md` (use today's date).
Log what was done, what is in-progress, and what is blocked.

## During the session
Update the session file as work progresses — key decisions, blockers hit, fixes found.

**Automatic checkpoints are running.** After every complete response, `checkpoint.ps1`
commits and pushes all staged changes as a WIP snapshot. You do not need to manually
manage this — but you can run `powershell -ExecutionPolicy Bypass -File scripts/checkpoint.ps1 -Reason manual` at any time.

## If approaching the 5-hour usage limit
When the user mentions "approaching limit", "save progress", or similar:
1. **First action before anything else:** `powershell -ExecutionPolicy Bypass -File scripts/checkpoint.ps1 -Reason limit-warning`
   This is also triggered automatically by the `detect-limit-warning.py` hook.
2. Update the session file with current state, what's in-progress, what's next.
3. Run `powershell -ExecutionPolicy Bypass -File scripts/push.ps1` for a full production push with doc sync.
4. Leave a clear "RESUME FROM HERE" note at the bottom of the session file.

The limit-warning hook fires automatically when it detects "approaching limit",
"5 hour limit", "save progress", etc. in the conversation. Claude does not need
to be told to run it explicitly.

## At the end of every session
1. Finalize the session file with:
   - What was completed
   - What is pending / next steps
   - Any new lessons learned (add to `LESSONS_LEARNED.md`)
2. **Compass:** for each feature touched this session, record its **next step** (in the session
   file / `tasks/current-state.md`). If a durable human decision changed — a confirmed grouping,
   `importance`, a `next_step` override, or a decommissioned project — capture it in
   `~/.claude/compass/overlay.json`. This is the highest-value input `/compass` reads at re-entry;
   keep it current. Do NOT run `/compass` here — it is a session-START (re-entry) tool, not a close step.
   (Compass is frozen at the probe; see `docs/agent-feature-standup-v2.md`. Do NOT add it to the
   registered-agents list in AGENTS.md until it is actually registered at P4.)
3. Run `powershell -ExecutionPolicy Bypass -File scripts/push.ps1` to do a full push with doc sync.
4. Run `powershell -ExecutionPolicy Bypass -File scripts/start-guardian.ps1 -Stop` to stop the background guardian.

## Checkpoint system overview

| Layer | What it does | When it fires |
|---|---|---|
| Stop hook | `checkpoint.ps1` after every response | End of every Claude turn |
| Guardian | `checkpoint.ps1` every 20 min | Time-based, independent of Claude |
| Limit-warning hook | `checkpoint.ps1` immediately | When limit keywords detected in conversation |
| Manual | `powershell -ExecutionPolicy Bypass -File scripts/checkpoint.ps1 -Reason manual` | Explicitly |

**Checkpoint log:** `.claude/checkpoint.log` — review this to see what was committed when.
