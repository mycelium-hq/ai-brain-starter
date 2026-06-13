#!/usr/bin/env bash
# CI integration wrapper — runs the first-run context-load self-test fixture
# suite (scripts/test-context-load-selftest.sh) as part of `scripts/ci.sh`.
# Thin: the fixtures live next to the script they exercise (check-context-load.py).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
exec bash "$ROOT/scripts/test-context-load-selftest.sh"
