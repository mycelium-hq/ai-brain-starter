#Requires -Version 5.1
<#
  Behavioral test for relocate-machinery-sidecar.ps1 (MYC-2383 - Windows parity
  of relocate-machinery-sidecar.sh). Runs under pwsh on any OS. On Windows the
  machinery links are junctions, elsewhere symbolic links; both carry the
  ReparsePoint attribute, so the link assertions hold cross-platform. Proves:
  .git -> pointer file via --separate-git-dir, caches -> links, manifest names
  the vault (the offer-suppression key), idempotency, full rollback, dry-run
  inertness, and the live-worktree refusal gate (paired negative control).

  Run: pwsh -File scripts/test-relocate-machinery-sidecar.ps1
#>
$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot
$MS   = Join-Path $Here "relocate-machinery-sidecar.ps1"
$script:fails = 0
$gear = [string][char]0x2699 + [string][char]0xFE0F   # keep this file ASCII-clean

function Check { param([string]$Label, [bool]$Cond)
  if ($Cond) { Write-Host "PASS  $Label" } else { Write-Host "FAIL  $Label"; $script:fails++ }
}
function Get-Py {
  foreach ($n in @("python3", "python")) {
    $c = Get-Command $n -ErrorAction SilentlyContinue
    if ($c) { $v = (& $c.Source -c "import sys;print(sys.version_info[0])" 2>$null); if ("$v".Trim() -eq "3") { return $c.Source } }
  }
  throw "python 3 required for the test"
}
$Py = Get-Py
function RealPath { param([string]$p) return ("$(& $Py -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' $p)").Trim() }
function Is-Reparse { param([string]$p)
  $it = Get-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
  return ($it -and (($it.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0))
}
function Run-MS { param([string[]]$MsArgs)
  $out = & pwsh -NoProfile -File $MS @MsArgs 2>&1
  return [pscustomobject]@{ rc = $LASTEXITCODE; out = ("$out" -join "`n") }
}
function New-Vault { param([string]$Path)
  New-Item -ItemType Directory -Force -Path $Path | Out-Null
  Set-Content -LiteralPath (Join-Path $Path "CLAUDE.md") -Value "# brain"
  & git -C $Path init -q | Out-Null
  & git -C $Path config user.email "t@example.com" | Out-Null
  & git -C $Path config user.name "t" | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $Path ".smart-env") | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $Path ".codegraph") | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $Path "$gear Meta/Sessions") | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $Path ".claude/worktrees") | Out-Null
  Set-Content -LiteralPath (Join-Path $Path ".smart-env/cache.bin") -Value "x"
}

