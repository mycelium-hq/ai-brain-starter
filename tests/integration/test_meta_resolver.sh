#!/usr/bin/env bash
# CI integration wrapper - runs the meta-resolver regression suite
# (scripts/test-meta-resolver.sh) as part of scripts/ci.sh. Kept thin so the
# test logic has ONE home next to the resolver it exercises.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
exec bash "$ROOT/scripts/test-meta-resolver.sh"
