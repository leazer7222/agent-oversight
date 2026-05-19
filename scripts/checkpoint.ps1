# scripts/checkpoint.ps1 — Rapid WIP checkpoint
#
# Called automatically by the Claude Code Stop hook after every response.
# Also called by the session guardian every 20 minutes.
# Can be run manually at any time.
#
# What it does:
#   1. If nothing has changed since last commit — exits immediately (fast path)
#   2. Stages ALL modified/untracked files
#   3. Commits with "WIP: checkpoint HH:MM:SS"
#   4. Pushes to remote with --no-verify (bypasses pre-push doc gate)
#
# This is NOT a production push. It is a safety net.
# Use scripts/push.ps1 for production pushes with full doc sync.
#
# Speed target: < 5 seconds when there are changes, < 1 second when clean.

param(
    [string]$Reason = "auto"   # "auto" | "guardian" | "manual" | "limit-warning"
)

$ErrorActionPreference = "SilentlyContinue"  # Never block Claude's response on checkpoint failure

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

# ── Fast path: nothing to do ────────────────────────────────────────────────
$status = git status --porcelain 2>&1
if (-not $status) {
    # Nothing changed — exit silently
    exit 0
}

# ── Stage everything ─────────────────────────────────────────────────────────
git add -A 2>&1 | Out-Null

# Check again after staging (might have been whitespace-only)
$staged = git diff --cached --name-only 2>&1
if (-not $staged) {
    exit 0
}

# ── Commit ───────────────────────────────────────────────────────────────────
$timestamp  = Get-Date -Format "HH:mm:ss"
$branch     = git rev-parse --abbrev-ref HEAD 2>&1
$fileCount  = ($staged | Measure-Object -Line).Lines
$commitMsg  = "WIP: checkpoint $timestamp [$Reason] $fileCount file(s)"

git commit -m $commitMsg 2>&1 | Out-Null

if ($LASTEXITCODE -ne 0) {
    # Commit failed (e.g. nothing staged after all) — exit silently
    exit 0
}

# ── Push ─────────────────────────────────────────────────────────────────────
# --no-verify bypasses .githooks/pre-push (which redirects to push.ps1)
# This is intentional — checkpoint is a safety net, not a production push

# Try normal push first; if it fails because upstream isn't set, set it and retry
git push --no-verify 2>&1 | Out-Null
$pushResult = $LASTEXITCODE

if ($pushResult -ne 0) {
    # Attempt to set upstream and push (handles first push of a new worktree branch)
    $currentBranch = git rev-parse --abbrev-ref HEAD 2>&1
    git push --no-verify --set-upstream origin $currentBranch 2>&1 | Out-Null
    $pushResult = $LASTEXITCODE
}

# Log to a checkpoint log so sessions can see history
$logFile = Join-Path $ProjectRoot ".claude\checkpoint.log"
$logEntry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $Reason | $branch | $fileCount files | push:$( if ($pushResult -eq 0) {'ok'} else {'failed'} )"
Add-Content -Path $logFile -Value $logEntry -ErrorAction SilentlyContinue

exit 0  # Never fail — checkpoint errors must not disrupt Claude Code
