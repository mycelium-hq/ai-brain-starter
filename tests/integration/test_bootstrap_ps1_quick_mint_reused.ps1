# Regression test for bootstrap.ps1's quick-mint "reused" reply handling
# (MYC-5093).
#
# Bug: POST /api/install/quick-mint answers a resubmit for an email that
# already has a live install token with {ok:true, reused:true,
# resent:<bool>} and NO "token" property -- the endpoint is public and
# unauthenticated, so it deliberately never hands an existing token back
# out. bootstrap.ps1's inline-mint block recognized only a 32-hex "token"
# property; anything else, including this reply, fell through to
# Err("Inline mint returned no token. Falling back."), landing on
# $script:Failed.
#
# Runs cross-platform (pwsh on macOS/Linux, Windows PowerShell 5.1 on
# Windows), same pattern as the other bootstrap.ps1 regression tests in this
# directory (test_bootstrap_ps1_slash_commands.ps1 in particular: the block
# under test calls Log/Ok/Warn/Err/T, which this harness stubs exactly the
# same way).
#
# Asserts:
#   1. The block is present in bootstrap.ps1 and extractable by its markers.
#   2. reused+resent=true -> Warn (never Err), $env:TOKEN stays unset, exact
#      "I sent the link to your inbox again" copy.
#   3. reused+resent=false -> Warn (never Err), $env:TOKEN stays unset, exact
#      "The link is in your inbox from last time" copy.
#   4. Existing first-time-token path is unchanged.
#   5. A thrown request (network failure) still lands on Err via the catch
#      block, untouched by this change.
#   6. Spanish copy: T selects the ES lines for both reused cases.
#   7. NEGATIVE CONTROL: the identical harness against the frozen ffddd85
#      (pre-fix) fixture must fail the way the bug actually failed -- Err
#      called once, no Warn, no reused handling -- proving this test would
#      have caught the original bug, not just exercised dead code.
#   8. Strict boolean read (independent review finding, MYC-5093): a reply
#      built by round-tripping raw JSON through ConvertFrom-Json (never a
#      PSCustomObject literal -- see Run-ScenarioJson) with reused:1 or
#      reused:"true" must NOT take the warn branch, because neither an
#      Int64 nor a String is a [bool]. Only a genuine JSON boolean true
#      does. Same strictness for resent.
#
# Self-contained; no network (Invoke-RestMethod is shadowed by a local
# function so the block's unqualified call resolves to the stub, never the
# real cmdlet -- standard PowerShell command-precedence: function beats
# cmdlet in the same session).
#
# Exit 0 = pass, 1 = fail.

