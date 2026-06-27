#Requires -Version 5.1
# preflight.ps1 - verify every prerequisite BEFORE bootstrap.ps1 touches the machine.
#
# Bilingual (English / Español, locale-detected via $env:PREFLIGHT_LANG and Get-Culture).
# Returns 0 GREEN / 1 YELLOW / 2 RED.
#
# Usage:
#   pwsh scripts\preflight.ps1            # human-readable terminal report
#   pwsh scripts\preflight.ps1 -Json      # machine-readable JSON for bootstrap
#   pwsh scripts\preflight.ps1 -Quiet     # only the final status line
#
# bootstrap.ps1 runs this first and refuses to proceed on RED.
# Bypass for development: $env:PREFLIGHT_BYPASS = "1"

param(
    [switch]$Json,
    [switch]$Quiet
)

$ErrorActionPreference = "Continue"

$script:Green  = @()
$script:Yellow = @()
$script:Red    = @()
$script:Info   = @()

# ─── Locale detection ─────────────────────────────────────────────────────────
function Detect-Lang {
    $raw = $env:PREFLIGHT_LANG
    if (-not $raw) { $raw = $env:LC_ALL }
    if (-not $raw) { $raw = $env:LANG }
    if (-not $raw) { try { $raw = (Get-Culture).Name } catch { $raw = "en-US" } }
    if ($raw.Substring(0, [Math]::Min(2, $raw.Length)) -eq "es") { return "es" }
    return "en"
}
$script:LangCode = Detect-Lang

# Translation helper: T "english" "spanish"
function T([string]$en, [string]$es) {
    if ($script:LangCode -eq "es") { return $es } else { return $en }
}

# ─── Output helpers ───────────────────────────────────────────────────────────
function Section($msg) {
    if (-not $Json -and -not $Quiet) { Write-Host ""; Write-Host $msg -ForegroundColor White }
}
function Green($msg) {
    $script:Green += $msg
    if (-not $Json -and -not $Quiet) { Write-Host "  + $msg" -ForegroundColor Green }
}
function Yellow($msg) {
    $script:Yellow += $msg
    if (-not $Json -and -not $Quiet) { Write-Host "  ! $msg" -ForegroundColor Yellow }
}
function Red($msg) {
    $script:Red += $msg
    if (-not $Json -and -not $Quiet) { Write-Host "  X $msg" -ForegroundColor Red }
}
function Info($msg) {
    $script:Info += $msg
    if (-not $Json -and -not $Quiet) { Write-Host "  - $msg" -ForegroundColor DarkGray }
}
function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

# ─── Header ───────────────────────────────────────────────────────────────────
if (-not $Json -and -not $Quiet) {
    Write-Host ""
    Write-Host (T "AI Brain Starter - pre-flight check" "AI Brain Starter - verificación previa") -ForegroundColor White
    Write-Host (T "Verifying every prerequisite before any tool gets installed." `
                  "Verificando cada requisito antes de instalar nada.") -ForegroundColor DarkGray
}

# ─── 1. Operating system ──────────────────────────────────────────────────────
Section (T "Operating system" "Sistema operativo")

$winVer = [System.Environment]::OSVersion.Version
$winBuild = $winVer.Build
# Win10 v1909 = build 18363, Win11 = build 22000+
if ($winBuild -ge 22000) {
    Green (T "Windows 11 (build $winBuild) - supported" `
              "Windows 11 (build $winBuild) - compatible")
} elseif ($winBuild -ge 18363) {
    Green (T "Windows 10 (build $winBuild) - supported" `
              "Windows 10 (build $winBuild) - compatible")
} elseif ($winBuild -ge 17763) {
    Yellow (T "Windows 10 build $winBuild is older than 1909. Most things install but winget may need manual install." `
               "Windows 10 build $winBuild es anterior a 1909. La mayoría se instala, pero winget puede requerir instalación manual.")
} else {
    Red (T "Windows build $winBuild is too old. Upgrade to Windows 10 1909+ or Windows 11." `
            "Windows build $winBuild es muy antiguo. Actualizá a Windows 10 1909+ o Windows 11.")
}

$arch = $env:PROCESSOR_ARCHITECTURE
Info (T "Architecture: $arch" "Arquitectura: $arch")

# ─── 2. PowerShell version ────────────────────────────────────────────────────
Section (T "PowerShell" "PowerShell")

$psVer = $PSVersionTable.PSVersion
if ($psVer.Major -ge 7) {
    Green (T "PowerShell $psVer (modern, recommended)" "PowerShell $psVer (moderno, recomendado)")
} elseif ($psVer.Major -eq 5 -and $psVer.Minor -ge 1) {
    Green (T "PowerShell $psVer (supported)" "PowerShell $psVer (compatible)")
} else {
    Red (T "PowerShell $psVer is too old. Need 5.1 minimum, 7+ recommended." `
            "PowerShell $psVer es muy antiguo. Mínimo 5.1, recomendado 7+.")
}

