#!/usr/bin/env bash
# CI lock for the SessionStart forward guard (MYC-571, parent incident MYC-570).
#
# scripts/audit-sessionstart-boundedness.py asserts that every SessionStart-wired
# hook which does a recursive / corpus-scale filesystem walk carries all three
# bounded-hook guards - single-instance flock + cooldown stamped-at-START +
# wall-clock deadline - OR a co-located `# sessionstart-walk-bounded: <reason>`
# exemption.
#
# This is the FORWARD half of the 2026-06-05 Mac-freeze fix. MYC-512 moved the
# corpus-walk secret scan off SessionStart, MYC-514 hardened it, and
# test_sessionstart_freeze_class_excluded.sh pins those two SPECIFIC hooks. But
# nothing stopped the NEXT new SessionStart hook from re-introducing the
# corpus-walk-on-cold-start class. This guard + test close that gap by making the
# bounded-hook property checkable by construction (it mechanizes the hand-written
# "Bound" column in docs/HOOK_FLEET_RESOURCE_GOVERNANCE.md).
#
# Asserts:
#   1. The detector's own pos/neg controls pass (--selftest).
#   2. The REAL shipped SessionStart fleet (this repo's hooks.json) is clean (--all).
#   3. NEGATIVE CONTROL: a synthetic hooks.json wiring an unguarded corpus-walk
#      hook on SessionStart trips --all (exit 1), and --check trips on that file.
#      Proves the guard BITES, not just passes.
#   4. POSITIVE CONTROL: a fully-guarded walk passes --check (exit 0).
#
# Stdlib python3 + bash only. No network, no git. Tmpdirs removed on exit.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AUDIT="$REPO_ROOT/scripts/audit-sessionstart-boundedness.py"

PASS=0
FAIL=0
TMPDIRS=()
cleanup() { for d in "${TMPDIRS[@]:-}"; do [ -n "$d" ] && rm -rf "$d"; done; }
trap cleanup EXIT

ok()  { PASS=$((PASS + 1)); echo "PASS  $1"; }
bad() { FAIL=$((FAIL + 1)); echo "FAIL  $1 :: $2"; }

echo "=== precondition ==="
if [ -f "$AUDIT" ]; then ok "detector present"; else bad "detector present" "missing $AUDIT"; fi

echo "=== 1. detector pos/neg controls (--selftest) ==="
if python3 "$AUDIT" --selftest >/dev/null 2>&1; then
  ok "--selftest passes"
else
  bad "--selftest passes" "run: python3 $AUDIT --selftest"
fi

echo "=== 2. shipped SessionStart fleet is clean (--all) ==="
if python3 "$AUDIT" --all >/dev/null 2>&1; then
  ok "real shipped fleet is guarded/declared-bounded"
else
  bad "real shipped fleet clean" "a wired hook is an unguarded corpus walk (run: python3 $AUDIT --all)"
fi

echo "=== 3. NEGATIVE CONTROL: an unguarded corpus-walk hook trips the guard ==="
NEG="$(mktemp -d)"
TMPDIRS+=("$NEG")
mkdir -p "$NEG/hooks"
cat > "$NEG/hooks/evil-walk.py" <<'PY'
#!/usr/bin/env python3
import os
def main():
    for _root, _dirs, _files in os.walk(os.path.expanduser("~")):  # unbounded corpus walk, no guards
        pass
PY
cat > "$NEG/hooks.json" <<'JSON'
{"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/evil-walk.py"}]}]}}
JSON
if python3 "$AUDIT" --all --hooks-json "$NEG/hooks.json" --hooks-dir "$NEG/hooks" >/dev/null 2>&1; then
  bad "neg control --all trips" "an unguarded SessionStart corpus walk PASSED --all (the guard is asleep)"
else
  ok "neg control --all trips (exit 1)"
fi
if python3 "$AUDIT" --check "$NEG/hooks/evil-walk.py" >/dev/null 2>&1; then
  bad "neg control --check trips" "an unguarded corpus walk PASSED --check"
else
  ok "neg control --check trips (exit 1)"
fi

echo "=== 4. POSITIVE CONTROL: a fully-guarded walk passes --check ==="
POS="$(mktemp -d)"
TMPDIRS+=("$POS")
cat > "$POS/good-walk.py" <<'PY'
#!/usr/bin/env python3
import fcntl, time
from pathlib import Path
MARKER = Path("~/.last").expanduser()
def _stamp(): MARKER.write_text(str(time.time()))
def main():
    fh = open("/tmp/x.lock", "w"); fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    _stamp()  # cooldown stamped BEFORE the walk
    deadline = time.time() + 60
    for p in Path("~/vault").expanduser().rglob("*.md"):
        if time.time() > deadline:
            break
PY
if python3 "$AUDIT" --check "$POS/good-walk.py" >/dev/null 2>&1; then
  ok "positive control (3 guards) passes --check"
else
  bad "positive control passes --check" "a fully-guarded walk was wrongly flagged"
fi

echo
echo "=== summary: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
