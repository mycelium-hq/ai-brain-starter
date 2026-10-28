#!/usr/bin/env bash
# exit-contract: NOT-A-CHECKER -- installs a launchd or cron agent; a
#   one-shot installer

# install-vault-daily-maintenance.sh
#
# One-shot installer for the daily vault-maintenance launchd agent on macOS,
# and for the 30-minute disk-pressure check beside it. Substitutes each template
# plist with operator-specific paths, copies it to ~/Library/LaunchAgents/, and
# loads it. The daily job runs at 04:30 local, at low CPU + IO priority, and is
# itself load-gated + mutex-serialized. The check runs dev-build-reclaim.py only,
# which exits at once while the disk has room.
#
# Usage:
#   ./scripts/install-vault-daily-maintenance.sh /abs/path/to/vault
#
# Idempotent: re-running unloads each old plist before writing the new one.
#
# Calls launchctl only when $HOME is the home directory the user database records
# for this uid. launchd keys a job by label for the whole account, so under any
# other HOME (a test, a throwaway checkout) `launchctl unload` and `load` would
# replace the account's real job. There the plist is still written, and one line
# says that loading was skipped.
#
# Requires: macOS, launchctl, /bin/bash. Linux users: add a cron line instead
# (see the comment block in templates/launchd/com.abs.vault-daily-maintenance.plist.template).
set -euo pipefail

VAULT_ROOT=""
QUIET=0
for arg in "$@"; do
    case "$arg" in
        --quiet) QUIET=1 ;;
        *) [[ -z "$VAULT_ROOT" ]] && VAULT_ROOT="$arg" ;;
    esac
done
say() { [[ $QUIET -eq 1 ]] || echo "$@"; }

if [[ -z "$VAULT_ROOT" ]]; then
    echo "usage: $0 /abs/path/to/vault [--quiet]" >&2
    exit 2
fi
if [[ ! -d "$VAULT_ROOT" ]]; then
    echo "vault root does not exist: $VAULT_ROOT" >&2
    exit 2
fi

# Opt-OUT only (MYC-2363). This job is what keeps the machine from only ever
# getting fuller, so nothing may gate its VALUE behind an opt-in — an opt-in
# default leaves every fresh install without any GC at all, which is the bug.
# A power user who drives reclaim by hand sets ABS_NO_AUTO_GC=1.
if [[ "${ABS_NO_AUTO_GC:-0}" == "1" ]]; then
    say "[install-vault-daily-maintenance] skipped (ABS_NO_AUTO_GC=1)"
    exit 0
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$HOME/.local/state/ai-brain-starter"

# ---- Linux / non-macOS: a cron line, same job, same gates ------------------
# Without this branch the whole daily pass is macOS-only, so a Linux install
# gets no GC at all while looking installed.
if [[ "$(uname -s)" != "Darwin" ]]; then
    if ! command -v crontab >/dev/null 2>&1; then
        say "[install-vault-daily-maintenance] no launchd and no crontab — daily maintenance NOT scheduled."
        say "  Run it from your own scheduler: bash $REPO_ROOT/scripts/vault-daily-maintenance.sh --vault-root $VAULT_ROOT"
        exit 0
    fi
    MARKER="# ai-brain-starter: vault-daily-maintenance"
    LINE="30 4 * * * /bin/bash $REPO_ROOT/scripts/vault-daily-maintenance.sh --vault-root '$VAULT_ROOT' >/dev/null 2>&1 $MARKER"
    RECLAIM_MARKER="# ai-brain-starter: dev-build-reclaim"
    RECLAIM_LINE="*/30 * * * * nice -n 10 /usr/bin/env python3 '$REPO_ROOT/scripts/dev-build-reclaim.py' --auto-gc >>'$LOG_DIR/dev-build-reclaim.out.log' 2>&1 $RECLAIM_MARKER"
    mkdir -p "$LOG_DIR"
    # Idempotent: drop any previous lines we installed, then append the current
    # ones, so a moved repo or vault re-points instead of accumulating entries.
    ( crontab -l 2>/dev/null | grep -vF -e "$MARKER" -e "$RECLAIM_MARKER" || true
      echo "$LINE"; echo "$RECLAIM_LINE" ) | crontab -
    say "[install-vault-daily-maintenance] cron entries installed (daily 04:30 local; disk check every 30 minutes)"
    say "Stop: crontab -l | grep -vF -e '$MARKER' -e '$RECLAIM_MARKER' | crontab -"
    exit 0
fi

TEMPLATES="$REPO_ROOT/templates/launchd"
TARGET_DIR="$HOME/Library/LaunchAgents"
JOBS=(com.abs.vault-daily-maintenance com.abs.dev-build-reclaim)

for job in "${JOBS[@]}"; do
    if [[ ! -f "$TEMPLATES/$job.plist.template" ]]; then
        echo "template missing at $TEMPLATES/$job.plist.template" >&2
        exit 2
    fi
done

mkdir -p "$TARGET_DIR" "$LOG_DIR"

# The home directory the user database records for this uid. Deliberately not read
# from $HOME: $HOME is the thing a sandbox overrides.
account_home() {
    dscacheutil -q user -a uid "$(id -u)" 2>/dev/null | sed -n '/^dir: /{s/^dir: //p;q;}'
}
# True when both name one existing directory, however each is spelled (a symlink or
# a trailing slash is not a different home). An empty or missing one is not a match.
same_dir() {
    local a b
    [[ -n "$1" && -n "$2" ]] || return 1
    a="$(cd "$1" 2>/dev/null && pwd -P)" || return 1
    b="$(cd "$2" 2>/dev/null && pwd -P)" || return 1
    [[ "$a" == "$b" ]]
}
LOAD_JOB=0
if same_dir "$HOME" "$(account_home || true)"; then
    LOAD_JOB=1
fi

for job in "${JOBS[@]}"; do
    target="$TARGET_DIR/$job.plist"
    if [[ -f "$target" && $LOAD_JOB -eq 1 ]]; then
        say "[install-vault-daily-maintenance] unloading existing $job..."
        launchctl unload "$target" 2>/dev/null || true
    fi
    # Substitute placeholders. sed -i differs across macOS / GNU; use a temp file.
    sed \
        -e "s|{{REPO_ROOT}}|$REPO_ROOT|g" \
        -e "s|{{VAULT_ROOT}}|$VAULT_ROOT|g" \
        -e "s|{{LOG_DIR}}|$LOG_DIR|g" \
        "$TEMPLATES/$job.plist.template" > "$target"
    say "[install-vault-daily-maintenance] wrote $target"
    if [[ $LOAD_JOB -eq 1 ]]; then
        launchctl load "$target"
    fi
done
if [[ $LOAD_JOB -eq 0 ]]; then
    # Printed even under --quiet, and on stderr: the hook installer runs this with --quiet
    # and shows a finished child's stderr but never its stdout. A job that was written and
    # not loaded is not a success.
    echo "[install-vault-daily-maintenance] skipped loading ${JOBS[*]} in $TARGET_DIR: HOME is not this account's home directory, and launchd would replace the account's real jobs" >&2
    exit 0
fi
say "[install-vault-daily-maintenance] loaded (daily at 04:30 local; disk check every 30 minutes)"
say
say "Logs:           $LOG_DIR/{vault-daily-maintenance,dev-build-reclaim}.{out,err}.log"
say "Run now (test): bash $REPO_ROOT/scripts/vault-daily-maintenance.sh --vault-root $VAULT_ROOT --force"
say "Stop:           launchctl unload each $TARGET_DIR/<job>.plist  (or ABS_NO_AUTO_GC=1 before re-install)"
