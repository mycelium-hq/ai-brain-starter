#!/usr/bin/env bash
# Test the resource-aware session-close: the close hook (session-end-hook.sh)
# DEFERS its aggregators + git snapshot when the machine is saturated or a
# sibling close holds the cascade mutex, and the daily-maintenance cron
# (vault-daily-maintenance.sh) reconciles (commits) the deferred close later.
#
# Why this exists: on a mature vault the close-time git snapshot can pin/crash a
# machine that is already saturated. The fix is a load gate + close-cascade mutex
# shared via _session_close_guard.sh, plus a daily cron that catches up so a
# deferred close loses nothing.
#
# Assertions:
#   1. _session_close_guard.sh exists, sources clean, defines the 4 functions.
#   2. Load gate is deterministic: threshold 0 => high (defer); huge => low (run).
#   3. Mutex: acquire / contended-acquire-times-out / release-then-reacquire /
#      stale-PID reclaim.
#   4. session-end-hook.sh sources the guard and carries the CLOSE_DEFER gate.
#   5. NORMAL close (load below threshold) COMMITS the session file.
#   6. DEFERRED close (forced high load) does NOT commit + still cleans the marker.
#   7. vault-daily-maintenance.sh --reconcile-only --force COMMITS the deferred
#      session file (the catch-up).
#
# Self-contained: temp git vaults + temp HOME, cleaned on exit. Exit 0 = pass.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GUARD="$REPO_ROOT/scripts/_session_close_guard.sh"
HOOK="$REPO_ROOT/scripts/session-end-hook.sh"
MAINT="$REPO_ROOT/scripts/vault-daily-maintenance.sh"

fail() { echo "FAIL: $1" >&2; exit 1; }

for f in "$GUARD" "$HOOK" "$MAINT"; do
  [ -f "$f" ] || fail "missing required file: $f"
  bash -n "$f" 2>/dev/null || fail "bash -n failed: $f"
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ─── Assertion 1: guard sources clean + defines the 4 functions ────────────
# shellcheck source=/dev/null
( . "$GUARD"
  for fn in close_resource_high close_load_per_core close_mutex_acquire close_mutex_release; do
    command -v "$fn" >/dev/null 2>&1 || { echo "missing fn $fn" >&2; exit 1; }
  done ) || fail "guard did not define all 4 functions"
echo "PASS: guard sources clean and defines close_{resource_high,load_per_core,mutex_acquire,mutex_release}"

# ─── Assertion 2: load gate is deterministic ───────────────────────────────
( . "$GUARD"
  CLOSE_MAX_LOAD_PER_CORE=0
  close_resource_high || { echo "thr=0 should be HIGH" >&2; exit 1; }
  CLOSE_MAX_LOAD_PER_CORE=99999
  close_resource_high && { echo "thr=99999 should be low" >&2; exit 1; }
  exit 0 ) || fail "load gate threshold logic wrong"
echo "PASS: load gate defers at threshold 0 and runs at threshold 99999"

# ─── Assertion 3: mutex acquire / contend / release / stale-reclaim ─────────
( . "$GUARD"
  export CLOSE_MUTEX="$TMP/mutex3.lock"
  close_mutex_acquire 2 || { echo "acquire#1 failed" >&2; exit 1; }
  # A child trying to acquire while we hold it (live holder) must time out.
  ( . "$GUARD"; export CLOSE_MUTEX="$TMP/mutex3.lock"
    if close_mutex_acquire 2; then echo "contended acquire wrongly succeeded" >&2; exit 1; fi )
  contend_rc=$?
  [ $contend_rc -eq 0 ] || { echo "contended-acquire subshell reported failure" >&2; exit 1; }
  close_mutex_release
  close_mutex_acquire 2 || { echo "re-acquire after release failed" >&2; exit 1; }
  close_mutex_release
  # Stale reclaim: a dead PID in the lock must be reclaimed.
  echo "999999" > "$CLOSE_MUTEX"
  close_mutex_acquire 2 || { echo "stale-PID reclaim failed" >&2; exit 1; }
  close_mutex_release
  exit 0 ) || fail "mutex acquire/contend/release/stale-reclaim wrong"
echo "PASS: mutex acquires, times out on a live holder, re-acquires, reclaims a stale lock"

