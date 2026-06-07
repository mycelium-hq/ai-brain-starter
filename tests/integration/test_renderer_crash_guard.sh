#!/usr/bin/env bash
# CI integration wrapper - runs the renderer-crash detection negative-control
# suite (scripts/test-renderer-crash-guard.sh) as part of scripts/ci.sh. Thin:
# logic lives next to the script it exercises.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
exec bash "$ROOT/scripts/test-renderer-crash-guard.sh"
