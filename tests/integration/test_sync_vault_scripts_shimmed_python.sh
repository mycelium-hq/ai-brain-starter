#!/usr/bin/env bash
# test_sync_vault_scripts_shimmed_python.sh
#
# sync-vault-scripts.sh needs a real Python 3 before it can read the vault
# path from settings.json or run _meta_resolver.py, and it used to look for one
# in exactly three places: `python3`, `python`, `py`. A Claude Code plugin that
# puts its own WRAPPER named `python3` (and `python`) on PATH --
# trailofbits/modern-python is the one in the wild -- defeats all three at
# once. Both wrappers satisfy `command -v`, both refuse the call ("Use
# `uv run python3 ...` instead"), and `py` does not exist off Windows. PY_CMD
# came back EMPTY.
#
# Empty PY_CMD is not an error there. The script reports "no vault resolved"
# or "no Meta folder", calls it non-fatal and exits 0, and its automated
# callers (sync-skills.py after an update, heal-journal-guard.py) pass
# --quiet, so not even that line shows. Nothing is installed.
# journal-preflight.py never reached the vault, which left the /journal Step-0
# guard demanding a script that had never shipped -- unsatisfiable, so
# JOURNAL_CONTEXT_BYPASS=1 became routine and the guard stopped guarding.
# Measured 2026-08-30.
#
# Wrapper SHAPES are planted because the shape decides whether a probe can
# even see the problem:
#
#   * refuses everything -- what modern-python 1.5.0 ships: `-c`, `-m`, `-`
#     and a script path are all refused.
#   * ASYMMETRIC -- forwards `-c`/`-`/`-m` to a real interpreter and refuses
#     only a script path (documented in tests/integration/lib/real_python.sh).
#     PY_CMD runs BOTH on stdin and on a script FILE (_meta_resolver.py), so a
#     probe of the forwarded form adopts the wrapper and then dies on the one
#     call that matters.
#   * exits 0 printing advice -- an exit-code probe adopts it; only the
#     sentinel the probe file prints back rejects it.
#
# Legs 2-11, 13 and 14 source the probe block lifted verbatim from the shipped
# script; leg 12 runs the whole script end to end, so the two places that USE
# what the block picked are exercised too; leg 1 runs a copy of the old code.
# All of them run in a cleared environment with a PATH built from scratch: the
# dirs under test plus a TOOLS dir holding only the commands the block runs
# (leg 12 appends the caller's PATH behind those for the script's other
# tools). The verdict then cannot depend on the developer's own PATH (a
# Homebrew `py` launcher, the real plugin shim) or on an exported
# AI_BRAIN_PYTHON.

set -uo pipefail
unset AI_BRAIN_PYTHON

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SYNC="$REPO_ROOT/scripts/sync-vault-scripts.sh"

FAILED=0
pass() { printf '  PASS: %s\n' "$1"; }
fail() { printf '  FAIL: %s\n' "$1"; FAILED=1; }

echo "test_sync_vault_scripts_shimmed_python"

[ -f "$SYNC" ] || { echo "  FAIL: $SYNC not found"; exit 1; }

WORK="$(mktemp -d)" || { echo "  FAIL: mktemp"; exit 1; }
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# --- a real interpreter to build the fixtures against ------------------------
# Probed by running a FILE, the shape this test is about: a `-c` probe returns
# the asymmetric wrapper itself on a machine carrying one. The fixtures point
# at sys.executable, so a launcher that needs its own PATH (a pyenv shim) never
# ends up behind them.
printf '%s\n' 'import sys' 'print("__fixture_ok__ " + sys.executable)' \
    > "$WORK/is_real.py"
