#!/bin/bash
# vault-daily-maintenance.sh - heavy vault maintenance, kept OFF the interactive
# session-close path.
#
# Two jobs:
#   1. RECONCILE (data safety): re-run the aggregators and commit any session /
#      decision / captures files a session-close left uncommitted. The close
#      hook (session-end-hook.sh) DEFERS its git snapshot when the machine is
#      saturated or a sibling close holds the cascade mutex; this is the catch-up
#      that snapshots that work within a day so nothing is lost.
#   2. HEAVY HYGIENE (best effort): the full-tree / git-log-walking scripts the
#      substrate ships but that are too heavy to run at every close -
#      drift-detection, check-rule-conflicts --scan-all, passive-capture. They
#      run here once a day, resource-gated, serialized, and at low IO/CPU
#      priority (see templates/launchd/com.abs.vault-daily-maintenance.plist).
#
# Resource-aware: shares the load gate + close-cascade mutex with the close hook
# via _session_close_guard.sh. If 1-min loadavg/core >= CLOSE_MAX_LOAD_PER_CORE
# (default 3.0) it skips the heavy work and logs "deferred - high load"; the next
# daily run (or a --force run) catches up. Serialized on the same mutex the close
# hook uses, so a heavy daily pass never overlaps a live close cascade.
#
# Usage:
#   vault-daily-maintenance.sh --vault-root /path/to/vault          # load-gated
#   VAULT_ROOT=/path/to/vault vault-daily-maintenance.sh            # env form
#   vault-daily-maintenance.sh --vault-root /path --force           # ignore load gate
#   vault-daily-maintenance.sh --vault-root /path --reconcile-only  # skip heavy hygiene
#
# Exit codes: 0 = ran (or cleanly deferred); 1 only on its own setup error
# (missing vault root). Individual maintenance steps never abort the run.

set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

FORCE=0
RECONCILE_ONLY=0
VAULT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=1 ;;
    --reconcile-only) RECONCILE_ONLY=1 ;;
    --vault-root) shift; VAULT="${1:-}" ;;
    --vault-root=*) VAULT="${1#--vault-root=}" ;;
    *) ;;
  esac
  shift
done
[ -z "$VAULT" ] && VAULT="${VAULT_ROOT:-}"

if [ -z "$VAULT" ] || [ ! -d "$VAULT" ]; then
  echo "vault-daily-maintenance: set --vault-root PATH or VAULT_ROOT env to an existing vault" >&2
  exit 1
fi

# Shared load gate + close-cascade mutex. Fail-open if the guard is absent.
CLOSE_GUARD="$SCRIPT_DIR/_session_close_guard.sh"
if [ -f "$CLOSE_GUARD" ]; then
  # shellcheck source=/dev/null
  . "$CLOSE_GUARD"
else
  close_resource_high() { return 1; }
  close_load_per_core() { echo "0"; }
  close_mutex_acquire() { return 0; }
  close_mutex_release() { :; }
fi

# Auto-detect the Meta folder via the shared resolver (prefers the variant
# containing a known human-memory subfolder), like the close hook. See
# scripts/_meta_resolver.py.
META_DIR="$(python3 "$SCRIPT_DIR/_meta_resolver.py" "$VAULT" Sessions Decisions 2>/dev/null || true)"
[ -z "$META_DIR" ] && META_DIR="$VAULT/Meta"

LOG_DIR="$META_DIR/logs"
mkdir -p "$LOG_DIR" 2>/dev/null
LOG="$LOG_DIR/vault-daily-maintenance.log"