# ─── 3. Execution policy ──────────────────────────────────────────────────────
$policy = Get-ExecutionPolicy -Scope CurrentUser
if ($policy -eq "Restricted") {
    Yellow (T "Execution policy is Restricted. Bootstrap will fail. Fix: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned" `
               "Política de ejecución en Restricted. Bootstrap fallará. Solución: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned")
} else {
    Info (T "Execution policy: $policy" "Política de ejecución: $policy")
}

# ─── 4. Disk space ────────────────────────────────────────────────────────────
Section (T "Disk space" "Espacio en disco")

try {
    $drive = (Get-Item $env:USERPROFILE).PSDrive.Name
    $free = (Get-PSDrive -Name $drive).Free
    $freeGB = [Math]::Round($free / 1GB, 1)
    if ($freeGB -ge 2) {
        Green (T "$freeGB GB free on $drive`: (>=2 GB needed)" "$freeGB GB libres en $drive`: (mínimo 2 GB)")
    } else {
        Red (T "Only $freeGB GB free on $drive`:. Free at least 2 GB before installing." `
                "Solo $freeGB GB libres en $drive`:. Liberá al menos 2 GB antes de instalar.")
    }
} catch {
    Yellow (T "Could not measure free disk space" "No se pudo medir el espacio libre")
}

# ─── 5. Network connectivity ──────────────────────────────────────────────────
Section (T "Network connectivity" "Conexión a internet")

function Test-Reachable($url, $timeoutSec = 6) {
    # Any HTTP response (incl. 403/404) counts as reachable.
    # Only DNS / connect refused / timeout count as unreachable.
    try {
        $req = [System.Net.HttpWebRequest]::Create($url)
        $req.Timeout = $timeoutSec * 1000
        $req.Method = "GET"
        $req.AllowAutoRedirect = $true
        $req.UserAgent = "ai-brain-starter-preflight"
        $resp = $req.GetResponse()
        $resp.Close()
        return $true
    } catch [System.Net.WebException] {
        # WebException with a Response means we got an HTTP code (e.g. 403/404)
        # - still counts as reachable.
        if ($_.Exception.Response) { return $true }
        return $false
    } catch {
        return $false
    }
}

$hosts = @(
    @{ url = "https://github.com"; name = "GitHub" }
    @{ url = "https://raw.githubusercontent.com"; name = "GitHub raw (scripts)" }
    @{ url = "https://registry.npmjs.org"; name = "npm registry (Claude Code)" }
    @{ url = "https://claude.ai"; name = "claude.ai (Claude Code sign-in)" }
)
foreach ($h in $hosts) {
    if (Test-Reachable $h.url) {
        Green (T "$($h.name) reachable" "$($h.name) accesible")
    } else {
        Red (T "$($h.name) NOT reachable at $($h.url) - check VPN / firewall / corporate proxy" `
                "$($h.name) NO accesible en $($h.url) - revisá VPN / firewall / proxy corporativo")
    }
}

# ─── 6. Claude Code ───────────────────────────────────────────────────────────
Section (T "Claude Code" "Claude Code")

$claudePaths = @(
    "$env:LOCALAPPDATA\Programs\claude\Claude.exe",
    "$env:LOCALAPPDATA\Programs\Claude\Claude.exe",
    "$env:ProgramFiles\Claude\Claude.exe"
)
$claudeApp = $claudePaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
$claudeOk = $false
if ($claudeApp) {
    Green (T "Claude Code desktop app found at $claudeApp" "Claude Code (app de escritorio) encontrado en $claudeApp")
    $claudeOk = $true
}
if (Have claude) {
    $cv = (& claude --version 2>$null | Select-Object -First 1)
    Green (T "Claude Code CLI on PATH: $cv" "Claude Code CLI en PATH: $cv")
    $claudeOk = $true
}
if (-not $claudeOk) {
    Red (T "Claude Code is not installed. Install from https://claude.ai/download then re-run this check." `
            "Claude Code no está instalado. Instalalo desde https://claude.ai/download y volvé a correr esta verificación.")
} else {
    Yellow (T "Make sure you are signed in to Claude Code with a paid plan (Pro, Max, or Team) before pasting the install prompt." `
               "Asegurate de estar logueado en Claude Code con un plan pago (Pro, Max o Team) antes de pegar el prompt de instalación.")
}

# ─── 7. Admin / non-admin ─────────────────────────────────────────────────────
Section (T "Admin permissions" "Permisos de administrador")

$wid = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$wp = New-Object System.Security.Principal.WindowsPrincipal($wid)
$isAdmin = $wp.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    Yellow (T "Running as Administrator. Install will work, but the recommended path is your normal user account." `
               "Corriendo como Administrador. Funciona, pero la ruta recomendada es tu cuenta normal.")
} else {
    Green (T "Standard user account (recommended). Windows may prompt for admin rights during install." `
              "Cuenta de usuario estándar (recomendado). Windows puede pedir permisos de administrador durante la instalación.")
}

# ─── 8. winget / pre-existing tools ───────────────────────────────────────────
Section (T "Existing tools (informational)" "Herramientas ya instaladas (informativo)")

if (Have winget) {
    Info (T "winget available" "winget disponible")
} else {
    Yellow (T "winget not installed. Bootstrap will auto-install via the Microsoft Store URL aka.ms/getwinget." `
               "winget no instalado. Bootstrap lo instalará automáticamente vía aka.ms/getwinget.")
}

if (Have node) {
    $nv = (node --version 2>$null) -replace '^v',''
    $nMaj = [int]($nv -split '\.')[0]
    if ($nMaj -ge 18) {
        Info (T "Node $nv (OK)" "Node $nv (OK)")
    } else {
        Yellow (T "Node $nv is older than recommended (>=18). Bootstrap keeps your version; upgrade later if anything fails." `
                   "Node $nv es anterior al recomendado (>=18). Bootstrap mantiene tu versión; actualizá después si algo falla.")
    }
}

if (Have python) {
    $pv = (python --version 2>&1) -replace 'Python ',''
    try {
        $pVersion = [version]$pv
        if ($pVersion -ge [version]"3.10") {
            Info (T "Python $pv (OK)" "Python $pv (OK)")
        } else {
            Yellow (T "Python $pv is older than 3.10. Bootstrap installs 3.12 alongside; not blocking." `
                       "Python $pv es anterior a 3.10. Bootstrap instala 3.12 al lado; no es bloqueante.")
        }
    } catch {
        Info (T "Python detected: $pv" "Python detectado: $pv")
    }
}

