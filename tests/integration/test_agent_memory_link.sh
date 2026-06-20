#!/usr/bin/env bash
# Negative control for the memory-durability fix: prove that after linking,
# memory Claude Code writes to its project dir actually lands IN THE VAULT.
# Without this, the symlink could point at the wrong key and silently no-op —
# the exact brain-loss bug the fix exists to kill.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LINKER="$ROOT/scripts/link-agent-memory.py"
PASS=0 FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
VAULT="$WORK/My Vault"
mkdir -p "$VAULT/.obsidian"
export CLAUDE_HOME="$WORK/.claude"   # redirect ~/.claude/projects for the test

KEY="$(python3 "$ROOT/scripts/_project_key.py" "$VAULT")"
PROJ="$CLAUDE_HOME/projects/$KEY"
AGENT_MEM="$VAULT/⚙️ Meta/Agent Memory"

echo "== case 1: fresh link (no prior memory dir) =="
python3 "$LINKER" --vault "$VAULT" --quiet
[ -d "$AGENT_MEM" ] && pass "vault Agent Memory dir created" || fail "vault Agent Memory dir missing"
[ -L "$PROJ/memory" ] && pass "project memory is a symlink" || fail "project memory is not a symlink"
# THE NEGATIVE CONTROL: write where Claude Code would, assert it reaches the vault.
echo "remembered-fact" > "$PROJ/memory/MEMORY.md"
if [ -f "$AGENT_MEM/MEMORY.md" ] && grep -q remembered-fact "$AGENT_MEM/MEMORY.md"; then
  pass "memory written via project dir LANDS IN THE VAULT"
else
  fail "memory written via project dir did NOT reach the vault"
fi

echo "== case 2: idempotent re-run =="
python3 "$LINKER" --vault "$VAULT" --quiet
[ -L "$PROJ/memory" ] && grep -q remembered-fact "$AGENT_MEM/MEMORY.md" \
  && pass "re-run is a no-op, content intact" || fail "re-run damaged the link or content"

echo "== case 3: loss-free migration of a pre-existing real memory dir =="
VAULT2="$WORK/Vault Two"
mkdir -p "$VAULT2/.obsidian"
KEY2="$(python3 "$ROOT/scripts/_project_key.py" "$VAULT2")"
PROJ2="$CLAUDE_HOME/projects/$KEY2"
mkdir -p "$PROJ2/memory"
echo "old-profile" > "$PROJ2/memory/user_profile.md"      # pre-existing tool-dir memory
python3 "$LINKER" --vault "$VAULT2" --quiet
AGENT_MEM2="$VAULT2/⚙️ Meta/Agent Memory"
[ -L "$PROJ2/memory" ] && pass "real dir replaced by symlink" || fail "real dir not replaced"
grep -q old-profile "$AGENT_MEM2/user_profile.md" 2>/dev/null \
  && pass "pre-existing memory MIGRATED into the vault (no loss)" || fail "pre-existing memory lost"
ls -d "$PROJ2"/memory.pre-link-backup* >/dev/null 2>&1 \
  && pass "old dir backed up, not deleted" || fail "old dir was deleted (not loss-free)"

echo "== case 4: refuses to clobber a foreign symlink =="
VAULT3="$WORK/Vault Three"
mkdir -p "$VAULT3/.obsidian"
KEY3="$(python3 "$ROOT/scripts/_project_key.py" "$VAULT3")"
PROJ3="$CLAUDE_HOME/projects/$KEY3"
mkdir -p "$PROJ3" "$WORK/elsewhere"
ln -s "$WORK/elsewhere" "$PROJ3/memory"
if python3 "$LINKER" --vault "$VAULT3" --quiet 2>/dev/null; then
  fail "clobbered a foreign symlink (should have refused)"
else
  pass "refused to clobber a foreign symlink (fail-loud)"
fi

echo
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
