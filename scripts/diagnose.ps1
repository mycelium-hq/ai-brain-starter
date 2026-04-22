# diagnose.ps1 - Self-check for an installed AI Brain Starter vault.
# Windows port of diagnose.sh. Runs ~10 checks, prints green/yellow/red.
#
# Usage:
#   pwsh diagnose.ps1                      # use $env:VAULT_PATH or current dir
#   pwsh diagnose.ps1 -Vault C:\path\vault
#
# Exit codes: 0 = all green, 1 = at least one FAIL, 2 = only WARNs.
#
# This file MUST start with a UTF-8 BOM (EF BB BF). Windows PowerShell 5.1
# reads BOM-less .ps1 as Windows-1252 and crashes on non-ASCII bytes.
# Verify with: Get-Content -Encoding Byte -TotalCount 3 diagnose.ps1
# Should print: 239 187 191

param(
  [string]$Vault = $env:VAULT_PATH
)

$script:Green  = 0
$script:Yellow = 0
$script:Red    = 0

function Section($title) { Write-Host ""; Write-Host $title -ForegroundColor Cyan }
function Ok($msg)        { Write-Host "  OK    $msg" -ForegroundColor Green;  $script:Green++ }
function Warn($msg, $hint = $null) {
  Write-Host "  WARN  $msg" -ForegroundColor Yellow
  if ($hint) { Write-Host "        -> $hint" -ForegroundColor DarkYellow }
  $script:Yellow++
}
function Bad($msg, $hint = $null) {
  Write-Host "  FAIL  $msg" -ForegroundColor Red
  if ($hint) { Write-Host "        -> $hint" -ForegroundColor DarkRed }
  $script:Red++
}

# ----- locate vault -----
if (-not $Vault) { $Vault = (Get-Location).Path }
if (-not (Test-Path -LiteralPath $Vault -PathType Container)) {
  Write-Host "Vault path not a directory: $Vault" -ForegroundColor Red
  Write-Host "Pass the vault path: pwsh diagnose.ps1 -Vault C:\path\to\vault"
  exit 1
}
$Vault = (Resolve-Path -LiteralPath $Vault).Path

Write-Host "AI Brain Starter diagnostics" -ForegroundColor White
Write-Host "Vault: $Vault"

# ----- 1. CLAUDE.md -----
Section "1. Vault memory (CLAUDE.md)"
$claudeMd = Join-Path $Vault "CLAUDE.md"
if (Test-Path -LiteralPath $claudeMd) {
  $size = (Get-Item -LiteralPath $claudeMd).Length
  if ($size -lt 200) {
    Warn "CLAUDE.md exists but is tiny ($size bytes)" "Re-run /setup-brain Phase 4."
  } else {
    Ok "CLAUDE.md present ($size bytes)"
  }
  if (Select-String -LiteralPath $claudeMd -Pattern "## Vault Map" -Quiet) {
    Ok "Vault Map section present"
  } else {
    Warn "No '## Vault Map' section in CLAUDE.md" "Claude will create duplicate folders without it."
  }
} else {
  Bad "CLAUDE.md missing" "Run /setup-brain Phase 4."
}

# ----- 2. Meta folder -----
Section "2. Meta folder"
$meta = Join-Path $Vault "$([char]0x2699)$([char]0xFE0F) Meta"
if (Test-Path -LiteralPath $meta -PathType Container) {
  Ok "Meta/ folder present"
  foreach ($sub in @("scripts", "rules")) {
    if (Test-Path -LiteralPath (Join-Path $meta $sub) -PathType Container) {
      Ok "Meta/$sub/ present"
    } else {
      Warn "Meta/$sub/ missing"
    }
  }
} else {
  Bad "Meta/ folder missing" "Run /setup-brain Phase 3."
}

# ----- 3. Skills installed -----
Section "3. Claude Code skills"
$skillsDir = Join-Path $env:USERPROFILE ".claude\skills"
if (Test-Path -LiteralPath $skillsDir -PathType Container) {
  Ok "~/.claude/skills/ exists"
  if (Test-Path -LiteralPath (Join-Path $skillsDir "ai-brain-starter") -PathType Container) {
    Ok "ai-brain-starter skill installed"
  } else {
    Warn "ai-brain-starter skill not in ~/.claude/skills/" "Re-run bootstrap to clone it."
  }
  if (Test-Path -LiteralPath (Join-Path $skillsDir "daily-journal") -PathType Container) {
    Ok "daily-journal skill installed"
  } else {
    Warn "daily-journal skill not installed" "/setup-brain Phase 10a creates it."
  }
} else {
  Bad "~/.claude/skills/ missing" "Claude Code may not be installed."
}

