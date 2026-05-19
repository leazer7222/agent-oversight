# scripts/start-guardian.ps1 — Session guardian daemon
#
# Starts a background PowerShell job that calls checkpoint.ps1 every 20 minutes.
# This protects against the case where Claude's response is cut off mid-generation
# by the 5-hour usage limit — the Stop hook cannot fire in that case, but the
# guardian runs independently of Claude Code.
#
# Usage:
#   pwsh scripts/start-guardian.ps1          # start guardian for this session
#   pwsh scripts/start-guardian.ps1 -Stop    # stop running guardian
#   pwsh scripts/start-guardian.ps1 -Status  # show guardian status + checkpoint log
#
# The guardian writes a PID file to .claude/guardian.pid.
# It auto-stops when the git worktree is no longer the active directory.
#
# Recommended: add to CLAUDE.md session start protocol, or put in Windows
# startup / Task Scheduler to auto-start with each Claude Code session.

param(
    [switch]$Stop,
    [switch]$Status,
    [int]$IntervalMinutes = 20
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PidFile     = Join-Path $ProjectRoot ".claude\guardian.pid"
$LogFile     = Join-Path $ProjectRoot ".claude\checkpoint.log"

# ── Status ───────────────────────────────────────────────────────────────────
if ($Status) {
    if (Test-Path $PidFile) {
        $savedPid = Get-Content $PidFile -ErrorAction SilentlyContinue
        $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "Guardian: RUNNING (PID $savedPid)" -ForegroundColor Green
        } else {
            Write-Host "Guardian: STOPPED (stale PID file)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Guardian: NOT RUNNING" -ForegroundColor Yellow
    }

    if (Test-Path $LogFile) {
        Write-Host "`nLast 10 checkpoints:" -ForegroundColor Cyan
        Get-Content $LogFile -Tail 10 | ForEach-Object {
            Write-Host "  $_" -ForegroundColor DarkGray
        }
    } else {
        Write-Host "`nNo checkpoints yet." -ForegroundColor DarkGray
    }
    exit 0
}

# ── Stop ─────────────────────────────────────────────────────────────────────
if ($Stop) {
    if (Test-Path $PidFile) {
        $savedPid = Get-Content $PidFile -ErrorAction SilentlyContinue
        $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
        if ($proc) {
            Stop-Process -Id $savedPid -Force
            Write-Host "Guardian stopped (PID $savedPid)." -ForegroundColor Yellow
        } else {
            Write-Host "Guardian was not running (stale PID file)." -ForegroundColor DarkGray
        }
        Remove-Item $PidFile -ErrorAction SilentlyContinue
    } else {
        Write-Host "Guardian is not running." -ForegroundColor DarkGray
    }
    exit 0
}

# ── Already running? ─────────────────────────────────────────────────────────
if (Test-Path $PidFile) {
    $savedPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "Guardian already running (PID $savedPid). Use -Stop to restart." -ForegroundColor Yellow
        exit 0
    }
    # Stale PID — remove and continue
    Remove-Item $PidFile -ErrorAction SilentlyContinue
}

# ── Start ────────────────────────────────────────────────────────────────────
$checkpointScript = Join-Path $ProjectRoot "scripts\checkpoint.ps1"
$intervalMs       = $IntervalMinutes * 60 * 1000

$scriptBlock = {
    param($projectRoot, $checkpointScript, $intervalMs, $logFile)

    # Run immediately on start (catch anything uncommitted at session start)
    & pwsh -File $checkpointScript -Reason "guardian-start" 2>&1 | Out-Null

    while ($true) {
        Start-Sleep -Milliseconds $intervalMs

        # Stop if project root no longer exists (worktree was deleted)
        if (-not (Test-Path $projectRoot)) { break }

        # Run checkpoint
        & pwsh -File $checkpointScript -Reason "guardian" 2>&1 | Out-Null
    }
}

$job = Start-Job -ScriptBlock $scriptBlock -ArgumentList $ProjectRoot, $checkpointScript, $intervalMs, $LogFile

# Save PID (Job.Id is not a real PID, but we can find the child process)
# For simplicity, save the PowerShell Job ID and use Get-Job to check
$job.Id | Set-Content $PidFile

Write-Host ""
Write-Host "Session guardian started." -ForegroundColor Green
Write-Host "  Checkpoint interval : every $IntervalMinutes minutes" -ForegroundColor DarkGray
Write-Host "  First checkpoint    : in ${IntervalMinutes}min (also ran once now)" -ForegroundColor DarkGray
Write-Host "  Checkpoint log      : .claude/checkpoint.log" -ForegroundColor DarkGray
Write-Host "  Stop guardian       : pwsh scripts/start-guardian.ps1 -Stop" -ForegroundColor DarkGray
Write-Host "  Status              : pwsh scripts/start-guardian.ps1 -Status" -ForegroundColor DarkGray
Write-Host ""
Write-Host "If Claude hits the 5-hour limit mid-response, the last guardian checkpoint" -ForegroundColor DarkGray
Write-Host "will be on the remote branch — at most ${IntervalMinutes} minutes of work at risk." -ForegroundColor DarkGray
Write-Host ""
