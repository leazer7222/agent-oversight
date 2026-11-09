# Keeps the swim-sourcing worker alive on this PC as a Windows Scheduled Task.
#
#   powershell -ExecutionPolicy Bypass -File scripts/swim-worker-task.ps1 -Install
#   powershell -ExecutionPolicy Bypass -File scripts/swim-worker-task.ps1 -Status
#   powershell -ExecutionPolicy Bypass -File scripts/swim-worker-task.ps1 -RunNow
#   powershell -ExecutionPolicy Bypass -File scripts/swim-worker-task.ps1 -Uninstall
#
# What it does: every 2 minutes, runs `python agents/teams/swim-sourcing/worker.py --drain`
# from this repository (the checkout this script lives in), appending output to
# .claude/swim-worker.log. --drain exits as soon as the queue is empty, so an idle
# tick costs one query. Overlapping ticks are ignored (one worker at a time).
#
# Runs only while this Windows user is logged on (no stored password). Jobs queued
# while the PC is off or locked-out wait in the database and run on the next tick.
# The worker reads .env.local from the repository root; keep secrets there, not here.
# PowerShell 5.1 compatible (no ternary, no ??).

param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Status,
    [switch]$RunNow,
    [int]$EveryMinutes = 2
)

$ErrorActionPreference = "Stop"
$TaskName = "AgentOversight-SwimSourcingWorker"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Worker = Join-Path $RepoRoot "agents\teams\swim-sourcing\worker.py"
$LogDir = Join-Path $RepoRoot ".claude"
$Log = Join-Path $LogDir "swim-worker.log"

function Get-PythonExe {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cmd = Get-Command py -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "python was not found on PATH"
}

function Show-Status {
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $t) { Write-Host "[task] $TaskName is NOT installed"; return }
    $i = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host "[task] $TaskName state=$($t.State) lastRun=$($i.LastRunTime) lastResult=$($i.LastTaskResult) nextRun=$($i.NextRunTime)"
    if (Test-Path $Log) {
        Write-Host "[task] last log lines ($Log):"
        Get-Content $Log -Tail 8 | ForEach-Object { Write-Host "       $_" }
    }
}

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "[task] removed $TaskName (if it existed)"
    exit 0
}

if ($Status) { Show-Status; exit 0 }

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "[task] started $TaskName; check -Status in a minute"
    exit 0
}

if (-not $Install) {
    Write-Host "Use -Install, -Status, -RunNow or -Uninstall."
    exit 1
}

if (-not (Test-Path $Worker)) { throw "worker not found at $Worker" }
if (-not (Test-Path (Join-Path $RepoRoot ".env.local"))) { throw ".env.local missing at $RepoRoot; the worker needs it" }
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$python = Get-PythonExe
# cmd.exe wrapper so stdout/stderr land in the log with a timestamp per tick.
$inner = "echo [%DATE% %TIME%] tick >> `"$Log`" && `"$python`" `"$Worker`" --drain >> `"$Log`" 2>&1"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $inner" -WorkingDirectory $RepoRoot

# [TimeSpan]::MaxValue is rejected by the task scheduler on this Windows build
# (0x80041318, value out of range); ten years is indefinite enough.
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Hidden

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "Runs the Agent Oversight swim-sourcing worker (--drain) every $EveryMinutes minutes from $RepoRoot" | Out-Null

Write-Host "[task] installed ${TaskName}: every $EveryMinutes min, python=$python, repo=$RepoRoot"
Write-Host "[task] log: $Log"
Show-Status