# ----- 4. Hooks -----
Section "4. Claude Code hooks"
$settings      = Join-Path $env:USERPROFILE ".claude\settings.json"
$localSettings = Join-Path $Vault ".claude\settings.local.json"
$hookFound = $false
foreach ($f in @($settings, $localSettings)) {
  if ((Test-Path -LiteralPath $f) -and (Select-String -LiteralPath $f -Pattern '"hooks"' -Quiet)) {
    $hookFound = $true
    Ok "hooks registered in $f"
  }
}
if (-not $hookFound) {
  Warn "No hooks registered" "/setup-brain Phase 5 wires them. Without them, no auto context-loading."
}

$gch = Join-Path $meta "scripts\graph-context-hook.sh"
if (Test-Path -LiteralPath $gch) {
  Ok "graph-context-hook.sh present (Bash, runs in WSL/Git Bash on Windows)"
} else {
  Warn "graph-context-hook.sh not in Meta/scripts/" "Phase 5 installs it."
}

# ----- 5. Insights pipeline -----
Section "5. Insights pipeline"
$index = Join-Path $meta "journal-index.json"
if (Test-Path -LiteralPath $index) {
  $ageDays = [int]((Get-Date) - (Get-Item -LiteralPath $index).LastWriteTime).TotalDays
  if ($ageDays -gt 14) {
    Warn "journal-index.json is $ageDays days old" "Re-run build-journal-index.py or /weekly to refresh."
  } else {
    Ok "journal-index.json is fresh ($ageDays days old)"
  }
  try {
    Get-Content -LiteralPath $index -Raw | ConvertFrom-Json | Out-Null
    Ok "journal-index.json is valid JSON"
  } catch {
    Bad "journal-index.json is malformed" "Delete it and re-run build-journal-index.py."
  }
} else {
  Warn "No journal-index.json yet" "/weekly or /monthly will build it on first run."
}

# ----- 6. Required CLI tools -----
Section "6. Required CLI tools"
foreach ($tool in @("git", "python", "python3")) {
  if (Get-Command $tool -ErrorAction SilentlyContinue) {
    Ok "$tool installed"
  } elseif ($tool -eq "python3") {
    # On Windows the binary is usually 'python', so this is fine if python is present
    if (Get-Command python -ErrorAction SilentlyContinue) {
      Ok "python3 available (as 'python')"
    } else {
      Bad "python missing" "Install from python.org or 'winget install Python.Python.3.12'"
    }
  } elseif ($tool -eq "python") {
    # handled above
  } else {
    Bad "$tool missing" "Install $tool. 'winget install Git.Git' for git."
  }
}

# ----- 7. Vault git -----
Section "7. Vault git status"
if (Test-Path -LiteralPath (Join-Path $Vault ".git") -PathType Container) {
  Ok "Vault is a git repo (snapshot history available)"
  Push-Location -LiteralPath $Vault
  $remote = git remote -v 2>$null | Select-Object -First 1
  Pop-Location
  if ($remote) {
    Warn "Vault has a git remote: $remote" "Vaults are usually local-only."
  } else {
    Ok "No git remote (correct for a private vault)"
  }
} else {
  Warn "Vault is not a git repo" "You won't have rollback history. Optional but recommended."
}

