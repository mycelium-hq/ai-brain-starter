#!/usr/bin/env bash
# Regression tests for hooks/check-claude-code-version.sh measuring the binary
# that RUNS the session, not the one PATH happens to reach first (MYC-5205).
#
# THE BUG: the hook ran `claude --version` from PATH. A machine carries several
# Claude Code copies at once (one npm install per node version, a Homebrew one,
# the desktop app's bundled one) and each reaches a different consumer, so the
# PATH-first copy told a desktop session it was on 2.1.258 while it ran 2.1.284,
# and two other copies sat weeks behind with every upgrade "verified" against the
# wrong one. Its 6h cache then replayed whichever binary happened to refresh it
# last into every session.
#
# These drive the REAL, unmodified hook. The running binary is a genuine process
# ancestor: a tiny compiled program named `claude` that prints a version for
# --version and, given --run, runs a command as its child (so the hook's parent
# chain is hook -> sh -> claude, the shape Claude Code produces). A shell script
# cannot stand in for it: the image a script runs as is its interpreter (macOS
# `ps` shows /bin/sh for a script named claude), and a copied system shell is
# killed by macOS (rc 137), so only a compiled image has the right name AND can
# answer --version. `gh` is a PATH shim, so nothing here touches the network.
#
# Controls (each fails against the pre-fix hook; see CHECK_CLAUDE_VERSION_TARGET):
#   1. ancestor prints 9.9.9 while PATH's claude prints 1.1.1 -> the hook reports
#      9.9.9 and names the ancestor as its source
#   2. no claude ancestor -> PATH is used, and the line says so
#   3. two installs at different versions -> ONE warning naming both; the same
#      two at one version -> silence. An npm install is never spawned.
#   4. one binary's cached reading is never replayed into a session running another
# plus: a stale copy on a LaunchAgent PATH is named, the newest desktop bundle is
# read, a hung `claude --version` cannot hang the hook, an upgrade in place
# invalidates the cache, and the desktop path with a space in it survives `ps`.
#
# CHECK_CLAUDE_VERSION_TARGET=<file> runs the same cases against another copy of
# the hook (that is how the pre-fix hook is shown RED). Self-contained.
# Exit 0 = pass, 1 = fail.

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
TARGET="${CHECK_CLAUDE_VERSION_TARGET:-$ROOT/hooks/check-claude-code-version.sh}"

# shellcheck source=tests/integration/lib/sandbox_home.sh
. "$HERE/lib/sandbox_home.sh"
# shellcheck source=tests/integration/lib/gnu_stat_shim.sh
. "$HERE/lib/gnu_stat_shim.sh"
# shellcheck source=tests/integration/lib/real_python.sh
. "$HERE/lib/real_python.sh"

[[ -f "$TARGET" ]] || { echo "FAIL: target not found: $TARGET"; exit 1; }

