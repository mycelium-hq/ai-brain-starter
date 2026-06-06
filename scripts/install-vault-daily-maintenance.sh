#!/usr/bin/env bash
# install-vault-daily-maintenance.sh
#
# One-shot installer for the daily vault-maintenance launchd agent on macOS.
# Substitutes the template plist with operator-specific paths, copies it to
# ~/Library/LaunchAgents/, and loads it. The job runs once a day at 04:30 local,
# at low CPU + IO priority, and is itself load-gated + mutex-serialized.
#
# Usage:
#   ./scripts/install-vault-daily-maintenance.sh /abs/path/to/vault
#
# Idempotent: re-running unloads the old plist before writing the new one.
#
# Requires: macOS, launchctl, /bin/bash. Linux users: add a cron line instead
# (see the comment block in templates/launchd/com.abs.vault-daily-maintenance.plist.template).
set -euo pipefail

VAULT_ROOT="${1:-}"
if [[ -z "$VAULT_ROOT" ]]; then
    echo "usage: $0 /abs/path/to/vault" >&2
    exit 2
fi
if [[ ! -d "$VAULT_ROOT" ]]; then
    echo "vault root does not exist: $VAULT_ROOT" >&2
    exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$REPO_ROOT/templates/launchd/com.abs.vault-daily-maintenance.plist.template"
TARGET_DIR="$HOME/Library/LaunchAgents"
TARGET_FILE="$TARGET_DIR/com.abs.vault-daily-maintenance.plist"
LOG_DIR="$HOME/.local/state/ai-brain-starter"

if [[ ! -f "$TEMPLATE" ]]; then
    echo "template missing at $TEMPLATE" >&2
    exit 2
fi

mkdir -p "$TARGET_DIR" "$LOG_DIR"

if [[ -f "$TARGET_FILE" ]]; then
    echo "[install-vault-daily-maintenance] unloading existing plist..."
    launchctl unload "$TARGET_FILE" 2>/dev/null || true
fi

# Substitute placeholders. sed -i differs across macOS / GNU; use a temp file.
sed \
    -e "s|{{REPO_ROOT}}|$REPO_ROOT|g" \
    -e "s|{{VAULT_ROOT}}|$VAULT_ROOT|g" \
    -e "s|{{LOG_DIR}}|$LOG_DIR|g" \
    "$TEMPLATE" > "$TARGET_FILE"

echo "[install-vault-daily-maintenance] wrote $TARGET_FILE"
launchctl load "$TARGET_FILE"
echo "[install-vault-daily-maintenance] loaded (runs daily at 04:30 local)"
echo
echo "Logs:           $LOG_DIR/vault-daily-maintenance.{out,err}.log"
echo "Run now (test): bash $REPO_ROOT/scripts/vault-daily-maintenance.sh --vault-root $VAULT_ROOT --force"
echo "Stop:           launchctl unload $TARGET_FILE"
