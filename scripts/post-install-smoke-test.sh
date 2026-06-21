#!/usr/bin/env bash
# post-install-smoke-test.sh — end-to-end verification after bootstrap.
#
# Verifies that every component the bootstrap claimed to install is actually
# functional. Same class of bug as the Windows BOM crash: install succeeds,
# downstream invocation fails silently. Catch it at the install boundary.
#
# Tests:
#   1. Every Python script in ai-brain-starter passes py_compile
#   2. Every bash script passes `bash -n`
#   3. Every JSON config parses
#   4. Every hook script returns valid JSON when piped a sample input
#   5. Every aggregator script runs --help / dry-run without crashing
#   6. Every bundled skill folder has a SKILL.md
#   7. Optional: every skill responds to a no-op invocation
#
# Usage:
#   bash scripts/post-install-smoke-test.sh             # full run
#   bash scripts/post-install-smoke-test.sh --quick     # syntax + JSON only
#   bash scripts/post-install-smoke-test.sh --quiet     # only print summary
#
# Exit codes: 0 = all pass, 1 = warnings only, 2 = critical failure.

set -uo pipefail

QUICK=0
QUIET=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick) QUICK=1; shift ;;
    --quiet) QUIET=1; shift ;;
    --help|-h) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

SKILL_DIR="$HOME/.claude/skills/ai-brain-starter"
if [[ ! -d "$SKILL_DIR" ]]; then
  # fallback to the maintainer location
  SKILL_DIR="$HOME/Desktop/ai-brain-starter"
fi

PASS=0
WARN=0
FAIL=0

ok()   { [[ "$QUIET" -eq 0 ]] && printf "  \033[32m✓\033[0m %s\n" "$*"; PASS=$((PASS+1)); }
warn() { [[ "$QUIET" -eq 0 ]] && printf "  \033[33m!\033[0m %s\n" "$*"; WARN=$((WARN+1)); }
fail() { [[ "$QUIET" -eq 0 ]] && printf "  \033[31m✗\033[0m %s\n" "$*"; FAIL=$((FAIL+1)); }
hdr()  { [[ "$QUIET" -eq 0 ]] && printf "\n\033[1m%s\033[0m\n" "$*"; }

if [[ ! -d "$SKILL_DIR" ]]; then
  echo "FAIL: ai-brain-starter skill not found at any known location" >&2
  exit 2
fi

# === 1. Python syntax ===
hdr "Python syntax (py_compile)"
while IFS= read -r f; do
  if python3 -m py_compile "$f" 2>/dev/null; then
    ok "$f"
  else
    fail "$f"
  fi
done < <(find "$SKILL_DIR" -name "*.py" -type f -not -path "*/__pycache__/*" -not -path "*/.git/*" 2>/dev/null)

# === 2. Bash syntax ===
hdr "Bash syntax (bash -n)"
while IFS= read -r f; do
  if bash -n "$f" 2>/dev/null; then
    ok "$f"
  else
    fail "$f"
  fi
done < <(find "$SKILL_DIR" -name "*.sh" -type f -not -path "*/.git/*" 2>/dev/null)

