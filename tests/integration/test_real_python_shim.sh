#!/usr/bin/env bash
# test_real_python_shim.sh
#
# lib/real_python.sh exists because a `python3` shim on PATH turns the whole
# suite red for a reason no test asserts. Every check below is a NEGATIVE
# control: the shim is planted and the helper must defeat it, or no shim exists
# and the helper must leave PATH alone. A helper that has never faced the thing
# it defeats is unproven, and one that meddles when nothing is wrong is a new
# hazard of its own.
#
# Two shim SHAPES are planted, because the shape decides whether the helper can
# even see the problem. A shim that refuses every form is easy. The one that
# actually ships is asymmetric: trailofbits/modern-python hands `-c`, `-` and
# `-m` (bar pip) to the real interpreter and refuses only a script PATH — the
# single form all 103 python-invoking tests here use. The helper used to probe
# with `python3 -c 'pass'`, which that shim answers 0 to, so it returned early on
# exactly the machines it existed to rescue. Legs 4 and 5 are that shape, and
# each one first proves its own fixture is asymmetric — a control that refuses
# `-c` as well would have been caught by the old check too, and would prove
# nothing about the blind spot.
#
# Every assertion runs a script FILE, never `-c`, for the same reason.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/lib/real_python.sh"

FAILED=0
pass() { printf '  PASS: %s\n' "$1"; }
fail() { printf '  FAIL: %s\n' "$1"; FAILED=1; }

echo "test_real_python_shim"

[ -f "$LIB" ] || { echo "  FAIL: $LIB not found"; exit 1; }

# The suite's own invocation shape, owned by this file rather than imported from
# the library under test: a helper that blanked its sentinel would make an
# imported probe match anything, and these assertions with it.
MARKER='PROBE_RAN'
PROBE_DIR="$(mktemp -d)" || { echo "  FAIL: mktemp"; exit 1; }
PROBE="$PROBE_DIR/probe.py"
printf 'print("%s")\n' "$MARKER" > "$PROBE"
trap 'rm -rf "$PROBE_DIR"' EXIT

runs_script() { # runs_script <interpreter> — does it run a script FILE?
    local out
    out="$("$1" "$PROBE" 2>/dev/null)" || return 1
    case "$out" in *"$MARKER"*) return 0 ;; esac
    return 1
}

# A stand-in for a shim that refuses every form.
plant_shim() {
    local d; d="$(mktemp -d)"
    cat > "$d/python3" <<'SH'
#!/bin/sh
echo "ERROR: Use \`uv run python3\` instead of \`python3\`" >&2
exit 1
SH
    chmod +x "$d/python3"
    printf '%s' "$d"
}

# A stand-in for the shape that ships: `-c` / `-m` / `-` succeed, a script path
# is refused. The real shim forwards those three to a working interpreter; only
# the refusal is under test here, so the passthrough is stubbed to a silent
# success. Takes the names to answer to, so a versioned candidate can be
# poisoned as well as the bare one.
plant_asymmetric_shim() {
    local d n; d="$(mktemp -d)"
    for n in "$@"; do
        cat > "$d/$n" <<'SH'
#!/bin/sh
case "${1:-}" in
  -c|-m|-) exit 0 ;;
esac
echo "ERROR: Use \`uv run python $*\` instead of \`python3 $*\`" >&2
exit 1
SH
        chmod +x "$d/$n"
    done
    printf '%s' "$d"
}

# A python3 that works, for the leg where the helper must do nothing. Probed the
# same way the suite calls it, so this fixture can never hand back a shim.
plant_working() {
    local d r c; d="$(mktemp -d)"
    for c in python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 \
             /usr/bin/python3 /opt/homebrew/bin/python3; do
        r="$(command -v "$c" 2>/dev/null)" || continue
        [ -n "$r" ] || continue
        if runs_script "$r"; then ln -s "$r" "$d/python3"; printf '%s' "$d"; return 0; fi
    done
    rm -rf "$d"; return 1
}

# --- 1. defeats a refusing shim ---------------------------------------------
SHIMDIR="$(plant_shim)"
out=$(
    PATH="$SHIMDIR:$PATH"
    if python3 "$PROBE" >/dev/null 2>&1; then echo "FIXTURE_INERT"; exit 0; fi
    # shellcheck source=tests/integration/lib/real_python.sh
    . "$LIB"
    ensure_real_python >/dev/null 2>&1 || { echo "HELPER_FAILED"; exit 0; }
    r="$(python3 "$PROBE" 2>&1)"
    [ -n "${REAL_PYTHON_SHIM_DIR:-}" ] && rm -rf "$REAL_PYTHON_SHIM_DIR"
    printf '%s' "$r"
)
case "$out" in
  "$MARKER")     pass "a refusing python3 shim on PATH is defeated" ;;
  FIXTURE_INERT) fail "fixture never shadowed python3 — this control proves nothing" ;;
  HELPER_FAILED) fail "helper found no working interpreter to fall back to" ;;
  *)             fail "helper did not yield a runnable python3: $out" ;;
