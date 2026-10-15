# Regression test for bootstrap.ps1's slash-command install step.
#
# Bug class: ARTIFACT-WITHOUT-ACTIVATION, Windows leg. bootstrap.sh has copied
# commands/*.md into ~/.claude/commands/ since the 2026-05-14 install report
# (/second-brain-mapping installed but absent from the palette). bootstrap.ps1
# never had that step, so every Windows install shipped the skills with NONE of
# the slash commands -- `/meeting-todos`, `/daily-journal`, `/graphify` and the
# rest did not exist there. Nothing errored: the skills still answered natural
# language, so the gap was only visible to someone who typed "/".
#
# Runs cross-platform (pwsh on macOS/Linux, Windows PowerShell 5.1 on Windows)
# so the logic is gated on every push, not only on the Windows runner. The REAL
# end-to-end proof is windows-install.yml's "assert slash commands installed"
# step, which checks the outcome after running the actual bootstrap.
#
# Asserts:
#   1. The block is present in bootstrap.ps1 and extractable by its markers.
#   2. Fresh install: every commands/*.md lands in the destination.
#   3. Idempotent: a second run copies nothing and reports "already current".
#   4. A locally-modified command is BACKED UP before being overwritten.
#   5. A missing commands/ dir warns instead of throwing.
#   6. In a git checkout, a stale copy of a shipped version is replaced but a
#      command the user wrote (a blob the repo never shipped) is KEPT and
#      reported under Skipped. Assertion 4 runs on a non-git fixture, where
#      provenance is unknowable and the old replace-with-backup still holds.
#
# Exit 0 = pass, 1 = fail.

