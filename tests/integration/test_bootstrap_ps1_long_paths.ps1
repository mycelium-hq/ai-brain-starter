#!/usr/bin/env pwsh
# Test bootstrap.ps1's 8.3 short-path handling (tickets#7337).
#
# Bug: TEMP and LOCALAPPDATA can arrive as an 8.3 alias (C:\Users\JUANAR~1\...)
# on an account with a long or accented profile name, and bootstrap.ps1 built
# every download, unzip and install path from them unresolved.
#
# Covered:
#   A. The helpers ship in bootstrap.ps1 between `ai-brain:long-paths` markers.
#   B. An aliased TEMP / LOCALAPPDATA is rewritten to the long form (fake expander,
#      so this runs on pwsh 7 anywhere), and TMP too.
#   C. A resolver result that is NOT an existing folder is never trusted.
#   D. A path with no alias is returned byte-identical (nothing churns).
#   E. Non-Windows: Get-LongPath resolves nothing, so nothing changes.
#   F. Windows only: the REAL GetLongPathNameW turns a real 8.3 name back into
#      the long folder (skipped, loudly, when the volume has 8.3 names off).
#
# The block is EXTRACTED from the real bootstrap.ps1, never reimplemented here.
# Self-contained; no network; never writes outside its own temp dir.

$ErrorActionPreference = "Stop"

$RepoRoot  = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Bootstrap = Join-Path $RepoRoot "bootstrap.ps1"
$OnWindows = ($env:OS -eq "Windows_NT")
$script:Failures = @()

function Check([bool]$Ok, [string]$Msg) {
    if ($Ok) { Write-Host "  ok    $Msg" }
    else { Write-Host "  FAIL  $Msg" -ForegroundColor Red; $script:Failures += $Msg }
}

$TmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("abs-longpath-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TmpRoot | Out-Null
$Saved = @{}
foreach ($n in @("TEMP", "TMP", "LOCALAPPDATA")) { $Saved[$n] = [Environment]::GetEnvironmentVariable($n, "Process") }

try {
    Write-Host "A. helpers are present and extractable"
    $src = [System.IO.File]::ReadAllText($Bootstrap)
    $si = $src.IndexOf("# ai-brain:long-paths:start")
    $ei = $src.IndexOf("# ai-brain:long-paths:end")
    Check ($si -ge 0 -and $ei -gt $si) "bootstrap.ps1 carries the long-paths markers"
    if ($si -lt 0 -or $ei -le $si) { Write-Host "ERROR: cannot extract the helpers." -ForegroundColor Red; exit 1 }
    $block = $src.Substring($si, $ei - $si)
    Check ($block -notmatch "(?m)^\s*(Warn|Log|Ok|Err|Hdr|Dry)\s") "extracted block calls no bootstrap-only helper"
    $blockFile = Join-Path $TmpRoot "long-paths.ps1"
    [System.IO.File]::WriteAllText($blockFile, $block, (New-Object System.Text.UTF8Encoding($false)))
    . $blockFile
    Check ($src -match '(?m)^\$script:LongPathsChanged = @\(Initialize-LongEnvPaths\)') "bootstrap.ps1 runs it before any TEMP use"
    $first = $src.IndexOf('$env:TEMP')
    $call  = $src.IndexOf("Initialize-LongEnvPaths)")
    Check ($call -ge 0 -and $call -lt $first) "the call comes before the first use of TEMP"

    Write-Host "B. an aliased TEMP / TMP / LOCALAPPDATA is rewritten"
    $realTemp  = Join-Path $TmpRoot "Temporary Files Long Name"
    $realLocal = Join-Path $TmpRoot "Local Application Data"
    New-Item -ItemType Directory -Path $realTemp, $realLocal | Out-Null
    $aliasTemp  = "C:\Users\JUANAR~1\AppData\Local\Temp"
    $aliasLocal = "C:\Users\JUANAR~1\AppData\Local"
    $map = @{ $aliasTemp = $realTemp; $aliasLocal = $realLocal }
    $expand = { param($p) if ($map.ContainsKey($p)) { $map[$p] } else { $null } }.GetNewClosure()
    [Environment]::SetEnvironmentVariable("TEMP", $aliasTemp, "Process")
    [Environment]::SetEnvironmentVariable("TMP", $aliasTemp, "Process")
    [Environment]::SetEnvironmentVariable("LOCALAPPDATA", $aliasLocal, "Process")
    $changed = @(Initialize-LongEnvPaths $expand)
    Check ($env:TEMP -eq $realTemp) "TEMP resolved to the long folder"
    Check ($env:TMP -eq $realTemp) "TMP resolved to the long folder"
    Check ($env:LOCALAPPDATA -eq $realLocal) "LOCALAPPDATA resolved to the long folder"
    Check ($changed.Count -eq 3) "all three reported as changed (got $($changed.Count))"

    Write-Host "C. a result that is not an existing folder is never trusted"
    $bogus = Join-Path $TmpRoot "does-not-exist"
    $r = Resolve-AliasedPath $aliasTemp { param($p) $bogus }
    Check ($r -eq $aliasTemp) "missing folder -> original kept"
    $aFile = Join-Path $TmpRoot "a-file.txt"
    Set-Content -LiteralPath $aFile -Value "x"
    $r = Resolve-AliasedPath $aliasTemp { param($p) $aFile }
    Check ($r -eq $aliasTemp) "a file is not a folder -> original kept"
    $r = Resolve-AliasedPath $aliasTemp { param($p) throw "boom" }
    Check ($r -eq $aliasTemp) "an expander that throws -> original kept"
    $r = Resolve-AliasedPath "" { param($p) $realTemp }
    Check ([string]::IsNullOrEmpty($r)) "empty input stays empty"

    Write-Host "D. a path with no alias is unchanged"
    [Environment]::SetEnvironmentVariable("TEMP", $realTemp, "Process")
    [Environment]::SetEnvironmentVariable("TMP", $realTemp, "Process")
    [Environment]::SetEnvironmentVariable("LOCALAPPDATA", $realLocal, "Process")
    $changed = @(Initialize-LongEnvPaths { param($p) $p })
    Check ($changed.Count -eq 0) "same path back -> nothing changed"
    Check ($env:TEMP -eq $realTemp -and $env:LOCALAPPDATA -eq $realLocal) "values byte-identical"

    if (-not $OnWindows) {
        Write-Host "E. non-Windows resolves nothing"
        Check ($null -eq (Get-LongPath $realTemp)) "Get-LongPath returns nothing off Windows"
        $changed = @(Initialize-LongEnvPaths)
        Check ($changed.Count -eq 0) "default expander changes nothing off Windows"
    } else {
        Write-Host "F. real GetLongPathNameW on this Windows box"
        $long = Join-Path $TmpRoot "A Long Folder Name"
        New-Item -ItemType Directory -Path $long | Out-Null
        Add-Type -Namespace "AbsTest" -Name "Short" -MemberDefinition @"
[System.Runtime.InteropServices.DllImport("kernel32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
public static extern uint GetShortPathNameW(string p, System.Text.StringBuilder s, uint n);
"@
        $sb = New-Object System.Text.StringBuilder 1024
        $n = [AbsTest.Short]::GetShortPathNameW($long, $sb, 1024)
        $short = $sb.ToString()
        if ($n -eq 0 -or $short -eq $long -or $short -notmatch "~") {
            Write-Host "  SKIP  this volume has 8.3 names off; the real-resolution check did not run" -ForegroundColor Yellow
        } else {
            $got = Get-LongPath $short
            Check ($got -eq $long) "short alias $short resolves to the long folder"
            [Environment]::SetEnvironmentVariable("TEMP", $short, "Process")
            $changed = @(Initialize-LongEnvPaths)
            Check ($env:TEMP -eq $long -and $changed -contains "TEMP") "TEMP given as the real alias is resolved"
        }
    }
}
finally {
    foreach ($n in $Saved.Keys) { [Environment]::SetEnvironmentVariable($n, $Saved[$n], "Process") }
    Remove-Item -Recurse -Force -LiteralPath $TmpRoot -ErrorAction SilentlyContinue
}

Write-Host ""
if ($script:Failures.Count -gt 0) {
    Write-Host "FAILED - bootstrap.ps1 short-path handling ($($script:Failures.Count) check(s)):" -ForegroundColor Red
    foreach ($f in $script:Failures) { Write-Host "  x $f" -ForegroundColor Red }
    exit 1
}
Write-Host "PASSED - bootstrap.ps1 short-path handling" -ForegroundColor Green
exit 0
