#!/usr/bin/env bash
# Negative-control test for check-renderer-crashes.py (the large-vault renderer-OOM guard).
# A guard earns trust only by failing on the thing it catches: this asserts a HIT
# for a reports dir with repeated Obsidian-renderer EXC_BREAKPOINT crashes AND OK
# for every negative control (no reports, wrong app, wrong signature, a single
# isolated crash, and crashes outside the time window).
# Run: bash scripts/test-renderer-crash-guard.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/check-renderer-crashes.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0

# mk DIR FILENAME EXCEPTION-LINE - write a synthetic .ips crash report. The
# Obsidian/Renderer identity lives in the FILENAME (that is what the detector
# matches); the EXCEPTION-LINE carries the crash signature.
mk() { mkdir -p "$1"; printf '%s\n' "$3" > "$1/$2"; }

assert_token() { # label  expected-prefix  dir
  local label="$1" want="$2" d="$3" got
  got="$(python3 "$CHECK" --porcelain --reports-dir "$d" 2>/dev/null)"
  case "$got" in
    "$want"*) echo "PASS  $label  ($got)";;
    *)        echo "FAIL  $label  want=$want got=$got"; fails=$((fails+1));;
  esac
}

assert_rc() { # label  want-rc  dir
  local label="$1" want="$2" d="$3"
  python3 "$CHECK" --porcelain --reports-dir "$d" >/dev/null 2>&1
  local rc=$?
  [ "$rc" = "$want" ] && echo "PASS  $label (rc=$rc)" || { echo "FAIL  $label want-rc=$want got-rc=$rc"; fails=$((fails+1)); }
}

EXC="Exception Type:  EXC_BREAKPOINT (SIGTRAP)"

# POSITIVE: >=2 fresh Obsidian-renderer EXC_BREAKPOINT reports must be flagged HIT (exit 1)
POS="$TMP/pos"
mk "$POS" "Obsidian Helper (Renderer)-2026-06-06-100000.ips" "$EXC"
mk "$POS" "Obsidian Helper (Renderer)-2026-06-06-110000.ips" "$EXC"
mk "$POS" "Obsidian Helper (Renderer)-2026-06-06-120000.ips" "$EXC"
assert_token "repeated renderer crashes" "RENDERER_CRASHES" "$POS"
assert_rc    "HIT exits 1"               1                  "$POS"

# NEGATIVE CONTROL 1: empty dir -> OK (proves it is not just always-HIT; a guard
# that always fires is as useless as one that never does)
assert_token "no reports"  "OK_NO_CRASHES" "$TMP/empty"
assert_rc    "OK exits 0"  0               "$TMP/empty"

# NEGATIVE CONTROL 2: wrong app / wrong process (filename lacks Obsidian or Renderer)
WRONGAPP="$TMP/wrongapp"
mk "$WRONGAPP" "SomeEditor Helper (Renderer)-1.ips" "$EXC"
mk "$WRONGAPP" "Obsidian-main-1.ips"                 "$EXC"
assert_token "wrong app/process" "OK_NO_CRASHES" "$WRONGAPP"

# NEGATIVE CONTROL 3: right file, wrong signature (not an OOM EXC_BREAKPOINT)
WRONGSIG="$TMP/wrongsig"
mk "$WRONGSIG" "Obsidian Helper (Renderer)-a.ips" "Exception Type:  EXC_CRASH (SIGABRT)"
mk "$WRONGSIG" "Obsidian Helper (Renderer)-b.ips" "Exception Type:  EXC_CRASH (SIGABRT)"
assert_token "wrong signature" "OK_NO_CRASHES" "$WRONGSIG"

# NEGATIVE CONTROL 4: a single isolated crash is below the "repeated" threshold
SINGLE="$TMP/single"
mk "$SINGLE" "Obsidian Helper (Renderer)-only.ips" "$EXC"
assert_token "single crash (<threshold)" "OK_NO_CRASHES" "$SINGLE"

# NEGATIVE CONTROL 5: crashes outside the time window do not count. Backdate via
# Python os.utime so it is portable across BSD/GNU date (CI runs on ubuntu).
OLD="$TMP/old"
mk "$OLD" "Obsidian Helper (Renderer)-old1.ips" "$EXC"
mk "$OLD" "Obsidian Helper (Renderer)-old2.ips" "$EXC"
python3 - "$OLD" <<'PY'
import os, sys, glob, time
old = time.time() - 400 * 86400
for f in glob.glob(os.path.join(sys.argv[1], "*.ips")):
    os.utime(f, (old, old))
PY
assert_token "old crashes (outside window)" "OK_NO_CRASHES" "$OLD"

echo
if [ "$fails" -gt 0 ]; then echo "FAILED: $fails"; exit 1; fi
echo "ALL TESTS PASSED"
