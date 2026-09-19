#!/usr/bin/env bash
# Test bootstrap.sh's Python interpreter discovery.
#
# Bug (2026-08-18 cohort feedback): bootstrap.sh tested one name -- `python3` --
# and, finding it older than 3.10, installed Python 3.12. On macOS `python3` is
# /usr/bin/python3 (3.9) whenever Homebrew sits later in PATH, so the machine
# got a redundant install that could not help: installing a formula does not
# change what `python3` resolves to while /usr/bin still comes first, so every
# python3 call in the rest of the script kept running 3.9. Machines that already
# had a perfectly good python3.14 went through the whole detour.
#
# pick_python() resolves an interpreter ONCE, up front, preferring `python3` when
# it already qualifies (so nothing changes for anyone bootstrap already worked
# for) and otherwise walking the version-suffixed names newest-first.
#
# Covered here:
#   1. pick_python() exists and is extractable from the real bootstrap.sh.
#   2. THE REPORTED CASE: python3 too old, python3.12 present -> the versioned
#      one is chosen. Paired with a NEGATIVE CONTROL asserting the ambient
#      python3 in that same sandbox really does fail the >=3.10 test, so this
#      cannot pass because the fixture forgot to model the bug.
#   3. python3 already new enough -> it is kept, and a newer sibling does NOT
#      displace it. This is the "changes nothing for existing installs" claim.
#   4. Newest-first ordering among several qualifying versioned names.
#   5. Nothing new enough -> pick_python reports failure rather than silently
#      selecting a too-old interpreter.
#   6. AI_BRAIN_PYTHON names an interpreter no search would find.
#   7. Every executed python3 call in bootstrap.sh routes through "$PY" -- a
#      structural check, because one missed call site silently runs 3.9 again.
#
# pick_python is extracted from the real bootstrap.sh (never reimplemented), so
# this cannot drift from the shipped source -- same technique as
# test_bootstrap_userspace_fallback.sh.
#
# PATH is sealed to the stub directory alone, so the runner's own interpreters
# cannot decide any outcome. That matters: /usr/bin/python3 is 3.9 on macOS but
# 3.12 on the Ubuntu CI runner, and a leaky PATH would make check 5 pass locally
# and fail in CI (exactly the trap documented in the userspace-fallback test).
# Stubs use #!/bin/sh, not `env bash`, because `env` needs a PATH to find bash.
#
# Self-contained; no network. Its own writes stay in its temp dir, with one
# exception worth knowing: run_pick uses `env -i`, which clears TMPDIR, so
# pick_python's probe dir lands in the system temp instead. pick_python removes
# it on every path, but this file's EXIT trap cannot reach it if that is
# interrupted mid-run.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=tests/integration/lib/sandbox_home.sh
. "$REPO_ROOT/tests/integration/lib/sandbox_home.sh"
BOOTSTRAP="$REPO_ROOT/bootstrap.sh"
[ -f "$BOOTSTRAP" ] || { echo "ERROR: $BOOTSTRAP not found" >&2; exit 1; }

fail() { echo "FAIL: $1" >&2; exit 1; }

TMP="$(mktemp -d)"
sandbox_home "$TMP/realhome-guard"
trap 'rm -rf "$TMP"' EXIT

# Absolute bash, captured BEFORE any PATH sealing below.
BASH_BIN="$(command -v bash)"

# ── 1. pick_python() is present in the shipped script ──
PICK_SRC="$(awk '/^pick_python\(\)[ ]*\{/,/^}$/' "$BOOTSTRAP")"
[ -n "$PICK_SRC" ] || fail "1: pick_python() not found in bootstrap.sh"

# mk_py DIR NAME VERSION — a stand-in interpreter answering the questions
# pick_python asks: the >=3.10 probe as a SCRIPT FILE (the shape every later
# "$PY" call uses), the same probe via -c, and --version.
mk_py() {
  local path="$1/$2" minor="${3#3.}"
  cat > "$path" <<STUB
#!/bin/sh
case "\$1" in
  -c) [ "$minor" -ge 10 ] && exit 0; exit 1 ;;
  --version|-V) echo "Python $3"; exit 0 ;;
  *.py) [ "$minor" -ge 10 ] && echo "__ai_brain_python_ok__"; exit 0 ;;
esac
echo "Python $3"
STUB
  chmod +x "$path"
}

