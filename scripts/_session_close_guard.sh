#!/bin/bash
# _session_close_guard.sh - shared resource-awareness + serialization for the
# session-close path (session-end-hook.sh) and the daily-maintenance cron
# (vault-daily-maintenance.sh).
#
# SOURCE this file; do not execute it. ONE source of truth for the load gate +
# the close-cascade mutex so the two callers can never drift apart.
#
# Why this exists: on a mature Obsidian vault (10k-60k+ tracked files) the
# session-close git snapshot is the one genuinely heavy operation on the
# interactive close path - `git add` + `git commit` read and rewrite an index
# that is megabytes large. When the machine is already saturated (many parallel
# sessions, a sync client churning, a graph build running), piling that IO on at
# close can pin or crash the machine right when the user is wrapping up. The fix
# is two primitives:
#   1. a LOAD GATE so heavy work is skipped when the machine is already saturated
#      (the daily-maintenance cron catches up later), and
#   2. a close-cascade MUTEX so two concurrent closes never hammer the git index
#      at the same time.
#
# Cross-platform: the load read works on Linux (/proc/loadavg) and macOS/BSD
# (sysctl vm.loadavg). Every read FAILS OPEN - any error yields a load of 0, so
# a platform we cannot read load on (or a broken sysctl) never wedges the close;
# it simply never defers.

# --- load gate -------------------------------------------------------------
# Normalized 1-min load average per core. At or above the threshold the machine
# is saturated; skip heavy work so we do not add to the fire. Override with the
# CLOSE_MAX_LOAD_PER_CORE env var (e.g. 0 forces "always high", a huge value
# forces "never high" - both used by the test suite).
: "${CLOSE_MAX_LOAD_PER_CORE:=3.0}"

close_ncpu() {
  # Echoes the online CPU count. getconf is the most portable; fall back to
  # nproc (Linux) / sysctl (macOS); default 1 on any failure.
  local n=""
  n=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo "")
  case "$n" in ''|*[!0-9]*) n="" ;; esac
  if [ -z "$n" ]; then
    n=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 1)
  fi
  case "$n" in ''|*[!0-9]*) n=1 ;; esac
  [ "$n" -lt 1 ] && n=1
  echo "$n"
}

close_load_1min() {
  # Echoes the raw 1-min load average, cross-platform. Empty on any read error.
  local one=""
  if [ -r /proc/loadavg ]; then
    one=$(awk '{print $1}' /proc/loadavg 2>/dev/null)          # Linux
  else
    # macOS/BSD: `sysctl -n vm.loadavg` -> "{ 4.90 6.59 11.53 }" (field 2 = 1-min)
    one=$(sysctl -n vm.loadavg 2>/dev/null | awk '{print $2}')
  fi
  case "$one" in ''|*[!0-9.]*) one="" ;; esac      # keep only a plain number
  echo "$one"
}

close_load_per_core() {
  # Echoes the 1-min loadavg divided by ncpu, e.g. "0.38". 0 on any read error
  # (fail-open: a load we cannot read must never wedge the close).
  local one ncpu
  one=$(close_load_1min)
  [ -z "$one" ] && { echo "0"; return; }
  ncpu=$(close_ncpu)
  awk -v o="$one" -v n="$ncpu" 'BEGIN{ if (n < 1) n = 1; printf "%.2f", o / n }'
}

close_resource_high() {
  # Returns 0 (true) when normalized 1-min load >= CLOSE_MAX_LOAD_PER_CORE.
  local per_core
  per_core=$(close_load_per_core)
  awk -v p="$per_core" -v t="$CLOSE_MAX_LOAD_PER_CORE" 'BEGIN{ exit !((p + 0) >= (t + 0)) }'
}

# --- close-cascade mutex ---------------------------------------------------
# `set -C` (noclobber) + redirect is atomic on a local filesystem. flock(1) is
# absent on stock macOS, so we use the portable noclobber primitive. Serializes
# heavy close/maintenance passes so two never hammer the git index concurrently.
CLOSE_MUTEX="${CLOSE_MUTEX:-${TMPDIR:-/tmp}/abs-close-cascade.lock}"
_CLOSE_MUTEX_HELD=0

_close_mutex_cleanup() {
  [ "$_CLOSE_MUTEX_HELD" = "1" ] && rm -f "$CLOSE_MUTEX" 2>/dev/null
}

_close_lock_mtime() {
  # Epoch mtime of $1, cross-platform (BSD `stat -f%m` vs GNU `stat -c%Y`).
  stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null || echo ""
}

close_mutex_acquire() {
  # arg1: max seconds to wait (default 20). Returns 0 if acquired, 1 if not.
  # Reclaims a stale lock (holder PID dead, OR lock file older than 600s).
  local max_wait="${1:-20}" waited=0 held_pid now mt lock_age
  while ! (set -C; echo "$$" > "$CLOSE_MUTEX") 2>/dev/null; do
    held_pid=$(cat "$CLOSE_MUTEX" 2>/dev/null | tr -d '[:space:]')
    if [ -n "$held_pid" ] && printf '%s' "$held_pid" | grep -qE '^[0-9]+$' \
       && ! kill -0 "$held_pid" 2>/dev/null; then
      rm -f "$CLOSE_MUTEX" 2>/dev/null; continue        # dead holder -> reclaim
    fi
    now=$(date +%s)
    mt=$(_close_lock_mtime "$CLOSE_MUTEX"); [ -z "$mt" ] && mt="$now"
    lock_age=$(( now - mt ))
    if [ "$lock_age" -gt 600 ]; then
      rm -f "$CLOSE_MUTEX" 2>/dev/null; continue          # proven-orphan -> reclaim
    fi
    [ "$waited" -ge "$max_wait" ] && return 1
    sleep 2; waited=$((waited + 2))
  done
  _CLOSE_MUTEX_HELD=1
  trap _close_mutex_cleanup EXIT
  return 0
}

close_mutex_release() {
  _close_mutex_cleanup
  _CLOSE_MUTEX_HELD=0
  trap - EXIT
}
