#!/usr/bin/env bash
# CI lock for the Footprint SLA gate (MYC-2358, epic MYC-2348).
#
# scripts/footprint-sla-check.py --gate asserts the substrate hook fleet's
# per-event / per-tool cold-start FAN-OUT and the default-on DAEMON count stay
# within footprint-budgets.json. Without it, the fan-out re-grows silently every
# time a hook is added and the install slowly slows the machine
# (SLOW-INSTALL-FROM-LAZY-PLUMBING).
#
# Sibling-by-design with test_sessionstart_boundedness.sh: that gate governs each
# hook's WORK SHAPE (no unbounded corpus walk); this one governs the FLEET's
# fan-out + footprint. Neither duplicates the other.
#
# Asserts:
#   1. The gate's own pos/neg controls pass (--selftest).
#   2. The REAL shipped fleet (this repo's hooks.json) is within budget (--gate, exit 0).
#   3. NEGATIVE CONTROL: a synthetic over-budget fleet trips --gate (exit 1) AND a
#      default-on daemon trips it. Proves the gate BITES, not just passes.
#   4. POSITIVE CONTROL: a within-budget synthetic fleet passes (exit 0).
#   5. FAIL-LOUD: a missing budgets file / hooks.json exits 2 (never a silent green).
#   6. CACHE POSITIONING (MYC-2359): the stable per-session injectors
#      (session-start-context.py, inject-instinct-context.py) are wired on
#      SessionStart (once per session-segment -> cached prefix), NOT UserPromptSubmit
#      (every message -> fresh tokens), and hooks.json carries no dead `once: true`
#      (ignored in settings.json -> a "once" UPS hook silently re-fires every turn).
#
# Stdlib python3 + bash only. No network, no git, no hook execution. Tmpdirs
# removed on exit.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GATE="$REPO_ROOT/scripts/footprint-sla-check.py"

PASS=0
FAIL=0
TMPDIRS=()
cleanup() { for d in "${TMPDIRS[@]:-}"; do [ -n "$d" ] && rm -rf "$d"; done; }
trap cleanup EXIT

ok()  { PASS=$((PASS + 1)); echo "PASS  $1"; }
bad() { FAIL=$((FAIL + 1)); echo "FAIL  $1 :: $2"; }

echo "=== precondition ==="
if [ -f "$GATE" ]; then ok "gate present"; else bad "gate present" "missing $GATE"; fi
if [ -f "$REPO_ROOT/footprint-budgets.json" ]; then ok "budgets file present"
else bad "budgets file present" "missing $REPO_ROOT/footprint-budgets.json"; fi

echo "=== 1. gate pos/neg controls (--selftest) ==="
if python3 "$GATE" --selftest >/dev/null 2>&1; then
  ok "--selftest passes"
else
  bad "--selftest passes" "run: python3 $GATE --selftest"
fi

echo "=== 2. shipped fleet is within budget (--gate, exit 0) ==="
if python3 "$GATE" --gate >/dev/null 2>&1; then
  ok "real shipped fleet within footprint budget"
else
  bad "real shipped fleet within budget" "fan-out grew past budget (run: python3 $GATE --gate)"
fi

echo "=== 3. NEGATIVE CONTROL: an over-budget fleet trips the gate ==="
NEG="$(mktemp -d)"
TMPDIRS+=("$NEG")
mkdir -p "$NEG/hooks" "$NEG/scripts"
# 30 substrate-python hooks fanned out on Write
python3 - "$NEG/hooks.json" <<'PY'
import json, sys
entries = [{"type": "command",
            "command": f"python3 ~/.claude/skills/ai-brain-starter/hooks/evil-{i}.py 2>/dev/null || echo '{{}}'"}
           for i in range(30)]
json.dump({"hooks": {"PreToolUse": [{"matcher": "Write|Edit", "hooks": entries}]}},
          open(sys.argv[1], "w"))
PY
# a clean bootstrap (no daemons) + budgets with Write:7
printf '#!/usr/bin/env bash\necho hi\n' > "$NEG/bootstrap.sh"
cat > "$NEG/budgets.json" <<'JSON'
{"fanout_per_event": {"SessionStart": 50, "UserPromptSubmit": 50, "Stop": 50, "PreCompact": 50, "SessionEnd": 50},
 "fanout_per_tool": {"PreToolUse": {"Write": 7, "Edit": 7}, "PostToolUse": {}},
 "default_on_daemons": 0}
JSON
if python3 "$GATE" --gate --hooks-json "$NEG/hooks.json" --hooks-dir "$NEG/hooks" \
   --scripts-dir "$NEG/scripts" --budgets "$NEG/budgets.json" --bootstrap "$NEG/bootstrap.sh" \
   >/dev/null 2>&1; then
  bad "neg control fan-out trips" "a 30-hook Write fan-out PASSED a budget of 7 (the gate is asleep)"
else
  ok "neg control fan-out trips (exit 1)"
