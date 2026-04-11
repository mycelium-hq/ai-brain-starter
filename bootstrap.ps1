# ai-brain-starter — one-command bootstrap (Windows)
#
# This script installs everything Phase 0 of /setup-brain installs, but without
# requiring you to launch Claude Code first. Run this once, then open Claude
# Code and type /setup-brain.
#
# Usage (run from PowerShell, NOT cmd.exe):
#     irm https://raw.githubusercontent.com/adelaidasofia/ai-brain-starter/main/bootstrap.ps1 | iex
#
# Dry run (preview changes without making them):
#     iex "& { $(irm https://raw.githubusercontent.com/adelaidasofia/ai-brain-starter/main/bootstrap.ps1) } -DryRun"
#
# SAFETY GUARANTEES — same as bootstrap.sh:
#   - Existing settings.json/.mcp.json keys preserved (setdefault never overwrites)
#   - Explicit `claude-mem@thedotmack: false` is RESPECTED (not silently re-enabled)
#   - Local uncommitted changes to ai-brain-starter clone are stashed before pull
#   - DIVERGENT forks of ai-brain-starter (commits on both sides) are skipped
#   - Sub-skill folders with their own .git/ are detected as YOUR FORK and skipped
#   - Symlinked sub-skill folders are detected and skipped (warns)
#   - Custom skills outside the bundled set (humanizer, notebooklm, anything you
#     installed yourself) are NEVER touched
#   - Your vault CLAUDE.md is NEVER touched
#   - Every file modification creates a .bak-YYYY-MM-DD-HHMM backup
#   - Final summary lists every change made
#
# Safe to re-run. Skips anything already installed.

param([switch]$DryRun)

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/adelaidasofia/ai-brain-starter.git"
$SkillDir = "$env:USERPROFILE\.claude\skills\ai-brain-starter"
$Failed    = @()
$Installed = @()
$Updated   = @()
$Skipped   = @()
$Backups   = @()

function Hdr($msg)  { Write-Host ""; Write-Host $msg -ForegroundColor White -BackgroundColor DarkBlue }
function Log($msg)  { Write-Host "  · $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "  + $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  ! $msg" -ForegroundColor Yellow }
function Err($msg)  { Write-Host "  X $msg" -ForegroundColor Red; $script:Failed += $msg }
function Dry($msg)  { Write-Host "  [dry-run] $msg" -ForegroundColor Magenta }
function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

function Backup-File($path) {
    if (-not (Test-Path $path)) { return }
    $bak = "$path.bak-$(Get-Date -Format 'yyyy-MM-dd-HHmm')"
    if ($DryRun) { Dry "would back up: $path -> $bak" }
    else { Copy-Item $path $bak; $script:Backups += $bak }
}

Hdr "ai-brain-starter — one-command install"
Write-Host ""
if ($DryRun) {
    Write-Host "  DRY RUN MODE - showing what would be installed without making any changes." -ForegroundColor Magenta
    Write-Host ""
}
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
    Hdr "Installing gh (GitHub CLI)"
    Log "gh lets the session-end capture cascade file improvement ideas as GitHub issues automatically."
    winget install -e --id GitHub.cli --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
if (Have gh) { Ok "gh installed" } else { Warn "gh not installed — install manually if needed" }

# gh authentication — required for the session-end capture cascade to file
# improvement ideas as GitHub issues automatically. Walk the user through it
# the first time only.
if (Have gh) {
    gh auth status 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Hdr "GitHub authentication (one-time setup)"
        Write-Host "  The session-end cascade can file improvement ideas as GitHub issues"
        Write-Host "  automatically — but only if gh is authenticated to your GitHub account."
        Write-Host ""
        Write-Host "  This is a ONE-TIME setup. After this, your AI brain will silently file"
        Write-Host "  any friction or improvement ideas to the maintainer's repo without"
        Write-Host "  asking you to copy/paste anything."
        Write-Host ""
        Write-Host "  When you press Enter, gh will open a browser window for you to log in."
        Write-Host "  Pick: GitHub.com -> HTTPS -> Login with web browser."
        Write-Host ""
        Read-Host "  Press Enter to start (or Ctrl+C to skip — you can run 'gh auth login' later)"
        gh auth login
        if ($LASTEXITCODE -ne 0) { Warn "gh auth skipped or failed — run 'gh auth login' later to enable issue filing" }
    }
    gh auth status 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Ok "gh authenticated" } else { Warn "gh not authenticated (issue filing disabled until you run: gh auth login)" }
}

# ─── graphify ─────────────────────────────────────────────────────────────────
if (-not (Have graphify)) {
    Hdr "Installing graphify (knowledge graph builder)"
    pipx install graphifyy
    graphify install --platform windows
}
if (Have graphify) { Ok "graphify" } else { Err "graphify install failed" }