$obsidianPaths = @(
    "$env:LOCALAPPDATA\Programs\obsidian\Obsidian.exe",
    "$env:LOCALAPPDATA\Obsidian\Obsidian.exe",
    "$env:ProgramFiles\Obsidian\Obsidian.exe",
    "${env:ProgramFiles(x86)}\Obsidian\Obsidian.exe"
)
$obs = $obsidianPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($obs) {
    Info (T "Obsidian already installed at $obs" "Obsidian ya instalado en $obs")
}

# ─── 9. Existing ai-brain-starter clone ───────────────────────────────────────
Section (T "Existing AI Brain Starter install" "Instalación previa de AI Brain Starter")

$absDir = "$env:USERPROFILE\.claude\skills\ai-brain-starter"
if (Test-Path "$absDir\.git") {
    Info (T "Existing clone found at $absDir - bootstrap will fast-forward if behind, skip if a fork." `
            "Clon existente en $absDir - bootstrap hará fast-forward si está atrás, saltará si es un fork.")
} elseif (Test-Path $absDir) {
    Yellow (T "Folder $absDir exists but is not a git clone. Bootstrap may overwrite. Move it aside if you have local changes." `
               "La carpeta $absDir existe pero no es un clon git. Bootstrap puede sobrescribir. Movela a un lado si tenés cambios locales.")
} else {
    Green (T "Clean slate - no previous install detected" "Comenzando de cero - sin instalación previa")
}

# ─── 10. JSON output ──────────────────────────────────────────────────────────
$status = if ($script:Red.Count -gt 0) { "red" } elseif ($script:Yellow.Count -gt 0) { "yellow" } else { "green" }

if ($Json) {
    $obj = [ordered]@{
        lang   = $script:LangCode
        green  = $script:Green.Count
        yellow = $script:Yellow.Count
        red    = $script:Red.Count
        lines  = [ordered]@{
            green  = @($script:Green)
            yellow = @($script:Yellow)
            red    = @($script:Red)
            info   = @($script:Info)
        }
        status = $status
    }
    $obj | ConvertTo-Json -Depth 6
}

# ─── 11. Summary ──────────────────────────────────────────────────────────────
if (-not $Json) {
    Write-Host ""
    Write-Host (T "Summary" "Resumen") -ForegroundColor White
    $line = "  {0} {1} | {2} {3} | {4} {5}" -f `
        $script:Green.Count,  (T "passed" "OK"), `
        $script:Yellow.Count, (T "warnings" "advertencias"), `
        $script:Red.Count,    (T "blockers" "bloqueantes")
    Write-Host $line
    Write-Host ""
}

if ($script:Red.Count -gt 0) {
    if (-not $Json) {
        Write-Host (T "Pre-flight FAILED. Fix the items marked X above, then run:" `
                       "Verificación FALLÓ. Arreglá los ítems marcados con X y volvé a correr:") -ForegroundColor Red
        Write-Host "  pwsh scripts\preflight.ps1"
        Write-Host ""
    }
    exit 2
} elseif ($script:Yellow.Count -gt 0) {
    if (-not $Json) {
        Write-Host (T "Pre-flight PASSED with warnings. Bootstrap will continue; see warnings above." `
                       "Verificación OK con advertencias. Bootstrap va a continuar; revisá las advertencias arriba.") -ForegroundColor Yellow
        Write-Host ""
    }
    exit 1
} else {
    if (-not $Json) {
        Write-Host (T "Pre-flight PASSED. You're ready - paste the install prompt into Claude Code." `
                       "Verificación OK. Listo - pegá el prompt de instalación en Claude Code.") -ForegroundColor Green
        Write-Host ""
    }
    exit 0
}