fi
# default-on daemon trips axis B
printf '#!/usr/bin/env bash\nlaunchctl load ~/Library/LaunchAgents/x.plist\n' > "$NEG/bootstrap_daemon.sh"
python3 - "$NEG/hooks_clean.json" <<'PY'
import json, sys
entries = [{"type": "command",
            "command": f"python3 ~/.claude/skills/ai-brain-starter/hooks/h-{i}.py 2>/dev/null || echo '{{}}'"}
           for i in range(3)]
json.dump({"hooks": {"PreToolUse": [{"matcher": "Write|Edit", "hooks": entries}]}},
          open(sys.argv[1], "w"))
PY
if python3 "$GATE" --gate --hooks-json "$NEG/hooks_clean.json" --hooks-dir "$NEG/hooks" \
   --scripts-dir "$NEG/scripts" --budgets "$NEG/budgets.json" --bootstrap "$NEG/bootstrap_daemon.sh" \
   >/dev/null 2>&1; then
  bad "neg control daemon trips" "a default-on launchctl daemon PASSED a budget of 0"
else
  ok "neg control daemon trips (exit 1)"
fi

echo "=== 4. POSITIVE CONTROL: a within-budget fleet passes (exit 0) ==="
if python3 "$GATE" --gate --hooks-json "$NEG/hooks_clean.json" --hooks-dir "$NEG/hooks" \
   --scripts-dir "$NEG/scripts" --budgets "$NEG/budgets.json" --bootstrap "$NEG/bootstrap.sh" \
   >/dev/null 2>&1; then
  ok "positive control (3-hook fan-out vs budget 7) passes (exit 0)"
else
  bad "positive control passes" "a within-budget fleet was wrongly flagged"
fi

echo "=== 5. FAIL-LOUD: missing budgets / hooks.json exits 2 (never silent green) ==="
python3 "$GATE" --gate --hooks-json "$NEG/hooks_clean.json" --hooks-dir "$NEG/hooks" \
   --scripts-dir "$NEG/scripts" --budgets "$NEG/does-not-exist.json" --bootstrap "$NEG/bootstrap.sh" \
   >/dev/null 2>&1
if [ "$?" -eq 2 ]; then ok "fail-loud on missing budgets (exit 2)"
else bad "fail-loud on missing budgets" "expected exit 2"; fi
python3 "$GATE" --gate --hooks-json "$NEG/does-not-exist.json" --hooks-dir "$NEG/hooks" \
   --scripts-dir "$NEG/scripts" --budgets "$NEG/budgets.json" --bootstrap "$NEG/bootstrap.sh" \
   >/dev/null 2>&1
if [ "$?" -eq 2 ]; then ok "fail-loud on missing hooks.json (exit 2)"
else bad "fail-loud on missing hooks.json" "expected exit 2"; fi

echo "=== 6. CACHE POSITIONING (MYC-2359): stable injectors on SessionStart, not UPS ==="
if CP_OUT="$(python3 - "$REPO_ROOT" <<'PY'
import json, sys, pathlib
repo = pathlib.Path(sys.argv[1])
hooks = json.loads((repo / "hooks.json").read_text())["hooks"]
def events_of(basename):
    return [ev for ev, blocks in hooks.items() for blk in blocks
            for e in blk.get("hooks", []) if basename in e.get("command", "")]
fails = []
for bn in ("session-start-context.py", "inject-instinct-context.py"):
    evs = events_of(bn)
    if evs != ["SessionStart"]:
        fails.append(f"{bn} wired on {evs or 'nothing'}, want ['SessionStart'] "
                     f"(UPS re-injects every message; once:true is dead in settings.json)")
    src = (repo / "hooks" / bn).read_text()
    if '"hookEventName": "SessionStart"' not in src:
        fails.append(f"{bn} does not emit hookEventName SessionStart")
once = sum(1 for ev in hooks for blk in hooks[ev]
          for e in blk.get("hooks", []) if e.get("once"))
if once:
    fails.append(f"{once} once:true entr(y/ies) in hooks.json - DEAD in settings.json (MYC-2359)")
print(" | ".join(fails))
sys.exit(1 if fails else 0)
PY
)"; then ok "stable injectors on SessionStart; no dead once:true"
else bad "cache positioning (MYC-2359)" "$CP_OUT"; fi

echo "=== 7. LIVE settings.json measurement (MYC-2396): --measure-live ==="
# Axis D-live measures an install's ACTUAL ~/.claude/settings.json (owned + unowned +
# non-.py + per-tool injectors the template-only axis D skips) by executing the literal
# wired command. Advisory; never gates. This locks the wiring at integration level: a
# regression to template-only behavior would drop the non-.py / per-tool asserts below.
LIVE="$(mktemp -d)"
TMPDIRS+=("$LIVE")
cat > "$LIVE/uncond.py" <<'PY'
import json
print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                          "additionalContext": "U" * 4000}}))
PY
cat > "$LIVE/pre.py" <<'PY'
import json
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                          "additionalContext": "P" * 2000}}))
PY
# A synthetic settings.json: an unconditional .py UPS injector, a non-.py inline-bash
# UPS injector, a JSON no-op, and a per-tool PreToolUse injector.
python3 - "$LIVE" > "$LIVE/settings.json" <<'PY'
import json, os, sys
d = sys.argv[1]
bash_inj = ("echo '{\"hookSpecificOutput\": {\"hookEventName\": \"UserPromptSubmit\", "
            "\"additionalContext\": \"" + "B" * 1200 + "\"}}'")
