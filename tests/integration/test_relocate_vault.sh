#!/usr/bin/env bash
# CI integration wrapper — runs the relocate-vault negative-control suite
# (scripts/test-relocate-vault.sh) as part of scripts/ci.sh. Thin: the logic
# lives next to the script it exercises.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
exec bash "$ROOT/scripts/test-relocate-vault.sh"
