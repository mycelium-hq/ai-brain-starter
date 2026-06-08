#!/usr/bin/env bash
#
# scripts/test-split-meta.sh - regression test for scripts/check-split-meta.py.
# Proves the detector flags a vault whose session data leaked into a plain
# "Meta/" beside the human "⚙️ Meta/", and stays quiet on healthy layouts.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DETECT="$HERE/check-split-meta.py"

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

# --- split-brain: human session data leaked into plain Meta (the bug) -------
mkdir -p "$base/split/Meta/Sessions"
mkdir -p "$base/split/Meta/Learnings"
mkdir -p "$base/split/⚙️ Meta/Decisions"
check "leaked Sessions/ in plain Meta -> SPLIT_META" "SPLIT_META:1" \
  "$(python3 "$DETECT" --porcelain "$base/split")"

# --- healthy partition: machine in Meta, human in ⚙️ Meta -------------------
mkdir -p "$base/clean/Meta/Learnings"
mkdir -p "$base/clean/⚙️ Meta/Sessions"
mkdir -p "$base/clean/⚙️ Meta/Decisions"
check "machine-only plain Meta -> OK_PARTITIONED" "OK_PARTITIONED" \
  "$(python3 "$DETECT" --porcelain "$base/clean")"

# --- single Meta vault (stock) ----------------------------------------------
mkdir -p "$base/single/⚙️ Meta/Decisions"
check "single Meta -> OK_SINGLE_META" "OK_SINGLE_META" \
  "$(python3 "$DETECT" --porcelain "$base/single")"

# --- no Meta at all ---------------------------------------------------------
mkdir -p "$base/empty"
check "no Meta -> OK_NO_META" "OK_NO_META" \
  "$(python3 "$DETECT" --porcelain "$base/empty")"

if [ "$fail" != 0 ]; then
  echo "FAILED: split-meta detector test"
  exit 1
fi
echo "PASSED: split-meta detector test (4 assertions)"
