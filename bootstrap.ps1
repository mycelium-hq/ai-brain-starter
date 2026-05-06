# ai-brain-starter, one-command bootstrap (Windows)
#
# This script installs everything Phase 0 of the setup-brain skill installs.
# It runs in two modes:
#   - Inside Claude Code (from the README paste-flow): Claude invokes this
#     as part of end-to-end setup and continues into the interview after.
#   - Standalone (irm-to-iex from PowerShell): tools get installed, then
#     the Next-Steps block tells the user to open Claude Code and paste the
#     setup prompt. Detection is via $env:CLAUDE_CODE_ENTRYPOINT.
#
# Usage (run from PowerShell, NOT cmd.exe):
#     irm https://raw.githubusercontent.com/adelaidasofia/ai-brain-starter/main/bootstrap.ps1 | iex
#
# Dry run (preview changes without making them):
#     iex "& { $(irm https://raw.githubusercontent.com/adelaidasofia/ai-brain-starter/main/bootstrap.ps1) } -DryRun"
#
# SAFETY GUARANTEES, same as bootstrap.sh:
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
$Cleaned   = @()

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

# ─── Locale detection + bilingual helper ──────────────────────────────────────
# Override via $env:BOOTSTRAP_LANG = "es"|"en". Otherwise: LC_ALL > LANG > Get-Culture > en.
function Detect-Lang {
    $raw = $env:BOOTSTRAP_LANG
    if (-not $raw) { $raw = $env:LC_ALL }
    if (-not $raw) { $raw = $env:LANG }
    if (-not $raw) { try { $raw = (Get-Culture).Name } catch { $raw = "en-US" } }
    if ($raw.Substring(0, [Math]::Min(2, $raw.Length)) -eq "es") { return "es" }
    return "en"
}
$script:LangCode = Detect-Lang
function T([string]$en, [string]$es) {
    if ($script:LangCode -eq "es") { return $es } else { return $en }
}

# ─── Email gate (universal, one-time) ──────────────────────────────────────
# Every install passes through the form once. The form at
# https://myceliumai.co/install captures email + context, mints a 32-char
# token, emails the install command. This script validates the token and
# writes a marker file. Future re-runs find the marker and skip the gate.
$emailMarker = "$env:USERPROFILE\.claude\.ai-brain-starter-email-on-file"
$installApiBase = if ($env:MYCELIUM_INSTALL_API) { $env:MYCELIUM_INSTALL_API } else { "https://myceliumai.co" }