# ─── Assertion 4: hook wires the guard + the CLOSE_DEFER gate ───────────────
grep -q '_session_close_guard.sh' "$HOOK" || fail "session-end-hook.sh does not source _session_close_guard.sh"
grep -q 'CLOSE_DEFER' "$HOOK" || fail "session-end-hook.sh has no CLOSE_DEFER resource gate"
grep -q 'close_mutex_acquire' "$HOOK" || fail "session-end-hook.sh does not acquire the close-cascade mutex"
echo "PASS: session-end-hook.sh sources the guard and carries the CLOSE_DEFER gate + mutex"

# ─── Shared helper: build a minimal git vault with one untracked session file ─
make_vault() {
  local v="$1"
  mkdir -p "$v/⚙️ Meta/Sessions"
  ( cd "$v"
    git init --quiet --initial-branch=master
    git config user.email "t@example.com"; git config user.name "t"
    echo "# vault" > README.md
    git add README.md && git commit --quiet -m "init" )
  # The model's captured session file: untracked (a new write this close).
  printf -- '---\ntype: session\n---\n# session\nbody\n' \
    > "$v/⚙️ Meta/Sessions/$(date +%Y-%m-%d)T00-00-main.md"
}

run_hook() {  # $1=vault $2=home $3=max_load
  local v="$1" home="$2" maxload="$3" sid="sid$$_${RANDOM}"
  local sf
  sf="$(ls "$v/⚙️ Meta/Sessions/"*.md | head -1)"
  mkdir -p "$home/.claude"
  printf '{"session_file":"%s","is_trivial":false}\n' "$sf" \
    > "$home/.claude/.closing-signal-$sid.json"
  printf '{"session_id":"%s","transcript_path":""}' "$sid" | \
    HOME="$home" VAULT_ROOT="$v" CLOSE_MAX_LOAD_PER_CORE="$maxload" \
    CLOSE_MUTEX="$home/close.lock" bash "$HOOK" >/dev/null 2>&1
  # Echo whether the marker was cleaned (0 = cleaned).
  [ ! -f "$home/.claude/.closing-signal-$sid.json" ] && echo "marker-cleaned" || echo "marker-left"
}

commits_with() { git -C "$1" log --oneline 2>/dev/null | grep -c "$2"; }

# ─── Assertion 5: NORMAL close commits the session file ────────────────────
VN="$TMP/vault-normal"; make_vault "$VN"
MC="$(run_hook "$VN" "$TMP/home-normal" 99999)"
[ "$MC" = "marker-cleaned" ] || fail "normal close did not clean the marker ($MC)"
[ "$(commits_with "$VN" 'session:')" -ge 1 ] || fail "normal close did NOT create a session commit"
echo "PASS: normal close (load below threshold) commits the session file + cleans the marker"

# ─── Assertion 6: DEFERRED close does NOT commit, still cleans the marker ──
VD="$TMP/vault-defer"; make_vault "$VD"
BEFORE="$(commits_with "$VD" '.')"
MC="$(run_hook "$VD" "$TMP/home-defer" 0)"   # threshold 0 => always "high" => defer
[ "$MC" = "marker-cleaned" ] || fail "deferred close did not clean the marker ($MC)"
AFTER="$(commits_with "$VD" '.')"
[ "$BEFORE" = "$AFTER" ] || fail "deferred close created a commit under high load (before=$BEFORE after=$AFTER)"
[ "$(commits_with "$VD" 'session:')" -eq 0 ] || fail "deferred close created a session commit under high load"
echo "PASS: deferred close (forced high load) skips the snapshot, leaves work on disk, cleans the marker"

# ─── Assertion 7: daily-maintenance reconcile commits the deferred close ───
# Heavy hygiene skipped via --reconcile-only so this stays fast + deterministic.
bash "$MAINT" --vault-root "$VD" --reconcile-only --force >/dev/null 2>&1
[ "$(commits_with "$VD" 'maint: reconcile')" -ge 1 ] \
  || fail "daily-maintenance --reconcile-only did NOT commit the deferred session file"
echo "PASS: daily-maintenance --reconcile-only --force commits the deferred close (catch-up)"

# ─── Assertion 8: daily-maintenance itself defers under high load ──────────
# Force high load via env so the gate fires regardless of the test host's load.
OUT="$(CLOSE_MAX_LOAD_PER_CORE=0 bash "$MAINT" --vault-root "$VD" --reconcile-only 2>&1)"
echo "$OUT" | grep -q "DEFERRED - high load" \
  || fail "daily-maintenance did not defer under forced high load"
echo "PASS: daily-maintenance defers under high load (no --force)"

echo
echo "All assertions passed. Resource-aware session-close invariant holds."
