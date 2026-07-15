#!/usr/bin/env bash
# test_heal_journal_guard.sh - end-to-end proof that the SessionStart self-heal
# (scripts/heal-journal-guard.py) restores the /journal Step-0 context guard on an
# account that lost it, and no-ops on a healthy one.
#
# Hermetic: a throwaway $HOME + throwaway vault. The REAL repo checkout is the
# canonical source (its hooks.json + install-hooks-user-level.py + sync-vault-scripts.sh),
# the fake $HOME is the target - the same split a real stale account has.
#
# Controls (a guard earns trust only by FAILING on the thing it catches):
#   1. NEGATIVE: an unprotected account (no registration, no preflight) trips
#      --check-only (exit 1).
#   2. The wired SessionStart run REPAIRS it: guard registered under BOTH matchers,
#      journal-preflight.py landed in the vault, and ONE surface line emitted.
#   3. POSITIVE: the now-healthy account passes --check-only (exit 0).
#   4. IDEMPOTENT: a second run stays clean and does not duplicate the registration.
#   5. In-script pos/neg controls (--self-test) pass.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HEAL="$REPO_ROOT/scripts/heal-journal-guard.py"

PASS=0
FAIL=0
TMPDIRS=()
cleanup() { for d in "${TMPDIRS[@]:-}"; do [ -n "$d" ] && rm -rf "$d"; done; }
trap cleanup EXIT

ok()  { PASS=$((PASS + 1)); echo "PASS  $1"; }
bad() { FAIL=$((FAIL + 1)); echo "FAIL  $1 :: $2"; }

echo "=== precondition ==="
if [ -f "$HEAL" ]; then ok "heal-journal-guard.py present"; else bad "present" "missing $HEAL"; fi

echo "=== 0. in-script controls (--self-test) ==="
if python3 "$HEAL" --self-test >/dev/null 2>&1; then
  ok "--self-test passes"
else
  bad "--self-test passes" "run: python3 $HEAL --self-test"
fi

# --- build a throwaway account + vault ---------------------------------------
FAKE_HOME="$(mktemp -d)"; TMPDIRS+=("$FAKE_HOME")
FAKE_VAULT="$(mktemp -d)"; TMPDIRS+=("$FAKE_VAULT")
# Sandboxing HOME alone does not isolate Windows Python: since 3.8,
# ntpath.expanduser/Path.home() resolve against USERPROFILE and ignore HOME
# (CPython bpo-36264), so the script under test would read/write the REAL
# ~/.claude. Point USERPROFILE at the same sandbox, Windows-spelled where
# cygpath exists (Git Bash). On Linux/macOS cygpath is absent and nothing
# reads the extra variable, so the CI (ubuntu) run is unchanged.
FAKE_HOME_NATIVE="$FAKE_HOME"
if command -v cygpath >/dev/null 2>&1; then
  FAKE_HOME_NATIVE="$(cygpath -w "$FAKE_HOME")"
fi
# The registered guard command resolves ~ against $HOME, so the guard script must
# exist under the fake skill path for the "script on disk" health check to pass.
mkdir -p "$FAKE_HOME/.claude/skills/ai-brain-starter/hooks"
cp "$REPO_ROOT/hooks/warn-journal-saved-without-context.py" \
   "$FAKE_HOME/.claude/skills/ai-brain-starter/hooks/warn-journal-saved-without-context.py"
# A vault the sync can resolve + write into (Decisions/Sessions disambiguate the human
# Meta folder for _meta_resolver), but WITHOUT journal-preflight.py yet.
mkdir -p "$FAKE_VAULT/⚙️ Meta/scripts" "$FAKE_VAULT/⚙️ Meta/Decisions" "$FAKE_VAULT/⚙️ Meta/Sessions"
# An unprotected settings.json: valid, but no journal guard registered anywhere.
printf '%s\n' '{"hooks": {}}' > "$FAKE_HOME/.claude/settings.json"

run_heal() {  # runs the wired SessionStart path against the fake account
  printf '%s' '{}' | env HOME="$FAKE_HOME" USERPROFILE="$FAKE_HOME_NATIVE" \
    VAULT_ROOT="$FAKE_VAULT" HEAL_JOURNAL_GUARD_NO_COOLDOWN=1 python3 "$HEAL" 2>/dev/null
}
check_only() {  # read-only diagnosis; exit 1 on any gap
  env HOME="$FAKE_HOME" USERPROFILE="$FAKE_HOME_NATIVE" VAULT_ROOT="$FAKE_VAULT" \
    python3 "$HEAL" --check-only >/dev/null 2>&1
}
guard_matchers() {  # prints the sorted PreToolUse matchers the guard is registered under
  python3 - "$FAKE_HOME/.claude/settings.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
ms = sorted({g.get("matcher") for g in d.get("hooks", {}).get("PreToolUse", [])
             for h in g.get("hooks", [])
             if "warn-journal-saved-without-context" in h.get("command", "")})
print(",".join(m or "" for m in ms))
PY
}

echo "=== 1. NEGATIVE control: unprotected account trips --check-only ==="
if check_only; then
  bad "neg control --check-only trips" "an unprotected account PASSED --check-only (guard asleep)"
else
  ok "neg control --check-only trips (exit 1)"
fi

echo "=== 2. the SessionStart run repairs it ==="
OUT="$(run_heal)"
rc=$?
if [ "$rc" -eq 0 ]; then ok "heal exits 0 (fail-open)"; else bad "heal exits 0" "exit $rc"; fi
if printf '%s' "$OUT" | python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); ctx=d.get("hookSpecificOutput",{}).get("additionalContext",""); sys.exit(0 if "heal-journal-guard" in ctx else 1)' 2>/dev/null; then
  ok "surfaced ONE line about the repaired guard"
else
  bad "surface line" "no additionalContext line: $OUT"
fi
if [ "$(guard_matchers)" = "Bash,Write|Edit|MultiEdit" ]; then
  ok "guard registered under BOTH matchers"
else
  bad "guard both matchers" "got: $(guard_matchers)"
fi
if [ -f "$FAKE_VAULT/⚙️ Meta/scripts/journal-preflight.py" ]; then
  ok "journal-preflight.py landed in the vault"
else
  bad "preflight in vault" "sync did not copy journal-preflight.py"
fi

echo "=== 3. POSITIVE control: healthy account passes --check-only ==="
if check_only; then
  ok "positive control --check-only passes (exit 0)"
else
  bad "positive control passes" "a repaired account still reports a gap"
fi

echo "=== 4. IDEMPOTENT: second run stays clean, no duplicate registration ==="
run_heal >/dev/null 2>&1
count="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf-8")); print(sum(1 for g in d.get("hooks",{}).get("PreToolUse",[]) for h in g.get("hooks",[]) if "warn-journal-saved-without-context" in h.get("command","")))' "$FAKE_HOME/.claude/settings.json")"
if [ "$count" = "2" ]; then
  ok "no duplicate registration after re-run (2 entries: one per matcher)"
else
  bad "idempotent registration" "expected 2 guard entries, got $count"
fi

echo
echo "=== summary: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
