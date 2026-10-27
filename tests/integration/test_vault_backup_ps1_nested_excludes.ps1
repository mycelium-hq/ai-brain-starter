#!/usr/bin/env pwsh
# Test that `vault-backup.ps1 run` leaves machine-exhaust out at ANY depth.
#
# THE BUG
# -------
# $ExcludeDirs names caches that are never worth backing up (__pycache__,
# node_modules, .venv, ...), but New-Archive joined every entry to the vault
# root before handing it to robocopy's /XD. robocopy then excluded
# <vault>\__pycache__ and nothing else. These caches sit next to whatever code
# made them, so in a real vault they are nested (a scripts folder's
# __pycache__, a small project's node_modules), and every one of them went into
# the archive. A bare name now goes to robocopy as a NAME, which matches at any
# depth; an entry with a separator (.claude\worktrees) stays a path under the
# vault root.
#
# COVERED HERE
#   A. Nested __pycache__, node_modules and .venv are not in the archive.
#      THE REPORTED CASE: fails on the code before this change.
#   B. The root-level entries are still excluded (__pycache__, .claude\worktrees).
#   C. Notes beside the excluded folders are kept, including a note whose name
#      contains an excluded name ("node_modules notes.md"), so the match is on
#      whole folder names, not on substrings or whole subtrees.
#   D. An entry with a separator stays anchored to the vault root: a nested
#      ...\.claude\worktrees folder is kept, as it was before.
#
# Windows only: New-Archive stages with robocopy. Elsewhere this SKIPs loudly.
# Self-contained; no network; never writes outside its own temp dir, and never
# touches the real ~/.claude/.vault-backup.conf or the last-run marker
# (VAULT_BACKUP_CONF and VAULT_BACKUP_MARKER are redirected).

$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    Write-Host "SKIP: vault-backup.ps1 stages with robocopy, which only exists on Windows" -ForegroundColor Yellow
    exit 0
}

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Script   = Join-Path (Join-Path $RepoRoot "scripts") "vault-backup.ps1"
if (-not (Test-Path -LiteralPath $Script)) {
    Write-Host "ERROR: $Script not found" -ForegroundColor Red
    exit 1
}

$PSExe = [System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
$Failures = 0
$Root = Join-Path ([IO.Path]::GetTempPath()) ("vbk-nested-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $Root | Out-Null

function Fail($m) { $script:Failures++; Write-Host "FAIL $m" -ForegroundColor Red }
function Pass($m) { Write-Host "PASS $m" -ForegroundColor Green }

function Put([string]$rel, [string]$text) {
    $p = Join-Path $vault $rel
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $p) | Out-Null
    Set-Content -LiteralPath $p -Value $text -Encoding UTF8
}

$vault = Join-Path $Root "vault"
$dest  = Join-Path $Root "dest"
New-Item -ItemType Directory -Force -Path $vault | Out-Null
New-Item -ItemType Directory -Force -Path $dest  | Out-Null

# Notes, which must all be kept.
$keep = @(
    "CLAUDE.md",
    "Meta\scripts\tool.py",
    "projects\node_modules notes.md",
    "projects\app\src\index.js",
    "projects\app\.claude\worktrees\nested-keep.md"
)
# Machine-exhaust, which must all be left out.
$nested = @(
    "Meta\scripts\__pycache__\tool.cpython-312.pyc",
    "projects\app\node_modules\pkg\index.js",
    "projects\app\.venv\pyvenv.cfg"
)
$rootLevel = @(
    "__pycache__\root.cpython-312.pyc",
    ".claude\worktrees\scratch\junk.md"
)
foreach ($f in $keep + $nested + $rootLevel) { Put $f ("content of " + $f) }

$conf = Join-Path $Root "conf.json"
$key  = (Resolve-Path -LiteralPath $vault).Path
$obj  = [pscustomobject]@{ vaults = [pscustomobject]@{} }
$obj.vaults | Add-Member -NotePropertyName $key -NotePropertyValue ([pscustomobject]@{
    dest = $dest; encrypt = $false; keep = 7; last = "2026-01-01T00:00:00Z"
}) -Force
$obj | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $conf -Encoding UTF8

$env:VAULT_BACKUP_CONF   = $conf
$env:VAULT_BACKUP_MARKER = Join-Path $Root "marker"

# EAP drops to Continue around the child: under 'Stop', Windows PowerShell 5.1
# turns a native command's stderr into a terminating error, which would abort
# the suite instead of reporting the failure.
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $out  = & $PSExe -NoProfile -ExecutionPolicy Bypass -File $Script run -Vault $key 2>&1 | Out-String
    $code = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $prevEAP
}

$zip = Get-ChildItem -LiteralPath $dest -Filter "vault-backup-*.zip" -File | Select-Object -First 1
if ($code -ne 0 -or -not $zip) {
    Fail "run did not write a .zip (exit $code): $($out.Trim())"
} else {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $z = [IO.Compression.ZipFile]::OpenRead($zip.FullName)
    try {
        # Windows PowerShell 5.1's Compress-Archive writes '\' separators.
        $entries = @($z.Entries | ForEach-Object { $_.FullName -replace '\\', '/' })
    } finally {
        $z.Dispose()
    }
    function Has([string]$rel) { $entries -contains ($rel -replace '\\', '/') }

    $leaked = @($nested | Where-Object { Has $_ })
    if ($leaked.Count -eq 0) {
        Pass "A: nested __pycache__, node_modules and .venv are not in the archive"
    } else {
        Fail "A: nested machine-exhaust leaked into the archive: $($leaked -join ', ')"
    }

    $leaked = @($rootLevel | Where-Object { Has $_ })
    if ($leaked.Count -eq 0) {
        Pass "B: root-level __pycache__ and .claude\worktrees are still excluded"
    } else {
        Fail "B: root-level exclusions regressed: $($leaked -join ', ')"
    }

    $missing = @($keep | Where-Object { $_ -notlike "*\.claude\*" -and -not (Has $_) })
    if ($missing.Count -eq 0) {
        Pass "C: notes beside the excluded folders are kept, 'node_modules notes.md' included"
    } else {
        Fail "C: notes missing from the archive: $($missing -join ', ')"
    }

    if (Has "projects\app\.claude\worktrees\nested-keep.md") {
        Pass "D: an entry with a separator stays anchored to the vault root"
    } else {
        Fail "D: a nested .claude\worktrees was excluded; anchored entries must stay root-only"
    }
}

Remove-Item -Recurse -Force -LiteralPath $Root -ErrorAction SilentlyContinue

if ($Failures -gt 0) {
    Write-Host "$Failures case(s) failed" -ForegroundColor Red
    exit 1
}
Write-Host "all cases passed" -ForegroundColor Green
exit 0
