#!/usr/bin/env bash
# Structural invariant on the shipped hooks.json SessionStart set — the hook
# fleet that EVERY install wires, free AND paid.
#
# Why this exists (MYC-569, paid analog of MYC-514): a Mycelium Personal /
# Team / Enterprise install does NOT vendor its own hook fleet. The paid
# "Personal scope" Claude Code substrate IS this repo — bootstrap.sh clones
# ai-brain-starter@main and install-hooks-user-level.py wires the canonical
# root hooks.json into ~/.claude/settings.json. So whatever this hooks.json
# wires on SessionStart is exactly what a paying Enterprise operator's machine
# runs (99.9% SLA). See docs/HOOK_FLEET_RESOURCE_GOVERNANCE.md.
#
# The 2026-06-05 Mac-freeze (load 36, total freeze) was caused by the corpus-
# walk secret scan (scan-prior-sessions-for-secrets.py) running on SessionStart:
# under N concurrent sessions it piled up N synchronous full-corpus walks.
# MYC-512 moved it OFF SessionStart (launchd job + cached-findings surfacer);
# MYC-514 hardened the scan + shipped the CLASS-2 stuck-hook reaper. But until
# now NOTHING asserted the wiring stays fixed: a future refactor could silently
# re-add the corpus walk to SessionStart and re-expose every paid install to a
# cold-start freeze. This test is that lock.
#
# Asserts (on the REAL canonical hooks.json):
#   1. The corpus-walk freeze hook (scan-prior-sessions-for-secrets.py) is NOT
#      wired in SessionStart. It belongs on a scheduled job / cached surfacer,
#      never the synchronous cold-start path.
#   2. The CLASS-2 stuck-hook reaper (remediate-runaway-procs.py) IS wired in
#      SessionStart — the protective hook must ship in every install.
#   3. NEGATIVE CONTROL: a mutated hooks.json that re-adds the freeze hook to
#      SessionStart MUST trip assertion 1 (proves the guard bites, not just
#      passes). And a mutated hooks.json that drops the reaper MUST trip
#      assertion 2.
#
# Companion guard: services/health-mcp/tests/test_v05_hooks.py asserts the
# network-syncing health-auto-sync.py also stays OUT of the default SessionStart
# set. Together they pin the two "heavy/concurrent work on cold start" classes.
#
# Isolation: reads the repo's own hooks.json; mutations are built in a tmpdir
# and removed on exit. Stdlib python3 + bash only; no network, no git.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOKS_JSON="$REPO_ROOT/hooks.json"

FREEZE_HOOK="scan-prior-sessions-for-secrets.py"
REAPER_HOOK="remediate-runaway-procs.py"

PASS=0
FAIL=0
TMPDIRS=()
cleanup() { for d in "${TMPDIRS[@]:-}"; do [ -n "$d" ] && rm -rf "$d"; done; }
trap cleanup EXIT

ok()  { PASS=$((PASS+1)); echo "PASS  $1"; }
bad() { FAIL=$((FAIL+1)); echo "FAIL  $1 :: $2"; }

# in_sessionstart <hooks.json path> <basename> -> rc 0 if wired in SessionStart,
# rc 1 if absent. Pure structural read of the canonical template shape
#   {"hooks": {"SessionStart": [ {"hooks": [ {"command": "..."} ]} ]}}.
in_sessionstart() {
  python3 - "$1" "$2" <<'PY'
import json, sys
path, needle = sys.argv[1], sys.argv[2]
data = json.load(open(path))
ss = data.get("hooks", {}).get("SessionStart", [])
blob = json.dumps(ss)
sys.exit(0 if needle in blob else 1)
PY
}

echo "=== precondition ==="
if [ -f "$HOOKS_JSON" ]; then ok "canonical hooks.json exists"; else bad "canonical hooks.json exists" "missing $HOOKS_JSON"; fi
if python3 -c "import json;json.load(open('$HOOKS_JSON'))" 2>/dev/null; then
  ok "hooks.json is valid JSON"
else
  bad "hooks.json is valid JSON" "parse error"
fi

echo "=== invariant 1: corpus-walk freeze hook is NOT on SessionStart ==="
if in_sessionstart "$HOOKS_JSON" "$FREEZE_HOOK"; then
  bad "freeze hook excluded from SessionStart" "$FREEZE_HOOK IS wired on SessionStart — re-exposes paid installs to cold-start corpus-walk pile-up (MYC-512/569)"
else
  ok "freeze hook ($FREEZE_HOOK) excluded from SessionStart"
fi

echo "=== invariant 2: CLASS-2 stuck-hook reaper IS on SessionStart ==="
if in_sessionstart "$HOOKS_JSON" "$REAPER_HOOK"; then
  ok "reaper ($REAPER_HOOK) wired on SessionStart"
else
  bad "reaper wired on SessionStart" "$REAPER_HOOK is NOT wired — the protective hook must ship in every install (MYC-514)"
fi

echo "=== negative control A: re-adding the freeze hook MUST trip invariant 1 ==="
NCA="$(mktemp -d)"; TMPDIRS+=("$NCA")
python3 - "$HOOKS_JSON" "$NCA/hooks.json" "$FREEZE_HOOK" <<'PY'
import json, sys
src, dst, needle = sys.argv[1], sys.argv[2], sys.argv[3]
data = json.load(open(src))
data.setdefault("hooks", {}).setdefault("SessionStart", []).append(
    {"hooks": [{"type": "command",
                "command": f"python3 ~/.claude/skills/ai-brain-starter/hooks/{needle}"}]}
)
json.dump(data, open(dst, "w"), indent=1)
PY
if in_sessionstart "$NCA/hooks.json" "$FREEZE_HOOK"; then
  ok "negative control A: guard detects a re-added freeze hook (bites)"
else
  bad "negative control A bites" "mutation with $FREEZE_HOOK on SessionStart was NOT detected — guard is blind"
fi

echo "=== negative control B: dropping the reaper MUST trip invariant 2 ==="
NCB="$(mktemp -d)"; TMPDIRS+=("$NCB")
python3 - "$HOOKS_JSON" "$NCB/hooks.json" "$REAPER_HOOK" <<'PY'
import json, sys
src, dst, needle = sys.argv[1], sys.argv[2], sys.argv[3]
data = json.load(open(src))
ss = data.get("hooks", {}).get("SessionStart", [])
for grp in ss:
    grp["hooks"] = [h for h in grp.get("hooks", []) if needle not in h.get("command", "")]
json.dump(data, open(dst, "w"), indent=1)
PY
if in_sessionstart "$NCB/hooks.json" "$REAPER_HOOK"; then
  bad "negative control B bites" "reaper still detected after removal — mutation harness is broken"
else
  ok "negative control B: guard detects a dropped reaper (bites)"
fi

echo ""
echo "=== SUMMARY: $PASS passed, $FAIL failed ==="
[ "$FAIL" = 0 ]
