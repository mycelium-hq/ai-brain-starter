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
# Three shim SHAPES are planted, because the shape decides whether the helper
# can even see the problem:
#
#   * refuses everything (leg 1, leg 2) — the easy case.
#   * ASYMMETRIC (leg 4, leg 5) — the shape that actually ships.
#     trailofbits/modern-python forwards `-c`, `-` and `-m` (bar pip) to the
#     real interpreter and refuses only a script PATH, the single form all 103
#     python-invoking tests here use. The helper used to probe with
#     `python3 -c 'pass'`, which that shim answers 0 to, so it returned early on
#     exactly the machines it existed to rescue.
#   * exits 0 without running the file (leg 6) — what the sentinel buys. An
#     exit-code-only probe adopts such a wrapper and every test downstream sees
#     empty output instead of results.
#
# The asymmetric stub FORWARDS `-c` to a real interpreter rather than faking a
# silent exit 0, because that is the axis legs 4 and 5 exist to control: a stub
# that exits 0 without running would let a probe of the form `-c "print(...)"`
# satisfy the sentinel and pass, which is the near-miss refactor most likely to
# reintroduce the bug. Its argv scan mirrors the shipped shim's, flags and all.
#
# Leg 5 poisons a VERSIONED name. trailofbits ships only `python` and `python3`,
# so that leg is defense-in-depth against a version-suffixed shim dir of the
# pyenv/asdf kind rather than a reproduction of this plugin; the fallback loop
# is the one path no other leg covers.
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
printf 'print("%s")\n' "$MARKER" > "$PROBE" || { echo "  FAIL: could not write $PROBE"; exit 1; }
trap 'rm -rf "$PROBE_DIR"' EXIT

runs_script() { # runs_script <interpreter> — does it run a script FILE?
    local out
    out="$("$1" "$PROBE" 2>/dev/null)" || return 1
    case "$out" in *"$MARKER"*) return 0 ;; esac
    return 1
}

