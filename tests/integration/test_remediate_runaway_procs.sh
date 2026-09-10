#!/usr/bin/env bash
# Test: remediate-runaway-procs.py — the CLASS 2 "stuck hook process" reaper.
#
# Bug class: a SessionStart hook that walks a large corpus piled up several
# concurrent multi-minute copies (live parent, comm "Python") and froze the
# machine (2026-06-05, load 36). The orphan-`yes` reaper (CLASS 1) never saw
# them. CLASS 2 reaps a stuck ~/.claude/hooks/ python process, gated by path
# scope + a dual age-AND-cpu threshold so a fast/idle/non-hook process is
# never touched.
#
# The reap decision is factored into the pure function `_should_reap_hook`,
# so this pos+neg control test exercises every branch DETERMINISTICALLY
# without spawning or killing any real process.
#
# Assertions:
#   POSITIVE control:
#     1. A high-age, high-CPU python process under ~/.claude/hooks/ IS reaped.
#   NEGATIVE controls (each must NOT be reaped):
#     2. Same process but too young (age < min_age).
#     3. Same process but low CPU (cpu < min_cpu).
#     4. A high-age, high-CPU python process NOT under the hooks dir.
#     5. A high-age, high-CPU process under the hooks dir but NOT python.
#     6. The reaper's own pid (never reaps itself).
#   END-TO-END:
#     7. RUNAWAY_REMEDIATE_BYPASS=1 -> no-op, valid JSON, continue:true.
#     8. main() with no matching process emits valid continue JSON (no crash).
#
# Self-contained. Exit 0 = pass, exit 1 = fail.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$REPO_ROOT/hooks/remediate-runaway-procs.py"
if [ ! -f "$HOOK" ]; then
  echo "FAIL: reaper hook not found at $HOOK" >&2
  exit 1
fi

# --- Assertions 1-6: pure-predicate pos/neg control ----------------------
HOOK="$HOOK" python3 - <<'PY'
import importlib.util
import os
import sys