# ----- 8. .ps1 sanity -----
Section "8. PowerShell files (Windows compat)"
$searchRoots = @($Vault, (Join-Path $env:USERPROFILE ".claude\skills\ai-brain-starter")) | Where-Object { Test-Path -LiteralPath $_ }
$ps1Files = @()
foreach ($root in $searchRoots) {
  $ps1Files += Get-ChildItem -LiteralPath $root -Recurse -Filter '*.ps1' -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\\.git\\' }
}
if ($ps1Files.Count -eq 0) {
  Ok "No .ps1 files to check"
} else {
  $bomFail = 0; $emFail = 0; $parseFail = 0
  foreach ($f in $ps1Files) {
    $bytes = [System.IO.File]::ReadAllBytes($f.FullName)
    if ($bytes.Length -lt 3 -or $bytes[0] -ne 0xEF -or $bytes[1] -ne 0xBB -or $bytes[2] -ne 0xBF) {
      $bomFail++
    }
    $text = [System.Text.Encoding]::UTF8.GetString($bytes)
    if ($text.Contains([char]0x2014)) { $emFail++ }
    $tokens = $null; $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
      $f.FullName, [ref]$tokens, [ref]$errors) | Out-Null
    if ($errors -and $errors.Count -gt 0) { $parseFail++ }
  }
  if ($bomFail -eq 0) { Ok "All .ps1 files have UTF-8 BOM" }
  else { Warn "$bomFail .ps1 file(s) missing UTF-8 BOM" "PS 5.1 will crash on non-ASCII." }
  if ($emFail -eq 0) { Ok "No em dashes in .ps1 files" }
  else { Warn "$emFail .ps1 file(s) contain em dashes" "Replace with ASCII hyphens." }
  if ($parseFail -eq 0) { Ok "All .ps1 files parse cleanly" }
  else { Bad "$parseFail .ps1 file(s) have parser errors" "Run pwsh on each to see the error." }
}

# ----- 9. MCP config -----
Section "9. MCP servers"
$mcpLocal  = Join-Path $Vault ".mcp.json"
$mcpGlobal = Join-Path $env:USERPROFILE ".claude.json"
$mcpFound = $false
foreach ($f in @($mcpLocal, $mcpGlobal)) {
  if ((Test-Path -LiteralPath $f) -and (Select-String -LiteralPath $f -Pattern '"mcpServers"' -Quiet)) {
    $mcpFound = $true
    try {
      Get-Content -LiteralPath $f -Raw | ConvertFrom-Json | Out-Null
      Ok "MCP config valid: $f"
    } catch {
      Bad "MCP config malformed: $f" "Invalid JSON. Fix the file."
    }
  }
}
if (-not $mcpFound) { Warn "No MCP config found" "MCPs are optional." }

# ----- 10. ai-brain-starter freshness -----
Section "10. ai-brain-starter freshness"
$absDir = Join-Path $env:USERPROFILE ".claude\skills\ai-brain-starter"
if (Test-Path -LiteralPath (Join-Path $absDir ".git") -PathType Container) {
  Push-Location -LiteralPath $absDir
  $localSha = (git rev-parse HEAD 2>$null)
  if ($localSha) { $localSha = $localSha.Substring(0, 7) }
  $fetchOk = $false
  try { git fetch origin main --quiet 2>$null; $fetchOk = $true } catch {}
  if ($fetchOk) {
    $remoteSha = (git rev-parse origin/main 2>$null)
    if ($remoteSha) { $remoteSha = $remoteSha.Substring(0, 7) }
    if ($localSha -eq $remoteSha) {
      Ok "ai-brain-starter is up to date ($localSha)"
    } else {
      $behind = (git rev-list --count "$localSha..$remoteSha" 2>$null)
      Warn "ai-brain-starter is $behind commit(s) behind origin/main" "cd $absDir; git pull"
    }
  } else {
    Warn "Could not fetch from origin (offline?)"
  }
  Pop-Location
} else {
  Warn "ai-brain-starter is not a git repo" "Re-run bootstrap.ps1 to clone it."
}

# ----- summary -----
Write-Host ""
Write-Host "Summary" -ForegroundColor White
Write-Host "  OK:   $script:Green"  -ForegroundColor Green
Write-Host "  WARN: $script:Yellow" -ForegroundColor Yellow
Write-Host "  FAIL: $script:Red"    -ForegroundColor Red
Write-Host ""

if ($script:Red -gt 0) {
  Write-Host "Something is broken. Fix the FAILs above, then re-run." -ForegroundColor Red
  exit 1
} elseif ($script:Yellow -gt 0) {
  Write-Host "Working, with caveats. Address WARNs when convenient." -ForegroundColor Yellow
  exit 2
} else {
  Write-Host "All green. Your second brain is healthy." -ForegroundColor Green
  exit 0
}