esac
rm -rf "$SHIMDIR"

# --- 2. shadows python3 ONLY, not the interpreter's whole bin dir ------------
# Prepending /usr/bin would reorder git, sed, and everything else for the rest of
# the run — a far larger change than the defect warrants.
SHIMDIR="$(plant_shim)"
out=$(
    PATH="$SHIMDIR:$PATH"
    # shellcheck source=tests/integration/lib/real_python.sh
    . "$LIB"
    ensure_real_python >/dev/null 2>&1 || { echo "HELPER_FAILED"; exit 0; }
    ls "$REAL_PYTHON_SHIM_DIR" | tr '\n' ' '
)
if [ "$(printf '%s' "$out" | tr -d ' ')" = "python3" ]; then
    pass "the prepended dir holds python3 and nothing else"
else
    fail "prepended dir was not surgical, it holds: $out"
fi
rm -rf "$SHIMDIR"

# --- 3. no-op when python3 already runs -------------------------------------
if WORKDIR="$(plant_working)"; then
    out=$(
        PATH="$WORKDIR:$PATH"
        # shellcheck source=tests/integration/lib/real_python.sh
        . "$LIB"
        before="$PATH"
        ensure_real_python >/dev/null 2>&1
        [ "$PATH" = "$before" ] && echo UNCHANGED || echo CHANGED
    )
    [ "$out" = "UNCHANGED" ] && pass "leaves PATH untouched when python3 already runs" \
                             || fail "meddled with PATH on a healthy machine ($out)"
    rm -rf "$WORKDIR"
else
    fail "could not find any working interpreter to build the no-op control"
fi

# --- 4. defeats an ASYMMETRIC shim: answers -c, refuses a script file --------
# The shape that ships, and the one a `python3 -c 'pass'` health check cannot
# see. The first guard below is the control ON THE FIXTURE: it asserts `-c`
# really does succeed here, so this leg genuinely occupies the state the old
# check called healthy.
SHIMDIR="$(plant_asymmetric_shim python3)"
out=$(
    PATH="$SHIMDIR:$PATH"
    python3 -c 'pass' >/dev/null 2>&1 || { echo "FIXTURE_SYMMETRIC"; exit 0; }
    if python3 "$PROBE" >/dev/null 2>&1; then echo "FIXTURE_INERT"; exit 0; fi
    # shellcheck source=tests/integration/lib/real_python.sh
    . "$LIB"
    ensure_real_python >/dev/null 2>&1 || { echo "HELPER_FAILED"; exit 0; }
    r="$(python3 "$PROBE" 2>&1)"
    [ -n "${REAL_PYTHON_SHIM_DIR:-}" ] && rm -rf "$REAL_PYTHON_SHIM_DIR"
    printf '%s' "$r"
)
case "$out" in
  "$MARKER")         pass "an asymmetric shim (-c succeeds, script refused) is defeated" ;;
  FIXTURE_SYMMETRIC) fail "fixture refused -c as well, so it does not model the shipped shim and proves nothing about the -c blind spot" ;;
  FIXTURE_INERT)     fail "fixture never shadowed python3 — this control proves nothing" ;;
  HELPER_FAILED)     fail "helper found no working interpreter to fall back to" ;;
  *)                 fail "helper did not yield a runnable python3: $out" ;;
esac
rm -rf "$SHIMDIR"

# --- 5. rejects a poisoned CANDIDATE, not just a poisoned python3 ------------
# The fallback loop probes python3.14 first. Probe a candidate with `-c` and an
# asymmetric shim answering to that versioned name is accepted and symlinked in
# as the "real" interpreter — the same defect one level down, where nothing
# downstream names it. Poison python3.14 alongside python3 and require the helper
# to walk past it to something that actually runs a file.
SHIMDIR="$(plant_asymmetric_shim python3 python3.14)"
out=$(
    PATH="$SHIMDIR:$PATH"
    python3.14 -c 'pass' >/dev/null 2>&1 || { echo "FIXTURE_SYMMETRIC"; exit 0; }
    # shellcheck source=tests/integration/lib/real_python.sh
    . "$LIB"
    ensure_real_python >/dev/null 2>&1 || { echo "HELPER_FAILED"; exit 0; }
    r="$(python3 "$PROBE" 2>&1)"
    [ -n "${REAL_PYTHON_SHIM_DIR:-}" ] && rm -rf "$REAL_PYTHON_SHIM_DIR"
    printf '%s' "$r"
)
case "$out" in
  "$MARKER")         pass "a shim answering to a versioned candidate name is walked past" ;;
  FIXTURE_SYMMETRIC) fail "poisoned candidate refused -c as well, so a -c probe would have rejected it too and this proves nothing" ;;
  HELPER_FAILED)     fail "helper found no working interpreter behind the poisoned candidate" ;;
  *)                 fail "helper adopted the poisoned candidate: $out" ;;
esac
rm -rf "$SHIMDIR"

[ $FAILED -eq 0 ] && echo "OK" || echo "FAILURES"
exit $FAILED
