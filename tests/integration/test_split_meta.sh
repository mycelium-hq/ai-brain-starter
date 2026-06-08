#!/usr/bin/env bash
# CI wrapper - runs the split-meta detector regression suite
# (scripts/test-split-meta.sh) as part of scripts/ci.sh.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
exec bash "$ROOT/scripts/test-split-meta.sh"
