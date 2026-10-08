#!/usr/bin/env bash
# CI lock: a test that sandboxes HOME cannot reach the host's launchd job, whatever
# the developer's shell exports.
#
# launchd keys a job by LABEL for the whole account, not by HOME. The hook installer
# defaults --vault-path to $VAULT_ROOT, and for a vault outside the system temp dir
# it runs scripts/install-vault-daily-maintenance.sh, which does `launchctl unload`
# and then `launchctl load` on the plist it writes. Run under a sandbox HOME on a
# machine that exports VAULT_ROOT, that could unload the real
# com.abs.vault-daily-maintenance job and load one that points into a directory
# about to be deleted. CI exports no VAULT_ROOT, so only a developer's machine was
# exposed.
#
# Two layers close it, and both are proved here:
#   1. tests/integration/lib/sandbox_home.sh: run_sandboxed unsets VAULT_ROOT and
#      sets ABS_NO_AUTO_GC=1 unless the caller names them.
#   2. scripts/install-vault-daily-maintenance.sh calls launchctl only when HOME is
#      the home directory the user database records for this uid.
# The hook installer is then run end to end with each layer defeated in turn, and the
# line that says a job was written and not loaded has to reach the user under --quiet,
# which is how bootstrap and the auto-updater run it.
#
# No real launchd is reached. A recording launchctl is first on PATH in every run,
# and the user database is injected through a stub dscacheutil, so the case where
# HOME IS the account's home is exercised without touching the account. uname is
# stubbed to Darwin so the launchd branch also runs on a Linux runner.
#
# Stdlib python3 + bash only. No network, no git. Tmpdir removed on exit.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCHED="$REPO_ROOT/scripts/install-vault-daily-maintenance.sh"
HOOK_INSTALLER="$REPO_ROOT/scripts/install-hooks-user-level.py"
# shellcheck source=tests/integration/lib/sandbox_home.sh
. "$SCRIPT_DIR/lib/sandbox_home.sh"

PASS=0; FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ok()  { PASS=$((PASS + 1)); echo "PASS  $1"; }
bad() { FAIL=$((FAIL + 1)); echo "FAIL  $1 :: $2"; }

# A real python to launch the hook installer with (a bare python3 may be a refuse-shim).
LAUNCH_PY=""
for c in /opt/homebrew/bin/python3 /usr/bin/python3 /usr/local/bin/python3; do
  [ -x "$c" ] && "$c" -c 'import sys' >/dev/null 2>&1 && { LAUNCH_PY="$c"; break; }
done
[ -z "$LAUNCH_PY" ] && LAUNCH_PY="$(command -v python3 || true)"
[ -z "$LAUNCH_PY" ] && { echo "SKIP: no real python3 to launch the hook installer"; exit 0; }

# BIN holds the recorder and the Darwin uname; PWBIN holds the user database.
BIN="$TMP/bin"; PWBIN="$TMP/pwbin"
mkdir -p "$BIN" "$PWBIN"
LOG="$TMP/launchctl.log"
cat > "$BIN/launchctl" <<'SH'
#!/bin/sh
printf '%s\n' "$*" >> "$LAUNCHCTL_LOG"
exit 0
SH
cat > "$BIN/uname" <<'SH'
#!/bin/sh
echo Darwin
SH
cat > "$PWBIN/dscacheutil" <<'SH'
#!/bin/sh
printf 'name: tester\npassword: *\nuid: %s\ngid: 20\ndir: %s\nshell: /bin/sh\n' "$(id -u)" "$STUB_PASSWD_HOME"
SH
chmod +x "$BIN/launchctl" "$BIN/uname" "$PWBIN/dscacheutil"
STUB_PATH="$BIN:$PWBIN:/usr/bin:/bin"   # recorder + an injected user database
OWN_DB_PATH="$BIN:/usr/bin:/bin"        # recorder + whatever this machine's database says

calls() { if [ -s "$LOG" ]; then wc -l < "$LOG" | tr -d ' '; else echo 0; fi; }

echo "=== 1. run_sandboxed drops VAULT_ROOT and opts out of auto-GC unless told otherwise ==="
H1="$TMP/h1"; mkdir -p "$H1"
SHOW='printf "%s|%s" "${VAULT_ROOT-unset}" "${ABS_NO_AUTO_GC-unset}"'
GOT="$(VAULT_ROOT=/ambient/vault ABS_NO_AUTO_GC=0 run_sandboxed "$H1" sh -c "$SHOW")"
if [ "$GOT" = "unset|1" ]; then ok "an exported VAULT_ROOT does not reach the child, and auto-GC is opted out"
else bad "defaults" "VAULT_ROOT|ABS_NO_AUTO_GC seen by the child: [$GOT], expected [unset|1]"; fi
GOT="$(run_sandboxed "$H1" env VAULT_ROOT=/chosen/vault ABS_NO_AUTO_GC=0 sh -c "$SHOW")"
if [ "$GOT" = "/chosen/vault|0" ]; then ok "a test that names either one still gets it"
else bad "explicit" "VAULT_ROOT|ABS_NO_AUTO_GC seen by the child: [$GOT], expected [/chosen/vault|0]"; fi

