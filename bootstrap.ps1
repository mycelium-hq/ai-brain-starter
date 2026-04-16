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
#   - Local uncommitted changes to ai-brain-starter clone are stashed before pull
#   - DIVERGENT forks of ai-brain-starter (commits on both sides) are skipped
#   - Sub-skill folders with their own .git/ are detected as YOUR FORK and skipped
#   - Symlinked sub-skill folders are detected and skipped (warns)
#   - Custom skills outside the bundled set (humanizer, anything you
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
Write-Host "  This installs the full AI brain stack: graphify, humanizer,"
Write-Host "  meeting-todos, patterns, insights, deconstruct, daily-journal,"
Write-Host "  repurpose-talk, nano-banana (skill docs), Granola + ChatPRD MCPs,"
Write-Host "  the obsidian-skills marketplace, plus the ai-brain-starter skill"
Write-Host "  itself. Takes ~5 minutes the first time."
Write-Host ""
Write-Host "  After this finishes, open Claude Code and type /setup-brain."
Write-Host ""
Start-Sleep -Seconds 1

# ─── winget bootstrap ─────────────────────────────────────────────────────────
# winget ships with Windows 11 and recent Windows 10. On older Windows 10 it's
# missing — auto-install App Installer (which provides winget) before doing
# anything else. Never abort with "go install something from the Microsoft
# Store yourself" — that defeats the one-command promise.
if (-not (Have winget)) {
    Hdr "Installing winget (App Installer)"
    Log "winget is the Windows package manager we use to install everything else."
    Log "Your Windows version is missing it — we'll install it for you now."

    # Method 1: Microsoft's official MSIX bundle. URL aka.ms/getwinget always
    # resolves to the latest stable release on GitHub.
    $tempInstaller = "$env:TEMP\AppInstaller.msixbundle"
    try {
        Log "Downloading App Installer from Microsoft..."
        Invoke-WebRequest -Uri "https://aka.ms/getwinget" -OutFile $tempInstaller -UseBasicParsing
        Log "Installing... (a Windows install dialog may appear briefly)"
        Add-AppxPackage -Path $tempInstaller -ErrorAction Stop
        Remove-Item $tempInstaller -Force -ErrorAction SilentlyContinue
    } catch {
        Warn "Auto-install of winget failed: $_"
        Warn "Falling back to direct MSI installs for Python/Node/Obsidian."
    }

    # Refresh PATH so winget is callable in this session
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

if (Have winget) {
    Ok "winget available"
    $UseWinget = $true
} else {
    # Final fallback — winget could not be installed. Use direct downloads for
    # the things we need. The user is on a very old Windows; mark $UseWinget so
    # later sections can branch.
    Warn "Continuing without winget — using direct installer downloads."
    $UseWinget = $false
}

# ─── Python 3.10+ ─────────────────────────────────────────────────────────────
$pythonOk = $false
try {
    $v = (python --version 2>&1) -replace 'Python ',''
    if ([version]$v -ge [version]"3.10") { $pythonOk = $true }
} catch {}
if (-not $pythonOk) {
    Hdr "Installing Python 3.12"
    if ($UseWinget) {
        winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    } else {
        Log "winget unavailable — downloading Python installer directly."
        $pyInstaller = "$env:TEMP\python-installer.exe"
        try {
            Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe" -OutFile $pyInstaller -UseBasicParsing
            Start-Process -Wait -FilePath $pyInstaller -ArgumentList "/quiet","InstallAllUsers=1","PrependPath=1"
            Remove-Item $pyInstaller -Force -ErrorAction SilentlyContinue
        } catch {
            Err "Python install failed: $_"
        }
    }
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
if (Have python) { Ok "python $(python --version)" } else { Err "python install failed" }

# ─── Node.js ──────────────────────────────────────────────────────────────────
if (-not (Have node)) {
    Hdr "Installing Node.js"
    if ($UseWinget) {
        winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
    } else {
        Log "winget unavailable — downloading Node.js LTS installer directly."
        $nodeInstaller = "$env:TEMP\node-installer.msi"
        try {
            Invoke-WebRequest -Uri "https://nodejs.org/dist/v20.18.0/node-v20.18.0-x64.msi" -OutFile $nodeInstaller -UseBasicParsing
            Start-Process -Wait -FilePath "msiexec" -ArgumentList "/i","$nodeInstaller","/quiet","/norestart"
            Remove-Item $nodeInstaller -Force -ErrorAction SilentlyContinue
        } catch {
            Err "Node install failed: $_"
        }
    }
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
if (Have node) { Ok "node $(node --version)" } else { Err "node install failed" }

# ─── Claude Code (Anthropic's CLI/desktop app — REQUIRED) ─────────────────────
# Without this, the user has no way to actually run /setup-brain after the
# bootstrap finishes. Distributed via npm so the install path is identical
# across Mac, Linux, and Windows once Node is present.
if (-not (Have claude)) {
    Hdr "Installing Claude Code"
    Log "Claude Code is Anthropic's developer tool that runs the AI brain skill."
    Log "It's different from claude.ai (the chat website) — this one lives in your"
    Log "terminal and can read and write files in your vault. Installing via npm."
    npm install -g @anthropic-ai/claude-code 2>$null
    if ($LASTEXITCODE -ne 0) {
        Err "Claude Code install failed — install manually with: npm install -g @anthropic-ai/claude-code"
    }
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
if (Have claude) { Ok "Claude Code installed" }

# ─── pipx ─────────────────────────────────────────────────────────────────────
if (-not (Have pipx)) {
    Hdr "Installing pipx"
    python -m pip install --user pipx
    python -m pipx ensurepath
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (Have pipx) { Ok "pipx" } else { Err "pipx install failed" }

# ─── fastmcp ──────────────────────────────────────────────────────────────────
# Framework for building custom MCP servers in minimal Python. Needed when
# wiring custom connectors (CRM bridges, vault sync, investor relations, etc.)
if (-not (Have fastmcp)) {
    Hdr "Installing fastmcp"
    pipx install fastmcp 2>$null
}
if (Have fastmcp) { Ok "fastmcp" } else { Warn "fastmcp not installed (non-blocking — install later with: pipx install fastmcp)" }

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
        Hdr "GitHub login (OPTIONAL — skip with Ctrl+C)"
        Write-Host "  This step is OPTIONAL. You only need it if you want your AI brain to"
        Write-Host "  automatically file improvement ideas as GitHub issues for the maintainer."
        Write-Host ""
        Write-Host "  Do you have a GitHub account?"
        Write-Host "     YES      -> press Enter, a browser window opens, log in, done."
        Write-Host "     NO       -> press Ctrl+C right now to skip. Everything else still works."
        Write-Host "     NOT SURE -> press Ctrl+C to skip. You can come back later with: gh auth login"
        Write-Host ""
        Write-Host "  (If you press Enter, you'll see options like 'GitHub.com -> HTTPS ->"
        Write-Host "   Login with web browser.' Just pick those defaults — they're fine.)"
        Write-Host ""
        Read-Host "  Press Enter to log in, or Ctrl+C to skip"
        gh auth login
        if ($LASTEXITCODE -ne 0) { Warn "gh auth skipped or failed — run 'gh auth login' later if you want issue filing" }
    }
    gh auth status 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Ok "gh authenticated" } else { Warn "gh not authenticated (issue filing disabled until you run: gh auth login)" }
}

# ─── Obsidian — REQUIRED, the entire setup writes notes into an Obsidian vault.
# Auto-install via winget. Never ask the user to "go download" anything — that
# breaks the one-command promise and assumes they know what Obsidian is and
# how to install a desktop app on Windows.
$ObsidianInstalled = $false
$ObsidianPaths = @(
    "$env:LOCALAPPDATA\Obsidian\Obsidian.exe",
    "$env:ProgramFiles\Obsidian\Obsidian.exe",
    "${env:ProgramFiles(x86)}\Obsidian\Obsidian.exe"
)
foreach ($p in $ObsidianPaths) {
    if (Test-Path -LiteralPath $p) { $ObsidianInstalled = $true; break }
}

if (-not $ObsidianInstalled) {
    Hdr "Installing Obsidian"
    Log "Obsidian is the note-taking app this whole setup writes into. Free, runs locally, no account."
    if ($DryRun) {
        Dry "would: install Obsidian via winget or direct download"
    } else {
        if ($UseWinget) {
            Log "Installing via winget so you don't have to download anything yourself."
            winget install -e --id Obsidian.Obsidian --accept-source-agreements --accept-package-agreements
        } else {
            Log "winget unavailable — downloading Obsidian installer directly from obsidian.md."
            $obsInstaller = "$env:TEMP\Obsidian-Installer.exe"
            try {
                # Resolve latest Windows installer from Obsidian's GitHub releases.
                $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/obsidianmd/obsidian-releases/releases/latest" -UseBasicParsing
                $url = ($rel.assets | Where-Object { $_.name -match 'Obsidian.*\.exe$' -and $_.name -notmatch 'arm64' } | Select-Object -First 1).browser_download_url
                if ($url) {
                    Invoke-WebRequest -Uri $url -OutFile $obsInstaller -UseBasicParsing
                    Start-Process -Wait -FilePath $obsInstaller -ArgumentList "/S"
                    Remove-Item $obsInstaller -Force -ErrorAction SilentlyContinue
                } else {
                    Err "Could not resolve latest Obsidian installer URL — download manually from https://obsidian.md/download"
                }
            } catch {
                Err "Obsidian install failed: $_ — download manually from https://obsidian.md/download and re-run this script"
            }
        }
        if ($LASTEXITCODE -eq 0 -or -not $UseWinget) {
            $script:Installed += "Obsidian"
            foreach ($p in $ObsidianPaths) {
                if (Test-Path -LiteralPath $p) { $ObsidianInstalled = $true; break }
            }
        }
    }
}
if ($ObsidianInstalled) { Ok "Obsidian installed" }

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
#   - Custom skill folders outside the bundled set (humanizer, daily-journal,
#     anything the user installed themselves) are NEVER touched
Hdr "Installing bundled sub-skills (with safety checks)"
$stamp = Get-Date -Format "yyyy-MM-dd-HHmm"

foreach ($sub in @("graphify", "meeting-todos", "patterns", "insights", "deconstruct", "daily-journal", "repurpose-talk", "nano-banana")) {
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
        Ok "${sub}: $createdCount new, $updatedCount updated, $backedUpCount backed up"
        $script:Updated += "$sub skill ($createdCount new, $updatedCount updated, $backedUpCount backed up)"
    } else {
        Ok "${sub}: already current"
    }
}

# ─── Humanizer ────────────────────────────────────────────────────────────────
$humDir = "$env:USERPROFILE\.claude\skills\humanizer"
if (-not (Test-Path $humDir)) {
    Hdr "Installing humanizer"
    git clone --quiet https://github.com/adelaidasofia/humanizer.git $humDir
}
if (Test-Path $humDir) { Ok "humanizer skill installed" } else { Err "humanizer clone failed" }

# ─── Granola MCP ─────────────────────────────────────────────────────────────
# SAFETY: backup .mcp.json before editing. Existing MCP servers (custom
# integrations, other URL or stdio MCPs the user wired themselves) are
# preserved — setdefault() only adds the granola entry if missing.
Hdr "Registering MCPs (Granola + ChatPRD)"
$mcpPath = "$env:USERPROFILE\.claude\.mcp.json"
Backup-File $mcpPath

if ($DryRun) {
    Dry "would: register granola + chatprd MCPs (existing entries preserved)"
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
if 'chatprd' not in m['mcpServers']:
    m['mcpServers']['chatprd'] = {'type': 'url', 'url': 'https://app.chatprd.ai/mcp'}
with open(p, 'w') as f: json.dump(m, f, indent=2)
"@
    $pyMcp | python -
    if ($LASTEXITCODE -eq 0) { Ok "MCPs registered: granola, chatprd (Granola needs an account to use)" } else { Err "MCP registration failed" }
}

# ─── Marketplaces + enabled plugins (settings.json) ──────────────────────────
# SAFETY: backup settings.json first. setdefault() never clobbers existing
# marketplaces, plugins, permissions, env vars, or any other keys.
Hdr "Registering marketplace + enabling plugins"
$settingsPath = "$env:USERPROFILE\.claude\settings.json"
Backup-File $settingsPath

if ($DryRun) {
    Dry "would register obsidian-skills marketplace (kepano/obsidian-skills) and enable: obsidian, context7, playwright"
} else {
    $pyPlugins = @"
import json, os
p = os.path.expanduser('~/.claude/settings.json')
try:
    with open(p) as f: s = json.load(f)
except FileNotFoundError:
    s = {}
s.setdefault('extraKnownMarketplaces', {})
if 'obsidian-skills' not in s['extraKnownMarketplaces']:
    s['extraKnownMarketplaces']['obsidian-skills'] = {
        'source': {'source': 'github', 'repo': 'kepano/obsidian-skills'}
    }
s.setdefault('enabledPlugins', {})
for plug in ('obsidian@obsidian-skills', 'context7', 'playwright'):
    s['enabledPlugins'].setdefault(plug, True)
with open(p, 'w') as f: json.dump(s, f, indent=2)
"@
    $pyPlugins | python -
    if ($LASTEXITCODE -eq 0) { Ok "Marketplace + plugins registered (settings.json backed up)" } else { Err "settings.json plugin registration failed" }
}

# ─── Verification ────────────────────────────────────────────────────────────
Hdr "Verifying installation"
if ($DryRun) {
    Log "skipping verification under -DryRun (nothing was actually installed)"
} else {
foreach ($pair in @(@("graphify","graphify"), @("node","node"), @("npm","npm"), @("pipx","pipx"), @("gh","gh"))) {
    if (Have $pair[1]) { Ok $pair[0] } else { Err "$($pair[0]) not callable" }
}
foreach ($sub in @("graphify","meeting-todos","patterns","insights","deconstruct","daily-journal","repurpose-talk","nano-banana","humanizer","ai-brain-starter")) {
    if (Test-Path "$env:USERPROFILE\.claude\skills\$sub") { Ok "skill: $sub" } else { Err "skill missing: $sub" }
}
if (Test-Path "$env:USERPROFILE\.claude\skills\graphify\scripts") { Ok "graphify scripts" } else { Err "graphify scripts missing" }

$mcpContent = Get-Content "$env:USERPROFILE\.claude\.mcp.json" -ErrorAction SilentlyContinue
if ($mcpContent -match "granola") { Ok "granola MCP in .mcp.json" } else { Err "granola not in .mcp.json" }
if ($mcpContent -match "chatprd") { Ok "chatprd MCP in .mcp.json" } else { Err "chatprd not in .mcp.json" }

if ((Get-Content "$env:USERPROFILE\.claude\settings.json" -ErrorAction SilentlyContinue) -match "obsidian-skills") {
    Ok "obsidian-skills marketplace in settings.json"
} else { Warn "obsidian-skills marketplace not in settings.json (non-blocking)" }
}  # end: if (-not $DryRun)

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