# Physical path: macOS /var/folders is a symlink to /private/var/folders, and the
# hook reports resolved paths, so every expectation below must use the same form.
TMP="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$TMP" ${REAL_PYTHON_SHIM_DIR:+"$REAL_PYTHON_SHIM_DIR"}' EXIT
sandbox_home "$TMP/home"
# reset_state deletes under $HOME; prove it is the sandbox before anything can.
case "$HOME" in "$TMP"/*) ;; *) echo "FAIL: HOME is not sandboxed ($HOME)"; exit 1 ;; esac

PASS=0
FAIL=0
ok()   { PASS=$((PASS + 1)); echo "PASS  $1"; }
bad()  { FAIL=$((FAIL + 1)); echo "FAIL  $1 :: $(redact "${2:-}")"; }
redact() { printf '%s' "${1//$TMP/<tmp>}"; }

ensure_real_python || { echo "FAIL: no python3 that runs a script file"; exit 1; }
PY3="$(command -v python3)"

# ---- the host's real claude installs must never reach the hook ---------------
# The skew scan lists every `claude` on PATH, so a developer machine (which has
# several) would make every run host-dependent. Keep only PATH directories that
# carry no claude.
clean_path() {
  local out="" d IFS=:
  # shellcheck disable=SC2086  # splitting PATH on ':' is the point
  for d in $PATH; do
    [ -n "$d" ] || continue
    [ -e "$d/claude" ] && continue
    out="${out:+$out:}$d"
  done
  printf '%s' "$out"
}
BASE_PATH="$(clean_path)"
SHIM="$TMP/shim"; PATHBIN="$TMP/pathbin"
mkdir -p "$SHIM" "$PATHBIN"
ln -s "$PY3" "$PATHBIN/python3"
TEST_PATH="$SHIM:$PATHBIN:$BASE_PATH"
for tool in perl awk ps cksum stat readlink mktemp date sed find mv cat bash; do
  PATH="$TEST_PATH" command -v "$tool" >/dev/null 2>&1 ||
    { echo "FAIL: '$tool' is not on the test PATH; the hook needs it"; exit 1; }
done

# gh: answers the release lookup from FAKE_LATEST, refuses the changelog, and logs
# every call so the cache assertions can count network round trips.
cat > "$SHIM/gh" <<'EOF'
#!/bin/sh
echo "gh $*" >> "${GH_LOG:-/dev/null}"
case "$*" in
  *releases/latest*) echo "v${FAKE_LATEST:-10.0.0}" ;;
  *) exit 1 ;;
esac
EOF
chmod +x "$SHIM/gh"
GH_LOG="$TMP/gh.log"
gh_calls() { if [ -f "$GH_LOG" ]; then wc -l < "$GH_LOG" | tr -d ' '; else echo 0; fi; }

# ---- the fake `claude` image -------------------------------------------------
HAVE_CC=0
if command -v cc >/dev/null 2>&1; then
  cat > "$TMP/fake_claude.c" <<'EOF'
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef FAKE_VERSION
#define FAKE_VERSION "0.0.0"
#endif
int main(int argc, char **argv) {
  if (argc > 1 && strcmp(argv[1], "--version") == 0) {
    printf("%s (Claude Code)\n", FAKE_VERSION);
    return 0;
  }
  if (argc > 2 && strcmp(argv[1], "--run") == 0) return system(argv[2]);
  return 2;
}
EOF
  cc -o "$TMP/probe_cc" "$TMP/fake_claude.c" 2>/dev/null && HAVE_CC=1
fi

# build_fake DEST VERSION -- a compiled `claude` that reports VERSION
build_fake() {
  mkdir -p "$(dirname "$1")"
  cc -DFAKE_VERSION="\"$2\"" -o "$1" "$TMP/fake_claude.c"
}
# A C compiler is the only way to get a process image with the right name. Missing
# on a developer box: say so. Missing on CI: that is a hole in the gate, so fail.
need_cc() {
  [ "$HAVE_CC" = 1 ] && return 0
  if [ -n "${CI:-}" ]; then
    bad "$1" "no working C compiler on a CI runner, so this control cannot run"
  else
    echo "SKIP  $1 (no working C compiler; CI requires one)"
  fi
  return 1
}

# ---- fixtures ----------------------------------------------------------------
# An npm-shaped install. Its exe is a script that leaves a SPAWNED marker, which is
# how the "never spawned" assertion tells a read from a run.
plant_npm_install() { # PREFIX VERSION
  local p=$1 v=$2 pkg="$1/lib/node_modules/@anthropic-ai/claude-code"
  mkdir -p "$pkg/bin" "$p/bin"
  printf '{"name":"@anthropic-ai/claude-code","version":"%s"}\n' "$v" > "$pkg/package.json"
  printf '#!/bin/sh\ntouch "%s/SPAWNED"\necho "%s (Claude Code)"\n' "$p" "$v" > "$pkg/bin/claude.exe"
  chmod +x "$pkg/bin/claude.exe"
  ln -sf "../lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe" "$p/bin/claude"
}
plant_plist() { # NAME PATH-VALUE|-  ("-" = a plist with no EnvironmentVariables at all)
  local dir="$HOME/Library/LaunchAgents"
  mkdir -p "$dir"
  {
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
    echo '<plist version="1.0"><dict>'
    echo "<key>Label</key><string>$1</string>"
    if [ "$2" != "-" ]; then
      echo "<key>EnvironmentVariables</key><dict><key>PATH</key><string>$2</string></dict>"
    fi
    echo '</dict></plist>'
  } > "$dir/$1.plist"
}
plant_path_claude() { # VERSION -- the claude that PATH reaches first (a plain script)
  printf '#!/bin/sh\necho "%s (Claude Code)"\n' "$1" > "$PATHBIN/claude"
  chmod +x "$PATHBIN/claude"
}
reset_state() {
  rm -rf "$HOME/.claude/.claude-code-version-check"* "$HOME/Library" "$TMP/fleet" "$TMP/anc" "$TMP/stale" "$GH_LOG"
  rm -f "$PATHBIN/claude"
  mkdir -p "$HOME/.claude"
  KNOWN=""            # no install location is scanned unless a case names one
  LATEST=10.0.0
}

# run_hook [VAR=val ...] [-- command...]   Default command: bash TARGET. Fills
# OUT, ERR, ALL and RC; env defaults can be overridden by the leading VAR=val.
run_hook() {
  local envs=()
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do envs+=("$1"); shift; done
  [ "${1:-}" = "--" ] && shift
  [ $# -gt 0 ] || set -- bash "$TARGET"
  env -u CLAUDE_VERSION_CHECK_WALK_FROM_PID -u CLAUDE_VERSION_CHECK_CACHE_FILE \
      -u CLAUDE_VERSION_CHECK_PROBE_TIMEOUT_SEC \
      PATH="$TEST_PATH" GH_LOG="$GH_LOG" FAKE_LATEST="$LATEST" \
      CLAUDE_VERSION_CHECK_KNOWN_INSTALLS="$KNOWN" \
      "${envs[@]+"${envs[@]}"}" "$@" > "$TMP/out" 2> "$TMP/err"
  RC=$?
  OUT="$(cat "$TMP/out")"; ERR="$(cat "$TMP/err")"
  ALL="$OUT
$ERR"
}
via_ancestor() { # ANCESTOR-PATH [VAR=val ...]  -- run the hook as its descendant
  local anc=$1; shift
  run_hook "$@" -- "$anc" --run "bash '$TARGET'"
}
has() { case "$1" in *"$2"*) return 0 ;; *) return 1 ;; esac; }
# `touch -t` stamp (CCYYMMDDhhmm) for N seconds ago, portable across BSD and GNU.
seconds_ago() { perl -e '@t = localtime(time - $ARGV[0]); printf "%04d%02d%02d%02d%02d", $t[5] + 1900, $t[4] + 1, @t[3, 2, 1]' "$1"; }
an_hour_ago() { seconds_ago 3600; }
headline() { printf '%s\n' "$ALL" | sed -n '/^\[claude-code-version\] [0-9]/{p;q;}'; }
skew_lines() { printf '%s\n' "$ALL" | grep -c 'SKEW'; }
os="$(uname -s)"

echo "target: ${TARGET#"$ROOT"/}"

# =============================================================================
echo "=== control 1: the running binary wins over PATH's claude"
reset_state
if need_cc "control 1"; then
  build_fake "$TMP/anc/claude" 9.9.9
  plant_path_claude 1.1.1
  via_ancestor "$TMP/anc/claude"
  H="$(headline)"
  if has "$H" "[claude-code-version] 9.9.9 (running binary: $TMP/anc/claude)"; then
    ok "control 1: ancestor prints 9.9.9, PATH prints 1.1.1 -> hook reports 9.9.9 and names the ancestor"
  else
    bad "control 1: expected '9.9.9 (running binary: <tmp>/anc/claude)'" "got: [$H] full: [$ALL]"
  fi
  if has "$H" "1.1.1"; then
    bad "control 1: PATH's 1.1.1 leaked into the headline" "$H"
  else
    ok "control 1: PATH's 1.1.1 is absent from the headline"
  fi
fi

# =============================================================================
echo "=== control 2: no claude above the hook -> PATH is used, and labeled"
reset_state
plant_path_claude 1.1.1
run_hook CLAUDE_VERSION_CHECK_WALK_FROM_PID=1
H="$(headline)"
if has "$H" "[claude-code-version] 1.1.1 (PATH claude: $PATHBIN/claude; no claude process above this hook)"; then
  ok "control 2: no ancestor -> PATH's 1.1.1 reported, labeled as the PATH fallback"
else
  bad "control 2: expected the PATH-fallback label" "got: [$H] full: [$ALL]"
fi
if has "$ALL" "running binary"; then
  bad "control 2: claimed a running binary with no claude process above the hook" "$ALL"
else
  ok "control 2: no 'running binary' claim without an ancestor"
fi

# =============================================================================
echo "=== control 3: skew between installs"
reset_state
plant_npm_install "$TMP/fleet/node-a" 3.0.0     # PATH reaches this one first
plant_npm_install "$TMP/fleet/node-b" 4.0.0
KNOWN="$TMP/fleet/node-*/bin/claude"
LATEST=4.0.0
TEST_PATH_SAVE="$TEST_PATH"; TEST_PATH="$TMP/fleet/node-a/bin:$TEST_PATH"
run_hook CLAUDE_VERSION_CHECK_WALK_FROM_PID=1
if [ "$(skew_lines)" = 1 ] &&
   has "$ALL" "3.0.0 $TMP/fleet/node-a/bin/claude" && has "$ALL" "4.0.0 $TMP/fleet/node-b/bin/claude"; then
  ok "control 3: 3.0.0 vs 4.0.0 -> exactly ONE warning, naming both versions and both paths"