find_real_interp() { # absolute path of an interpreter that runs a script file
    local r c
    for c in python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 \
             /usr/bin/python3 /opt/homebrew/bin/python3; do
        r="$(command -v "$c" 2>/dev/null)" || continue
        [ -n "$r" ] || continue
        case "$r" in /*) ;; *) continue ;; esac
        if runs_script "$r"; then printf '%s' "$r"; return 0; fi
    done
    return 1
}

REAL_INTERP="$(find_real_interp || true)"
[ -n "$REAL_INTERP" ] || {
    echo "  FAIL: no working interpreter on this machine, so no fixture below can be built"
    exit 1
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

# A stand-in for the shape that ships: `-c` / `-` / `-m` (bar pip) reach a real
# interpreter and RUN, a script path is refused. Takes the names to answer to,
# so a versioned candidate can be poisoned as well as the bare one.
plant_asymmetric_shim() {
    local d n; d="$(mktemp -d)"
    for n in "$@"; do
        {
            printf '#!/bin/sh\n'
            printf "REAL='%s'\n" "$REAL_INTERP"
            cat <<'SH'
# Mirrors the shipped shim's argv scan: step over interpreter flags, then decide
# on the first mode selector. -W/-X/--check-hash-based-pycs consume a value.
# The scan runs in a function so it shifts its OWN copy and the real argv, which
# the passthrough needs intact, is never disturbed.
decide() {
  while [ $# -gt 0 ]; do
    case "$1" in
      -c|-) echo passthrough; return ;;
      -m) if [ "${2:-}" = pip ]; then echo refuse; else echo passthrough; fi; return ;;
      -W|-X|--check-hash-based-pycs) shift 2 2>/dev/null || { echo refuse; return; } ;;
      -*) shift ;;
      *) echo refuse; return ;;
    esac
  done
  echo refuse
}
if [ "$(decide "$@")" = passthrough ]; then
  exec "$REAL" "$@"
fi
echo "ERROR: Use \`uv run python $*\` instead of \`python3 $*\`" >&2
exit 1
SH
        } > "$d/$n"
        chmod +x "$d/$n"
    done
    printf '%s' "$d"
}

# A wrapper that exits 0 and runs NOTHING — the shape an exit-code-only probe
# cannot tell from a working interpreter.
plant_silent_wrapper() {
    local d; d="$(mktemp -d)"
    cat > "$d/python3" <<'SH'
#!/bin/sh
echo "NOTE: this interpreter is managed; use the project runner"
exit 0
SH
    chmod +x "$d/python3"
    printf '%s' "$d"
}

# A python3 that works, for the leg where the helper must do nothing.
plant_working() {
    local d; d="$(mktemp -d)"
    ln -s "$REAL_INTERP" "$d/python3" || { rm -rf "$d"; return 1; }
    printf '%s' "$d"
}

# Run the helper under a fixture PATH and report what `python3 <script>` does
# afterwards. Prefixes NO_OP: when the helper never touched PATH, so a leg can
# tell "its probe was fooled and it returned early" from "it picked something
# broken" — two very different bugs that otherwise print the same advice text.
helper_then_probe() {
    # shellcheck source=tests/integration/lib/real_python.sh
    . "$LIB"
    ensure_real_python >/dev/null 2>&1 || { echo "HELPER_FAILED"; return 0; }
    local r; r="$(python3 "$PROBE" 2>&1)"
    if [ -z "${REAL_PYTHON_SHIM_DIR:-}" ]; then
        printf 'NO_OP:%s' "$r"
    else
        rm -rf "$REAL_PYTHON_SHIM_DIR"
        printf '%s' "$r"
    fi
}

# --- 1. defeats a refusing shim ---------------------------------------------
SHIMDIR="$(plant_shim)"
out=$(
    PATH="$SHIMDIR:$PATH"
    if python3 "$PROBE" >/dev/null 2>&1; then echo "FIXTURE_INERT"; exit 0; fi
    helper_then_probe
)
case "$out" in
  "$MARKER")     pass "a refusing python3 shim on PATH is defeated" ;;
  FIXTURE_INERT) fail "fixture never shadowed python3 — this control proves nothing" ;;
  HELPER_FAILED) fail "helper found no working interpreter to fall back to" ;;
  NO_OP:*)       fail "helper left PATH alone in front of a shim that refuses everything: ${out#NO_OP:}" ;;
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
    # shellcheck disable=SC2012  # names only; these are symlinks we just made
    r="$(ls "$REAL_PYTHON_SHIM_DIR" | tr '\n' ' ')"
    rm -rf "$REAL_PYTHON_SHIM_DIR"
    printf '%s' "$r"
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
    fail "could not build the no-op control"
fi

# --- 4. defeats an ASYMMETRIC shim: runs -c, refuses a script file -----------
# The shape that ships, and the one a `python3 -c 'pass'` health check cannot
# see. The two guards are controls ON THE FIXTURE: `-c` must really work here
# (or the old check would have caught this fixture anyway and the leg proves
# nothing about the blind spot), and the script form must really be refused.
SHIMDIR="$(plant_asymmetric_shim python3)"
out=$(
    PATH="$SHIMDIR:$PATH"
    python3 -c "print('fixture-c-works')" >/dev/null 2>&1 || { echo "FIXTURE_SYMMETRIC"; exit 0; }
    if python3 "$PROBE" >/dev/null 2>&1; then echo "FIXTURE_INERT"; exit 0; fi
    helper_then_probe
)
case "$out" in
  "$MARKER")         pass "an asymmetric shim (-c runs, script refused) is defeated" ;;
  FIXTURE_SYMMETRIC) fail "fixture did not run -c, so it does not model the shipped shim and proves nothing about the -c blind spot" ;;
  FIXTURE_INERT)     fail "fixture never refused a script file — this control proves nothing" ;;
  HELPER_FAILED)     fail "helper found no working interpreter to fall back to" ;;
  NO_OP:*)           fail "helper's probe was fooled and it returned early: ${out#NO_OP:}" ;;
  *)                 fail "helper did not yield a runnable python3: $out" ;;
esac
rm -rf "$SHIMDIR"

# --- 5. rejects a poisoned CANDIDATE, not just a poisoned python3 ------------
# The fallback loop probes python3.14 first. Probe a candidate with `-c` and an
# asymmetric shim answering to that versioned name is accepted and symlinked in
# as the "real" interpreter — the same defect one level down, where nothing
# downstream names it. Poison python3.14 alongside python3 and require the
# helper to walk past it to something that actually runs a file.
SHIMDIR="$(plant_asymmetric_shim python3 python3.14)"
out=$(
    PATH="$SHIMDIR:$PATH"
    python3.14 -c "print('fixture-c-works')" >/dev/null 2>&1 || { echo "FIXTURE_SYMMETRIC"; exit 0; }
    if python3 "$PROBE" >/dev/null 2>&1; then echo "FIXTURE_INERT"; exit 0; fi
    helper_then_probe
)
case "$out" in
  "$MARKER")         pass "a shim answering to a versioned candidate name is walked past" ;;
  FIXTURE_SYMMETRIC) fail "poisoned candidate did not run -c, so a -c probe would have rejected it too and this proves nothing" ;;
  FIXTURE_INERT)     fail "fixture never shadowed python3 — the candidate loop is never even reached" ;;
  HELPER_FAILED)     fail "helper found no working interpreter behind the poisoned candidate" ;;
  NO_OP:*)           fail "helper returned early, so the candidate loop was never reached: ${out#NO_OP:}" ;;
  *)                 fail "helper adopted the poisoned candidate: $out" ;;
esac
rm -rf "$SHIMDIR"

# --- 6. rejects a wrapper that exits 0 without running the file --------------
# Exit status alone cannot see this one: the wrapper succeeds and produces no
# result. This is the leg that makes the sentinel load-bearing rather than
# decorative — delete the sentinel check and only this leg goes red.
SHIMDIR="$(plant_silent_wrapper)"
out=$(
    PATH="$SHIMDIR:$PATH"
    python3 "$PROBE" >/dev/null 2>&1 || { echo "FIXTURE_NONZERO"; exit 0; }
    if python3 "$PROBE" 2>/dev/null | grep -q "$MARKER"; then echo "FIXTURE_ACTUALLY_RAN"; exit 0; fi
    helper_then_probe
)
case "$out" in
  "$MARKER")            pass "a wrapper that exits 0 without running the file is rejected" ;;
  FIXTURE_NONZERO)      fail "fixture exited non-zero, so an exit-code-only probe would have caught it and this proves nothing" ;;
  FIXTURE_ACTUALLY_RAN) fail "fixture really ran the script — it does not model a silent wrapper" ;;
  HELPER_FAILED)        fail "helper found no working interpreter to fall back to" ;;
  NO_OP:*)              fail "helper accepted a wrapper that runs nothing: ${out#NO_OP:}" ;;
  *)                    fail "helper did not yield a runnable python3: $out" ;;
esac
rm -rf "$SHIMDIR"

[ $FAILED -eq 0 ] && echo "OK" || echo "FAILURES"
exit $FAILED
