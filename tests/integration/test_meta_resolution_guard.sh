#!/usr/bin/env bash
# CI wrapper - runs the meta-resolution guard negative-control suite
# (scripts/test-meta-resolution-guard.sh) as part of scripts/ci.sh.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
exec bash "$ROOT/scripts/test-meta-resolution-guard.sh"