if ($env:EMAIL_GATE_BYPASS -ne "1" -and -not $DryRun -and -not (Test-Path $emailMarker)) {
    Hdr (T "Email gate (one-time)" "Verificación de email (una sola vez)")
    if (-not $env:TOKEN) {
        Write-Host ""
        Write-Host ("  " + (T "We need your email before installing the second brain." `
                              "Necesitamos tu email antes de instalar el segundo cerebro."))
        Write-Host ""
        Write-Host ("  " + (T "This is a one-time gate. Once you submit the form, you get a token by" `
                              "Esto es una sola vez. Una vez completes el formulario, recibís un token"))
        Write-Host ("  " + (T "email; future re-runs skip this prompt." `
                              "por email; las próximas corridas saltean este paso."))
        Write-Host ""
        Write-Host ("  1. " + (T "Open this URL in your browser:" "Abrí este URL en tu navegador:"))
        Write-Host "     https://myceliumai.co/install"
        Write-Host ("     (" + (T "Spanish:" "Español:") + " https://myceliumai.co/es/install)")
        Write-Host ""
        Write-Host ("  2. " + (T "Fill out the short form. Takes about 4 minutes." `
                              "Completá el formulario corto. Tarda unos 4 minutos."))
        Write-Host ""
        Write-Host ("  3. " + (T "Check your email. You'll receive your personalized install command." `
                              "Revisá tu email. Vas a recibir tu comando de instalación personalizado."))
        Write-Host ""
        Write-Host ("  4. " + (T "Either paste that full command into Claude Code (recommended)," `
                              "Pegá ese comando completo en Claude Code (recomendado),"))
        Write-Host ("     " + (T "OR re-run this script with the token:" `
                              "O volvé a correr este script con el token:"))
        Write-Host ""
        Write-Host '         $env:TOKEN = "<your-token-from-email>"; pwsh bootstrap.ps1'
        Write-Host ""
        exit 3
    }
    $tk = $env:TOKEN.ToLower().Trim()
    if ($tk -notmatch '^[a-f0-9]{32}$') {
        Err (T "Token shape invalid. Expected 32 hex characters." `
              "Formato de token inválido. Esperaba 32 caracteres hexadecimales.")
        exit 4
    }
    Log (T "Validating token against $installApiBase..." `
          "Validando token contra $installApiBase...")
    try {
        $verifyUri = "$installApiBase/api/install/verify?token=$tk"
        $resp = Invoke-RestMethod -Uri $verifyUri -Method Get -TimeoutSec 10 -ErrorAction Stop
        if ($resp.valid -ne $true) {
            $reason = if ($resp.reason) { $resp.reason } else { "unknown" }
            Err (T "Token validation failed (reason: $reason). Get a fresh token at https://myceliumai.co/install and re-run." `
                  "Falló la validación del token (motivo: $reason). Conseguí un token nuevo en https://myceliumai.co/install y volvé a correr.")
            exit 4
        }
    } catch {
        Err (T "Token validation request failed: $_. Get a fresh token at https://myceliumai.co/install and re-run." `
              "Falló la solicitud de validación de token: $_. Conseguí un token nuevo en https://myceliumai.co/install y volvé a correr.")
        exit 4
    }
    Ok (T "Token valid. Recording email-on-file marker." `
          "Token válido. Guardando marca de email-en-archivo.")
    New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude" | Out-Null
    Set-Content -Path $emailMarker -Value $tk -Encoding ASCII

    # Fetch recap for setup-brain Phase 1 pre-population
    try {
        $recapUri = "$installApiBase/api/install/recap?token=$tk"
        $recap = Invoke-WebRequest -Uri $recapUri -Method Get -TimeoutSec 8 -UseBasicParsing -ErrorAction Stop
        if ($recap.StatusCode -eq 200) {
            $recapPath = "$env:USERPROFILE\.claude\.ai-brain-starter-recap.json"
            Set-Content -Path $recapPath -Value $recap.Content -Encoding UTF8
            Ok (T "Recap cached for setup-brain Phase 1." `
                  "Recap guardado para Phase 1 de setup-brain.")
        }
    } catch {
        # Best-effort. Setup-brain Phase 1 falls back to asking the questions.
    }

    # Fire install_bootstrap_started event (best-effort)
    try {
        $os = "$([System.Environment]::OSVersion.VersionString) $env:PROCESSOR_ARCHITECTURE"
        $body = @{ token = $tk; os = $os } | ConvertTo-Json -Compress
        Invoke-RestMethod -Uri "$installApiBase/api/install/started" -Method Post `
            -Body $body -ContentType "application/json" -TimeoutSec 6 -ErrorAction SilentlyContinue | Out-Null
    } catch {
        # Best-effort. Funnel telemetry, not a hard dependency.
    }
}

# ─── Pre-flight gate (skip with $env:PREFLIGHT_BYPASS = "1") ──────────────────
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$preflightLocal = Join-Path $scriptRoot "scripts\preflight.ps1"
$preflightInstalled = "$env:USERPROFILE\.claude\skills\ai-brain-starter\scripts\preflight.ps1"
$preflightToRun = ""
if (Test-Path $preflightLocal) { $preflightToRun = $preflightLocal }
elseif (Test-Path $preflightInstalled) { $preflightToRun = $preflightInstalled }

if ($env:PREFLIGHT_BYPASS -ne "1" -and $preflightToRun -and -not $DryRun) {
    Hdr (T "Pre-flight check" "Verificación previa")
    Log (T "Verifying every prerequisite before any tool is installed." `
          "Verificando cada requisito antes de instalar nada.")
    & $preflightToRun
    $preflightRc = $LASTEXITCODE
    if ($preflightRc -eq 2) {
        Write-Host ""
        Write-Host (T "Bootstrap aborted: pre-flight found blockers. Fix them and re-run." `
                       "Bootstrap detenido: la verificación previa encontró bloqueantes. Arreglalos y volvé a correr.") `
                       -ForegroundColor Red
        Write-Host (T "To bypass during development: `$env:PREFLIGHT_BYPASS = '1'; pwsh bootstrap.ps1" `
                       "Para saltarla en desarrollo: `$env:PREFLIGHT_BYPASS = '1'; pwsh bootstrap.ps1")
        exit 2
    }
}