else
  bad "control 3: expected one SKEW line naming both installs" "skew-lines=$(skew_lines) all: [$ALL]"
fi
if [ -e "$TMP/fleet/node-b/SPAWNED" ]; then
  bad "control 3: an npm install was SPAWNED to read its version" "$TMP/fleet/node-b/SPAWNED exists"
else
  ok "control 3: the scanned npm install was read from package.json, never spawned"
fi

# same two installs, one version: silence
reset_state
plant_npm_install "$TMP/fleet/node-a" 4.0.0
plant_npm_install "$TMP/fleet/node-b" 4.0.0
KNOWN="$TMP/fleet/node-*/bin/claude"; LATEST=4.0.0
run_hook CLAUDE_VERSION_CHECK_WALK_FROM_PID=1
if [ -z "$OUT" ] && [ -z "$ERR" ]; then
  ok "control 3: the same two installs at ONE version -> no output at all"
else
  bad "control 3: an all-equal fleet must stay quiet" "stdout=[$OUT] stderr=[$ERR]"
fi
TEST_PATH="$TEST_PATH_SAVE"

# =============================================================================
echo "=== control 3b: a stale copy on ONE LaunchAgent's PATH is named"
reset_state
plant_npm_install "$TMP/fleet/node-a" 4.0.0
plant_npm_install "$TMP/stale" 1.0.0
plant_plist "com.example.fresh" "$TMP/fleet/node-a/bin:/usr/bin:/bin"
plant_plist "com.example.stale" "$TMP/stale/bin:/usr/bin:/bin"
plant_plist "com.example.nopath" "-"
KNOWN=""; LATEST=4.0.0
TEST_PATH_SAVE="$TEST_PATH"; TEST_PATH="$TMP/fleet/node-a/bin:$TEST_PATH"
run_hook CLAUDE_VERSION_CHECK_WALK_FROM_PID=1
if [ "$(skew_lines)" = 1 ] && has "$ALL" "1.0.0 $TMP/stale/bin/claude" && has "$ALL" "4.0.0 $TMP/fleet/node-a/bin/claude"; then
  ok "control 3b: a 1.0.0 copy reachable from one plist's PATH is named next to the 4.0.0 fleet"