# NOTE on the *.py arm: it exits 0 for EVERY version and prints the token only
# when the version qualifies, because that is what a real interpreter does — the
# probe script runs fine on 3.9 and simply prints nothing. Exiting non-zero for
# old versions instead would model a state no Python can reach, and it would
# make this whole file blind to a probe that reads the exit status and ignores
# stdout: such a probe selects a real 3.9 as $PY (the original 2026-08-18 bug)
# while every check here still passes. Check 5 is the oracle that catches it.

# mk_shim_py DIR NAME VERSION — a shim on the two axes check 8 turns on: `-c`
# is answered exactly as a real interpreter of that version would, and a SCRIPT
# PATH is refused. It is NOT a faithful model of trailofbits/modern-python
# elsewhere — that shim scans argv for a mode selector, so it also forwards `-`
# and `-m` (bar pip) and REFUSES `--version`, where this stub does the opposite.
# bootstrap.sh has several `"$PY" - <<` call sites the real shim forwards fine;
# anyone extending this stub to cover them must read the shim, not this.
mk_shim_py() {
  local path="$1/$2" minor="${3#3.}"
  cat > "$path" <<STUB
#!/bin/sh
case "\$1" in
  -c) [ "$minor" -ge 10 ] && exit 0; exit 1 ;;
  --version|-V) echo "Python $3"; exit 0 ;;
esac
echo "ERROR: Use 'uv run python <script>' instead of python3 <script>" >&2
exit 1
STUB
  chmod +x "$path"
}

# pick_python writes its probe to a temp file, so it needs mktemp and rm. The
# PATH seal below exists to control which INTERPRETERS are visible, not to
# forbid coreutils, so those two live in their own directory appended after the
# stub dir. It holds no python, so no outcome here can still be decided by the
# runner's own interpreters — the trap the seal was built for.
UTILS="$TMP/utils"; mkdir -p "$UTILS"
for _u in mktemp rm; do
  _r="$(command -v "$_u" 2>/dev/null)" || fail "setup: $_u not found, cannot build the utils dir"
  ln -s "$_r" "$UTILS/$_u"
done

# run_pick DIR [AI_BRAIN_PYTHON] -> prints "PY=<resolved>" and, on failure,
# "PICK_FAILED". PATH is the stub dir plus the python-free utils dir.
run_pick() {
  local dir="$1" override="${2:-}" harness="$TMP/pick-harness.sh"
  {
    echo 'set -euo pipefail'   # the flags bootstrap.sh itself runs under
    echo 'PY="python3"'
    printf '%s\n' "$PICK_SRC"
    echo 'pick_python || echo "PICK_FAILED"'
    echo 'echo "PY=$PY"'
  } > "$harness"
  env -i PATH="$dir:$UTILS" AI_BRAIN_PYTHON="$override" "$BASH_BIN" "$harness" 2>&1
}

# ── 2. THE REPORTED CASE: too-old python3, good python3.12 alongside ──
D2="$TMP/case2"; mkdir -p "$D2"
mk_py "$D2" python3 3.9
mk_py "$D2" python3.12 3.12

# Negative control FIRST: the sandbox must really reproduce the bug, or check 2
# would be asserting against a fixture that was never broken.
if env -i PATH="$D2" "$D2/python3" -c 'x' >/dev/null 2>&1; then
  fail "2 (negative control): the stub python3 passes the >=3.10 probe, so this sandbox does not model the reported bug at all"
fi

OUT2="$(run_pick "$D2")"
case "$OUT2" in
  *PICK_FAILED*) fail "2: pick_python found nothing, but python3.12 was right there. Output: $OUT2" ;;
esac
case "$OUT2" in
  *"PY=$D2/python3.12"*) : ;;
  *) fail "2: expected python3.12 to be chosen, got: $OUT2" ;;
esac

# ── 3. a qualifying python3 is KEPT (no change for existing installs) ──
D3="$TMP/case3"; mkdir -p "$D3"
mk_py "$D3" python3 3.12
mk_py "$D3" python3.14 3.14
OUT3="$(run_pick "$D3")"
case "$OUT3" in
  *"PY=$D3/python3"*) : ;;
  *) fail "3: a working python3 must be kept rather than displaced by a newer sibling, got: $OUT3" ;;
esac
case "$OUT3" in
  *python3.14*) fail "3: python3.14 displaced a perfectly good python3 — that is a behaviour change for installs that already worked. Got: $OUT3" ;;
esac