$TMP = Join-Path ([System.IO.Path]::GetTempPath()) ("ms-test-" + [Guid]::NewGuid().ToString("N").Substring(0, 10))
New-Item -ItemType Directory -Force -Path $TMP | Out-Null
try {
  # ---- 1. REAL relocate: .git pointer + cache links + manifest --------------
  $v1   = Join-Path $TMP "vault1"; New-Vault $v1
  $side = Join-Path $TMP "sidecar"
  $r = Run-MS -MsArgs @($v1, "-Sidecar", $side)
  Check "relocate: rc 0"                       ($r.rc -eq 0)
  $gitptr = Join-Path $v1 ".git"
  $gitIsFile = (Test-Path -LiteralPath $gitptr -PathType Leaf)
  Check "relocate: .git is now a pointer FILE" $gitIsFile
  if ($gitIsFile) {
    $first = Get-Content -LiteralPath $gitptr -TotalCount 1
    Check "relocate: .git pointer says 'gitdir:'" ("$first" -match '^gitdir:')
  }
  Check "relocate: .smart-env is a link"       (Is-Reparse (Join-Path $v1 ".smart-env"))
  Check "relocate: .codegraph is a link"       (Is-Reparse (Join-Path $v1 ".codegraph"))
  Check "relocate: emoji-Meta/Sessions is a link" (Is-Reparse (Join-Path $v1 "$gear Meta/Sessions"))
  Check "relocate: .claude/worktrees is a link" (Is-Reparse (Join-Path $v1 ".claude/worktrees"))
  Check "relocate: cached file survived the move" (Test-Path -LiteralPath (Join-Path $v1 ".smart-env/cache.bin"))
  $man = @(Get-ChildItem -LiteralPath (Join-Path $side "manifests") -Filter *.json -ErrorAction SilentlyContinue)
  Check "relocate: manifest written"           ($man.Count -eq 1)
  if ($man.Count -eq 1) {
    $doc = Get-Content -Raw -LiteralPath $man[0].FullName | ConvertFrom-Json
    Check "relocate: manifest 'vault' = resolved vault (suppression key)" ($doc.vault -eq (RealPath $v1))
    Check "relocate: manifest schema tag"      ($doc.schema -eq "machinery-sidecar/1")
  }

  # ---- 2. idempotency: re-run is a no-op report -----------------------------
  $r = Run-MS -MsArgs @($v1, "-Sidecar", $side)
  Check "idempotent: rc 0"                     ($r.rc -eq 0)
  Check "idempotent: .git already a pointer"   ($r.out -match "already a pointer")
  Check "idempotent: a cache already a link"   ($r.out -match "already a link")

  # ---- 3. rollback restores .git dir + caches, removes manifest -------------
  $r = Run-MS -MsArgs @($v1, "-Sidecar", $side, "-Rollback")
  Check "rollback: rc 0"                       ($r.rc -eq 0)
  Check "rollback: .git is a real dir again"   (Test-Path -LiteralPath (Join-Path $v1 ".git") -PathType Container)
  Check "rollback: .smart-env is a real dir again" ((Test-Path -LiteralPath (Join-Path $v1 ".smart-env") -PathType Container) -and -not (Is-Reparse (Join-Path $v1 ".smart-env")))
  Check "rollback: cached file still present"  (Test-Path -LiteralPath (Join-Path $v1 ".smart-env/cache.bin"))
  Check "rollback: manifest removed"           (-not (Test-Path -LiteralPath $man[0].FullName))

  # ---- 4. dry-run inertness -------------------------------------------------
  $v4 = Join-Path $TMP "vault4"; New-Vault $v4
  $r = Run-MS -MsArgs @($v4, "-Sidecar", (Join-Path $TMP "sidecar4"), "-DryRun")
  Check "dry-run: rc 0"                        ($r.rc -eq 0)
  Check "dry-run: .git still a real dir"       (Test-Path -LiteralPath (Join-Path $v4 ".git") -PathType Container)
  Check "dry-run: no sidecar manifest written" (-not (Test-Path -LiteralPath (Join-Path $TMP "sidecar4/manifests")))

  # ---- 5. GUARD: a live linked worktree REFUSES (separate-git-dir orphans) --
  $v5 = Join-Path $TMP "vault5"; New-Vault $v5
  Set-Content -LiteralPath (Join-Path $v5 "f.txt") -Value "x"
  & git -C $v5 add -A | Out-Null
  & git -C $v5 commit -qm init | Out-Null
  & git -C $v5 worktree add -q (Join-Path $TMP "wt5") -b scratch5 | Out-Null
  $r = Run-MS -MsArgs @($v5, "-Sidecar", (Join-Path $TMP "sidecar5"))
  Check "guard: linked worktree -> rc 1 (refuse)" ($r.rc -eq 1)
  Check "guard: explains the refusal"          ($r.out -match "refusing")
  Check "guard: .git untouched (still a dir)"   (Test-Path -LiteralPath (Join-Path $v5 ".git") -PathType Container)
  # negative control: -Force proceeds past the same guard
  $r = Run-MS -MsArgs @($v5, "-Sidecar", (Join-Path $TMP "sidecar5"), "-Force")
  Check "guard neg-control: -Force proceeds (rc 0)" ($r.rc -eq 0)
}
finally {
  # detach any worktree gitdir lock before cleanup
  Remove-Item -LiteralPath $TMP -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ""
if ($script:fails -gt 0) { Write-Host "FAILED: $($script:fails)"; exit 1 }
Write-Host "ALL TESTS PASSED"
exit 0
