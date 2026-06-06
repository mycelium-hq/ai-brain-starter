#!/usr/bin/env bash
# Negative-control test for check-cloud-sync.py (the vault-in-cloud-sync guard).
# A guard earns trust only by failing on the thing it catches: this asserts RISK
# for paths inside iCloud / OneDrive / Dropbox AND OK for a plain local path.
# Run: bash scripts/test-cloud-sync-guard.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/check-cloud-sync.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0

assert() { # label  expected-token  path
  local label="$1" want="$2" p="$3" got rc
  mkdir -p "$p"
  got="$(python3 "$CHECK" --porcelain "$p" 2>/dev/null)"; rc=$?
  case "$got" in
    "$want"*) echo "PASS  $label  ($got, rc=$rc)";;
    *)        echo "FAIL  $label  want=$want got=$got rc=$rc"; fails=$((fails+1));;
  esac
}

assert_rc() { # label  want-rc  path
  local label="$1" want="$2" p="$3"
  mkdir -p "$p"; python3 "$CHECK" --porcelain "$p" >/dev/null 2>&1
  local rc=$?
  [ "$rc" = "$want" ] && echo "PASS  $label (rc=$rc)" || { echo "FAIL  $label want-rc=$want got-rc=$rc"; fails=$((fails+1)); }
}

# POSITIVE: cloud-sync roots must be flagged RISK (exit 1)
assert    "iCloud Drive root"  "CLOUD_SYNC_RISK"  "$TMP/Library/Mobile Documents/com~apple~CloudDocs/Brain"
assert    "OneDrive root"      "CLOUD_SYNC_RISK"  "$TMP/OneDrive/Brain"
assert    "Dropbox root"       "CLOUD_SYNC_RISK"  "$TMP/Dropbox/Notes"
assert_rc "RISK exits 1"       1                  "$TMP/OneDrive/Brain"

# NEGATIVE CONTROL: a plain local path must be OK (exit 0) — proves it is not
# just always-RISK (a guard that always fires is as useless as one that never does)
assert    "plain local path"   "OK_LOCAL"         "$TMP/Brain"
assert_rc "OK exits 0"         0                  "$TMP/Brain"

echo
if [ "$fails" -gt 0 ]; then echo "FAILED: $fails"; exit 1; fi
echo "ALL TESTS PASSED"
