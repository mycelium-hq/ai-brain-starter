#!/usr/bin/env bash
# Regression tests: the CwdChanged and FileChanged hooks run their embedded Python
# isolated from the working directory.
#
# Both hooks parse their JSON payload with `python3 -c`. They run in the session's
# working directory, which may be a freshly cloned repository nobody has read, and a
# plain `python3 -c` puts that directory FIRST on sys.path: a json.py planted in it
# would run as part of the hook. `python3 -I` drops the directory (and ignores
# PYTHON* variables and the user site).
#
# These drive the REAL, unmodified hooks from a directory holding a planted json.py.
#   1. a plain interpreter DOES import the planted module from that directory, so the
#      assertions below are able to fail
#   2. neither hook imports it, and each still does its job (the directory change is
#      logged, a settings file is reported as valid, a broken one as invalid)
#   3. every python3 a hook starts carries `-I -X utf8`. This half does not depend on the
#      interpreter or the locale: it holds even where json is imported before any script
#      line runs.
#   4. the FileChanged hook gives Python the changed file's path as data, not as part of
#      the program: a path holding a single quote is still validated, and a path built
#      to end the string and run a statement runs nothing.
#   5. under a locale whose encoding is ASCII the hooks still read and print UTF-8. -I
#      ignores PYTHONUTF8, so only `-X utf8` (a command-line option, which -I keeps) makes
#      a settings file, a payload or a path holding non-ASCII text readable. Needs a host
#      with such a locale; elsewhere it prints a note and skips.
#
# CHECK_HOOKS_DIR=<dir> runs the same cases against another copy of the hooks (that is
# how hooks without -I are shown RED). Self-contained. Exit 0 = pass, 1 = fail.

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
HOOKS="${CHECK_HOOKS_DIR:-$ROOT/hooks}"

# shellcheck source=tests/integration/lib/sandbox_home.sh
. "$HERE/lib/sandbox_home.sh"
# shellcheck source=tests/integration/lib/real_python.sh
. "$HERE/lib/real_python.sh"

for h in cwd-changed.sh file-changed-settings.sh; do
  [[ -f "$HOOKS/$h" ]] || { echo "FAIL: hook not found: $HOOKS/$h"; exit 1; }
done