# ── 4. newest-first among versioned names ──
D4="$TMP/case4"; mkdir -p "$D4"
mk_py "$D4" python3 3.9
mk_py "$D4" python3.10 3.10
mk_py "$D4" python3.11 3.11
mk_py "$D4" python3.13 3.13
OUT4="$(run_pick "$D4")"
case "$OUT4" in
  *"PY=$D4/python3.13"*) : ;;
  *) fail "4: expected the newest qualifying interpreter (3.13), got: $OUT4" ;;
esac

# ── 5. nothing new enough -> reports failure, does not select a too-old one ──
D5="$TMP/case5"; mkdir -p "$D5"
mk_py "$D5" python3 3.9
mk_py "$D5" python3.8 3.8
OUT5="$(run_pick "$D5")"
case "$OUT5" in
  *PICK_FAILED*) : ;;
  *) fail "5: pick_python must report failure when nothing reaches 3.10, so the caller still installs one. Got: $OUT5" ;;
esac

# ── 6. AI_BRAIN_PYTHON reaches a prefix no search would guess ──
D6="$TMP/case6"; mkdir -p "$D6"
mk_py "$D6" python3 3.9
D6_ELSEWHERE="$TMP/case6-prefix"; mkdir -p "$D6_ELSEWHERE"
mk_py "$D6_ELSEWHERE" python3 3.12
OUT6="$(run_pick "$D6" "$D6_ELSEWHERE/python3")"
case "$OUT6" in
  *"PY=$D6_ELSEWHERE/python3"*) : ;;
  *) fail "6: AI_BRAIN_PYTHON was ignored, got: $OUT6" ;;
esac

# ── 7. every executed python3 call routes through "$PY" ──
# One missed call site runs 3.9 again on exactly the machines this fixes, and
# nothing would say so. Comments, the candidate list inside pick_python, apt/dnf
# PACKAGE names, and user-facing recovery text are all legitimately still
# "python3", so strip those before looking.
STRAY="$(grep -nE '(^|[^A-Za-z_#"])python3 ' "$BOOTSTRAP" \
  | grep -vE '^[0-9]+:[[:space:]]*#' \
  | grep -vE 'for candidate in' \
  | grep -vE 'apt-get install|dnf install|pacman -S' \
  | grep -vE '^[0-9]+:[[:space:]]*(err|dry|warn|log|ok) ' \
  || true)"
[ -z "$STRAY" ] || fail "7: these python3 invocations still bypass \$PY, so they keep running whatever PATH resolves first:
$STRAY"

# ── 8. a shim that answers -c but refuses a script file is NOT selected ──
# The shape trailofbits/modern-python ships. pick_python probed with `-c`, which
# that shim forwards to the real interpreter, so the version answer came back
# healthy and the SHIM ITSELF was selected as $PY. Every later use is a script
# path -- `exec "$PY" "$INSTALLER"` and `"$PY" "$USER_HOOK_INSTALLER"` -- so the
# install died there instead, with the shim's advice as the error. Measured on a
# machine carrying the plugin: the old probe picked the shim.
D8="$TMP/case8"; mkdir -p "$D8"
mk_shim_py "$D8" python3    3.14   # answers -c like a 3.14, refuses scripts
mk_py      "$D8" python3.12 3.12   # a real interpreter sitting right beside it

# Negative controls FIRST, on the fixture itself. The shim must genuinely PASS
# the old -c probe, or this leg is a re-run of case 2 and says nothing about the
# blind spot; and it must genuinely refuse a script file, or it is not a shim.
if ! env -i PATH="$D8" "$D8/python3" \
     -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,10) else 1)' >/dev/null 2>&1; then
  fail "8 (negative control): the shim stub fails the -c probe, so a -c-based pick_python would have rejected it anyway and this leg proves nothing"
fi
: > "$TMP/case8-probe.py"
if env -i PATH="$D8" "$D8/python3" "$TMP/case8-probe.py" >/dev/null 2>&1; then
  fail "8 (negative control): the shim stub runs script files, so it does not model a shim at all"
fi

OUT8="$(run_pick "$D8")"
case "$OUT8" in
  *PICK_FAILED*) fail "8: pick_python found nothing, but python3.12 was right there. Output: $OUT8" ;;
esac
case "$OUT8" in
  *"PY=$D8/python3.12"*) : ;;
  *"PY=$D8/python3"*)
    fail "8: pick_python selected the SHIM as \$PY. Every \"\$PY\" <script> call in bootstrap.sh then dies with the shim's advice instead of installing. Got: $OUT8" ;;
  *) fail "8: expected python3.12 to be chosen, got: $OUT8" ;;
esac

echo "PASS: test_bootstrap_python_discovery (8 checks, 3 negative controls)"