else
  bad "control 3b: the stale plist copy was not reported" "$ALL"
fi
# the same fleet with the stale copy brought up to date: quiet again
plant_npm_install "$TMP/stale" 4.0.0
rm -f "$HOME/.claude/.claude-code-version-check"*
run_hook CLAUDE_VERSION_CHECK_WALK_FROM_PID=1
if [ -z "$OUT" ] && [ -z "$ERR" ]; then
  ok "control 3b: all plists resolving 4.0.0 (and one with no PATH key at all) -> quiet"
else
  bad "control 3b: an all-equal fleet must stay quiet" "stdout=[$OUT] stderr=[$ERR]"
fi
TEST_PATH="$TEST_PATH_SAVE"

# =============================================================================
echo "=== control 3c: the newest desktop bundle is read; unreadable inputs are survivable"
reset_state
plant_npm_install "$TMP/fleet/node-a" 4.0.0
BUNDLE="$HOME/Library/Application Support/Claude/claude-code"
for v in 3.9.0 4.0.1; do
  mkdir -p "$BUNDLE/$v/claude.app/Contents/MacOS"
  printf '#!/bin/sh\ntouch "%s/SPAWNED"\necho "%s (Claude Code)"\n' "$BUNDLE/$v" "$v" > "$BUNDLE/$v/claude.app/Contents/MacOS/claude"
  chmod +x "$BUNDLE/$v/claude.app/Contents/MacOS/claude"
done
mkdir -p "$HOME/Library/LaunchAgents"; printf 'this is not a plist' > "$HOME/Library/LaunchAgents/com.example.broken.plist"
LATEST=4.0.1
TEST_PATH_SAVE="$TEST_PATH"; TEST_PATH="$TMP/fleet/node-a/bin:$TEST_PATH"
run_hook CLAUDE_VERSION_CHECK_WALK_FROM_PID=1
if has "$ALL" "4.0.1 ~/Library/Application Support/Claude/claude-code/4.0.1/claude.app/Contents/MacOS/claude" &&
   ! has "$ALL" "3.9.0"; then
  ok "control 3c: only the NEWEST desktop bundle (4.0.1) joins the comparison, shown with ~ for HOME"
else
  bad "control 3c: newest desktop bundle not reported as expected" "$ALL"
fi
if has "$ALL" "1 LaunchAgent plist(s) could not be read"; then
  ok "control 3c: a malformed plist is counted in the warning instead of aborting the scan"
else
  bad "control 3c: a malformed plist should be reported, not hidden" "$ALL"
fi
if [ -e "$BUNDLE/4.0.1/SPAWNED" ]; then
  bad "control 3c: the desktop bundle was spawned to read its version" "$BUNDLE/4.0.1/SPAWNED exists"
else
  ok "control 3c: the desktop bundle's version came from its directory name, no spawn"
fi
TEST_PATH="$TEST_PATH_SAVE"

# =============================================================================
echo "=== control 3d: a copy whose layout hides its version is asked, once"
reset_state
plant_npm_install "$TMP/fleet/node-a" 4.0.0
mkdir -p "$TMP/stale/bin"
printf '#!/bin/sh\necho "2.2.2 (Claude Code)"\n' > "$TMP/stale/bin/claude"; chmod +x "$TMP/stale/bin/claude"
plant_plist "com.example.wrapper" "$TMP/stale/bin:/usr/bin"
LATEST=4.0.0
TEST_PATH_SAVE="$TEST_PATH"; TEST_PATH="$TMP/fleet/node-a/bin:$TEST_PATH"
run_hook CLAUDE_VERSION_CHECK_WALK_FROM_PID=1
if has "$ALL" "2.2.2 $TMP/stale/bin/claude"; then
  ok "control 3d: a plain wrapper on a plist PATH is asked --version and its 2.2.2 is reported"
else
  bad "control 3d: the wrapper's version was not reported" "$ALL"
fi
TEST_PATH="$TEST_PATH_SAVE"