# mktemp must have made a directory before the trap below can delete one: an empty result
# turns `cd` into a no-op, TMP into the current directory (the repo root, under ci.sh) and
# the trap into `rm -rf` of it.
TMP="$(mktemp -d)" && [ -n "$TMP" ] || { echo "FAIL: mktemp -d gave no scratch directory"; exit 1; }
TMP="$(cd "$TMP" && pwd -P)" || exit 1
trap 'rm -rf "$TMP" ${REAL_PYTHON_SHIM_DIR:+"$REAL_PYTHON_SHIM_DIR"}' EXIT
sandbox_home "$TMP/home"
case "$HOME" in "$TMP"/*) ;; *) echo "FAIL: HOME is not sandboxed ($HOME)"; exit 1 ;; esac
mkdir -p "$HOME/.claude/hooks"

PASS=0
FAIL=0
ok()  { PASS=$((PASS + 1)); echo "PASS  $1"; }
bad() { FAIL=$((FAIL + 1)); echo "FAIL  $1 :: ${2:-}"; }
has() { case "$1" in *"$2"*) return 0 ;; *) return 1 ;; esac; }

ensure_real_python || { echo "FAIL: no python3 that runs a script file"; exit 1; }
PY3="$(command -v python3)"

echo "target: ${HOOKS#"$ROOT"/}"

# ---- the planted module -------------------------------------------------------
HOSTILE="$TMP/hostile"
mkdir -p "$HOSTILE"
printf 'open("IMPORTED-json", "w").close()\n' > "$HOSTILE/json.py"

# positive control: an interpreter that is not isolated imports it from this directory
( cd "$HOSTILE" && "$PY3" -c 'import json' ) > /dev/null 2>&1
SHADOWABLE=0
if [ -e "$HOSTILE/IMPORTED-json" ]; then
  SHADOWABLE=1
  ok "planted module: a plain python3 -c in that directory imports its json.py (the check can fail)"
else
  echo "NOTE  this interpreter imports json before any script line runs, so a planted json.py cannot show the exposure here; the -I check still applies"
fi
rm -f "$HOSTILE"/IMPORTED-*

# every python3 a hook starts is recorded (its first three arguments) by a shim that then
# runs the real one
mkdir -p "$TMP/pyshim"
printf '#!/bin/sh\nprintf "%%s %%s %%s\\n" "$1" "$2" "$3" >> "$PY_ARGV_LOG"\nexec "%s" "$@"\n' "$PY3" > "$TMP/pyshim/python3"
chmod +x "$TMP/pyshim/python3"
PY_ARGV_LOG="$TMP/py-argv.log"

# run_hook HOOK-FILE PAYLOAD -- from the hostile directory; fills OUT, ERR and RC.
# HOOK_ENV holds extra VAR=value settings for the hook's environment (none by default).
HOOK_ENV=()
run_hook() {
  : > "$PY_ARGV_LOG"
  ( cd "$HOSTILE" && printf '%s' "$2" | env "${HOOK_ENV[@]+"${HOOK_ENV[@]}"}" PATH="$TMP/pyshim:$PATH" PY_ARGV_LOG="$PY_ARGV_LOG" bash "$HOOKS/$1" ) \
    > "$TMP/out" 2> "$TMP/err"
  RC=$?
  OUT="$(cat "$TMP/out")"; ERR="$(cat "$TMP/err")"
}
# no import from the working directory (only provable where the control above imported it)
check_not_imported() { # LABEL
  [ "$SHADOWABLE" = 1 ] || return 0
  if [ ! -e "$HOSTILE/IMPORTED-json" ]; then
    ok "$1: imported nothing from the working directory"
  else
    bad "$1: a json.py in the working directory ran inside the hook" "$(ls -A "$HOSTILE")"
  fi
  rm -f "$HOSTILE"/IMPORTED-*
}
# every python3 it started ran isolated and in UTF-8 mode, and it did start one
check_isolated() { # LABEL
  if [ -s "$PY_ARGV_LOG" ] && [ "$(sort -u "$PY_ARGV_LOG")" = "-I -X utf8" ]; then
    ok "$1: every python3 it starts runs isolated, in UTF-8 mode (-I -X utf8)"
  else
    bad "$1: a python3 was started without -I -X utf8" "started: [$(sort "$PY_ARGV_LOG" | uniq -c | tr '\n' ';')]"
  fi
}

# =============================================================================
echo "=== CwdChanged logs the change without importing from the working directory"
run_hook cwd-changed.sh '{"cwd":"/work/new","previous_cwd":"/work/old"}'
check_not_imported "cwd-changed"
if has "$(cat "$HOME/.claude/hooks/cwd-changed.log" 2> /dev/null)" "/work/old -> /work/new"; then
  ok "cwd-changed: the directory change is still logged (the hook did run)"
else
  bad "cwd-changed: the change was not logged" "rc=$RC log=[$(cat "$HOME/.claude/hooks/cwd-changed.log" 2> /dev/null)] err=[$ERR]"
fi
check_isolated "cwd-changed"

# =============================================================================
echo "=== FileChanged validates a settings file without importing from the working directory"
printf '{"mcpServers": {}}\n' > "$TMP/settings.json"
run_hook file-changed-settings.sh "{\"file_path\":\"$TMP/settings.json\"}"
check_not_imported "file-changed (valid file)"
if has "$ERR" "updated and parses OK" && ! has "$ERR" "INVALID JSON"; then
  ok "file-changed: a valid settings file is reported as parsing"
else
  bad "file-changed: a valid settings file should be reported as parsing" "rc=$RC out=[$OUT] err=[$ERR]"
fi
check_isolated "file-changed (valid file)"

printf '{"broken": \n' > "$TMP/broken.json"
run_hook file-changed-settings.sh "{\"file_path\":\"$TMP/broken.json\"}"
check_not_imported "file-changed (broken file)"
if has "$ERR" "INVALID JSON"; then
  ok "file-changed: a settings file that does not parse is reported as invalid"
else
  bad "file-changed: a broken settings file should be reported as invalid" "rc=$RC out=[$OUT] err=[$ERR]"
fi
check_isolated "file-changed (broken file)"

# =============================================================================
echo "=== FileChanged reads the changed file's path as data, never as Python source"
# The validity check used to be a python3 -c whose SOURCE held the path: open('<path>'). A
# single quote in the path (a directory named "it's here") broke that program, so a valid
# file was reported as INVALID JSON, and a path built to end the string ran what followed.
QDIR="$TMP/it's here"
mkdir -p "$QDIR"
printf '{"mcpServers": {}}\n' > "$QDIR/it's valid.json"
printf '{"broken": \n' > "$QDIR/it's broken.json"
run_hook file-changed-settings.sh "{\"file_path\":\"$QDIR/it's valid.json\"}"
if has "$ERR" "updated and parses OK" && ! has "$ERR" "INVALID JSON"; then
  ok "file-changed: a valid settings file whose path holds a single quote is reported as parsing"
else
  bad "file-changed: a single quote in the path made a valid file look invalid" "rc=$RC out=[$OUT] err=[$ERR]"
fi
check_isolated "file-changed (quoted path)"
run_hook file-changed-settings.sh "{\"file_path\":\"$QDIR/it's broken.json\"}"
if has "$ERR" "INVALID JSON" && ! has "$ERR" "parses OK"; then
  ok "file-changed: a broken settings file whose path holds a single quote is still reported as invalid"
else
  bad "file-changed: a broken file under a quoted path should be reported as invalid" "rc=$RC out=[$OUT] err=[$ERR]"
fi

# A path built to end the string and run a statement of its own. Its first part is a real, valid
# file, so the old program got as far as the injected statement; the marker is created in the
# hook's working directory.
INJ_DIR="$TMP/inj"
mkdir -p "$INJ_DIR"
printf '{}\n' > "$INJ_DIR/x"
INJ="$INJ_DIR/x')); open('INJECTED','w').write('PWNED'); (('"
printf '{}\n' > "$INJ"
# positive control: spliced into Python source, that name does run its statement
( cd "$HOSTILE" && "$PY3" -I -c "import json,sys;json.load(open('$INJ'))" ) > /dev/null 2>&1
if [ -e "$HOSTILE/INJECTED" ]; then
  ok "injection: that path, spliced into Python source, runs its own statement (the check can fail)"
else
  bad "injection: the crafted path does not inject, so the check below proves nothing" "$(ls -A "$HOSTILE")"
fi
rm -f "$HOSTILE/INJECTED"
run_hook file-changed-settings.sh "{\"file_path\":\"$INJ\"}"
if [ ! -e "$HOSTILE/INJECTED" ]; then
  ok "injection: a crafted path ran nothing"
else
  bad "injection: the changed file's path ran as Python source" "a marker was created in the hook's working directory"
  rm -f "$HOSTILE/INJECTED"
fi
if has "$ERR" "updated and parses OK"; then
  ok "injection: the file with the crafted name is read and validated like any other"
else
  bad "injection: the file with the crafted name should be reported as parsing" "rc=$RC out=[$OUT] err=[$ERR]"
fi
check_isolated "file-changed (crafted path)"

# =============================================================================
echo "=== the hooks read and print UTF-8 whatever the locale says"
# -I makes the interpreter ignore PYTHONUTF8 and PYTHONIOENCODING, so under a locale whose
# encoding is ASCII the locale decided how a payload, a path and a settings file were read: a
# valid file holding non-ASCII text was reported as invalid JSON, a path holding any was
# skipped without a word, and a directory change was logged with both paths empty. The
# control proves this host has such a locale; without one nothing below can show the exposure.
ASCII_LOC=en_US.US-ASCII
printf 'caf\303\251\n' > "$TMP/utf8-sample.txt"
if LC_ALL=$ASCII_LOC LANG=$ASCII_LOC "$PY3" -I -c 'import sys; open(sys.argv[1]).read()' "$TMP/utf8-sample.txt" > /dev/null 2>&1; then
  echo "NOTE  this host has no locale whose default encoding rejects UTF-8, so the hooks' encoding cannot be shown here; the -I -X utf8 check above still applies"
else
  ok "utf-8: the control locale ($ASCII_LOC) makes an isolated interpreter reject UTF-8 (the check can fail)"
  E_ACUTE="$(printf '\303\251')"
  KANJI="$(printf '\346\227\245\346\234\254')"
  printf '{"name": "caf%s"}\n' "$E_ACUTE" > "$TMP/accent.json"       # valid JSON, non-ASCII text inside
  UDIR="$TMP/caf$E_ACUTE $KANJI"
  mkdir -p "$UDIR"
  printf '{}\n' > "$UDIR/plain.json"                                   # plain content, non-ASCII path
  CWD_LOG="$HOME/.claude/hooks/cwd-changed.log"
  for extra in "" PYTHONUTF8=1; do   # PYTHONUTF8=1 is the setting -I throws away
    HOOK_ENV=("LC_ALL=$ASCII_LOC" "LANG=$ASCII_LOC" ${extra:+"$extra"})
    where="$ASCII_LOC${extra:+ with $extra}"
    run_hook file-changed-settings.sh "{\"file_path\":\"$TMP/accent.json\"}"
    if has "$ERR" "updated and parses OK" && ! has "$ERR" "INVALID JSON"; then
      ok "utf-8 ($where): a valid settings file holding non-ASCII text is reported as parsing"
    else
      bad "utf-8 ($where): a valid settings file holding non-ASCII text was not reported as parsing" "rc=$RC out=[$OUT] err=[$ERR]"
    fi
    run_hook file-changed-settings.sh "{\"file_path\":\"$UDIR/plain.json\"}"
    if has "$ERR" "$UDIR/plain.json updated and parses OK"; then
      ok "utf-8 ($where): a settings file under a non-ASCII path is found and named"
    else
      bad "utf-8 ($where): a non-ASCII path was skipped or garbled" "rc=$RC out=[$OUT] err=[$ERR]"
    fi
    run_hook cwd-changed.sh "{\"cwd\":\"/work/caf$E_ACUTE\",\"previous_cwd\":\"/work/$KANJI\"}"
    if has "$(tail -1 "$CWD_LOG" 2> /dev/null)" "/work/$KANJI -> /work/caf$E_ACUTE"; then
      ok "utf-8 ($where): a directory change between non-ASCII paths is logged with both paths"
    else
      bad "utf-8 ($where): the directory change lost its non-ASCII paths" "rc=$RC log=[$(tail -1 "$CWD_LOG" 2> /dev/null)] err=[$ERR]"
    fi
  done
  HOOK_ENV=()
fi

echo
echo "passed=$PASS failed=$FAIL"
if [ "$FAIL" -ne 0 ]; then
  echo "FAIL: test_session_hooks_isolated_python"
  exit 1
fi
echo "PASS: test_session_hooks_isolated_python"