log() { printf '%s\n' "$*"; printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG" 2>/dev/null; }

LOAD_PER_CORE=$(close_load_per_core)
log "=== vault-daily-maintenance @ $(date -u +%Y-%m-%dT%H:%M:%SZ) (load=${LOAD_PER_CORE}/core, force=$FORCE, reconcile_only=$RECONCILE_ONLY) ==="

# --- ensure Claude Code memory lives in the vault (idempotent self-heal) ----
# Installs created before the memory-symlink fix have their memory stranded in
# ~/.claude/projects/<key>/memory/, invisible in Obsidian. Re-link it into the
# vault so the brain accumulates where the user can see it. Near-free + safe to
# run daily; runs BEFORE the load gate because it is trivially cheap and the
# durability it restores matters more than the few stats it costs.
LINK_MEM="$SCRIPT_DIR/link-agent-memory.py"
if [ -f "$LINK_MEM" ]; then
  if python3 "$LINK_MEM" --vault "$VAULT" --quiet >> "$LOG" 2>&1; then
    log "agent-memory link verified -> vault"
  else
    log "WARNING: agent-memory link failed (memory may strand in ~/.claude/); see log above"
  fi
fi

# --- load gate -------------------------------------------------------------
if [ $FORCE -eq 0 ] && close_resource_high; then
  log "DEFERRED - high load (${LOAD_PER_CORE}/core >= ${CLOSE_MAX_LOAD_PER_CORE:-3.0}). Next daily run will catch up."
  exit 0
fi

# --- serialize against a live close cascade --------------------------------
if ! close_mutex_acquire 60; then
  log "DEFERRED - a close cascade (or another maintenance pass) holds the mutex. Next daily run will catch up."
  exit 0
fi
log "acquired close-cascade mutex ($$)"

run() {
  # run <label> <command...> - runs at low priority, logs a tail, never aborts.
  local label="$1"; shift
  local out rc
  out=$(nice -n 10 "$@" 2>&1); rc=$?
  printf '%s\n' "$out" | tail -3
  log "[$label] rc=$rc :: $(printf '%s\n' "$out" | tail -1)"
}

# === RECONCILE (data safety): aggregators + commit deferred close artifacts ===
AGG_SESSIONS="$SCRIPT_DIR/aggregate-sessions.py"
AGG_DECISIONS="$SCRIPT_DIR/aggregate-decisions.py"
[ -f "$AGG_SESSIONS" ]  && VAULT_ROOT="$VAULT" run "aggregate-sessions"  /usr/bin/env python3 "$AGG_SESSIONS"
[ -f "$AGG_DECISIONS" ] && VAULT_ROOT="$VAULT" run "aggregate-decisions" /usr/bin/env python3 "$AGG_DECISIONS"

# Commit any close artifacts left uncommitted by a load-deferred close. Targeted
# paths only - NEVER `git add -A` (vaults are commonly 10k-60k+ files).
if [ -d "$VAULT/.git" ] || git -C "$VAULT" rev-parse --git-dir >/dev/null 2>&1; then
  WAITED=0
  while [ -f "$VAULT/.git/index.lock" ] && [ $WAITED -lt 60 ]; do sleep 2; WAITED=$((WAITED + 2)); done
  if [ ! -f "$VAULT/.git/index.lock" ]; then
    PATHS=()
    for p in "$META_DIR/Sessions" "$META_DIR/Decisions" \
             "$META_DIR/Last Session.md" "$META_DIR/Decision Log.md" \
             "$META_DIR/Session Captures.md"; do
      [ -e "$p" ] && PATHS+=("$p")
    done
    if [ ${#PATHS[@]} -gt 0 ]; then
      ( cd "$VAULT" && git add -- "${PATHS[@]}" 2>>"$LOG" \
          && { git diff --cached --quiet \
               || git commit -m "maint: reconcile deferred session-close $(date +%Y-%m-%d)" >/dev/null 2>>"$LOG"; } )
      log "[reconcile-commit] staged ${#PATHS[@]} close-artifact path(s)"
    fi
  else
    log "[reconcile-commit] SKIPPED - git index.lock held >60s"
  fi
fi

if [ $RECONCILE_ONLY -eq 1 ]; then
  close_mutex_release
  log "=== reconcile-only COMPLETE @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  exit 0
fi

# === HEAVY HYGIENE (best effort, low priority, never abort) ==================
# The full-tree / git-log-walking scripts that are too heavy for the close path.
# Each runs only if present and routes VAULT_ROOT to the user's vault.

# Drift detection (30-day git log walk; needs a git-tracked vault).
DRIFT="$SCRIPT_DIR/drift-detection.py"
if [ -f "$DRIFT" ] && { [ -d "$VAULT/.git" ] || git -C "$VAULT" rev-parse --git-dir >/dev/null 2>&1; }; then
  VAULT_ROOT="$VAULT" run "drift-detection" /usr/bin/env python3 "$DRIFT"
fi

# Rule-conflicts keyword scan (full-tree --scan-all).
RULECONF="$SCRIPT_DIR/check-rule-conflicts.py"
[ -f "$RULECONF" ] && VAULT_ROOT="$VAULT" run "check-rule-conflicts" /usr/bin/env python3 "$RULECONF" --scan-all

# Passive capture of the day's content (full-tree scan of today's transcripts).
PASSIVE="$SCRIPT_DIR/passive-capture.py"
[ -f "$PASSIVE" ] && VAULT_ROOT="$VAULT" run "passive-capture" /usr/bin/env python3 "$PASSIVE" --scan-today

# Vault-relocation watchdog (mode 2): scan the install's recorded move(s) for drift
# back to an old path (executed residuals / recreated old dir / missing vault root).
# Heavy (auto-discovers ~/dev + the vault at canonical ref) so it lives here, not on
# SessionStart. Writes the verdict cache the SessionStart surfacer reads; a no-op when
# no relocation was ever recorded. rc=1 (ALARM) is logged, never fatal (set +e + run).
RELOCWATCH="$SCRIPT_DIR/relocate-sweep.py"
[ -f "$RELOCWATCH" ] && run "relocate-watch" /usr/bin/env python3 "$RELOCWATCH" --watch

close_mutex_release
log "=== vault-daily-maintenance COMPLETE @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
exit 0