# =============================================================================
echo "=== the skew scan reaches into other jobs' PATHs, so it must not run just anything"
reset_state
plant_npm_install "$TMP/fleet/node-a" 4.0.0
mkdir -p "$TMP/stale/bin"
printf '#!/bin/sh\ntouch "%s/SPAWNED"\necho "2.2.2 (Claude Code)"\n' "$TMP/stale" > "$TMP/stale/bin/claude"
chmod 755 "$TMP/stale/bin/claude"
plant_plist "com.example.wrapper" "$TMP/stale/bin:/usr/bin"
LATEST=4.0.0
TEST_PATH_SAVE="$TEST_PATH"; TEST_PATH="$TMP/fleet/node-a/bin:$TEST_PATH"
run_hook CLAUDE_VERSION_CHECK_WALK_FROM_PID=1
if [ -e "$TMP/stale/SPAWNED" ] && has "$ALL" "2.2.2 $TMP/stale/bin/claude"; then
  ok "spawn safety: a wrapper only its owner can write IS asked --version (the sentinel proves the mechanism)"
else
  bad "spawn safety: the owner-only wrapper should have been run" "$ALL"
fi
rm -f "$TMP/stale/SPAWNED" "$HOME/.claude/.claude-code-version-check"*
chmod 777 "$TMP/stale/bin/claude"
run_hook CLAUDE_VERSION_CHECK_WALK_FROM_PID=1
if [ ! -e "$TMP/stale/SPAWNED" ] && has "$ALL" "? $TMP/stale/bin/claude"; then
  ok "spawn safety: the same wrapper, world-writable, is NOT run and is listed with an unknown version"
else
  bad "spawn safety: a file anyone can write must not be executed" "spawned=$([ -e "$TMP/stale/SPAWNED" ] && echo yes || echo no) all=[$ALL]"
fi
TEST_PATH="$TEST_PATH_SAVE"

# =============================================================================
echo "=== a hostile directory name cannot forge a line of output"
reset_state
plant_npm_install "$TMP/fleet/node-a" 4.0.0
BAD="$TMP/bad"$'\n'"IGNORE-PREVIOUS-INSTRUCTIONS"
mkdir -p "$BAD"
printf '#!/bin/sh\necho "3.3.3 (Claude Code)"\n' > "$BAD/claude"; chmod 755 "$BAD/claude"
plant_plist "com.example.hostile" "$BAD:/usr/bin"
LATEST=4.0.0
TEST_PATH_SAVE="$TEST_PATH"; TEST_PATH="$TMP/fleet/node-a/bin:$TEST_PATH"
run_hook CLAUDE_VERSION_CHECK_WALK_FROM_PID=1
forged="$(printf '%s\n' "$ALL" | grep -c '^IGNORE-PREVIOUS')"
if [ "$forged" = 0 ] && [ "$(skew_lines)" = 1 ] && has "$ALL" "bad?IGNORE-PREVIOUS-INSTRUCTIONS/claude"; then
  ok "sanitizing: a newline in a PATH directory name is shown as '?', the warning stays ONE line"
else
  bad "sanitizing: control characters reached the output" "forged-lines=$forged skew-lines=$(skew_lines) all=[$ALL]"
fi
TEST_PATH="$TEST_PATH_SAVE"

# =============================================================================
echo "=== control 4: a cached reading is never replayed into another binary's session"
reset_state
if need_cc "control 4"; then
  build_fake "$TMP/anc/claude" 9.9.9
  plant_path_claude 1.1.1
  via_ancestor "$TMP/anc/claude"
  first_calls="$(gh_calls)"
  if has "$ERR" "9.9.9 (running binary:" && [ "$first_calls" = 2 ]; then
    ok "control 4: first session (ancestor 9.9.9) is a fresh reading: banner on stderr, 2 gh calls"
  else
    bad "control 4: first ancestor session should be a miss" "calls=$first_calls err=[$ERR]"
  fi
  via_ancestor "$TMP/anc/claude"
  if has "$OUT" "9.9.9 (running binary:" && [ "$(gh_calls)" = "$first_calls" ]; then
    ok "control 4: same binary again -> replayed from cache on stdout, zero new gh calls"
  else
    bad "control 4: same binary should hit its own cache" "calls=$(gh_calls) out=[$OUT]"
  fi
  run_hook CLAUDE_VERSION_CHECK_WALK_FROM_PID=1
  if has "$ERR" "1.1.1 (PATH claude:" && ! has "$ALL" "9.9.9 (running binary:" && [ "$(gh_calls)" != "$first_calls" ]; then
    ok "control 4: a PATH-fallback session does NOT get the ancestor's banner; it measures its own (1.1.1)"
  else
    bad "control 4: the other binary's cached banner was replayed" "calls=$(gh_calls) all=[$ALL]"
  fi
  run_hook CLAUDE_VERSION_CHECK_WALK_FROM_PID=1
  if has "$OUT" "1.1.1 (PATH claude:" && ! has "$ALL" "9.9.9"; then
    ok "control 4: the PATH-fallback binary then hits ITS OWN cache"
  else
    bad "control 4: PATH-fallback should replay its own banner" "$ALL"
  fi
  via_ancestor "$TMP/anc/claude"
  if has "$OUT" "9.9.9 (running binary:" && ! has "$(headline)" "1.1.1"; then
    ok "control 4: back in the ancestor's session, its own banner again (nothing overwrote it)"
  else
    bad "control 4: ancestor banner lost" "$ALL"
  fi
  # The un-keyed file keeps working as "the last banner": other tools read it.
  mirror="$(cat "$HOME/.claude/.claude-code-version-check" 2>/dev/null)"
  if has "$mirror" "[claude-code-version]"; then
    ok "control 4: the un-keyed file name still receives the last fresh banner (mirror for other readers)"
  else
    bad "control 4: the legacy-name mirror is empty" "[$mirror]"
  fi
