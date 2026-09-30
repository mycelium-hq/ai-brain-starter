#!/usr/bin/env bash
# CI integration wrapper - runs the PowerShell quick-mint-reused suite
# (tests/integration/test_bootstrap_ps1_quick_mint_reused.ps1) as part of
# scripts/ci.sh. Same pattern as test_bootstrap_ps1_slash_commands.sh: pwsh is
# preinstalled on GitHub's ubuntu-latest runner, so CI always exercises it; if
# pwsh is absent locally we LOUDLY skip rather than block a contributor's other
# gates.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

if ! command -v pwsh >/dev/null 2>&1; then
  echo "SKIP: pwsh not installed here; CI's ubuntu + windows runners enforce this suite."
  echo "      install: brew install --cask powershell (macOS) / https://aka.ms/powershell (other)"
  exit 0
fi

pwsh -NoProfile -File "$ROOT/tests/integration/test_bootstrap_ps1_quick_mint_reused.ps1"