echo "=== 2. the scheduler installer leaves launchd alone under a sandbox HOME ==="
VAULT="$TMP/vault"; mkdir -p "$VAULT"
H2="$TMP/h2"; mkdir -p "$H2/Library/LaunchAgents"
PLIST2="$H2/Library/LaunchAgents/com.abs.vault-daily-maintenance.plist"
echo "an earlier install" > "$PLIST2"   # the case where the old script unloaded first
: > "$LOG"
OUT="$(run_sandboxed "$H2" env PATH="$STUB_PATH" LAUNCHCTL_LOG="$LOG" \
  STUB_PASSWD_HOME="$TMP/the-account-home" ABS_NO_AUTO_GC=0 /bin/bash "$SCHED" "$VAULT" 2>&1)"
RC=$?
if [ "$RC" -eq 0 ]; then ok "exits 0"; else bad "exit" "rc=$RC: $OUT"; fi
if [ "$(calls)" -eq 0 ]; then ok "launchctl was not called"
else bad "launchctl" "$(calls) call(s) recorded: $(tr '\n' ';' < "$LOG")"; fi
if grep -qF "$VAULT" "$PLIST2" 2>/dev/null; then ok "the plist is still written, inside the sandbox"
else bad "plist" "the plist at $PLIST2 was not rewritten"; fi
N="$(printf '%s\n' "$OUT" | grep -c 'skipped loading')"
if [ "$N" -eq 1 ]; then ok "one line says loading was skipped"
else bad "message" "expected exactly one 'skipped loading' line, got $N: $OUT"; fi

echo "=== 3. ...and it calls launchctl when HOME is the account's home (injected) ==="
H3="$TMP/h3"; mkdir -p "$H3/Library/LaunchAgents"
PLIST3="$H3/Library/LaunchAgents/com.abs.vault-daily-maintenance.plist"
echo "an earlier install" > "$PLIST3"
: > "$LOG"
run_sandboxed "$H3" env PATH="$STUB_PATH" LAUNCHCTL_LOG="$LOG" \
  STUB_PASSWD_HOME="$H3" ABS_NO_AUTO_GC=0 /bin/bash "$SCHED" "$VAULT" >/dev/null 2>&1
EXPECT="$(printf 'unload %s\nload %s' "$PLIST3" "$PLIST3")"
if [ "$(cat "$LOG")" = "$EXPECT" ]; then ok "unload, then load, on its own plist"
else bad "launchctl" "recorded [$(tr '\n' ';' < "$LOG")], expected unload then load of $PLIST3"; fi
# The same home spelled another way is still the account's home.
ln -s "$H3" "$TMP/h3-link"
for SPELLING in "$H3/" "$TMP/h3-link"; do
  : > "$LOG"
  run_sandboxed "$H3" env PATH="$STUB_PATH" LAUNCHCTL_LOG="$LOG" \
    STUB_PASSWD_HOME="$SPELLING" ABS_NO_AUTO_GC=0 /bin/bash "$SCHED" "$VAULT" >/dev/null 2>&1
  if [ "$(cat "$LOG")" = "$EXPECT" ]; then ok "the account's home spelled [$SPELLING] still loads"
  else bad "spelling" "[$SPELLING] recorded [$(tr '\n' ';' < "$LOG")]"; fi
done

echo "=== 3a. ...and it refuses when the user database gives no answer ==="
# Run from inside HOME: `cd ""` stays where it is, so an empty answer would read as
# a match for the directory the script happens to be standing in.
H3A="$TMP/h3a"; mkdir -p "$H3A"
: > "$LOG"
( cd "$H3A" && run_sandboxed "$H3A" env PATH="$STUB_PATH" LAUNCHCTL_LOG="$LOG" \
    STUB_PASSWD_HOME="" ABS_NO_AUTO_GC=0 /bin/bash "$SCHED" "$VAULT" >/dev/null 2>&1 )
if [ "$(calls)" -eq 0 ]; then ok "no launchctl call when the user database names no home"
else bad "empty answer" "$(calls) call(s) recorded: $(tr '\n' ';' < "$LOG")"; fi

echo "=== 3b. this machine's own user database refuses a sandbox HOME (macOS only) ==="
if [ "$(/usr/bin/uname -s 2>/dev/null)" = "Darwin" ] && [ -x /usr/bin/dscacheutil ]; then
  H3B="$TMP/h3b"; mkdir -p "$H3B"
  : > "$LOG"
  run_sandboxed "$H3B" env PATH="$OWN_DB_PATH" LAUNCHCTL_LOG="$LOG" \
    ABS_NO_AUTO_GC=0 /bin/bash "$SCHED" "$VAULT" >/dev/null 2>&1
  if [ "$(calls)" -eq 0 ]; then ok "no launchctl call with the machine's real user database"
  else bad "real database" "$(calls) call(s) recorded under a sandbox HOME"; fi
  # That refusal only means something if the real database answers with the
  # account's home. An empty answer would refuse every real install as well.
  LIFTED="$(sed -n '/^account_home() {/,/^}/p' "$SCHED")"
  if [ -z "$LIFTED" ]; then
    bad "account_home" "could not lift account_home() out of $SCHED"
  else
    LOOKUP="$(env PATH="$OWN_DB_PATH" bash -c "$LIFTED"$'\n''account_home')"
    ORACLE="$(eval "printf '%s' ~$(id -un)")"
    if [ -n "$LOOKUP" ] && [ "$(cd "$LOOKUP" && pwd -P)" = "$(cd "$ORACLE" && pwd -P)" ]; then
      ok "the real user database names this account's home (the shell's own lookup agrees)"
    else
      bad "account_home" "the script's lookup gave [$LOOKUP], the shell's own lookup [$ORACLE]"
    fi
  fi