fi

# =============================================================================
echo "=== control 4b: a running claude that reports no version still gets cache hits"
reset_state
if need_cc "control 4b"; then
  # The claude above the hook is found but prints nothing a version parser accepts
  # (the probe bound under load, or on Linux a comm=claude process whose exe is an
  # interpreter). The hook then reports PATH's claude, labeled. That reading must be
  # saved where the NEXT session under the same ancestor looks for it, or every
  # session start repeats both GitHub requests, the probes and the scan.
  build_fake "$TMP/anc/claude" no-version-here
  plant_path_claude 1.1.1
  via_ancestor "$TMP/anc/claude"; q1="$(gh_calls)"
  if has "$ERR" "1.1.1 (PATH claude:" && has "$ERR" "reported no version" && [ "$q1" = 2 ]; then
    ok "control 4b: an ancestor that reports no version -> PATH's 1.1.1, labeled with why, 2 gh calls"
  else
    bad "control 4b: the first session should be a labeled PATH fallback" "calls=$q1 err=[$ERR]"
  fi
  via_ancestor "$TMP/anc/claude"
  if has "$OUT" "1.1.1 (PATH claude:" && [ "$(gh_calls)" = "$q1" ]; then
    ok "control 4b: the same ancestor again -> replayed from cache, zero new gh calls"
  else
    bad "control 4b: a second session under the same ancestor must hit the cache" "calls=$(gh_calls) (was $q1) out=[$OUT] err=[$ERR]"
  fi
  # an ancestor that DOES answer must still not be served that reading
  build_fake "$TMP/anc/answering/claude" 9.9.9
  via_ancestor "$TMP/anc/answering/claude"
  if has "$ERR" "9.9.9 (running binary:" && ! has "$ALL" "no version"; then
    ok "control 4b: a different, answering ancestor is measured on its own, not served the fallback reading"
  else
    bad "control 4b: the fallback reading leaked into another binary's session" "calls=$(gh_calls) all=[$ALL]"
  fi
fi

# =============================================================================
echo "=== a binary newer than its reading voids the reading"
reset_state
if need_cc "upgrade"; then
  build_fake "$TMP/anc/claude" 9.9.9
  plant_path_claude 1.1.1
  touch -t 202001010000 "$TMP/anc/claude"
  via_ancestor "$TMP/anc/claude"; c1="$(gh_calls)"
  # Age the reading by an hour: well inside the 6h TTL, so from here only the
  # binary changing can void it (mtimes have one-second resolution on macOS).
  touch -t "$(an_hour_ago)" "$HOME"/.claude/.claude-code-version-check.*
  via_ancestor "$TMP/anc/claude"; c2="$(gh_calls)"
  touch "$TMP/anc/claude"                      # the file changed on disk
  via_ancestor "$TMP/anc/claude"; c3="$(gh_calls)"
  if [ "$c2" = "$c1" ] && [ "$c3" != "$c2" ]; then
    ok "upgrade: unchanged binary -> cache hit; a binary newer than its reading -> a fresh reading"
  else
    bad "upgrade: a changed binary should void its cached reading" "calls: first=$c1 second=$c2 after-touch=$c3"
  fi
fi

