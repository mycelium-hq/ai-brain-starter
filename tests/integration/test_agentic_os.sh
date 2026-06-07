#!/usr/bin/env bash
# CI integration wrapper - runs the agentic-os/ install-primitive invariant +
# negative-control suite (scripts/test-agentic-os.sh) as part of scripts/ci.sh.
# Thin: logic lives next to the template it exercises.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
exec bash "$ROOT/scripts/test-agentic-os.sh"
