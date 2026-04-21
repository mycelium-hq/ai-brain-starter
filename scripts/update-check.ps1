# update-check.ps1 — daily drift detector for the ai-brain-starter setup (Windows)
#
# See update-check.sh for full docs. This is the PowerShell port for Windows users.
#
# Usage (called from a Claude session via the CLAUDE.md rule):
#   powershell -File "$env:USERPROFILE\.claude\skills\ai-brain-starter\scripts\update-check.ps1"
#
# Force a re-check (bypass the once-per-day cooldown):
#   powershell -File "$env:USERPROFILE\.claude\skills\ai-brain-starter\scripts\update-check.ps1" -Force

param([switch]$Force)

$RepoDir   = "$env:USERPROFILE\.claude\skills\ai-brain-starter"
$CheckFile = "$env:USERPROFILE\.claude\.ai-brain-starter-last-check"
$Today     = (Get-Date -Format "yyyy-MM-dd")

# Daily cooldown
if (-not $Force -and (Test-Path $CheckFile)) {
    $last = (Get-Content $CheckFile -ErrorAction SilentlyContinue).Trim()
    if ($last -eq $Today) {
        Write-Output "STATUS: SKIPPED_TODAY"
        exit 0
    }
}

# Repo must exist
if (-not (Test-Path "$RepoDir\.git")) {
    Write-Output "STATUS: ERROR"
    Write-Output "REASON: ai-brain-starter not installed at $RepoDir"
    exit 0
}

Push-Location $RepoDir

try {
    git fetch --quiet origin main 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Output "STATUS: ERROR"
        Write-Output "REASON: git fetch failed (network down, or repo unreachable)"
        Set-Content -Path $CheckFile -Value $Today
        Pop-Location
        exit 0
    }

    $current = (git rev-parse HEAD 2>$null).Trim()
    $latest  = (git rev-parse origin/main 2>$null).Trim()

    if (-not $current -or -not $latest) {
        Write-Output "STATUS: ERROR"
        Write-Output "REASON: could not read HEAD or origin/main"
        Set-Content -Path $CheckFile -Value $Today
        Pop-Location
        exit 0
    }

    if ($current -eq $latest) {
        Write-Output "STATUS: UP_TO_DATE"
        Write-Output "CURRENT_HEAD: $((git rev-parse --short HEAD).Trim())"
        Set-Content -Path $CheckFile -Value $Today
        Pop-Location
        exit 0
    }

    # Behind. Count and extract the new CHANGELOG slice.
    $commitsBehind = (git rev-list --count "$current..$latest" 2>$null).Trim()

    Write-Output "STATUS: BEHIND"
    Write-Output "COMMITS_BEHIND: $commitsBehind"
    Write-Output "CURRENT_HEAD: $((git rev-parse --short $current).Trim())"
    Write-Output "LATEST_HEAD: $((git rev-parse --short $latest).Trim())"
    Write-Output "---CHANGELOG_NEW---"

    $newChangelog = git show "origin/main:docs/CHANGELOG.md" 2>$null
    if (-not $newChangelog) { $newChangelog = git show "origin/main:CHANGELOG.md" 2>$null }
    $currentChangelogContent = if (Test-Path "docs/CHANGELOG.md") { Get-Content "docs/CHANGELOG.md" -Raw } elseif (Test-Path "CHANGELOG.md") { Get-Content "CHANGELOG.md" -Raw } else { "" }

    if ($newChangelog -and $currentChangelogContent) {
        $firstCurrentH2 = ($currentChangelogContent -split "`n" | Where-Object { $_ -match '^## ' } | Select-Object -First 1)
        if ($firstCurrentH2) {
            $inEntry = $false
            $newChangelogLines = $newChangelog -split "`n"
            foreach ($line in $newChangelogLines) {
                if ($line.TrimEnd() -eq $firstCurrentH2.TrimEnd()) { break }
                if ($line -match '^## ') { $inEntry = $true }
                if ($inEntry) { Write-Output $line }
            }
        } else {
            Write-Output $newChangelog
        }
    }

    Write-Output "---END---"
    Set-Content -Path $CheckFile -Value $Today
}
finally {
    Pop-Location
}

exit 0
