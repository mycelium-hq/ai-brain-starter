#!/usr/bin/env bash
# CI integration wrapper — runs the relocate-sweep negative-control suite
# (scripts/test-relocate-sweep.py) as part of scripts/ci.sh. Thin: the logic
# lives next to the script it exercises. python3 (not bash) because the sweep and
# its test are Python — JSON parsing, AST/tokenize-aware classification, and
# git-ref grepping are not shell work.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
exec python3 "$ROOT/scripts/test-relocate-sweep.py"
