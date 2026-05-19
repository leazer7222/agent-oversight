# scripts/push.ps1 - Smart push with automatic documentation sync
#
# This is the canonical way to push from this repo.
# It ensures documentation is always current before the push lands in production.
#
# What it does, in order:
#   1. Detect new/modified migration files -> run linter, warn if unapplied
#   2. Code review -- if src/, agents/, or supabase/migrations/ changed, run the
#      code-review-agent. Blocks push if recommendation is BLOCK.
#   3. Stage all modified doc files (sessions/, docs/, LESSONS_LEARNED.md, AGENTS.md)
#   4. Commit them with a standard message if anything was staged
#   5. Run git push with any args you passed in
#
# Usage:
#   pwsh scripts/push.ps1                        # push current branch to origin
#   pwsh scripts/push.ps1 origin main            # explicit remote + branch
#   pwsh scripts/push.ps1 --no-doc-check         # skip doc sync (emergencies only)
#   pwsh scripts/push.ps1 --no-review            # skip code review (emergencies only)
#
# DO NOT run bare `git push` -- the Claude Code hook will redirect you here.

param(
    [string]$Remote   = "origin",
    [string]$Branch   = "",
    [switch]$NoDocCheck,
    [switch]$NoReview,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Resolve project root from script location
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

$Divider = "-" * 60

function Write-Step([string]$msg) {
    Write-Host "`n$Divider" -ForegroundColor DarkGray
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host $Divider -ForegroundColor DarkGray
}

function Write-Ok([string]$msg)   { Write-Host "  [OK]   $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Fail([string]$msg) { Write-Host "  [FAIL] $msg" -ForegroundColor Red }

# -- 0. Sanity check ----------------------------------------------------------
Write-Step "Pre-push checks"

$currentBranch = git rev-parse --abbrev-ref HEAD 2>&1
Write-Ok "Branch: $currentBranch"

# Warn if pushing directly to main without a worktree
if ($currentBranch -eq "main" -and -not $NoDocCheck) {
    Write-Warn "Pushing directly to main. Ensure all docs are current."
}

# -- 1. Migration linter ------------------------------------------------------
Write-Step "Migration check"

# Find migration files modified since last push (HEAD vs remote)
$remoteBranch = if ($Branch) { "$Remote/$Branch" } else { "$Remote/$currentBranch" }
$baseRef = git merge-base HEAD $remoteBranch 2>&1
if ($LASTEXITCODE -ne 0) {
    # No remote ref yet (first push) -- compare against all committed migrations
    $baseRef = "HEAD~1"
}

$changedMigrations = git diff --name-only $baseRef HEAD -- "supabase/migrations/*.sql" 2>&1 |
    Where-Object { $_ -ne "" }

if ($changedMigrations) {
    Write-Warn "New migrations in this push:"
    $changedMigrations | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkYellow }

    Write-Host ""
    Write-Host "  Running migration linter..." -ForegroundColor Cyan
    python scripts/check_migrations.py 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Migration linter failed. Fix before pushing."
        exit 1
    }
    Write-Ok "Migration linter: 0 hard failures"
} else {
    Write-Ok "No new migrations in this push"
}

# -- 2. Code review -----------------------------------------------------------
if (-not $NoReview) {
    $reviewPaths = @("src", "agents", "supabase/migrations")
    $changedCode = git diff --name-only $baseRef HEAD -- $reviewPaths 2>&1 |
        Where-Object { $_ -ne "" }

    if ($changedCode) {
        Write-Step "Code review ($($changedCode.Count) changed file(s) in src/agents/migrations)"

        python agents/library/code-review-agent/agent.py `
            --commit-sha HEAD `
            --base-sha $baseRef `
            --branch $currentBranch

        if ($LASTEXITCODE -eq 1) {
            Write-Fail "Code review BLOCKED the push. Fix findings before pushing."
            Write-Fail "To bypass in an emergency: pwsh scripts/push.ps1 --no-review"
            exit 1
        }
        Write-Ok "Code review passed"
    } else {
        Write-Step "Code review"
        Write-Ok "No src/agents/migrations changes -- skipping review"
    }
} else {
    Write-Step "Code review"
    Write-Warn "--no-review: skipping code review"
}

# -- 3. Documentation sync ----------------------------------------------------
if (-not $NoDocCheck) {
    Write-Step "Documentation sync"

    # Files/dirs that must be committed before a push
    $DocPaths = @(
        "sessions",
        "docs",
        "LESSONS_LEARNED.md",
        "AGENTS.md"
    )

    # Check for untracked or modified doc files
    $statusOutput = git status --short -- ($DocPaths -join " ") 2>&1
    $unstagedDocs = $statusOutput | Where-Object { $_ -match "^\s?[?M]" }
    $stagedDocs   = $statusOutput | Where-Object { $_ -match "^[AM]" }

    if ($unstagedDocs -or $stagedDocs) {
        Write-Warn "Uncommitted documentation changes found -- staging them now:"
        $statusOutput | Where-Object { $_ -ne "" } | ForEach-Object {
            Write-Host "    $_" -ForegroundColor DarkYellow
        }

        # Stage doc paths
        foreach ($path in $DocPaths) {
            if (Test-Path $path) {
                git add $path 2>&1 | Out-Null
            }
        }

        # Only commit if something was actually staged
        $nowStaged = git diff --cached --name-only 2>&1 | Where-Object { $_ -ne "" }
        if ($nowStaged) {
            $commitMsg = "docs: sync session documentation`n`nAuto-committed by scripts/push.ps1 pre-push sync."
            git commit -m $commitMsg 2>&1 | Out-Null
            Write-Ok "Documentation committed: $($nowStaged.Count) file(s)"
            $nowStaged | ForEach-Object { Write-Host "    + $_" -ForegroundColor DarkGreen }
        }
    } else {
        Write-Ok "Documentation is current -- nothing to commit"
    }

    # Warn if today's session file doesn't exist
    $today = (Get-Date).ToString("yyyy-MM-dd")
    $sessionFile = "sessions/$today.md"
    if (-not (Test-Path $sessionFile)) {
        Write-Warn "No session file for today ($sessionFile). Was this session logged?"
    } else {
        Write-Ok "Session file: $sessionFile"
    }
} else {
    Write-Warn "--no-doc-check: skipping documentation sync"
}

# -- 4. Final status ----------------------------------------------------------
Write-Step "Pre-push summary"

$ahead = git rev-list --count $remoteBranch..HEAD 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Ok "$ahead commit(s) ahead of $remoteBranch"
} else {
    Write-Ok "Commits ready to push (remote not yet fetched)"
}

# -- 5. Push ------------------------------------------------------------------
Write-Step "Pushing to $Remote"

$pushBranch = if ($Branch) { $Branch } else { $currentBranch }
$pushArgs = @("push", $Remote, $pushBranch)
if ($Force)   { $pushArgs += "--force-with-lease" }

Write-Host "  git $($pushArgs -join ' ')" -ForegroundColor DarkGray

# Signal to .githooks/pre-push that we are the legitimate caller
# so it doesn't block the push that we are intentionally making
$env:PUSH_SCRIPT_RUNNING = "1"
git @pushArgs
$env:PUSH_SCRIPT_RUNNING = ""

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Ok "Push complete. Production updated."
    Write-Host ""
} else {
    Write-Fail "Push failed. Check git output above."
    exit 1
}
