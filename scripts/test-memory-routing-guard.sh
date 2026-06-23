#!/usr/bin/env bash
# Negative-control + install-registration smoke for the memory-routing guard
# (hooks/warn-learning-to-tool-private-memory.py).
#
# Proves BOTH halves the guard's value depends on:
#   1. BEHAVIOR (negative control): a team-shaped learning written to a REAL
#      tool-private memory dir NUDGES; a genuinely-local memory, a SYMLINKED
#      (shared-backed) memory dir, an off-store path, and a bypassed write all
#      stay SILENT. A guard that only ever fires (or never fires) is unproven —
#      the SILENT cases are the assertion set that makes the nudge meaningful.
#   2. ACTIVATION (fresh-install smoke): the installer REGISTERS the guard in a
#      clean settings.json. Activation is the deliverable, not file presence
#      (else the guard ships dormant — the MYC-1017 bug class).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
GUARD="$ROOT/hooks/warn-learning-to-tool-private-memory.py"
INSTALLER="$ROOT/scripts/install-hooks-user-level.py"
HOOKS_JSON="$ROOT/hooks.json"

[ -f "$GUARD" ]      || { echo "FAIL: guard missing: $GUARD"; exit 1; }
[ -f "$INSTALLER" ]  || { echo "FAIL: installer missing: $INSTALLER"; exit 1; }
[ -f "$HOOKS_JSON" ] || { echo "FAIL: hooks.json missing: $HOOKS_JSON"; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0; fail=0
ok()  { echo "  ok   - $1"; pass=$((pass+1)); }
bad() { echo "  FAIL - $1"; fail=$((fail+1)); }

payload() { # $1 = file_path, $2 = content  → PreToolUse Write JSON on stdout
  python3 -c "import json,sys; print(json.dumps({'tool_name':'Write','tool_input':{'file_path':sys.argv[1],'content':sys.argv[2]}}))" "$1" "$2"
}
run() { printf '%s' "$1" | python3 "$GUARD" 2>/dev/null || true; }  # echoes guard stdout

LEARN_BODY=$'---\ntype: feedback\n---\n\n**Rule.** Fix the shared source, not the first consumer.\n\n**Why:** reach is the invariant.'
LOCAL_BODY=$'---\ntype: user\n---\n\nI am a data scientist focused on observability.'

REAL_MEM="$TMP/.claude/projects/realkey/memory"; mkdir -p "$REAL_MEM"
SYM_PROJ="$TMP/.claude/projects/symkey";        mkdir -p "$SYM_PROJ"
mkdir -p "$TMP/shared-brain"; ln -s "$TMP/shared-brain" "$SYM_PROJ/memory"
mkdir -p "$TMP/notes"

# 1. POSITIVE control — team-shaped learning in a REAL tool-private dir → NUDGE
out="$(run "$(payload "$REAL_MEM/feedback_fix_shared_source.md" "$LEARN_BODY")")"
printf '%s' "$out" | grep -q "memory-routing" \
  && ok "nudges on a team-shaped learning in real tool-private memory" \
  || bad "expected a nudge, got: ${out:0:100}"

# 2. NEGATIVE control — genuinely-local (type: user) memory → SILENT
out="$(run "$(payload "$REAL_MEM/user_role.md" "$LOCAL_BODY")")"
[ -z "$out" ] && ok "silent on a genuinely-local (type: user) memory" \
  || bad "expected silence on a local memory, got: ${out:0:100}"

# 3. NEGATIVE control — symlinked (shared-backed) memory dir → SILENT
out="$(run "$(payload "$SYM_PROJ/memory/feedback_fix_shared_source.md" "$LEARN_BODY")")"
[ -z "$out" ] && ok "silent when the memory dir is a symlink (shared-backed)" \
  || bad "expected silence on a symlinked dir, got: ${out:0:100}"

# 4. NEGATIVE control — path outside any tool-private memory store → SILENT
out="$(run "$(payload "$TMP/notes/feedback_x.md" "$LEARN_BODY")")"
[ -z "$out" ] && ok "silent on a path outside a tool-private memory store" \
  || bad "expected silence off-store, got: ${out:0:100}"

# 5. NEGATIVE control — bypass env honored → SILENT even on a team-shaped learning
pld="$(payload "$REAL_MEM/feedback_fix_shared_source.md" "$LEARN_BODY")"
out="$(printf '%s' "$pld" | TOOL_PRIVATE_MEMORY_BYPASS=1 python3 "$GUARD" 2>/dev/null || true)"
[ -z "$out" ] && ok "silent under TOOL_PRIVATE_MEMORY_BYPASS=1" \
  || bad "bypass not honored, got: ${out:0:100}"

# 6. ACTIVATION smoke — a fresh install REGISTERS the guard in settings.json
SETTINGS="$TMP/settings.json"; echo '{}' > "$SETTINGS"
python3 "$INSTALLER" --settings "$SETTINGS" --hooks-source "$HOOKS_JSON" --quiet >/dev/null 2>&1 || true
grep -q "warn-learning-to-tool-private-memory.py" "$SETTINGS" \
  && ok "fresh install registers the guard in settings.json (activation, not just file presence)" \
  || bad "installer did NOT register the guard in settings.json"

echo "memory-routing-guard: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
