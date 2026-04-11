# ai-brain-starter — one-command bootstrap (Windows)
#
# This script installs everything Phase 0 of /setup-brain installs, but without
# requiring you to launch Claude Code first. Run this once, then open Claude
# Code and type /setup-brain.
#
# Usage (run from PowerShell, NOT cmd.exe):
#     irm https://raw.githubusercontent.com/adelaidasofia/ai-brain-starter/main/bootstrap.ps1 | iex
#
# Safe to re-run. Skips anything already installed.

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/adelaidasofia/ai-brain-starter.git"
$SkillDir = "$env:USERPROFILE\.claude\skills\ai-brain-starter"
$Failed = @()

function Hdr($msg)  { Write-Host ""; Write-Host $msg -ForegroundColor White -BackgroundColor DarkBlue }
function Log($msg)  { Write-Host "  · $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "  + $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  ! $msg" -ForegroundColor Yellow }
function Err($msg)  { Write-Host "  X $msg" -ForegroundColor Red; $script:Failed += $msg }
function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

Hdr "ai-brain-starter — one-command install"
Write-Host ""
Write-Host "  This installs the full AI brain stack: graphify, humanizer, claude-mem,"
Write-Host "  notebooklm, meeting-todos, patterns, the Granola MCP, plus the ai-brain-starter"
Write-Host "  skill itself. Takes ~5 minutes the first time."
Write-Host ""
Write-Host "  After this finishes, open Claude Code and type /setup-brain."
Write-Host ""
Start-Sleep -Seconds 1

# ─── winget check ─────────────────────────────────────────────────────────────
if (-not (Have winget)) {
    Err "winget is required (Windows 11 / recent Windows 10). Install App Installer from the Microsoft Store and re-run."
    return
}

# ─── Python 3.10+ ─────────────────────────────────────────────────────────────
$pythonOk = $false
try {
    $v = (python --version 2>&1) -replace 'Python ',''
    if ([version]$v -ge [version]"3.10") { $pythonOk = $true }
} catch {}
if (-not $pythonOk) {
    Hdr "Installing Python 3.12"
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
if (Have python) { Ok "python $(python --version)" } else { Err "python install failed" }

# ─── Node.js ──────────────────────────────────────────────────────────────────
if (-not (Have node)) {
    Hdr "Installing Node.js"
    winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
if (Have node) { Ok "node $(node --version)" } else { Err "node install failed" }

# ─── pipx ─────────────────────────────────────────────────────────────────────
if (-not (Have pipx)) {
    Hdr "Installing pipx"
    python -m pip install --user pipx
    python -m pipx ensurepath
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (Have pipx) { Ok "pipx" } else { Err "pipx install failed" }

# ─── bun ──────────────────────────────────────────────────────────────────────
if (-not (Have bun) -and -not (Test-Path "$env:USERPROFILE\.bun\bin\bun.exe")) {
    Hdr "Installing bun (claude-mem dependency)"
    irm bun.sh/install.ps1 | iex
}
if ((Have bun) -or (Test-Path "$env:USERPROFILE\.bun\bin\bun.exe")) { Ok "bun installed" } else { Err "bun install failed" }

# ─── gh (GitHub CLI) ──────────────────────────────────────────────────────────
if (-not (Have gh)) {
    Hdr "Installing gh"
    winget install -e --id GitHub.cli --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
if (Have gh) { Ok "gh installed" } else { Warn "gh not installed — install manually if needed" }

# ─── graphify ─────────────────────────────────────────────────────────────────
if (-not (Have graphify)) {
    Hdr "Installing graphify (knowledge graph builder)"
    pipx install graphifyy
    graphify install --platform windows
}
if (Have graphify) { Ok "graphify" } else { Err "graphify install failed" }

# ─── Clone or update ai-brain-starter ─────────────────────────────────────────
Hdr "Installing the ai-brain-starter skill"
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude\skills" | Out-Null
if (Test-Path "$SkillDir\.git") {
    Log "Already installed, pulling latest..."
    Push-Location $SkillDir
    git pull --quiet
    Pop-Location
} else {
    git clone --quiet $RepoUrl $SkillDir
}
if (Test-Path "$SkillDir\SKILL.md") { Ok "ai-brain-starter at $SkillDir" } else { Err "ai-brain-starter clone failed" }

# ─── Sub-skills ──────────────────────────────────────────────────────────────
Hdr "Installing bundled sub-skills"
foreach ($sub in @("graphify", "meeting-todos", "patterns")) {
    $src = "$SkillDir\skills\$sub"
    $dst = "$env:USERPROFILE\.claude\skills\$sub"
    if (Test-Path $src) {
        New-Item -ItemType Directory -Force -Path $dst | Out-Null
        Copy-Item -Recurse -Force "$src\*" $dst
        Ok "$sub skill installed"
    } else {
        Err "$sub skill source missing in repo"
    }
}

# ─── Humanizer ────────────────────────────────────────────────────────────────
$humDir = "$env:USERPROFILE\.claude\skills\humanizer"
if (-not (Test-Path $humDir)) {
    Hdr "Installing humanizer"
    git clone --quiet https://github.com/adelaidasofia/humanizer.git $humDir
}
if (Test-Path $humDir) { Ok "humanizer skill installed" } else { Err "humanizer clone failed" }

# ─── NotebookLM ──────────────────────────────────────────────────────────────
$nblmDir = "$env:USERPROFILE\.claude\skills\notebooklm"
if (-not (Test-Path $nblmDir)) {
    Hdr "Installing notebooklm"
    git clone --quiet https://github.com/PleasePrompto/notebooklm-skill.git $nblmDir
}
if (Test-Path $nblmDir) { Ok "notebooklm skill installed" } else { Err "notebooklm clone failed" }

# ─── claude-mem ──────────────────────────────────────────────────────────────
Hdr "Registering claude-mem"
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude" | Out-Null

$pyScript = @"
import json, os
p = os.path.expanduser('~/.claude/settings.json')
try:
    with open(p) as f: s = json.load(f)
except FileNotFoundError:
    s = {}
s.setdefault('extraKnownMarketplaces', {})
if 'thedotmack' not in s['extraKnownMarketplaces']:
    s['extraKnownMarketplaces']['thedotmack'] = {'source': {'source': 'github', 'repo': 'thedotmack/claude-mem'}}
s.setdefault('enabledPlugins', {})['claude-mem@thedotmack'] = True
with open(p, 'w') as f: json.dump(s, f, indent=2)
"@
$pyScript | python -
if ($LASTEXITCODE -eq 0) { Ok "claude-mem registered" } else { Err "claude-mem registration failed" }
npx --yes claude-mem install 2>$null | Out-Null

# ─── Granola MCP ─────────────────────────────────────────────────────────────
Hdr "Registering Granola MCP"
$pyMcp = @"
import json, os
p = os.path.expanduser('~/.claude/.mcp.json')
try:
    with open(p) as f: m = json.load(f)
except FileNotFoundError:
    m = {'mcpServers': {}}
m.setdefault('mcpServers', {})
if 'granola' not in m['mcpServers']:
    m['mcpServers']['granola'] = {'type': 'url', 'url': 'https://mcp.granola.ai/mcp'}
with open(p, 'w') as f: json.dump(m, f, indent=2)
"@
$pyMcp | python -
if ($LASTEXITCODE -eq 0) { Ok "Granola MCP registered (you'll need a Granola account to use it)" } else { Err "Granola MCP registration failed" }

# ─── Verification ────────────────────────────────────────────────────────────
Hdr "Verifying installation"
foreach ($pair in @(@("graphify","graphify"), @("node","node"), @("npm","npm"), @("pipx","pipx"), @("gh","gh"))) {
    if (Have $pair[1]) { Ok $pair[0] } else { Err "$($pair[0]) not callable" }
}
if ((Have bun) -or (Test-Path "$env:USERPROFILE\.bun\bin\bun.exe")) { Ok "bun" } else { Err "bun not found" }

foreach ($sub in @("graphify","meeting-todos","patterns","humanizer","notebooklm","ai-brain-starter")) {
    if (Test-Path "$env:USERPROFILE\.claude\skills\$sub") { Ok "skill: $sub" } else { Err "skill missing: $sub" }
}
if (Test-Path "$env:USERPROFILE\.claude\skills\graphify\scripts") { Ok "graphify scripts" } else { Err "graphify scripts missing" }

if ((Get-Content "$env:USERPROFILE\.claude\settings.json" -ErrorAction SilentlyContinue) -match "claude-mem@thedotmack") {
    Ok "claude-mem registered in settings.json"
} else { Err "claude-mem not in settings.json" }

if ((Get-Content "$env:USERPROFILE\.claude\.mcp.json" -ErrorAction SilentlyContinue) -match "granola") {
    Ok "granola MCP in .mcp.json"
} else { Err "granola not in .mcp.json" }

Write-Host ""
if ($Failed.Count -eq 0) {
    Write-Host "━━━ All checks passed. ━━━" -ForegroundColor Green
} else {
    Write-Host "━━━ $($Failed.Count) check(s) failed: ━━━" -ForegroundColor Red
    foreach ($f in $Failed) { Write-Host "  • $f" }
    Write-Host ""
    Write-Host "Don't proceed silently — fix these before running /setup-brain."
}

Write-Host ""
Write-Host "━━━ Next steps ━━━" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. Open Claude Code in the directory where you want your vault to live."
Write-Host "     (For a NEW personal vault: a fresh empty folder.)"
Write-Host "     (For JOINING an existing team vault: cd into the team vault folder first.)"
Write-Host ""
Write-Host "  2. Type ONE of these:"
Write-Host ""
Write-Host "       /setup-brain                  # New personal vault — full conversational setup"
Write-Host "       /setup-brain join-team        # Joining an existing team vault — minimal setup"
Write-Host ""
Write-Host "  3. The setup is conversational. Answer the questions Claude asks."
Write-Host ""
Write-Host "━━━ Optional — image generation ━━━" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Nano Banana requires running /plugin commands inside Claude Code:"
Write-Host ""
Write-Host "       /plugin marketplace add devonjones/devon-claude-skills"
Write-Host "       /plugin install nano-banana@devon-claude-skills"
Write-Host ""
Write-Host "  And set GEMINI_API_KEY as a Windows env var (persists across sessions):"
Write-Host ""
Write-Host "       setx GEMINI_API_KEY your_key_here"
Write-Host ""
Write-Host "  Get the key at https://ai.google.dev/"
Write-Host ""