# =============================================================================
echo "=== a desktop-shaped ancestor path with a space, and the npm-shaped one"
reset_state
if need_cc "ancestor layouts"; then
  DESK="$HOME/Library/Application Support/Claude/claude-code/9.9.9/claude.app/Contents/MacOS/claude"
  build_fake "$DESK" 9.9.9
  plant_path_claude 1.1.1
  LATEST=9.9.9
  via_ancestor "$DESK"
  # up to date and nothing else installed that differs except PATH's 1.1.1 -> skew line only
  if has "$ALL" "9.9.9 ~/Library/Application Support/Claude/claude-code/9.9.9/claude.app/Contents/MacOS/claude"; then
    ok "desktop layout: a path containing a space survives ps/readlink and is the version-9.9.9 source"
  else
    bad "desktop layout: path with a space not handled" "$ALL"
  fi
  LATEST=10.0.0
  rm -f "$HOME/.claude/.claude-code-version-check"*
  via_ancestor "$DESK"
  if has "$(headline)" "This is the desktop app's bundled copy"; then
    ok "desktop layout: the hint says the bundled copy updates with the app, not npm"
  else
    bad "desktop layout: wrong upgrade hint" "$(headline)"
  fi

  reset_state
  plant_path_claude 1.1.1
  NPMP="$TMP/fleet/node-z"
  PKG="$NPMP/lib/node_modules/@anthropic-ai/claude-code"
  mkdir -p "$NPMP/bin"
  build_fake "$PKG/bin/claude.exe" 9.9.9
  printf '{"name":"@anthropic-ai/claude-code","version":"9.9.9"}\n' > "$PKG/package.json"
  ln -sf "../lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe" "$NPMP/bin/claude"
  touch -t 202001010000 "$PKG/bin/claude.exe"
  via_ancestor "$NPMP/bin/claude"; n1="$(gh_calls)"
  H="$(headline)"
  # macOS reports the path the process was exec'd by (the bin symlink); Linux
  # reports the image behind it. Either way the hint must name THIS install.
  if [ "$os" = Linux ]; then want_label="$PKG/bin/claude.exe"; else want_label="$NPMP/bin/claude"; fi
  if has "$H" "9.9.9 (running binary: $want_label)" &&
     has "$H" "npm i -g --prefix '$NPMP' @anthropic-ai/claude-code@latest"; then
    ok "npm layout: started through the bin symlink, the upgrade hint carries THIS install's --prefix"
  else
    bad "npm layout: expected the running binary path and a --prefix hint" "$H"
  fi
  # `npm i -g` replaces the file the bin symlink points at; the reading it voids
  # must be the one for THIS symlink, found through it.
  touch -t "$(an_hour_ago)" "$HOME"/.claude/.claude-code-version-check.*
  via_ancestor "$NPMP/bin/claude"; n2="$(gh_calls)"
  touch "$PKG/bin/claude.exe"
  via_ancestor "$NPMP/bin/claude"; n3="$(gh_calls)"
  if [ "$n2" = "$n1" ] && [ "$n3" != "$n2" ]; then
    ok "npm layout: reinstalling the file behind the bin symlink voids the cached reading"
  else
    bad "npm layout: a reinstall behind the symlink should void the cache" "calls: first=$n1 second=$n2 after-touch=$n3"
  fi
fi

# =============================================================================
echo "=== a binary replaced under a running session"
reset_state
if need_cc "replaced binary"; then
  build_fake "$TMP/anc/claude" 9.9.9
  plant_path_claude 1.1.1
  # The ancestor unlinks itself, then runs the hook: the file is gone but the
  # image is still what runs the session.
  run_hook -- "$TMP/anc/claude" --run "rm -f '$TMP/anc/claude'; bash '$TARGET'"
  H="$(headline)"
  if [ "$os" = Linux ]; then
    if has "$H" "9.9.9 (running binary:"; then
      ok "replaced binary (Linux): the unlinked image still reports 9.9.9 through /proc/<pid>/exe"
    else
      bad "replaced binary (Linux): should still measure the running image" "$H"
    fi
  else
    if has "$H" "1.1.1 (PATH claude:" && has "$H" "is no longer an executable file"; then
      ok "replaced binary (no procfs): says the running claude is gone and falls back to PATH, labeled"
    else
      bad "replaced binary (no procfs): expected a labeled PATH fallback" "$H"
    fi
  fi
fi

# =============================================================================
echo "=== things that must stay quiet or survivable"
reset_state
run_hook CLAUDE_VERSION_CHECK_WALK_FROM_PID=1
if [ -z "$OUT" ] && [ -z "$ERR" ] && [ "$RC" = 0 ] && [ "$(gh_calls)" = 0 ]; then
  ok "nothing to measure: no claude above the hook and none on PATH -> silent, rc 0, no gh call"
else
  bad "no claude anywhere should be a silent no-op" "rc=$RC out=[$OUT] err=[$ERR] calls=$(gh_calls)"
fi

reset_state
printf '#!/bin/sh\necho "2.1.286-beta (Claude Code)"\n' > "$PATHBIN/claude"; chmod +x "$PATHBIN/claude"
LATEST=2.1.290
run_hook CLAUDE_VERSION_CHECK_WALK_FROM_PID=1
if has "$(headline)" "2.1.286-beta (PATH claude:" && [ "$RC" = 0 ]; then
  ok "prerelease: a patch field like '286-beta' does not abort the hook (the gap arithmetic is guarded)"
else
  bad "prerelease: the hook must survive a non-numeric patch field" "rc=$RC all=[$ALL]"
fi

reset_state
if need_cc "relative path"; then
  build_fake "$TMP/anc/claude" 9.9.9
  plant_path_claude 1.1.1
  run_hook -- sh -c 'cd "$1" && exec ./claude --run "$2"' sh "$TMP/anc" "bash '$TARGET'"
  H="$(headline)"
  if [ "$os" = Linux ]; then
    # /proc/<pid>/exe is always absolute, so there is nothing relative to refuse.
    if has "$H" "9.9.9 (running binary:"; then
      ok "relative start (Linux): /proc gives the absolute image, so the running binary is still found"
    else
      bad "relative start (Linux): expected the running binary" "$H"
    fi
  else
    if has "$H" "1.1.1 (PATH claude:" && has "$H" "started by a relative path"; then
      ok "relative start (macOS): a claude started as ./claude cannot be located later; falls back to PATH and says why"
    else
      bad "relative start (macOS): expected a labeled PATH fallback" "$H"
    fi
  fi