REAL=""
for _c in python3 python3.15 python3.14 python3.13 python3.12 python3.11 \
          python3.10 python3.9 /opt/homebrew/bin/python3 \
          /usr/local/bin/python3 /usr/bin/python3; do
    _r="$(command -v "$_c" 2>/dev/null || true)"
    [ -n "$_r" ] || continue
    _out="$("$_r" "$WORK/is_real.py" 2>/dev/null | head -n1)"
    case "$_out" in
        "__fixture_ok__ /"*) REAL="${_out#__fixture_ok__ }"; break ;;
    esac
done
if [ -z "$REAL" ]; then
    echo "  SKIP: no real python3 to build fixtures against"
    exit 0
fi

# --- PATH building blocks ----------------------------------------------------
# TOOLS holds only the external commands the probe block runs.
TOOLS="$WORK/tools"; mkdir -p "$TOOLS"
for _t in mktemp rm head tr; do
    _p="$(command -v "$_t" 2>/dev/null || true)"
    case "$_p" in
        /*) ln -s "$_p" "$TOOLS/$_t" ;;
        *) echo "  FAIL: no '$_t' on PATH to build TOOLS from"; exit 1 ;;
    esac
done
REAL_MKTEMP="$(command -v mktemp)"

# A versioned name a wrapper dir does not ship, pointing at the real
# interpreter. The number is arbitrary; it only has to sit inside the ladder.
REALDIR="$WORK/real"; mkdir -p "$REALDIR"
ln -s "$REAL" "$REALDIR/python3.12"

# Fixture scripts take this bash's absolute path as their shebang, so they
# still run under the stripped PATHs below.
mkscript() {
    { printf '#!%s\n' "$BASH"; printf '%s\n' "$2"; } > "$1"
    chmod +x "$1"
}

SHIM="$WORK/shim"; mkdir -p "$SHIM"    # refuses everything (modern-python 1.5.0)
ASYM="$WORK/asym"; mkdir -p "$ASYM"    # forwards -c/-/-m, refuses a script file
ZERO="$WORK/zero"; mkdir -p "$ZERO"    # prints advice and exits 0
for n in python3 python; do
    mkscript "$SHIM/$n" 'echo "ERROR: Use \`uv run python3 $*\` instead" >&2
exit 1'
    mkscript "$ASYM/$n" "for a in \"\$@\"; do
    case \"\$a\" in -c|-m|-) exec \"$REAL\" \"\$@\" ;; esac
done
echo 'ERROR: Use uv run python3 instead' >&2
exit 1"
    mkscript "$ZERO/$n" 'echo "Use uv run python3 instead"
exit 0'
done

# --- the probe block, lifted verbatim from the script under test ------------
# Both markers are asserted. If the END marker moved, sed would read on to the
# end of the file and every leg below would source the rest of the deployer.
sed -n '/^PY_CMD=""$/,/^_pick_python || true$/p' "$SYNC" > "$WORK/probe_block.sh"
if [ "$(head -n1 "$WORK/probe_block.sh")" != 'PY_CMD=""' ] ||
   [ "$(tail -n1 "$WORK/probe_block.sh")" != '_pick_python || true' ]; then
    fail "probe block markers not found in $SYNC (renamed?) -- refusing to source it"
    exit 1
fi

echo 'print("FILE_RAN")' > "$WORK/x.py"
ERR="$WORK/stderr"

# Both helpers clear the environment and point HOME and USERPROFILE at the
# same decoy (Windows Python reads USERPROFILE, not HOME), so nothing the
# probed interpreters do can reach the real ~/.claude.
#
# probe PATH [NAME=VALUE ...] -> prints "PY_CMD|PY_ARGS"; the block's stderr
# lands in $ERR.
probe() {
    local p="$1"; shift
    env -i HOME="$WORK/home" USERPROFILE="$WORK/home" PATH="$p" "$@" "$BASH" -c \
        'set -u; source "$1"; printf "%s|%s" "${PY_CMD:-}" "${PY_ARGS:-}"' \
        _ "$WORK/probe_block.sh" 2>"$ERR"
}
# runs_file PATH [NAME=VALUE ...] -> what the picked interpreter prints for a
# script file, invoked the way the script's own callers invoke it.
runs_file() {
    local p="$1"; shift
    env -i HOME="$WORK/home" USERPROFILE="$WORK/home" PATH="$p" "$@" "$BASH" -c \
        'set -u; source "$1"; [ -n "${PY_CMD:-}" ] || exit 0
         "$PY_CMD" ${PY_ARGS:-} "$2" 2>/dev/null' \
        _ "$WORK/probe_block.sh" "$WORK/x.py" 2>/dev/null
}

# --- LEG 1: NEGATIVE CONTROL - the old 3-name list comes back EMPTY ---------
# A faithful copy of the code this replaced, its `py -3` case included.
old_pick() {
    local cand v out=""
    for cand in python3 python py; do
        command -v "$cand" >/dev/null 2>&1 || continue
        if [ "$cand" = "py" ]; then
            v="$(py -3 -c 'import sys; print(sys.version_info[0])' 2>/dev/null | head -n1 | tr -d '\r')"
            if [ "$v" = "3" ]; then out="py -3"; break; fi
        else
            v="$("$cand" -c 'import sys; print(sys.version_info[0])' 2>/dev/null | head -n1 | tr -d '\r')"
            if [ "$v" = "3" ]; then out="$cand"; break; fi
        fi
    done
    printf '%s' "$out"
}
got="$(env -i PATH="$SHIM:$REALDIR:$TOOLS" "$BASH" -c "$(declare -f old_pick); old_pick")"
if [ -z "$got" ]; then
    pass "negative control: the old python3/python/py list finds NOTHING behind the wrapper"
else
    fail "negative control did not reproduce -- the old list found '$got'"
fi

# --- LEG 2: the shipped probe reaches past the wrapper, and what it picks runs a file
res="$(probe "$SHIM:$REALDIR:$TOOLS")"; cmd="${res%%|*}"
noise="$(head -c 200 "$ERR")"
ran="$(runs_file "$SHIM:$REALDIR:$TOOLS")"
if [ -z "$cmd" ]; then
    fail "the shipped probe returned EMPTY behind the wrapper -- the silent no-op is back"
elif [ "$cmd" != "$REALDIR/python3.12" ]; then
    fail "expected the versioned name behind the wrapper ($REALDIR/python3.12), picked '$cmd'"
elif [ "$ran" != "FILE_RAN" ]; then
    fail "the chosen interpreter did not run a script file (picked '$cmd', got '$ran')"
elif [ -n "$noise" ]; then
    fail "probing past the wrapper leaked its refusal to stderr on a run that worked: $noise"
else
    pass "the shipped probe reaches past the wrapper quietly, and its pick runs a file ($cmd)"
fi

# --- LEG 3: the ASYMMETRIC wrapper must not be adopted ----------------------
# First prove the fixture really forwards -c. A stub that refused -c as well
# would let this leg pass for the wrong reason.
if [ "$(env -i PATH="$ASYM:$TOOLS" "$BASH" -c 'python3 -c "print(3)"' 2>/dev/null)" != "3" ]; then
    fail "fixture: the asymmetric wrapper does not forward -c, so this leg cannot see the bug"
else
    res="$(probe "$ASYM:$REALDIR:$TOOLS")"; cmd="${res%%|*}"
    ran="$(runs_file "$ASYM:$REALDIR:$TOOLS")"
    if [ "$cmd" = "$REALDIR/python3.12" ] && [ "$ran" = "FILE_RAN" ]; then
        pass "the file probe rejects the asymmetric wrapper a -c probe adopts ($cmd)"
    else
        fail "asymmetric wrapper adopted, or nothing runnable picked (picked '$cmd', ran '$ran')"
    fi
fi

# --- LEG 4: the sentinel decides, not the exit code -------------------------
res="$(probe "$ZERO:$REALDIR:$TOOLS")"; cmd="${res%%|*}"
ran="$(runs_file "$ZERO:$REALDIR:$TOOLS")"
if [ "$cmd" = "$REALDIR/python3.12" ] && [ "$ran" = "FILE_RAN" ]; then
    pass "a wrapper that prints advice and exits 0 is rejected"
else
    fail "an exit-0 wrapper was adopted (picked '$cmd', ran '$ran')"
fi

# --- LEG 5: the only real Python sits at a standard install location --------
# No versioned name anywhere on PATH, e.g. a Mac whose one real interpreter is
# /usr/bin/python3. Skipped where none of the standard locations holds one.
STD=""
for _s in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    [ -x "$_s" ] || continue
    case "$("$_s" "$WORK/is_real.py" 2>/dev/null | head -n1)" in
        "__fixture_ok__ "*) STD="$_s"; break ;;
    esac
done
if [ -z "$STD" ]; then
    echo "  SKIP: no working python3 at a standard install location here"
else
    res="$(probe "$SHIM:$TOOLS")"; cmd="${res%%|*}"
    ran="$(runs_file "$SHIM:$TOOLS")"
    if [ "$cmd" = "$STD" ] && [ "$ran" = "FILE_RAN" ]; then
        pass "with no versioned name on PATH, the standard location is found ($cmd)"
    else
        fail "only $STD holds a real Python, and the probe picked '$cmd' (ran '$ran')"
    fi
fi

# --- LEG 6: AI_BRAIN_PYTHON wins, read as ONE path --------------------------
SPACED="$WORK/dir with space"; mkdir -p "$SPACED"
ln -s "$REAL" "$SPACED/python3"
res="$(probe "$SHIM:$REALDIR:$TOOLS" AI_BRAIN_PYTHON="$SPACED/python3")"; cmd="${res%%|*}"
ran="$(runs_file "$SHIM:$REALDIR:$TOOLS" AI_BRAIN_PYTHON="$SPACED/python3")"
if [ "$cmd" = "$SPACED/python3" ] && [ "$ran" = "FILE_RAN" ]; then
    pass "AI_BRAIN_PYTHON is used first and read as one path, spaces included"
else
    fail "AI_BRAIN_PYTHON='$SPACED/python3' was not honoured (picked '$cmd', ran '$ran')"
fi

# --- LEG 7: an AI_BRAIN_PYTHON that does not work is reported ----------------
res="$(probe "$REALDIR:$TOOLS" AI_BRAIN_PYTHON="$WORK/no-such/python3")"; cmd="${res%%|*}"
if grep -q 'AI_BRAIN_PYTHON' "$ERR" && [ -n "$cmd" ]; then
    pass "a broken AI_BRAIN_PYTHON is reported, and the ladder still resolves ($cmd)"
else
    fail "a broken AI_BRAIN_PYTHON was skipped silently or stopped the ladder (picked '$cmd', stderr: $(head -c 200 "$ERR"))"
fi

# --- LEG 8: the Windows `py` launcher gets -3, outside PY_CMD ---------------
PYDIR="$WORK/pylauncher"; mkdir -p "$PYDIR"
mkscript "$PYDIR/py" "[ \"\${1:-}\" = \"-3\" ] || { echo 'py: this launcher needs -3' >&2; exit 1; }
shift
exec \"$REAL\" \"\$@\""
res="$(probe "$SHIM:$PYDIR:$TOOLS")"; cmd="${res%%|*}"; args="${res#*|}"
ran="$(runs_file "$SHIM:$PYDIR:$TOOLS")"
if [ "$cmd" = "$PYDIR/py" ] && [ "$args" = "-3" ] && [ "$ran" = "FILE_RAN" ]; then
    pass "the py launcher is run with -3, and PY_CMD stays one path"
else
    fail "py launcher mishandled (PY_CMD='$cmd' PY_ARGS='$args', ran '$ran')"
fi

# --- LEG 9: no temp dir for the probe file -----------------------------------
# GNU mktemp on a stale TMPDIR, a full or read-only temp dir. The `-c` probe
# this replaced needed no file, so giving up here would be a regression.
FAILMK="$WORK/failmk"; mkdir -p "$FAILMK"
mkscript "$FAILMK/mktemp" 'echo "mktemp: cannot create temp dir" >&2
exit 1'
res="$(probe "$FAILMK:$REALDIR:$TOOLS")"; cmd="${res%%|*}"
warned=no; grep -q 'WARN.*probe' "$ERR" && warned=yes
ran="$(runs_file "$FAILMK:$REALDIR:$TOOLS")"
if [ "$cmd" = "$REALDIR/python3.12" ] && [ "$ran" = "FILE_RAN" ] && [ "$warned" = yes ]; then
    pass "with no temp dir it warns, probes on stdin, and still resolves ($cmd)"
else
    fail "mktemp failure: picked '$cmd', ran '$ran', warned=$warned"
fi

# --- LEG 9b: a temp dir that cannot be written -------------------------------
# Same fallback, and the failed write must not print its own error ahead of
# the WARN. Skipped for a user who can write a 555 dir anyway (root).
RODIR="$WORK/ro"; mkdir -p "$RODIR"; chmod 555 "$RODIR"
ROMK="$WORK/romk"; mkdir -p "$ROMK"
mkscript "$ROMK/mktemp" "echo \"$RODIR\""
if ( : > "$RODIR/.w" ) 2>/dev/null; then
    rm -f "$RODIR/.w"
    echo "  SKIP: this user can write a read-only dir, so the case cannot be staged"
else
    res="$(probe "$ROMK:$REALDIR:$TOOLS")"; cmd="${res%%|*}"
    other="$(grep -v 'WARN' "$ERR" | head -c 200)"
    if [ "$cmd" = "$REALDIR/python3.12" ] && grep -q 'WARN.*probe' "$ERR" && [ -z "$other" ]; then
        pass "an unwritable temp dir: the WARN is all it prints, and it still resolves"
    else
        fail "unwritable temp dir: picked '$cmd', stderr: $(head -c 200 "$ERR")"
    fi
fi
chmod 755 "$RODIR" 2>/dev/null || true

# --- LEG 10: the probe's temp dir is removed ---------------------------------
LOGMK="$WORK/logmk"; mkdir -p "$LOGMK"
MKLOG="$WORK/mktemp.log"; : > "$MKLOG"
mkscript "$LOGMK/mktemp" "d=\"\$(\"$REAL_MKTEMP\" \"\$@\")\" || exit 1
printf '%s\n' \"\$d\" >> \"$MKLOG\"
printf '%s\n' \"\$d\""
probe "$LOGMK:$REALDIR:$TOOLS" >/dev/null
probe "$LOGMK:$REALDIR:$TOOLS" AI_BRAIN_PYTHON="$WORK/no-such/python3" >/dev/null
made=0; left=0
while IFS= read -r d; do
    [ -n "$d" ] || continue
    made=$((made + 1))
    if [ -e "$d" ]; then left=$((left + 1)); fi
done < "$MKLOG"
if [ "$made" -ge 2 ] && [ "$left" -eq 0 ]; then
    pass "the probe's temp dir is removed ($made created, 0 left)"
else
    fail "probe temp dirs: $made created, $left left behind"
fi

# --- LEG 11: MEDDLING CONTROL - a working bare python3 keeps first place -----
# With no wrapper, the old code took the first working `python3` on PATH (an
# activated venv, say). The fallbacks must not change that.
BAREDIR="$WORK/bare"; mkdir -p "$BAREDIR"
ln -s "$REAL" "$BAREDIR/python3"
res="$(probe "$BAREDIR:$REALDIR:$TOOLS")"; cmd="${res%%|*}"
ran="$(runs_file "$BAREDIR:$REALDIR:$TOOLS")"
if [ "$cmd" = "$BAREDIR/python3" ] && [ "$ran" = "FILE_RAN" ] && [ ! -s "$ERR" ]; then
    pass "with no wrapper, the first working python3 on PATH still wins, silently"
else
    fail "clean PATH: expected $BAREDIR/python3, picked '$cmd', ran '$ran', stderr '$(head -c 200 "$ERR")'"
fi

# --- LEG 12: END TO END through the shipped call sites -----------------------
# The legs above drive the extracted block. This one runs the real script with
# no --vault, so both places that USE PY_CMD + PY_ARGS run: the stdin read of
# settings.json and the _meta_resolver.py file call. The only interpreter is a
# py launcher that refuses to run without -3, behind the wrapper. The full
# script needs more tools than TOOLS holds, so the caller's PATH goes BEHIND
# the dirs under test: the wrapper still shadows python3/python and the stub
# is reached before any versioned name. A dry run writes nothing.
E2E="$WORK/e2e"; EVAULT="$E2E/vault"; EHOME="$E2E/home"
mkdir -p "$EVAULT/⚙️ Meta/scripts" "$EVAULT/⚙️ Meta/Decisions" "$EVAULT/⚙️ Meta/Sessions" \
         "$EHOME/.claude"
printf '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"python3 %s/⚙️ Meta/scripts/x.py"}]}]}}\n' \
    "$EVAULT" > "$EHOME/.claude/settings.json"
out="$(env -i HOME="$EHOME" USERPROFILE="$EHOME" PATH="$SHIM:$PYDIR:$PATH" \
       "$BASH" "$SYNC" --dry-run 2>&1)"
written="$(find "$EVAULT" "$EHOME" -type f | wc -l | tr -d ' ')"
if printf '%s\n' "$out" | grep -q '^meta: ' && [ "$written" = 1 ]; then
    pass "end to end: the vault comes from settings.json and its Meta folder resolves, via py -3"
else
    fail "end to end via py -3: files under vault+home=$written (want 1), output: $(printf '%s' "$out" | head -c 300)"
fi

# --- LEG 13: a path that already failed is not run again ---------------------
# Bare python3 is often /usr/bin/python3, which the ladder also names outright.
# A counting stub stands in for it, reached first as AI_BRAIN_PYTHON and then
# again as the bare name.
CNT="$WORK/count"; mkdir -p "$CNT"; CNTLOG="$WORK/count.log"; : > "$CNTLOG"
mkscript "$CNT/python3" "echo run >> \"$CNTLOG\"
exit 1"
res="$(probe "$CNT:$REALDIR:$TOOLS" AI_BRAIN_PYTHON="$CNT/python3")"; cmd="${res%%|*}"
runs="$(wc -l < "$CNTLOG" | tr -d ' ')"
if [ "$runs" = 1 ] && [ "$cmd" = "$REALDIR/python3.12" ]; then
    pass "a candidate that already failed is not run a second time"
else
    fail "the failing stub ran $runs time(s) (want 1); picked '$cmd'"
fi

# --- LEG 14: the same path with DIFFERENT args is still tried ----------------
# AI_BRAIN_PYTHON pointing at the py launcher is probed without -3 and fails;
# the ladder's own `py` entry, probed WITH -3, must not be skipped as a repeat.
res="$(probe "$SHIM:$PYDIR:$TOOLS" AI_BRAIN_PYTHON="$PYDIR/py")"; cmd="${res%%|*}"; args="${res#*|}"
if [ "$cmd" = "$PYDIR/py" ] && [ "$args" = "-3" ]; then
    pass "a failed override does not block the same launcher's own -3 probe"
else
    fail "the py launcher was skipped after the override failed (PY_CMD='$cmd' PY_ARGS='$args')"
fi

echo
if [ "$FAILED" -eq 0 ]; then
    echo "  test_sync_vault_scripts_shimmed_python: ALL PASS"
else
    echo "  test_sync_vault_scripts_shimmed_python: FAILURES"
fi
exit "$FAILED"