Hdr "Cleaning up deprecated tools"

# claude-mem: unauthenticated local HTTP API, arbitrary file-read surface,
# API keys in plaintext, hook that injected content into every session.
$settingsPath = "$env:USERPROFILE\.claude\settings.json"
$claudeMemPresent = $false
if (Test-Path $settingsPath) {
    try {
        $s = Get-Content $settingsPath -Raw | ConvertFrom-Json
        $hasMkt  = $s.extraKnownMarketplaces -and $s.extraKnownMarketplaces.PSObject.Properties.Name -contains "thedotmack"
        $hasPlug = $s.enabledPlugins -and $s.enabledPlugins.PSObject.Properties.Name -contains "claude-mem@thedotmack"
        $claudeMemPresent = $hasMkt -or $hasPlug
    } catch {}
}
if ($claudeMemPresent) {
    if ($DryRun) { Dry "would remove claude-mem from settings.json (marketplace + plugin entry)" }
    else {
        Backup-File $settingsPath
        $s = Get-Content $settingsPath -Raw | ConvertFrom-Json
        if ($s.extraKnownMarketplaces) { $s.extraKnownMarketplaces.PSObject.Properties.Remove("thedotmack") }
        if ($s.enabledPlugins)         { $s.enabledPlugins.PSObject.Properties.Remove("claude-mem@thedotmack") }
        $s | ConvertTo-Json -Depth 10 | Set-Content $settingsPath
        Ok "Removed claude-mem, had security issues (open local HTTP port, file-read surface). Built-in memory covers everything it did."
        $script:Cleaned += "claude-mem"
    }
} else { Ok "claude-mem not present, nothing to clean" }

# notebooklm: browser automation + Google login dance wasn't worth it for most users.
$notebooklmDir = "$env:USERPROFILE\.claude\skills\notebooklm"
if (Test-Path $notebooklmDir) {
    if ($DryRun) { Dry "would remove $notebooklmDir (notebooklm skill)" }
    else {
        Remove-Item -Recurse -Force $notebooklmDir
        Ok "Removed notebooklm, rarely used, required browser automation + Google login on every session. To restore: git clone https://github.com/PleasePrompto/notebooklm-skill.git `$env:USERPROFILE\.claude\skills\notebooklm"
        $script:Cleaned += "notebooklm"
    }
} else { Ok "notebooklm not present, nothing to clean" }

