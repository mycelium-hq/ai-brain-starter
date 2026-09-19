#!/usr/bin/env bash
# Guarantee that `python3` on PATH is an interpreter which actually runs a script.
#
# Some machines carry a `python3` shim that refuses a direct call and answers with
# advice instead of running: the trailofbits/modern-python plugin ships one that
# replies "ERROR: Use `uv run python <script>` instead". That is a defensible
# default for interactive work and ruinous here — 103 test files in this suite
# shell out to `python3 <script.py>`, so on a machine carrying the shim every one
# of them fails, and the failure text is the shim's advice rather than anything
# the test asserts. A whole red suite that says nothing about the code is worse
# than a broken test, because it trains you to stop reading the output.
#
# The refusal is NOT uniform across invocation forms, and that asymmetry is why
# this file carries a probe of its own. Read the shim's source (hooks/shims/python
# in the plugin): it scans argv for a mode selector and hands `-c`, `-` and `-m`
# (except pip) straight to the real interpreter, on the stated grounds that none
# of them resolves a script against a project's dependencies. It refuses exactly
# one shape — a SCRIPT PATH — and that is the only shape this suite ever uses.
# So `python3 -c 'pass'` exits 0, silently, on precisely the machines this helper
# exists to rescue.
#
# Probing with `-c` was this file's own bug. The check passed on a machine where
# `python3 script.py` did not run at all, the helper concluded it was not needed,
# and all 103 python-invoking tests failed with the shim's advice standing in for
# every assertion — the exact failure the first paragraph describes, produced by
# the guard against it. Probe with the shape the callers actually rely on. That
# also generalizes past this one plugin: any future shim is then judged on what
# this suite does, rather than on a special case written for its name.
#
# Sandboxing HOME does not help: the shim sits on PATH by absolute path and
# outlives the decoy home the suite installs.
#
# ensure_real_python is a no-op wherever `python3` already runs a script — CI, and
# most contributor machines. Where it does not, it prepends a directory holding a
# single `python3` symlink to a working interpreter. Only python3 is shadowed:
# prepending the interpreter's own directory (/usr/bin, say) would reorder every
# other tool on PATH for the rest of the run, which is a much larger promise than
# this needs to make.
#
# ci.sh calls it once for the whole suite. A single test run by hand opts in the
# same way:
#
#   . tests/integration/lib/real_python.sh && ensure_real_python
#
# On success PATH is exported and REAL_PYTHON_SHIM_DIR names the directory it
# created — empty when nothing was needed — so the caller can clean it up.

# An OUTPUT of ensure_real_python, never an input: deliberately NOT inherited
# from the environment. ci.sh's exit trap runs `rm -rf "$REAL_PYTHON_SHIM_DIR"`
# whenever it is non-empty, so honouring an exported value would let
# `REAL_PYTHON_SHIM_DIR=~/work bash scripts/ci.sh` delete a directory this run
# never created. The function assigns it on every path.
REAL_PYTHON_SHIM_DIR=''

# Printed by the probe script, required back by _real_python_runs. A status of 0
# on its own is too weak: a wrapper is free to print its advice and exit 0, and
# one that did would satisfy an exit-code-only check while running nothing.
# Demanding the script's own output proves the interpreter executed the file.
_REAL_PYTHON_SENTINEL='__real_python_runs_ok__'

# _real_python_runs <interpreter> <probe-script>
#
# Does this interpreter run a script FILE? That is the question the suite's 103
# python-invoking tests ask, and — per the asymmetry note above — the only
# question worth asking here.
_real_python_runs() {
    local out
    out="$("$1" "$2" 2>/dev/null)" || return 1
    case "$out" in
        *"$_REAL_PYTHON_SENTINEL"*) return 0 ;;
        *) return 1 ;;
    esac
}

ensure_real_python() {
    local probe_dir probe cand resolved real=''

    # Re-assert the output contract on every path, the no-op one included, so a
    # stale or exported value can never reach the caller's cleanup as if this
    # run had created it.
    REAL_PYTHON_SHIM_DIR=''

    probe_dir="$(mktemp -d)" || return 1
    probe="$probe_dir/real_python_probe.py"
    if ! printf 'print("%s")\n' "$_REAL_PYTHON_SENTINEL" > "$probe"; then
        rm -rf "$probe_dir"
        return 1
    fi

    if _real_python_runs python3 "$probe"; then
        rm -rf "$probe_dir"
        return 0
    fi

    # Versioned names and absolute paths are what escape a shim: it only ever
    # claims the bare `python3` and `python` names. Each candidate is probed with
    # the same script-file shape as the check above — a candidate can be a shim
    # too, and accepting one on a `-c` probe would reinstate the defect exactly
    # one level further down, where it is harder to see.
    for cand in python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 \
                /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
        resolved="$(command -v "$cand" 2>/dev/null)" || continue
        [ -n "$resolved" ] || continue
        # A relative PATH entry (`bin`, `node_modules/.bin`, `.`) makes
        # command -v hand back a relative path. It would PASS the probe, which
        # runs it against the current directory, and then `ln -s` would resolve
        # the same string against the temp dir instead — a dangling symlink,
        # after which python3 falls through to the next PATH entry (the shim)
        # while this function reports success. Take absolute paths only.
        case "$resolved" in
            /*) ;;
            *) continue ;;
        esac
        if _real_python_runs "$resolved" "$probe"; then
            real="$resolved"
            break
        fi
    done

    rm -rf "$probe_dir"

    if [ -z "$real" ]; then
        echo "ensure_real_python: \`python3\` on PATH does not run a script file, and no" >&2
        echo "  working interpreter was found. Every test that shells out to python3 would" >&2
        echo "  fail for that reason alone, saying nothing about the code under test." >&2
        return 1
    fi

    REAL_PYTHON_SHIM_DIR="$(mktemp -d)" || return 1
    ln -s "$real" "$REAL_PYTHON_SHIM_DIR/python3" || return 1
    PATH="$REAL_PYTHON_SHIM_DIR:$PATH"
    export PATH
    echo "    note: \`python3\` on PATH does not run script files (a shim); using $real for this run"
}
