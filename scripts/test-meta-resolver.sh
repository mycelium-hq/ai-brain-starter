#!/usr/bin/env bash
#
# scripts/test-meta-resolver.sh - regression test for scripts/_meta_resolver.py
# and the shell scripts that resolve the vault "Meta" folder through it.
#
# Bug class (fixed 2026-06-07): a vault can hold BOTH "⚙️ Meta" (human memory:
# Decisions/, Sessions/) AND a plain "Meta" (machine memory: Learnings/). The old
# shell glob `for c in "$VAULT"/*Meta; do ...; break` took the FIRST sorted match,
# and plain "Meta" sorts before the emoji-prefixed "⚙️ Meta", so the session log,
# session archive, traffic dashboard and maintenance logs silently leaked into the
# machine folder. The resolver picks whichever variant CONTAINS the requested
# subfolder, so the human folder wins regardless of sort order or locale.
#
# These assertions lock that in, plus negative controls proving we did not
# over-correct (machine-memory callers, single-Meta vaults, no-Meta vaults).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESOLVER="$HERE/_meta_resolver.py"

fail=0
check() {  # check <description> <expected> <actual>
  if [ "$2" = "$3" ]; then
    echo "  ok: $1"
  else
    echo "  FAIL: $1"
    echo "        expected: [$2]"
    echo "        actual:   [$3]"
    fail=1
  fi
}

base="$(mktemp -d)"
trap 'rm -rf "$base"' EXIT

# --- Fixture A: both Meta variants present (the bug scenario) ----------------
mkdir -p "$base/both/Meta/Learnings"
mkdir -p "$base/both/⚙️ Meta/Decisions"
mkdir -p "$base/both/⚙️ Meta/Sessions"

check "both exist, prefer Decisions -> human emoji Meta" \
  "$base/both/⚙️ Meta" "$(python3 "$RESOLVER" "$base/both" Decisions)"
check "both exist, prefer Sessions Decisions -> human emoji Meta" \
  "$base/both/⚙️ Meta" "$(python3 "$RESOLVER" "$base/both" Sessions Decisions)"
check "both exist, prefer Learnings -> machine plain Meta" \
  "$base/both/Meta" "$(python3 "$RESOLVER" "$base/both" Learnings)"

# --- Fixture B: stock single plain-Meta vault (no regression) ----------------
mkdir -p "$base/single/Meta/Decisions"
check "single plain Meta -> picks it" \
  "$base/single/Meta" "$(python3 "$RESOLVER" "$base/single" Decisions)"

# --- Fixture C: neither variant has the subfolder (documented fallback) ------
mkdir -p "$base/nosub/Meta"
mkdir -p "$base/nosub/⚙️ Meta"
check "neither has subfolder -> first sorted Meta" \
  "$base/nosub/Meta" "$(python3 "$RESOLVER" "$base/nosub" Decisions)"

# --- Fixture D: no Meta folder at all -> non-zero exit, no output ------------
mkdir -p "$base/empty"
if out="$(python3 "$RESOLVER" "$base/empty" Decisions)"; then
  check "no Meta dir -> non-zero exit" "nonzero" "zero (out=[$out])"
else
  check "no Meta dir -> non-zero exit" "nonzero" "nonzero"
fi

if [ "$fail" != 0 ]; then
  echo "FAILED: meta-resolver regression test"
  exit 1
fi
echo "PASSED: meta-resolver regression test (6 assertions)"
