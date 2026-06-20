#!/usr/bin/env bash
# CI integration wrapper - runs the worktree-on-vault melt-guard negative-control
# suite (scripts/test-worktree-on-vault-guard.sh) as part of scripts/ci.sh. Thin:
# logic lives next to the script it exercises.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
exec bash "$ROOT/scripts/test-worktree-on-vault-guard.sh"