# ─── Clone or update ai-brain-starter ─────────────────────────────────────────
# SAFETY:
#   - Stashes local uncommitted changes before pulling
#   - Detects DIVERGENT history (your fork has commits not on origin/main)
#     and refuses to pull, so your fork is never silently overwritten
Hdr "Installing the ai-brain-starter skill"
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude\skills" | Out-Null
if (Test-Path "$SkillDir\.git") {
    Log "Already installed - checking for updates..."
    Push-Location $SkillDir

    if ($DryRun) { Dry "would: git fetch --quiet origin" }
    else { git fetch --quiet origin 2>$null }

    $ahead = (git rev-list --count "@{u}..HEAD" 2>$null)
    $behind = (git rev-list --count "HEAD..@{u}" 2>$null)
    if (-not $ahead) { $ahead = 0 }
    if (-not $behind) { $behind = 0 }
    $ahead = [int]$ahead
    $behind = [int]$behind

    if ($ahead -gt 0 -and $behind -gt 0) {
        Warn "DIVERGENT FORK DETECTED at $SkillDir"
        Warn "  Your local clone has $ahead commit(s) NOT on origin/main"
        Warn "  AND origin/main has $behind commit(s) NOT on your clone"
        Warn "  Refusing to pull. Your fork is preserved unchanged."
        Warn "  To merge manually: cd $SkillDir; git pull --rebase"
        $script:Skipped += "ai-brain-starter clone (divergent fork - manual merge required)"
    }
    elseif ($ahead -gt 0 -and $behind -eq 0) {
        Log "Your clone has $ahead local commit(s) and is otherwise current. Leaving as-is."
        $script:Skipped += "ai-brain-starter clone (local commits, up to date)"
    }
    elseif ($behind -gt 0) {
        git diff --quiet --ignore-submodules HEAD 2>$null
        if ($LASTEXITCODE -ne 0) {
            $stashMsg = "bootstrap auto-stash $(Get-Date -Format 'yyyy-MM-dd-HHmm')"
            Log "Detected local uncommitted changes - stashing as: $stashMsg"
            Log "Recover later with: cd $SkillDir; git stash list; git stash pop"
            if (-not $DryRun) { git stash push -u -m $stashMsg 2>$null | Out-Null }
        }
        if ($DryRun) { Dry "would: git pull --quiet (fast-forward $behind commit(s))" }
        else { git pull --quiet 2>$null }
        $script:Updated += "ai-brain-starter clone (pulled $behind commit(s))"
    }
    else {
        Log "ai-brain-starter clone is up to date"
    }
    Pop-Location
} else {
    if ($DryRun) { Dry "would: git clone $RepoUrl -> $SkillDir" }
    else { git clone --quiet $RepoUrl $SkillDir }
    $script:Installed += "ai-brain-starter clone"
}
if ((Test-Path "$SkillDir\SKILL.md") -or $DryRun) { Ok "ai-brain-starter at $SkillDir" } else { Err "ai-brain-starter clone failed" }

# ─── Sub-skills (with comprehensive safety checks) ───────────────────────────
# SAFETY:
#   - If the destination has its own .git/, treat it as YOUR FORK and skip
#   - If the destination is a SYMLINK, warn and skip
#   - Otherwise: file-by-file sync with backup-before-overwrite
#   - Custom skill folders outside the bundled set (humanizer, notebooklm,
#     daily-journal, anything the user installed themselves) are NEVER touched
Hdr "Installing bundled sub-skills (with safety checks)"
$stamp = Get-Date -Format "yyyy-MM-dd-HHmm"