$ErrorActionPreference = "Stop"
$Bootstrap = Join-Path $PSScriptRoot "../../bootstrap.ps1"
$Fixture = Join-Path $PSScriptRoot "../fixtures/bootstrap-prefix-ffddd85-quickmint.ps1.txt"
$TmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("abs-quickmint-" + [System.Guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force -Path $TmpRoot | Out-Null

$script:Failures = 0
function Check($cond, $msg) {
    if ($cond) { Write-Host "  ok    $msg" -ForegroundColor Green }
    else { Write-Host "  FAIL  $msg" -ForegroundColor Red; $script:Failures++ }
}

try {
    if (-not (Test-Path -LiteralPath $Fixture) -or (Get-Item -LiteralPath $Fixture).Length -eq 0) {
        Write-Host "ERROR: the frozen pre-fix fixture is missing or empty at $Fixture. Without a 'before' source the negative control cannot run, and a control that cannot run must not report success." -ForegroundColor Red
        exit 1
    }

    Write-Host "A. the block ships in bootstrap.ps1 and is extractable"
    $src = [System.IO.File]::ReadAllText($Bootstrap)
    $startMark = "# ai-brain:quick-mint:start"
    $endMark = "# ai-brain:quick-mint:end"
    $si = $src.IndexOf($startMark)
    $ei = $src.IndexOf($endMark)
    Check ($si -ge 0) "bootstrap.ps1 carries the $startMark marker"
    Check ($ei -gt $si) "bootstrap.ps1 carries the $endMark marker after it"
    if ($si -lt 0 -or $ei -le $si) {
        Write-Host "ERROR: cannot extract the block; the rest of this test would be vacuous." -ForegroundColor Red
        exit 1
    }
    $block = $src.Substring($si, $ei - $si)
    Check ($block -match "\.reused") "extracted block understands a reused reply"
    $blockFile = Join-Path $TmpRoot "block.ps1"
    [System.IO.File]::WriteAllText($blockFile, $block, (New-Object System.Text.UTF8Encoding($false)))

    # PowerShell's dot-source operator silently no-ops on a non-.ps1
    # extension (confirmed empirically: byte-identical content dot-sourced
    # from a .ps1.txt path executes NOTHING -- no error, no output, every
    # variable simply keeps its prior value -- while the same bytes at a
    # .ps1 path run normally). So the vendored fixture, which is named
    # .ps1.txt precisely so scripts/shellcheck-equivalent linting and
    # PSScriptAnalyzer never touch a frozen historical snapshot, is copied
    # to a proper .ps1 path before being dot-sourced, exactly like the
    # extracted block above.
    $fixtureText = [System.IO.File]::ReadAllText($Fixture)
    $fixtureFile = Join-Path $TmpRoot "prefix.ps1"
    [System.IO.File]::WriteAllText($fixtureFile, $fixtureText, (New-Object System.Text.UTF8Encoding($false)))

    # Provenance, not merely presence (same reasoning as the bash suite's
    # fixture checks): the fixture must genuinely predate this fix, not be a
    # copy of the current block under a different name.
    Check (-not ($fixtureText -match "\.reused")) "fixture has NO reused handling (genuinely pre-fix, not a re-extraction from HEAD)"
    Check ($fixtureText -ne $block) "fixture is not byte-identical to the current block (control can actually fail)"

    # Bootstrap-only helpers the block calls. Stubbed so the block runs in
    # isolation, same pattern as test_bootstrap_ps1_slash_commands.ps1.
    # $script:LangCode drives T exactly like bootstrap.ps1's own top-level
    # $script:LangCode = Detect-Lang.
    $script:LangCode = "en"
    function Hdr($msg) { }
    function Log($msg) { }
    function Ok($msg) { $script:LastOk = $msg }
    function Warn($msg) { $script:LastWarn = $msg }
    function Err($msg) { $script:LastErr = $msg; $script:ErrCount++ }
    function T([string]$en, [string]$es) {
        if ($script:LangCode -eq "es") { return $es } else { return $en }
    }

    # Invoke-RestMethod is shadowed for the duration of this test: a locally
    # defined function of the same name takes precedence over the cmdlet for
    # every unqualified call in this session, so the block's real call site
    # (Invoke-RestMethod -Uri ... -Method Post ...) resolves here, never to
    # the network. $script:QmThrow simulates the request itself failing
    # (timeout, DNS, non-2xx with -ErrorAction Stop), which the block's own
    # catch{} handles.
    $script:QmResponse = $null
    $script:QmThrow = $null
    function Invoke-RestMethod {
        param($Uri, $Method, $ContentType, $Body, $TimeoutSec, $ErrorAction)
        if ($script:QmThrow) { throw $script:QmThrow }
        return $script:QmResponse
    }

    # Run-Scenario BLOCKFILE RESPONSE LANGCODE THROWMSG -> executes the given
    # block/fixture file with EMAIL+NAME set and TOKEN unset, exactly as
    # bootstrap.ps1's enclosing signup gate does before reaching this block.
    function Run-Scenario($BlockFile, $Response, [string]$LangCode = "en", [string]$ThrowMsg = $null) {
        $script:LastOk = $null; $script:LastWarn = $null; $script:LastErr = $null; $script:ErrCount = 0
        $script:LangCode = $LangCode
        $script:QmResponse = $Response
        $script:QmThrow = $ThrowMsg
        $env:EMAIL = "user@example.com"
        $env:NAME = "Test User"
        $env:LANG_HINT = $LangCode
        Remove-Item Env:\TOKEN -ErrorAction SilentlyContinue
        $installApiBase = "https://mycelium-ai.co"
        . $BlockFile
    }

    # Run-ScenarioJson BLOCKFILE JSONTEXT LANGCODE -> same as Run-Scenario, but
    # builds the mocked reply by round-tripping raw JSON TEXT through
    # ConvertFrom-Json, so it genuinely exercises PowerShell's JSON
    # deserialization type coercion (a [PSCustomObject] literal built directly
    # in this test, as every scenario below Run-Scenario uses, never routes
    # through that deserializer and so cannot catch a type-coercion bug in
    # either direction -- this is what independent review flagged as
    # uncovered).
    function Run-ScenarioJson($BlockFile, [string]$JsonText, [string]$LangCode = "en") {
        $response = $JsonText | ConvertFrom-Json
        Run-Scenario $BlockFile $response $LangCode
    }

    Write-Host "B. reused + resent=true -> Warn (never Err), TOKEN stays unset"
    Run-Scenario $blockFile ([PSCustomObject]@{ ok = $true; reused = $true; resent = $true; sideEffects = @{ welcomeEmailSent = $true } })
    Check ($script:LastWarn -eq "You already started an install with this email. I sent the link to your inbox again.") "exact resent copy printed (got: $($script:LastWarn))"
    Check ($script:ErrCount -eq 0) "Err was never called (got $($script:ErrCount) calls)"
    Check (-not $env:TOKEN) "TOKEN was not set from a reused reply (got: $($env:TOKEN))"

    Write-Host "C. reused + resent=false -> Warn (never Err), TOKEN stays unset"
    Run-Scenario $blockFile ([PSCustomObject]@{ ok = $true; reused = $true; resent = $false; sideEffects = @{ welcomeEmailSent = $false } })
    Check ($script:LastWarn -eq "You already started an install with this email. The link is in your inbox from last time.") "exact not-resent copy printed (got: $($script:LastWarn))"
    Check ($script:ErrCount -eq 0) "Err was never called (got $($script:ErrCount) calls)"
    Check (-not $env:TOKEN) "TOKEN was not set from a reused reply (got: $($env:TOKEN))"

    Write-Host "D. existing first-time-token path is unchanged"
    Run-Scenario $blockFile ([PSCustomObject]@{ ok = $true; token = "0123456789abcdef0123456789abcdef" })
    Check ($script:LastOk -eq "Token minted inline. No browser needed.") "Ok fired with the unchanged copy (got: $($script:LastOk))"
    Check ($script:ErrCount -eq 0) "Err was never called on a normal token reply (got $($script:ErrCount) calls)"
    Check ($env:TOKEN -eq "0123456789abcdef0123456789abcdef") "TOKEN was set from the first-time reply (got: $($env:TOKEN))"

    Write-Host "E. a thrown request still lands on Err via the catch block (untouched by this change)"
    Run-Scenario $blockFile $null "en" "simulated network failure"
    Check ($script:ErrCount -eq 1) "Err was called exactly once (got $($script:ErrCount))"
    Check ($script:LastErr -match "^Inline mint failed:") "the original catch-block copy still prints (got: $($script:LastErr))"
    Check (-not $env:TOKEN) "TOKEN was not set on a thrown request"

    Write-Host "F. Spanish copy"
    Run-Scenario $blockFile ([PSCustomObject]@{ ok = $true; reused = $true; resent = $true }) "es"
    Check ($script:LastWarn -eq "Ya empezaste una instalación con este email. Te reenvié el link a tu bandeja de entrada.") "Spanish resent copy printed (got: $($script:LastWarn))"
    Run-Scenario $blockFile ([PSCustomObject]@{ ok = $true; reused = $true; resent = $false }) "es"
    Check ($script:LastWarn -eq "Ya empezaste una instalación con este email. El link está en tu bandeja de entrada de la última vez.") "Spanish not-resent copy printed (got: $($script:LastWarn))"

    Write-Host "G. NEGATIVE CONTROL: identical harness against the frozen ffddd85 (pre-fix) fixture"
    Run-Scenario $fixtureFile ([PSCustomObject]@{ ok = $true; reused = $true; resent = $true; sideEffects = @{ welcomeEmailSent = $true } })
    Check ($script:ErrCount -eq 1) "pre-fix source calls Err exactly once on a reused reply (got $($script:ErrCount)) -- this harness would NOT have caught the bug otherwise"
    Check ($script:LastErr -eq "Inline mint returned no token. Falling back.") "pre-fix source prints the OLD no-token copy, with no idea what 'reused' means (got: $($script:LastErr))"
    Check ($null -eq $script:LastWarn) "pre-fix source never warns on a reused reply (got: $($script:LastWarn))"
    Check (-not $env:TOKEN) "pre-fix source leaves TOKEN unset on a reused reply"

    Write-Host "H. strict boolean read: a JSON non-bool reused/resent must NOT take the warn branch (independent review, MYC-5093)"
    Run-ScenarioJson $blockFile '{"ok":true,"reused":1}'
    Check ($null -eq $script:LastWarn) "reused:1 (JSON number, not a real boolean) does not Warn (got: $($script:LastWarn))"
    Check ($script:ErrCount -eq 1) "reused:1 falls through to the pre-existing no-token Err path instead (got $($script:ErrCount) Err calls)"
    Check ($script:LastErr -eq "Inline mint returned no token. Falling back.") "the exact pre-existing no-token copy prints (got: $($script:LastErr))"
    Check (-not $env:TOKEN) "TOKEN stays unset"

    Run-ScenarioJson $blockFile '{"ok":true,"reused":"true"}'
    Check ($null -eq $script:LastWarn) "reused:`"true`" (JSON string, not a real boolean) does not Warn (got: $($script:LastWarn))"
    Check ($script:ErrCount -eq 1) "reused:`"true`" falls through to the pre-existing no-token Err path instead (got $($script:ErrCount) Err calls)"
    Check (-not $env:TOKEN) "TOKEN stays unset"

    Run-ScenarioJson $blockFile '{"ok":true,"reused":true,"resent":true}'
    Check ($script:LastWarn -eq "You already started an install with this email. I sent the link to your inbox again.") "reused:true, resent:true (real JSON booleans, round-tripped through ConvertFrom-Json) DOES Warn with the resent copy (got: $($script:LastWarn))"
    Check ($script:ErrCount -eq 0) "Err was never called (got $($script:ErrCount))"

    Run-ScenarioJson $blockFile '{"ok":true,"reused":true,"resent":1}'
    Check ($script:LastWarn -eq "You already started an install with this email. The link is in your inbox from last time.") "reused:true (real bool) but resent:1 (JSON number, not a real boolean) reads as NOT resent -- falls to the not-resent copy (got: $($script:LastWarn))"
    Check ($script:ErrCount -eq 0) "Err was never called (got $($script:ErrCount))"

    Write-Host ""
    if ($script:Failures -gt 0) {
        Write-Host "FAILED: $($script:Failures) assertion(s)" -ForegroundColor Red
        exit 1
    }
    Write-Host "PASS: bootstrap.ps1 recognizes reused/resent, warns (never errs), leaves TOKEN unset, and the token/throw/ES paths are unchanged; negative control confirmed against the frozen pre-fix fixture (ffddd85)" -ForegroundColor Green
    exit 0
}
finally {
    Remove-Item Env:\EMAIL -ErrorAction SilentlyContinue
    Remove-Item Env:\NAME -ErrorAction SilentlyContinue
    Remove-Item Env:\LANG_HINT -ErrorAction SilentlyContinue
    Remove-Item Env:\TOKEN -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force -LiteralPath $TmpRoot -ErrorAction SilentlyContinue
}