print(json.dumps({"hooks": {
    "UserPromptSubmit": [{"hooks": [
        {"type": "command", "command": f"python3 {os.path.join(d, 'uncond.py')}"},
        {"type": "command", "command": bash_inj},
        {"type": "command", "command": "echo '{\"continue\": true, \"suppressOutput\": true}'"},
    ]}],
    "PreToolUse": [{"matcher": "Write|Edit", "hooks": [
        {"type": "command", "command": f"python3 {os.path.join(d, 'pre.py')}"},
    ]}],
}}))
PY
OUT="$(python3 "$GATE" --measure-live --execute --settings "$LIVE/settings.json" --event all 2>&1)"
if echo "$OUT" | grep -q "Move it to SessionStart"; then
  ok "measure-live flags an unconditional UPS injector with a relocate-to-SessionStart hint"
else bad "measure-live relocate hint" "expected a SessionStart hint; got: $OUT"; fi
if echo "$OUT" | grep -q "PreToolUse - injected tokens"; then
  ok "measure-live covers per-tool (PreToolUse) injectors"
else bad "measure-live per-tool coverage" "expected a PreToolUse line; got: $OUT"; fi
# non-.py coverage: a settings.json whose ONLY UPS injector is the inline-bash form
# must still yield a nonzero headline (the template axis D would score it 0).
python3 - "$LIVE" > "$LIVE/settings-bashonly.json" <<'PY'
import json, sys
bash_inj = ("echo '{\"hookSpecificOutput\": {\"hookEventName\": \"UserPromptSubmit\", "
            "\"additionalContext\": \"" + "B" * 1200 + "\"}}'")
print(json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [
    {"type": "command", "command": bash_inj}]}]}}))
PY
OUT_BASH="$(python3 "$GATE" --measure-live --execute --settings "$LIVE/settings-bashonly.json" --event UserPromptSubmit 2>&1)"
if echo "$OUT_BASH" | grep -q "Headline: ~0 tokens"; then
  bad "measure-live non-.py coverage" "an inline-bash injector measured 0 (template axis D blind spot not closed): $OUT_BASH"
else ok "measure-live covers non-.py (inline-bash) injectors"; fi
# structural-only mode (no --execute) must NOT execute (no Headline line).
OUT2="$(python3 "$GATE" --measure-live --settings "$LIVE/settings.json" 2>&1)"
if echo "$OUT2" | grep -qi "Structural inventory only" && ! echo "$OUT2" | grep -q "Headline:"; then
  ok "measure-live without --execute is structural-only (no execution)"
else bad "measure-live structural-only" "expected structural-only, no Headline; got: $OUT2"; fi
# missing settings.json -> graceful exit 0 (advisory never blocks).
if python3 "$GATE" --measure-live --execute --settings "$LIVE/nope.json" >/dev/null 2>&1; then
  ok "measure-live on a missing settings.json exits 0 (advisory)"
else bad "measure-live missing settings" "advisory mode should exit 0 on a missing settings.json"; fi

echo "=== 8. SAFE DEFAULTS (MYC-2409): UPS-only default + write-hook opt-in warning ==="
# Default (no --event) must probe ONLY UserPromptSubmit - the safe per-message headline -
# NOT the tool-WRITE events. The synthetic settings has a PreToolUse injector; by default
# it must NOT be probed (no "PreToolUse - injected tokens" line).
OUT_DEF="$(python3 "$GATE" --measure-live --execute --settings "$LIVE/settings.json" 2>&1)"
if echo "$OUT_DEF" | grep -q "UserPromptSubmit - injected tokens" \
   && ! echo "$OUT_DEF" | grep -q "PreToolUse - injected tokens"; then
  ok "default --measure-live --execute probes UserPromptSubmit only (safe default)"
else bad "measure-live safe default" "default should probe UPS only, not tool events; got: $OUT_DEF"; fi
# Opting into tool events must print the WRITE-hook / throwaway-dir safety disclosure.
OUT_ALL="$(python3 "$GATE" --measure-live --execute --settings "$LIVE/settings.json" --event all 2>&1)"
if echo "$OUT_ALL" | grep -qi "THROWAWAY working dir"; then
  ok "opting into tool events discloses write-hooks run in a throwaway dir"
else bad "measure-live tool-event disclosure" "expected a throwaway-dir write-hook warning; got: $OUT_ALL"; fi

echo
echo "=== summary: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
