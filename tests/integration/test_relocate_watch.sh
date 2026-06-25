#!/usr/bin/env bash
# CI integration wrapper — runs the relocate-WATCH (mode 2) integration + negative-
# control suite (scripts/test-relocate-watch.py) as part of scripts/ci.sh. Thin: the
# logic lives next to the engine it exercises. python3 (not bash) because the watch,
# the manifest, the surfacer hook, and the boundedness check are Python — JSON,
# subprocess-driving the bash relocate-vault.sh, and exit-code assertions.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
exec python3 "$ROOT/scripts/test-relocate-watch.py"
