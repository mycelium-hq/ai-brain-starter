#!/usr/bin/env bash
# CI integration wrapper - runs the PowerShell relocate parity suites
# (scripts/test-relocate-vault.ps1 + scripts/test-relocate-machinery-sidecar.ps1,
# MYC-2383) as part of scripts/ci.sh. pwsh is preinstalled on GitHub's
# ubuntu-latest runner, so CI always exercises them. If pwsh is absent locally we
# LOUDLY skip (CI still enforces) rather than block a contributor's other gates -
# the same graceful-degradation pattern ci.sh uses for shellcheck and ruff.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

if ! command -v pwsh >/dev/null 2>&1; then
  echo "SKIP: pwsh not installed here; CI's ubuntu runner enforces the .ps1 behavioral tests."
  echo "      install: brew install --cask powershell (macOS) / https://aka.ms/powershell (other)"
  exit 0
fi

pwsh -NoProfile -File "$ROOT/scripts/test-relocate-vault.ps1"
pwsh -NoProfile -File "$ROOT/scripts/test-relocate-machinery-sidecar.ps1"
