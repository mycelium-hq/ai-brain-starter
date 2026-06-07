#!/usr/bin/env bash
# Test: scan-prior-sessions-for-secrets.py — fail-CLOSED auto-scrub partition
# + hex-256bit Workflow-cache-key carve-out (the two secret-scan residuals the
# in-session freeze fix did not close).
#
# Runs the Python regression suite hooks/test_scan_prior_sessions.py, which
# carries the NEGATIVE CONTROLS that make the fix detectable:
#   - partition_for_scrub(None)  -> scrub nothing   (fail-OPEN regression = red)
#   - partition_for_scrub(set()) -> scrub nothing   (fail-OPEN regression = red)
#   - a non-empty active set still scrubs closed + skips active (feature intact)
#   - _auto_scrub redacts a bare 64-hex secret but PRESERVES a `"key":"v2:<hex>"`
#     Workflow cache key (the scrub-corrupts-resume guard)
#   - scan() skips the v2 cache key but still catches a bare 64-hex secret
#
# Hermetic: HOME is pointed at a temp dir so nothing touches the real
# ~/.claude. The Python suite is otherwise self-contained (pure functions +
# its own tempdirs), so it never mutates the repo or the real corpus.
#
# Exit 0 = pass, exit 1 = fail.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SUITE="$REPO_ROOT/hooks/test_scan_prior_sessions.py"
if [ ! -f "$SUITE" ]; then
  echo "FAIL: regression suite not found at $SUITE" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "--- hooks/test_scan_prior_sessions.py (fail-closed partition + hex v2 carve-out)"
HOME="$TMP" python3 "$SUITE"

echo
echo "PASS: secret-scan residual regressions hold (fail-closed scrub + hex v2 carve-out)."