hook_path = os.environ["HOOK"]
spec = importlib.util.spec_from_file_location("reaper_under_test", hook_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

HOOKS = os.path.expanduser("~/.claude/hooks/")
hook_cmd = f"python3 {HOOKS}scan-prior-sessions-for-secrets.py"
common = dict(hooks_dir=HOOKS, self_pid=999999, min_age=12.0, min_cpu=50.0)

failures = []

def check(label, expected, **kw):
    got = mod._should_reap_hook(**kw)
    if got is not expected:
        failures.append(f"{label}: expected {expected}, got {got}")
    else:
        print(f"PASS: {label} -> {got}")

# 1. POSITIVE: stuck hook process — high age + high cpu + hooks path + python.
check("positive: stuck hook proc reaped", True,
      command=hook_cmd, age_min=20.0, cpu=80.0, pid=12345, **common)

# 2. NEG: too young (age < min_age).
check("negative: young hook proc not reaped", False,
      command=hook_cmd, age_min=2.0, cpu=80.0, pid=12345, **common)

# 3. NEG: low cpu (cpu < min_cpu) — a bounded/idle hook is left alone.
check("negative: low-cpu hook proc not reaped", False,
      command=hook_cmd, age_min=20.0, cpu=10.0, pid=12345, **common)

# 4. NEG: not under the hooks dir (a user program / busy compiler).
check("negative: non-hook path not reaped", False,
      command="python3 /usr/local/bin/some_user_script.py",
      age_min=20.0, cpu=80.0, pid=12345, **common)

# 5. NEG: under hooks dir but not python (e.g. a shell hook).
check("negative: non-python hook proc not reaped", False,
      command=f"bash {HOOKS}rotate-logs.sh",
      age_min=20.0, cpu=80.0, pid=12345, **common)

# 6. NEG: the reaper's own pid is never reaped.
check("negative: self pid not reaped", False,
      command=hook_cmd, age_min=20.0, cpu=80.0, pid=999999, **common)

if failures:
    print("PREDICATE CONTROL FAILED:", file=sys.stderr)
    for f in failures:
        print("  " + f, file=sys.stderr)
    sys.exit(1)
print("All predicate pos/neg controls passed.")
PY

echo "PASS: _should_reap_hook pos+neg control (assertions 1-6)"

# --- Assertions 9-19: CLASS 3 orphaned-session-helper pos/neg control -----
# Bug class: the 2026-09-09 melt (load 172 on 10 cores, swap 97.8% full).
# Helpers whose session had died sat at PPID 1 holding hundreds of MB. CLASS 1
# missed them (comm not in RUNAWAY_PROC_NAMES); CLASS 2 missed them (not under
# hooks/). Assertion 14 is the one that matters most: a launchd-managed daemon
# is PPID == 1 BY DESIGN, so without that exclusion this reaper would kill the
# user's own scheduled agents every session.
HOOK="$HOOK" python3 - <<'PY2'
import importlib.util
import os
import sys

spec = importlib.util.spec_from_file_location("reaper_under_test", os.environ["HOOK"])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

CLAUDE = os.path.expanduser("~/.claude/")
HOOKS = os.path.expanduser("~/.claude/hooks/")
helper_cmd = f"{CLAUDE}whatsapp-mcp/whatsapp-bridge/bin/whatsapp-bridge"
common = dict(claude_dir=CLAUDE, hooks_dir=HOOKS, self_pid=999999,
              min_age=15.0, launchd_pids=set())

failures = []

def check(label, expected, **kw):
    got = mod._should_reap_orphan_helper(**kw)
    if got is not expected:
        failures.append(f"{label}: expected {expected}, got {got}")
    else:
        print(f"PASS: {label} -> {got}")

# 9. POSITIVE: orphaned session helper under ~/.claude/, old, not launchd.
check("positive: orphaned session helper reaped", True,
      command=helper_cmd, age_min=300.0, ppid=1, pid=12345, **common)

# 10. NEG: live parent — the session that owns it is still running.
check("negative: live-parent helper not reaped", False,
      command=helper_cmd, age_min=300.0, ppid=4242, pid=12345, **common)

# 11. NEG: not under ~/.claude/ — a real user program that happens to be PPID 1.
check("negative: user program outside ~/.claude not reaped", False,
      command="/opt/homebrew/bin/postgres -D /usr/local/var/postgres",
      age_min=300.0, ppid=1, pid=12345, **common)

# 12. NEG: under hooks/ — CLASS 2 owns that path, with its own CPU gate.
check("negative: hooks-dir process left to CLASS 2", False,
      command=f"{HOOKS}scan-prior-sessions-for-secrets.py --flag",
      age_min=300.0, ppid=1, pid=12345, **common)

# 13. NEG: too young — never a helper still mid-handshake.
check("negative: young helper not reaped", False,
      command=helper_cmd, age_min=3.0, ppid=1, pid=12345, **common)

# 14. NEG: launchd-managed. PPID == 1 BY DESIGN. THE false positive.
check("negative: launchd-managed daemon not reaped", False,
      command=helper_cmd, age_min=300.0, ppid=1, pid=12345,
      claude_dir=CLAUDE, hooks_dir=HOOKS, self_pid=999999,
      min_age=15.0, launchd_pids={12345})

# 15. NEG: launchctl unreadable -> cannot distinguish -> reap nothing.
check("negative: unknown launchd state fails closed", False,
      command=helper_cmd, age_min=300.0, ppid=1, pid=12345,
      claude_dir=CLAUDE, hooks_dir=HOOKS, self_pid=999999,
      min_age=15.0, launchd_pids=None)

# 16. NEG: the reaper's own pid is never reaped.
check("negative: self pid not reaped", False,
      command=helper_cmd, age_min=300.0, ppid=1, pid=999999, **common)

# 17-19. NEG: THE REGRESSION. Scope is argv[0], never a command-line substring.
# Found by dry-running the predicate against a real machine's process table:
# a command-line test selected 3 live processes, ALL false positives, because
# every Claude Code tool shell sources a snapshot from ~/.claude/shell-snapshots/.
# One of them was a detached compile in a worktree that another session was
# monitoring — reaping it would have destroyed real work.
check("negative: tool shell that merely SOURCES from ~/.claude not reaped", False,
      command=f"/bin/zsh -c source {CLAUDE}shell-snapshots/snapshot-zsh-1789012345.sh",
      age_min=300.0, ppid=1, pid=12345, **common)

check("negative: detached build mentioning ~/.claude not reaped", False,
      command=f"bash -c cd /tmp/some-worktree && source {CLAUDE}shell-snapshots/s.sh && cargo test",
      age_min=300.0, ppid=1, pid=12345, **common)

check("negative: a shell living under ~/.claude is still a wrapper", False,
      command=f"{CLAUDE}bin/bash -c 'sleep 1'",
      age_min=300.0, ppid=1, pid=12345, **common)

if failures:
    print("CLASS 3 PREDICATE CONTROL FAILED:", file=sys.stderr)
    for f in failures:
        print("  " + f, file=sys.stderr)
    sys.exit(1)
print("All CLASS 3 predicate pos/neg controls passed.")
PY2

echo "PASS: _should_reap_orphan_helper pos+neg control (assertions 9-19)"

# --- Assertion 7: bypass env -> no-op, valid JSON -------------------------
OUT="$(RUNAWAY_REMEDIATE_BYPASS=1 printf '{}' | RUNAWAY_REMEDIATE_BYPASS=1 python3 "$HOOK" 2>/dev/null)"
echo "$OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("continue") is True, d' \
  || { echo "FAIL: bypass did not emit continue:true JSON (got: $OUT)" >&2; exit 1; }
echo "PASS: RUNAWAY_REMEDIATE_BYPASS=1 -> continue:true no-op"

# --- Assertion 8: real run with no match -> valid continue JSON, no crash --
# Set both gates absurdly high so nothing on the CI box matches; the hook must
# still emit valid JSON and exit 0.
OUT="$(printf '{}' | RUNAWAY_HOOK_MIN_AGE_MIN=99999 RUNAWAY_HOOK_MIN_CPU=999 RUNAWAY_PROC_NAMES=__none__ RUNAWAY_HELPER_MIN_AGE_MIN=99999 python3 "$HOOK" 2>/dev/null)"
echo "$OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("continue") is True, d' \
  || { echo "FAIL: no-match run did not emit valid continue JSON (got: $OUT)" >&2; exit 1; }
echo "PASS: no-match run emits valid continue JSON (no crash)"

echo
echo "All assertions passed. CLASS-2 stuck-hook + CLASS-3 orphaned-helper invariants hold (pos+neg control)."