else
  echo "SKIP: 3b needs macOS (dscacheutil)"
fi

echo "=== 4. the hook installer leaves launchd alone, with each layer defeated in turn ==="
# A vault the installer treats as real: outside the directory it believes is the
# system temp dir, which TMPDIR moves for these runs.
mkdir -p "$TMP/elsewhere" "$TMP/vault4"
INSTALLER_OUT="$TMP/installer.out"   # what the hook installer printed, both streams
skip_lines() { grep -c 'skipped loading' "$INSTALLER_OUT" || true; }
# --quiet unless the caller sets QUIET_ARG to something else (empty: not quiet).
run_installer() {  # run_installer VAULT_ROOT_FOR_THE_CALLER INNER_ENV...   (inner env defeats run_sandboxed's defaults)
  H4="$TMP/h4"; rm -rf "$H4"; mkdir -p "$H4/.claude"; echo '{}' > "$H4/.claude/settings.json"
  : > "$LOG"
  # shellcheck disable=SC2086
  VAULT_ROOT="$1" run_sandboxed "$H4" env -u CLAUDECODE TMPDIR="$TMP/elsewhere" PATH="$STUB_PATH" \
    LAUNCHCTL_LOG="$LOG" "${@:2}" \
    "$LAUNCH_PY" "$HOOK_INSTALLER" --hooks-source "$REPO_ROOT/hooks.json" ${QUIET_ARG---quiet} >"$INSTALLER_OUT" 2>&1
}
# Layer 2 defeated: the user database says HOME IS the account's home. Only
# run_sandboxed stands between this run and launchd.
run_installer "$TMP/vault4" STUB_PASSWD_HOME="$TMP/h4"
if [ "$(calls)" -eq 0 ]; then ok "run_sandboxed alone keeps an exported VAULT_ROOT from reaching launchd"
else bad "run_sandboxed" "$(calls) launchctl call(s) recorded: $(tr '\n' ';' < "$LOG")"; fi
# Layer 1 defeated: the test names its vault and turns auto-GC on, as a test that
# bypasses the helper's defaults would. Only the scheduler's own check is left.
run_installer "" VAULT_ROOT="$TMP/vault4" ABS_NO_AUTO_GC=0 STUB_PASSWD_HOME="$TMP/the-account-home"
if [ "$(calls)" -eq 0 ]; then ok "the scheduler's own check alone keeps a sandbox HOME away from launchd"
else bad "scheduler check" "$(calls) launchctl call(s) recorded: $(tr '\n' ';' < "$LOG")"; fi
# bootstrap and the auto-updater run the hook installer with --quiet. A job that was
# written and not loaded must not pass without a word, so the one line that says so has
# to get through.
if [ "$(skip_lines)" -eq 1 ]; then ok "the user is told the job was written and not loaded, even under --quiet"
else bad "skipped loading" "expected one 'skipped loading' line from the hook installer under --quiet, got $(skip_lines): $(tr '\n' ' ' < "$INSTALLER_OUT")"; fi
# ...and once, not twice, when the installer is not quiet.
QUIET_ARG='' run_installer "" VAULT_ROOT="$TMP/vault4" ABS_NO_AUTO_GC=0 STUB_PASSWD_HOME="$TMP/the-account-home"
if [ "$(skip_lines)" -eq 1 ]; then ok "the line is said once without --quiet too"
else bad "skipped loading" "expected one 'skipped loading' line without --quiet, got $(skip_lines): $(tr '\n' ' ' < "$INSTALLER_OUT")"; fi
# Both defeated: the recorder does see the call, so the two runs above mean something.
run_installer "" VAULT_ROOT="$TMP/vault4" ABS_NO_AUTO_GC=0 STUB_PASSWD_HOME="$TMP/h4"
if [ "$(calls)" -gt 0 ]; then ok "control: with both layers defeated the installer does reach launchctl"
else bad "control" "no launchctl call recorded with both layers defeated, so the runs above prove nothing"; fi
if [ "$(skip_lines)" -eq 0 ]; then ok "control: nothing is said about skipping when the job was loaded"
else bad "skipped loading" "the job was loaded, yet the hook installer reported skipping: $(tr '\n' ' ' < "$INSTALLER_OUT")"; fi

echo
echo "=== summary: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