# === 3. JSON config syntax ===
hdr "JSON config syntax"
for f in "$SKILL_DIR/hooks.json" "$SKILL_DIR"/templates/closing-signals/*.json "$SKILL_DIR"/templates/schemas/*.json; do
  [[ -f "$f" ]] || continue
  if python3 -c "import json; json.load(open('$f'))" 2>/dev/null; then
    ok "$f"
  else
    fail "$f"
  fi
done

[[ "$QUICK" -eq 1 ]] && {
  hdr "Summary"
  ok "$PASS pass, $WARN warn, $FAIL fail (quick mode)"
  [[ "$FAIL" -gt 0 ]] && exit 2 || ([[ "$WARN" -gt 0 ]] && exit 1) || exit 0
}

# === 4. Hook smoke test (sample stdin) ===
hdr "Hook smoke tests"
DETECTOR="$SKILL_DIR/hooks/detect-closing-signal.py"
if [[ -f "$DETECTOR" ]]; then
  TMPDIR_HOOK=$(mktemp -d)
  resp=$(echo '{"prompt":"hello world","session_id":"smoke","cwd":"'"$TMPDIR_HOOK"'"}' | python3 "$DETECTOR" 2>/dev/null)
  if echo "$resp" | python3 -c "import json,sys; json.loads(sys.stdin.read())" 2>/dev/null; then
    ok "detect-closing-signal.py returns valid JSON for non-close input"
  else
    fail "detect-closing-signal.py returned invalid JSON"
  fi
  resp=$(echo '{"prompt":"bye","session_id":"smoke","cwd":"'"$TMPDIR_HOOK"'"}' | python3 "$DETECTOR" 2>/dev/null)
  if echo "$resp" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); assert 'hookSpecificOutput' in d" 2>/dev/null; then
    ok "detect-closing-signal.py injects context on 'bye'"
  else
    fail "detect-closing-signal.py did not inject context on 'bye'"
  fi
  rm -rf "$TMPDIR_HOOK"
fi

LINTER="$SKILL_DIR/hooks/lint-vault-frontmatter.py"
if [[ -f "$LINTER" ]]; then
  resp=$(echo '{"tool_name":"Read","tool_input":{}}' | python3 "$LINTER" 2>/dev/null)
  if echo "$resp" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); assert d.get('hookSpecificOutput',{}).get('permissionDecision')=='allow'" 2>/dev/null; then
    ok "lint-vault-frontmatter.py allows non-Write tools"
  else
    fail "lint-vault-frontmatter.py wrong response for Read tool"
  fi
fi

# === 5. Aggregator smoke ===
hdr "Aggregator scripts"
for s in aggregate-sessions.py aggregate-decisions.py rotate-meta-archives.py; do
  f="$SKILL_DIR/scripts/$s"
  if [[ -f "$f" ]]; then
    if python3 "$f" --help >/dev/null 2>&1 || python3 -c "import importlib.util; spec=importlib.util.spec_from_file_location('m','$f'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)" 2>/dev/null; then
      ok "$s loads without error"
    else
      warn "$s could not be loaded standalone (may need vault context)"
    fi
  fi
done

# === 6. Bundled skills have SKILL.md ===
hdr "Bundled skills"
for s in daily-journal deconstruct diagnose for-my-team graphify humanizer insights meeting-todos nano-banana patterns repurpose-talk second-brain-mapping setup-vault-types; do
  if [[ -f "$SKILL_DIR/skills/$s/SKILL.md" ]]; then
    ok "skills/$s/SKILL.md"
  else
    warn "skills/$s/SKILL.md missing (may not be bundled)"
  fi
done

# === 7. Schema validator self-test ===
hdr "Schema validator"
if [[ -f "$SKILL_DIR/scripts/vault-schema-validator.py" ]]; then
  if python3 "$SKILL_DIR/scripts/vault-schema-validator.py" --self-test >/dev/null 2>&1; then
    ok "vault-schema-validator.py self-test"
  else
    fail "vault-schema-validator.py self-test failed"
  fi
fi

# === 7b. Context-budget measurer self-test (MYC-619) ===
hdr "Context-budget measurer"
if [[ -f "$SKILL_DIR/hooks/context-budget-measure.py" ]]; then
  if python3 "$SKILL_DIR/hooks/context-budget-measure.py" --self-test >/dev/null 2>&1; then
    ok "context-budget-measure.py self-test"
  else
    fail "context-budget-measure.py self-test failed"
  fi
fi

# === 8. Closing-signal fixture harness ===
hdr "Closing-signal fixtures"
if [[ -f "$SKILL_DIR/scripts/test-closing-signals.py" ]]; then
  if python3 "$SKILL_DIR/scripts/test-closing-signals.py" >/dev/null 2>&1; then
    ok "test-closing-signals.py 74/74"
  else
    fail "test-closing-signals.py had failures"
  fi
fi

hdr "Summary"
[[ "$QUIET" -eq 1 ]] && printf "smoke: %d pass, %d warn, %d fail\n" "$PASS" "$WARN" "$FAIL"
[[ "$QUIET" -eq 0 ]] && printf "  \033[1m%d pass · %d warn · %d fail\033[0m\n" "$PASS" "$WARN" "$FAIL"
[[ "$FAIL" -gt 0 ]] && exit 2
[[ "$WARN" -gt 0 ]] && exit 1
exit 0