Hdr (T "ai-brain-starter, one-command install" "ai-brain-starter, instalación de un solo comando")
Write-Host ""
if ($DryRun) {
    Write-Host ("  " + (T "DRY RUN MODE - showing what would be installed without making any changes." `
                            "MODO DE PRUEBA - mostrando lo que se instalaría sin hacer cambios reales.")) -ForegroundColor Magenta
    Write-Host ""
}
Write-Host ("  " + (T "This installs the full AI brain stack: graphify, humanizer," `
                       "Esto instala el stack completo de AI brain: graphify, humanizer,"))
Write-Host ("  " + (T "meeting-todos, patterns, insights, deconstruct, daily-journal," `
                       "meeting-todos, patterns, insights, deconstruct, daily-journal,"))
Write-Host ("  " + (T "repurpose-talk, nano-banana (skill docs), Granola + ChatPRD MCPs," `
                       "repurpose-talk, nano-banana (docs de skill), MCPs de Granola + ChatPRD,"))
Write-Host ("  " + (T "the obsidian-skills marketplace, plus the ai-brain-starter skill" `
                       "el marketplace obsidian-skills, y la skill ai-brain-starter"))
Write-Host ("  " + (T "itself. Takes ~5 minutes the first time." `
                       "misma. Tarda ~5 minutos la primera vez."))
Write-Host ""
Write-Host ("  " + (T "When it's done, Claude continues with the setup interview automatically." `
                       "Cuando termine, Claude continúa con la entrevista de setup automáticamente."))
Write-Host ("  " + (T "You don't need to type anything." "No necesitás tipear nada."))
Write-Host ""
Start-Sleep -Seconds 1

# ─── winget bootstrap ─────────────────────────────────────────────────────────
# winget ships with Windows 11 and recent Windows 10. On older Windows 10 it's
# missing, auto-install App Installer (which provides winget) before doing
# anything else. Never abort with "go install something from the Microsoft
# Store yourself", that defeats the one-command promise.
if (-not (Have winget)) {
    Hdr (T "Installing winget (App Installer)" "Instalando winget (App Installer)")
    Log (T "winget is the Windows package manager we use to install everything else." `
          "winget es el gestor de paquetes de Windows que usamos para instalar todo lo demás.")
    Log (T "Your Windows version is missing it, we'll install it for you now." `
          "Tu versión de Windows no lo tiene, lo instalamos por vos ahora.")

    # Method 1: Microsoft's official MSIX bundle. URL aka.ms/getwinget always
    # resolves to the latest stable release on GitHub.
    $tempInstaller = "$env:TEMP\AppInstaller.msixbundle"
    try {
        Log (T "Downloading App Installer from Microsoft..." "Descargando App Installer de Microsoft...")
        Invoke-WebRequest -Uri "https://aka.ms/getwinget" -OutFile $tempInstaller -UseBasicParsing
        Log (T "Installing... (a Windows install dialog may appear briefly)" `
              "Instalando... (puede aparecer brevemente un diálogo de instalación de Windows)")
        Add-AppxPackage -Path $tempInstaller -ErrorAction Stop
        Remove-Item $tempInstaller -Force -ErrorAction SilentlyContinue
    } catch {
        Warn (T "Auto-install of winget failed: $_" "Falló la auto-instalación de winget: $_")
        Warn (T "Falling back to direct MSI installs for Python/Node/Obsidian." `
               "Volviendo a instalaciones MSI directas para Python/Node/Obsidian.")
    }

    # Refresh PATH so winget is callable in this session
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

if (Have winget) {
    Ok "winget available"
    $UseWinget = $true
} else {
    # Final fallback, winget could not be installed. Use direct downloads for
    # the things we need. The user is on a very old Windows; mark $UseWinget so
    # later sections can branch.
    Warn "Continuing without winget, using direct installer downloads."
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
        Log "winget unavailable, downloading Python installer directly."
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
        Log "winget unavailable, downloading Node.js LTS installer directly."
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

# ─── Claude Code (Anthropic's CLI/desktop app, REQUIRED) ─────────────────────
# Without this, the user has no way to actually run /setup-brain after the
# bootstrap finishes. Distributed via npm so the install path is identical
# across Mac, Linux, and Windows once Node is present.
if (-not (Have claude)) {
    Hdr (T "Installing Claude Code" "Instalando Claude Code")
    Log (T "Claude Code is Anthropic's developer tool that runs the AI brain skill." `
          "Claude Code es la herramienta de Anthropic para developers que corre la skill del AI brain.")
    Log (T "It's different from claude.ai (the chat website), this one lives in your" `
          "Es diferente de claude.ai (el sitio de chat); este vive en tu")
    Log (T "terminal and can read and write files in your vault. Installing via npm." `
          "terminal y puede leer y escribir archivos en tu vault. Instalando vía npm.")
    npm install -g @anthropic-ai/claude-code 2>$null
    if ($LASTEXITCODE -ne 0) {
        Err (T "Claude Code install failed, install manually with: npm install -g @anthropic-ai/claude-code" `
              "Falló la instalación de Claude Code. Instalalo manual con: npm install -g @anthropic-ai/claude-code")
    }
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
if (Have claude) { Ok (T "Claude Code installed" "Claude Code instalado") }

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
if (Have fastmcp) { Ok "fastmcp" } else { Warn "fastmcp not installed (non-blocking, install later with: pipx install fastmcp)" }

# ─── gh (GitHub CLI) ──────────────────────────────────────────────────────────
if (-not (Have gh)) {
    Hdr "Installing gh (GitHub CLI)"
    Log "gh lets the session-end capture cascade file improvement ideas as GitHub issues automatically."
    winget install -e --id GitHub.cli --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
if (Have gh) { Ok "gh installed" } else { Warn "gh not installed, install manually if needed" }

# gh authentication, required for the session-end capture cascade to file
# improvement ideas as GitHub issues automatically. Walk the user through it
# the first time only.
if (Have gh) {
    gh auth status 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Hdr "GitHub login (OPTIONAL, skip with Ctrl+C)"
        Write-Host "  This step is OPTIONAL. You only need it if you want your AI brain to"
        Write-Host "  automatically file improvement ideas as GitHub issues for the maintainer."
        Write-Host ""
        Write-Host "  Do you have a GitHub account?"
        Write-Host "     YES      -> press Enter, a browser window opens, log in, done."
        Write-Host "     NO       -> press Ctrl+C right now to skip. Everything else still works."
        Write-Host "     NOT SURE -> press Ctrl+C to skip. You can come back later with: gh auth login"
        Write-Host ""
        Write-Host "  (If you press Enter, you'll see options like 'GitHub.com -> HTTPS ->"
        Write-Host "   Login with web browser.' Just pick those defaults, they're fine.)"
        Write-Host ""
        Read-Host "  Press Enter to log in, or Ctrl+C to skip"
        gh auth login
        if ($LASTEXITCODE -ne 0) { Warn "gh auth skipped or failed, run 'gh auth login' later if you want issue filing" }
    }
    gh auth status 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Ok "gh authenticated" } else { Warn "gh not authenticated (issue filing disabled until you run: gh auth login)" }
}

# ─── Obsidian, REQUIRED, the entire setup writes notes into an Obsidian vault.
# Auto-install via winget. Never ask the user to "go download" anything, that
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
    Hdr (T "Installing Obsidian" "Instalando Obsidian")
    Log (T "Obsidian is the note-taking app this whole setup writes into. Free, runs locally, no account." `
          "Obsidian es la app de notas en la que todo este setup escribe. Gratis, corre local, sin cuenta.")
    if ($DryRun) {
        Dry "would: install Obsidian via winget or direct download"
    } else {
        if ($UseWinget) {
            Log (T "Installing via winget so you don't have to download anything yourself." `
                  "Instalando vía winget para que no tengas que descargar nada manual.")
            winget install -e --id Obsidian.Obsidian --accept-source-agreements --accept-package-agreements
        } else {
            Log (T "winget unavailable, downloading Obsidian installer directly from obsidian.md." `
                  "winget no disponible, descargando instalador de Obsidian directamente desde obsidian.md.")
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
                    Err "Could not resolve latest Obsidian installer URL, download manually from https://obsidian.md/download"
                }
            } catch {
                Err "Obsidian install failed: $_, download manually from https://obsidian.md/download and re-run this script"
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

    # Regular folder or missing, eligible for sync
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
# preserved, setdefault() only adds the granola entry if missing.
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
foreach ($sub in @("graphify","meeting-todos","patterns","insights","deconstruct","daily-journal","repurpose-talk","nano-banana","humanizer","ai-brain-starter","diagnose")) {
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
    Write-Host ("━━━ " + (T "All checks passed." "Todas las verificaciones pasaron.") + " ━━━") -ForegroundColor Green
} else {
    Write-Host ("━━━ $($Failed.Count) " + (T "check(s) failed:" "verificación(es) fallaron:") + " ━━━") -ForegroundColor Red
    foreach ($f in $Failed) { Write-Host "  - $f" }
    Write-Host ""
    Write-Host (T "Don't proceed silently - fix these before continuing the setup interview." `
                  "No sigas en silencio: arreglá esto antes de continuar con la entrevista de setup.")
}

# ─── Change summary ──────────────────────────────────────────────────────────
Hdr "Change summary"
if ($DryRun) { Write-Host "DRY RUN - no actual changes made." -ForegroundColor Magenta }

if ($Installed.Count -eq 0 -and $Updated.Count -eq 0 -and $Skipped.Count -eq 0 -and $Backups.Count -eq 0 -and $Cleaned.Count -eq 0) {
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
    if ($Cleaned.Count -gt 0) {
        Write-Host ""
        Write-Host "  Removed (deprecated):" -ForegroundColor Red
        foreach ($x in $Cleaned) { Write-Host "    X $x" }
    }
}
Write-Host ""

Write-Host ""
Write-Host ("━━━ " + (T "Install complete" "Instalación completa") + " ━━━") -ForegroundColor Cyan
Write-Host ""

# ─── Report install completion to Mycelium (best-effort, fail-open) ──────────
if ((Test-Path $emailMarker) -and -not $DryRun) {
    try {
        $recordedToken = (Get-Content -Path $emailMarker -TotalCount 1).Trim()
        if ($recordedToken) {
            $os = "$([System.Environment]::OSVersion.VersionString) $env:PROCESSOR_ARCHITECTURE"
            $sigPath = "$env:USERPROFILE\.claude\.ai-brain-starter-hmac-secret"
            $signature = $null
            if (Test-Path $sigPath) {
                try {
                    $secret = (Get-Content -Path $sigPath -TotalCount 1).Trim()
                    if ($secret) {
                        $hmac = [System.Security.Cryptography.HMACSHA256]::new(
                            [System.Text.Encoding]::UTF8.GetBytes($secret))
                        $hash = $hmac.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($recordedToken))
                        $signature = ($hash | ForEach-Object { $_.ToString("x2") }) -join ""
                        $hmac.Dispose()
                    }
                } catch {
                    # Skip signing on any error; server still accepts unsigned during rollout.
                }
            }
            $payload = @{ token = $recordedToken; os = $os; completed = $true }
            if ($signature) { $payload.signature = $signature }
            $body = $payload | ConvertTo-Json -Compress
            Invoke-RestMethod -Uri "$installApiBase/api/install/complete" -Method Post `
                -Body $body -ContentType "application/json" -TimeoutSec 8 -ErrorAction SilentlyContinue | Out-Null
        }
    } catch {
        # Best-effort. Failing to report shouldn't block the user.
    }
}

if ($env:CLAUDE_CODE_ENTRYPOINT) {
    # Running inside Claude Code (the paste-flow from the README). Claude will
    # continue with the setup interview automatically; no user action needed.
    Write-Host ("  " + (T "Tools are ready. Claude continues with the setup interview automatically" `
                            "Las herramientas están listas. Claude continúa con la entrevista de setup automáticamente"))
    Write-Host ("  " + (T "from here, no commands to type and no folders to open." `
                            "desde acá, sin comandos que tipear y sin carpetas que abrir."))
    Write-Host ""
    Write-Host ("  " + (T "Image generation (Nano Banana via Gemini) is the one thing that can't" `
                            "Generación de imágenes (Nano Banana vía Gemini) es lo único que no se puede"))
    Write-Host ("  " + (T "auto-install here. Ask Claude to turn it on when you want image" `
                            "auto-instalar acá. Pedile a Claude que la prenda cuando quieras generar"))
    Write-Host ("  " + (T "generation. You don't need it for the core setup." `
                            "imágenes. No la necesitás para el setup base."))
    Write-Host ""
} else {
    # Running standalone (irm-to-iex from PowerShell). Guide the user into the
    # paste-flow inside the Claude Code desktop app.
    Write-Host ("  " + (T "Tools are ready. Now open the Claude Code desktop app and paste this" `
                            "Las herramientas están listas. Ahora abrí la app de escritorio de Claude Code y pegá esto"))
    Write-Host ("  " + (T "into the chat to run the setup interview:" `
                            "en el chat para correr la entrevista de setup:"))
    Write-Host ""
    if ($script:LangCode -eq "es") {
        Write-Host "      Por favor configurá mi AI Brain Starter completo en esta sesión."
        Write-Host "      La skill ai-brain-starter ya está instalada en"
        Write-Host "      ~/.claude/skills/ai-brain-starter. Empezá la entrevista de setup"
        Write-Host "      corriendo la skill setup-brain y guiame por cada fase sin parar."
    } else {
        Write-Host "      Please set up my AI Brain Starter end-to-end in this session. The"
        Write-Host "      ai-brain-starter skill is already installed at"
        Write-Host "      ~/.claude/skills/ai-brain-starter. Start the setup interview by"
        Write-Host "      running the setup-brain skill and walk me through every phase"
        Write-Host "      without stopping."
    }
    Write-Host ""
    Write-Host ("  " + (T "Claude will ask where your vault should live and build everything" `
                            "Claude te va a preguntar dónde vivirá tu vault y va a construir todo"))
    Write-Host ("  " + (T "around your answers. You don't need to type any other commands." `
                            "alrededor de tus respuestas. No necesitás tipear ningún otro comando."))
    Write-Host ""
}