$ErrorActionPreference = "Stop"
$Bootstrap = Join-Path $PSScriptRoot "../../bootstrap.ps1"
$TmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("abs-slashcmd-" + [System.Guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force -Path $TmpRoot | Out-Null

$script:Failures = 0
function Check($cond, $msg) {
    if ($cond) { Write-Host "  ok    $msg" -ForegroundColor Green }
    else { Write-Host "  FAIL  $msg" -ForegroundColor Red; $script:Failures++ }
}

# Bootstrap-only helpers the block calls. Stubbed so the block runs in
# isolation; $script:Backups / $script:Updated mirror bootstrap's trackers.
function Hdr($msg) { }
function Log($msg) { }
function Ok($msg) { $script:LastOk = $msg }
function Warn($msg) { $script:LastWarn = $msg }
function Err($msg) { $script:LastErr = $msg }
function Dry($msg) { $script:LastDry = $msg }

try {
    Write-Host "A. the block ships in bootstrap.ps1 and is extractable"
    $src = [System.IO.File]::ReadAllText($Bootstrap)
    $startMark = "# ai-brain:slash-commands:start"
    $endMark = "# ai-brain:slash-commands:end"
    $si = $src.IndexOf($startMark)
    $ei = $src.IndexOf($endMark)
    Check ($si -ge 0) "bootstrap.ps1 carries the $startMark marker"
    Check ($ei -gt $si) "bootstrap.ps1 carries the $endMark marker after it"
    if ($si -lt 0 -or $ei -le $si) {
        Write-Host "ERROR: cannot extract the block; the rest of this test would be vacuous." -ForegroundColor Red
        exit 1
    }
    $block = $src.Substring($si, $ei - $si)
    Check ($block -match "\.claude") "extracted block targets a .claude destination"
    Check ($block -match "bak-") "extracted block backs up before overwriting"

    $blockFile = Join-Path $TmpRoot "block.ps1"
    [System.IO.File]::WriteAllText($blockFile, $block, (New-Object System.Text.UTF8Encoding($false)))

    # One fixture per case: a fake SkillDir with commands/, and a fake HOME.
    function New-Case($name, [switch]$NoCommands) {
        $d = Join-Path $TmpRoot $name
        New-Item -ItemType Directory -Force -Path $d | Out-Null
        $skill = Join-Path $d "skill"
        if (-not $NoCommands) {
            New-Item -ItemType Directory -Force -Path (Join-Path $skill "commands") | Out-Null
            foreach ($n in @("meeting-todos", "daily-journal", "graphify")) {
                Set-Content -LiteralPath (Join-Path $skill "commands/$n.md") -Value "# $n`nbody" -NoNewline
            }
        } else {
            New-Item -ItemType Directory -Force -Path $skill | Out-Null
        }
        New-Item -ItemType Directory -Force -Path (Join-Path $d "home") | Out-Null
        return $d
    }

    # Run the extracted block against a fixture. The block reads $SkillDir,
    # $env:USERPROFILE, $DryRun and $stamp from its enclosing scope, exactly as
    # it does inside bootstrap.ps1.
    function Invoke-Block($caseDir, [switch]$AsDryRun) {
        $script:Backups = @()
        $script:Updated = @()
        $script:Skipped = @()
        $script:LastOk = $null; $script:LastWarn = $null; $script:LastDry = $null
        $SkillDir = Join-Path $caseDir "skill"
        $savedProfile = $env:USERPROFILE
        $env:USERPROFILE = Join-Path $caseDir "home"
        $DryRun = [bool]$AsDryRun
        $stamp = "TESTSTAMP"
        try { . $blockFile } finally { $env:USERPROFILE = $savedProfile }
    }

    Write-Host "B. fresh install copies every command"
    $d = New-Case "b"
    Invoke-Block $d
    $dst = Join-Path $d "home/.claude/commands"
    Check (Test-Path -LiteralPath $dst) "destination dir created"
    $got = @(Get-ChildItem -File -Filter *.md -LiteralPath $dst).Count
    Check ($got -eq 3) "all 3 commands installed (found $got)"
    Check (Test-Path -LiteralPath (Join-Path $dst "meeting-todos.md")) "meeting-todos.md present -> /meeting-todos resolves"
    Check ($script:Updated.Count -eq 1) "reported the install in the Updated summary"

    Write-Host "C. second run is idempotent"
    Invoke-Block $d
    Check ($script:LastOk -eq "commands: already current") "reports 'already current' (got: $($script:LastOk))"
    Check ($script:Backups.Count -eq 0) "made no backups on an unchanged run"

    Write-Host "D. a locally-modified command is backed up, not silently clobbered"
    Set-Content -LiteralPath (Join-Path $dst "meeting-todos.md") -Value "MY LOCAL EDIT" -NoNewline
    Invoke-Block $d
    Check ($script:Backups.Count -eq 1) "one backup recorded (got $($script:Backups.Count))"
    $bak = Join-Path $dst "meeting-todos.md.bak-TESTSTAMP"
    Check (Test-Path -LiteralPath $bak) "backup file written next to it"
    if (Test-Path -LiteralPath $bak) {
        Check ((Get-Content -Raw -LiteralPath $bak) -eq "MY LOCAL EDIT") "backup preserves the user's edit"
    }
    Check ((Get-Content -Raw -LiteralPath (Join-Path $dst "meeting-todos.md")) -match "meeting-todos") "shipped version restored"

    Write-Host "E. dry-run writes nothing"
    $d2 = New-Case "e"
    Invoke-Block $d2 -AsDryRun
    Check (-not (Test-Path -LiteralPath (Join-Path $d2 "home/.claude/commands"))) "dry-run created no destination"
    Check ($null -ne $script:LastDry) "dry-run announced what it would do"

    Write-Host "F. a missing commands/ dir warns instead of throwing"
    $d3 = New-Case "f" -NoCommands
    Invoke-Block $d3
    Check ($null -ne $script:LastWarn) "warned about the missing commands/ dir"

    Write-Host "G. git checkout: stale shipped copy replaced, user-authored command kept"
    $d4 = Join-Path $TmpRoot "g"
    $skill4 = Join-Path $d4 "skill"
    New-Item -ItemType Directory -Force -Path (Join-Path $skill4 "commands") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $d4 "home/.claude/commands") | Out-Null
    $eapSaved = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & git -C $skill4 init --quiet 2>$null
        & git -C $skill4 config user.email t@example.com
        & git -C $skill4 config user.name T
        [System.IO.File]::WriteAllText((Join-Path $skill4 ".gitattributes"), "* text=auto eol=lf`n")
        foreach ($n in @("meeting-todos", "graphify")) {
            [System.IO.File]::WriteAllText((Join-Path $skill4 "commands/$n.md"), "# $n`nversion one`n")
        }
        & git -C $skill4 add -A 2>$null
        & git -C $skill4 commit --quiet -m v1 2>$null
        foreach ($n in @("meeting-todos", "graphify")) {
            [System.IO.File]::WriteAllText((Join-Path $skill4 "commands/$n.md"), "# $n`nversion two`n")
        }
        & git -C $skill4 add -A 2>$null
        & git -C $skill4 commit --quiet -m v2 2>$null
    } finally { $ErrorActionPreference = $eapSaved }
    $dst4 = Join-Path $d4 "home/.claude/commands"
    # meeting-todos: a CRLF copy of the shipped v1 (stale). graphify: the user's own.
    [System.IO.File]::WriteAllText((Join-Path $dst4 "meeting-todos.md"), "# meeting-todos`r`nversion one`r`n")
    [System.IO.File]::WriteAllText((Join-Path $dst4 "graphify.md"), "MY OWN GRAPHIFY")
    Invoke-Block $d4
    Check ((Get-Content -Raw -LiteralPath (Join-Path $dst4 "meeting-todos.md")) -match "version two") "stale shipped copy (CRLF) replaced by the current version"
    Check ((Get-Content -Raw -LiteralPath (Join-Path $dst4 "graphify.md")) -eq "MY OWN GRAPHIFY") "user-authored command left exactly as written"
    Check (-not (Test-Path -LiteralPath (Join-Path $dst4 "graphify.md.bak-TESTSTAMP"))) "no backup of the kept command (nothing was replaced)"
    Check ($script:Backups.Count -eq 1) "exactly one backup, for the stale copy (got $($script:Backups.Count))"
    Check (@($script:Skipped | Where-Object { $_ -match "^/graphify " }).Count -eq 1) "kept command reported under Skipped"

    Write-Host ""
    if ($script:Failures -gt 0) {
        Write-Host "FAILED: $($script:Failures) assertion(s)" -ForegroundColor Red
        exit 1
    }
    Write-Host "PASS: bootstrap.ps1 installs slash commands (fresh + idempotent + backup + dry-run + missing-dir + keeps user-authored)" -ForegroundColor Green
    exit 0
}
finally {
    Remove-Item -Recurse -Force -LiteralPath $TmpRoot -ErrorAction SilentlyContinue
}