fi

reset_state
if need_cc "cache cleanup"; then
  build_fake "$TMP/anc/claude" 9.9.9
  plant_path_claude 1.1.1
  C="$HOME/.claude/.claude-code-version-check"
  printf 'idle banner\n' > "$C.%2Fgone%2Fclaude"; touch -t "$(seconds_ago $((30 * 86400)))" "$C.%2Fgone%2Fclaude"
  printf 'recent banner\n' > "$C.%2Frecent%2Fclaude"; touch -t "$(seconds_ago $((3 * 86400)))" "$C.%2Frecent%2Fclaude"
  via_ancestor "$TMP/anc/claude"
  if [ ! -e "$C.%2Fgone%2Fclaude" ] && [ -e "$C.%2Frecent%2Fclaude" ] && [ -e "$C" ]; then
    ok "cleanup: a per-binary cache idle for 30 days is removed; a 3-day-old one and the un-keyed file stay"
  else
    bad "cleanup: only long-idle per-binary caches may be removed" "$(ls -A "$HOME/.claude")"
  fi
fi

# A scan that cannot run must not look like a fleet that agrees.
reset_state
plant_path_claude 2.1.286
LATEST=2.1.286
mkdir -p "$TMP/badpy"
printf '#!/bin/sh\nexit 7\n' > "$TMP/badpy/python3"; chmod +x "$TMP/badpy/python3"
TEST_PATH_SAVE="$TEST_PATH"; TEST_PATH="$TMP/badpy:$TEST_PATH"
run_hook CLAUDE_VERSION_CHECK_WALK_FROM_PID=1
if has "$ALL" "install-skew scan failed (python3 exited 7)"; then
  ok "scan failure: a crashing scan says so instead of reading as 'all copies agree'"
else
  bad "scan failure: a scan that could not run must not be silent" "$ALL"
fi
TEST_PATH="$TEST_PATH_SAVE"

# =============================================================================
echo "=== a hung claude --version cannot hang the hook"
reset_state
printf '#!/bin/sh\nexec sleep 30\n' > "$PATHBIN/claude"; chmod +x "$PATHBIN/claude"
start=$SECONDS
run_hook CLAUDE_VERSION_CHECK_WALK_FROM_PID=1 CLAUDE_VERSION_CHECK_PROBE_TIMEOUT_SEC=1
took=$((SECONDS - start))
if [ "$took" -lt 12 ] && [ -z "$OUT" ] && [ -z "$ERR" ] && [ "$RC" = 0 ]; then
  ok "timeout: a claude that never answers is cut off after the probe bound ($took s), hook exits 0 silently"
else
  bad "timeout: the hook must be bounded and silent" "took=${took}s rc=$RC out=[$OUT] err=[$ERR]"
fi

# =============================================================================
echo "=== the keyed cache survives GNU stat semantics"
reset_state
if need_cc "gnu stat"; then
  build_fake "$TMP/anc/claude" 9.9.9
  plant_path_claude 1.1.1
  install_gnu_stat_shim "$TMP/gnu-stat-shim"
  TEST_PATH_SAVE="$TEST_PATH"; TEST_PATH="$TMP/gnu-stat-shim:$TEST_PATH"
  via_ancestor "$TMP/anc/claude"; g1="$(gh_calls)"
  via_ancestor "$TMP/anc/claude"
  if has "$OUT" "9.9.9 (running binary:" && [ "$(gh_calls)" = "$g1" ]; then
    ok "gnu stat: key derivation and the cache-age read both work (miss, then a hit with no new gh calls)"
  else
    bad "gnu stat: the keyed cache misbehaved under GNU stat's -f behavior" "calls=$(gh_calls) out=[$OUT] err=[$ERR]"
  fi
  TEST_PATH="$TEST_PATH_SAVE"
fi

# =============================================================================
echo "=== CLAUDE_VERSION_CHECK_CACHE_FILE pins the cache"
reset_state
plant_path_claude 1.1.1
printf '%s\n' "[claude-code-version] pinned banner" > "$TMP/pinned"
run_hook CLAUDE_VERSION_CHECK_CACHE_FILE="$TMP/pinned"
if has "$OUT" "pinned banner" && [ "$(gh_calls)" = 0 ]; then
  ok "pin: an explicit cache file is read as-is (no key, no gh call)"
else
  bad "pin: the pinned cache file was not honored" "out=[$OUT] calls=$(gh_calls)"
fi

echo
echo "passed=$PASS failed=$FAIL"
if [ "$FAIL" -ne 0 ]; then
  echo "FAIL: test_check_claude_code_version_running_binary"
  exit 1
fi
echo "PASS: test_check_claude_code_version_running_binary"
