#!/usr/bin/env bash
# CI integration wrapper — runs the memory-routing-guard negative-control +
# install-registration smoke (scripts/test-memory-routing-guard.sh) as part of
# scripts/ci.sh. Thin: the logic lives next to the script it exercises.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
exec bash "$ROOT/scripts/test-memory-routing-guard.sh"