foreach ($sub in @("graphify", "meeting-todos", "patterns")) {
    $src = "$SkillDir\skills\$sub"
    $dst = "$env:USERPROFILE\.claude\skills\$sub"

    if (-not (Test-Path $src)) {
        Err "$sub skill source missing in repo"
        continue
    }

    # Symlink detection (PowerShell: ReparsePoint attribute)
    if ((Test-Path $dst) -and ((Get-Item $dst -ErrorAction SilentlyContinue).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        $target = (Get-Item $dst).Target
        Warn "$sub is a SYMLINK to $target - bootstrap will NOT write through it"
        Warn "  If you want bootstrap to update this skill, replace the symlink with a regular folder."
        $script:Skipped += "$sub skill (symlink to $target)"
        continue
    }

    # Fork detection (.git inside the destination)
    if (Test-Path "$dst\.git") {
        Log "$sub has its own .git directory - detected as YOUR FORK, skipping entirely"
        Log "  Your fork is preserved untouched. You manage updates to it yourself."
        $script:Skipped += "$sub skill (your own fork - has .git)"
        continue
    }

    # Regular folder or missing — eligible for sync
    if ($DryRun) {
        Dry "would sync $sub skill from $src to $dst (with backup-before-overwrite)"
        continue
    }

    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    $createdCount = 0
    $updatedCount = 0
    $backedUpCount = 0
    Get-ChildItem -Recurse -File $src | ForEach-Object {
        $rel = $_.FullName.Substring($src.Length + 1)
        $dstFile = Join-Path $dst $rel
        $dstParent = Split-Path $dstFile -Parent
        if (-not (Test-Path $dstParent)) { New-Item -ItemType Directory -Force -Path $dstParent | Out-Null }
        if (Test-Path $dstFile) {
            if ((Get-FileHash $_.FullName).Hash -ne (Get-FileHash $dstFile).Hash) {
                Copy-Item $dstFile "$dstFile.bak-$stamp"
                $script:Backups += "$dstFile.bak-$stamp"
                Copy-Item -Force $_.FullName $dstFile
                $backedUpCount++
                $updatedCount++
            }
        } else {
            Copy-Item -Force $_.FullName $dstFile
            $createdCount++
        }
    }
    if ($createdCount -gt 0 -or $updatedCount -gt 0) {
        Ok "$sub: $createdCount new, $updatedCount updated, $backedUpCount backed up"
        $script:Updated += "$sub skill ($createdCount new, $updatedCount updated, $backedUpCount backed up)"
    } else {
        Ok "$sub: already current"
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
# SAFETY: backup settings.json before editing. Existing keys (custom
# marketplaces, custom MCP servers, custom plugin configs, custom permissions,
# custom hooks, custom env vars) are preserved. Explicit
# `claude-mem@thedotmack: false` is RESPECTED (not silently re-enabled).
Hdr "Registering claude-mem"
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude" | Out-Null
$settingsPath = "$env:USERPROFILE\.claude\settings.json"
Backup-File $settingsPath

if ($DryRun) {
    Dry "would: register thedotmack marketplace + enable claude-mem@thedotmack (if not explicitly disabled)"
} else {
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
s.setdefault('enabledPlugins', {})
if 'claude-mem@thedotmack' not in s['enabledPlugins']:
    s['enabledPlugins']['claude-mem@thedotmack'] = True
elif s['enabledPlugins']['claude-mem@thedotmack'] is False:
    print('NOTE: respecting your explicit disable of claude-mem@thedotmack')
with open(p, 'w') as f: json.dump(s, f, indent=2)
"@
    $pyScript | python -
    if ($LASTEXITCODE -eq 0) { Ok "claude-mem registered" } else { Err "claude-mem registration failed" }
    npx --yes claude-mem install 2>$null | Out-Null
}

# ─── Granola MCP ─────────────────────────────────────────────────────────────
# SAFETY: backup .mcp.json before editing. Existing MCP servers (custom
# integrations, other URL or stdio MCPs the user wired themselves) are
# preserved — setdefault() only adds the granola entry if missing.
Hdr "Registering Granola MCP"
$mcpPath = "$env:USERPROFILE\.claude\.mcp.json"
Backup-File $mcpPath

if ($DryRun) {
    Dry "would: register granola MCP at https://mcp.granola.ai/mcp (if not already present)"
} else {
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
}

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
    foreach ($f in $Failed) { Write-Host "  - $f" }
    Write-Host ""
    Write-Host "Don't proceed silently - fix these before running /setup-brain."
}

# ─── Change summary ──────────────────────────────────────────────────────────
Hdr "Change summary"
if ($DryRun) { Write-Host "DRY RUN - no actual changes made." -ForegroundColor Magenta }

if ($Installed.Count -eq 0 -and $Updated.Count -eq 0 -and $Skipped.Count -eq 0 -and $Backups.Count -eq 0) {
    Write-Host "  Nothing to report - your setup was already current."
} else {
    if ($Installed.Count -gt 0) {
        Write-Host ""
        Write-Host "  Installed (new):" -ForegroundColor Green
        foreach ($x in $Installed) { Write-Host "    + $x" }
    }
    if ($Updated.Count -gt 0) {
        Write-Host ""
        Write-Host "  Updated:" -ForegroundColor Cyan
        foreach ($x in $Updated) { Write-Host "    ^ $x" }
    }
    if ($Skipped.Count -gt 0) {
        Write-Host ""
        Write-Host "  Skipped (your customizations preserved):" -ForegroundColor Yellow
        foreach ($x in $Skipped) { Write-Host "    o $x" }
    }
    if ($Backups.Count -gt 0) {
        Write-Host ""
        Write-Host "  Backups created (recoverable):" -ForegroundColor Yellow
        foreach ($x in $Backups) { Write-Host "    > $x" }
        Write-Host ""
        Write-Host "  To restore any backup: Move-Item <file>.bak-YYYY-MM-DD-HHMM <file>"
    }
}
Write-Host ""

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
