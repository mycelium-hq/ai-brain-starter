#!/usr/bin/env bash
# CI integration wrapper - runs the bootstrap.ps1 8.3 short-path suite
# (tests/integration/test_bootstrap_ps1_long_paths.ps1, tickets#7337) on pwsh 7.
# The real GetLongPathNameW check only runs on Windows: windows-install.yml runs
# the same .ps1 under Windows PowerShell 5.1 for that half.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

if ! command -v pwsh >/dev/null 2>&1; then
  echo "SKIP: pwsh not installed here; CI's ubuntu + windows runners enforce this suite."
  exit 0
fi

pwsh -NoProfile -File "$ROOT/tests/integration/test_bootstrap_ps1_long_paths.ps1"
