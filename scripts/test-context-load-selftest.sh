#!/usr/bin/env bash
# test-context-load-selftest.sh — fixture suite for scripts/check-context-load.py
#
# check-context-load.py is MYC-630: the automated first-run context-load
# self-test. It simulates Claude Code's CLAUDE.md ancestor-walk so the install
# can PROVE the vault's personalized context will load on first launch — instead
# of relying on the user happening to launch from the right cwd (wrong folder =
# generic answer = "this doesn't work" = churn).
#
# This suite builds throwaway fixture vaults and asserts the porcelain verdict +
# exit code for each first-run failure mode. Logic lives next to the script it
# exercises; tests/integration/test_context_load_selftest.sh is a thin CI wrapper.
#
# Exit 0 = all fixtures pass.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK="$HERE/check-context-load.py"

PASS=0
FAIL=0

# A filled, personalized CLAUDE.md (no template placeholders). References the
# canonical session-start files so the missing-context check has something to
# resolve.
write_filled_claude() {
  cat > "$1/CLAUDE.md" <<'EOF'
# Memory

## Me
Jane Doe. Founder of Acme. Building a longevity platform.

## Current Focus
- Ship the PRD this week
- Close the seed round

## People
- **Sam** — cofounder and CTO

## Vault Map
- 📓 Journals/
- 🏠 Home/
- ⚙️ Meta/

## Session Protocol
1. Start: read this file + ⚙️ Meta/Last Session.md + ⚙️ Meta/Current Priorities.md
   and 🏠 Home/About Me.md. Don't ask what we were doing.
EOF
}

# Create the canonical session-start context files the filled CLAUDE.md points at.
write_context_layer() {
  mkdir -p "$1/⚙️ Meta" "$1/🏠 Home"
  printf 'Last session: wrote tests.\n' > "$1/⚙️ Meta/Last Session.md"
  printf 'Top priority: ship.\n'        > "$1/⚙️ Meta/Current Priorities.md"
  printf 'Jane Doe. Founder.\n'         > "$1/🏠 Home/About Me.md"
}

# run_case <label> <expected-verdict-prefix> <expected-exit> -- <check args...>
run_case() {
  local label="$1" expect_verdict="$2" expect_exit="$3"; shift 3
  [ "$1" = "--" ] && shift
  local out rc
  out="$(python3 "$CHECK" "$@" --porcelain 2>/dev/null)"
  rc=$?
  if [[ "$out" == "$expect_verdict"* ]] && [ "$rc" -eq "$expect_exit" ]; then
    printf '  \033[32mPASS\033[0m %-22s -> %s (exit %d)\n' "$label" "$out" "$rc"
    PASS=$((PASS+1))
  else
    printf '  \033[31mFAIL\033[0m %-22s\n        got:    %s (exit %d)\n        expect: %s* (exit %d)\n' \
      "$label" "$out" "$rc" "$expect_verdict" "$expect_exit"
    FAIL=$((FAIL+1))
  fi
}

ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT

# --- Fixture 1: healthy vault, launched from the vault root ------------------
V1="$ROOT/good"; mkdir -p "$V1"; write_filled_claude "$V1"; write_context_layer "$V1"
run_case "healthy"        OK_WILL_LOAD        0 -- "$V1" --launch-dir "$V1"

# --- Fixture 2: healthy vault, launched from a subfolder (descendant is OK) --
run_case "healthy-subdir" OK_WILL_LOAD        0 -- "$V1" --launch-dir "$V1/🏠 Home"

# --- Fixture 3: no launch-dir given => defaults to vault, still loads --------
run_case "default-launch" OK_WILL_LOAD        0 -- "$V1"

# --- Fixture 4: no CLAUDE.md at vault root ----------------------------------
V4="$ROOT/no-claude"; mkdir -p "$V4"; write_context_layer "$V4"
run_case "no-claude-md"   FAIL_NO_CLAUDE_MD   1 -- "$V4" --launch-dir "$V4"

# --- Fixture 5: unfilled template (placeholders survived) -------------------
V5="$ROOT/template"; mkdir -p "$V5"; write_context_layer "$V5"
cat > "$V5/CLAUDE.md" <<'EOF'
# Memory

## Me
[Name]. [What they do]. [Key context from their answers.]

## Current Focus
- [Priority 1 — with specifics from their answer]

## Vault Map
[FILL THIS IN — list the actual folders created in Phase 3]
EOF
run_case "unfilled-template" FAIL_TEMPLATE_UNFILLED 1 -- "$V5" --launch-dir "$V5"

# --- Fixture 6: stub CLAUDE.md (too small to be real personalization) -------
V6="$ROOT/stub"; mkdir -p "$V6"; write_context_layer "$V6"
printf '# Memory\n' > "$V6/CLAUDE.md"
run_case "stub-claude-md"  FAIL_TEMPLATE_UNFILLED 1 -- "$V6" --launch-dir "$V6"

# --- Fixture 7: healthy vault, launched from the WRONG folder (the cwd bug) --
WRONG="$ROOT/somewhere-else"; mkdir -p "$WRONG"
run_case "wrong-cwd"       FAIL_WRONG_CWD     1 -- "$V1" --launch-dir "$WRONG"

# --- Fixture 8: filled CLAUDE.md but the context layer it references is gone -
V8="$ROOT/missing-context"; mkdir -p "$V8"; write_filled_claude "$V8"
run_case "missing-context" WARN_MISSING_CONTEXT 2 -- "$V8" --launch-dir "$V8"

# --- Fixture 9: human (non-porcelain) output prints the exact launch command -
human_out="$(python3 "$CHECK" "$V1" 2>/dev/null)"
if printf '%s' "$human_out" | grep -q "cd .*good.* && claude"; then
  printf '  \033[32mPASS\033[0m %-22s -> prints launch command\n' "launch-command"
  PASS=$((PASS+1))
else
  printf '  \033[31mFAIL\033[0m %-22s -> no exact launch command in human output\n' "launch-command"
  FAIL=$((FAIL+1))
fi

# --- Fixture 10: --json emits parseable, structured output ------------------
if python3 "$CHECK" "$V1" --json 2>/dev/null \
    | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['verdict']=='OK_WILL_LOAD'; assert 'launch_command' in d" 2>/dev/null; then
  printf '  \033[32mPASS\033[0m %-22s -> valid JSON with verdict+launch_command\n' "json-output"
  PASS=$((PASS+1))
else
  printf '  \033[31mFAIL\033[0m %-22s -> --json output not parseable/complete\n' "json-output"
  FAIL=$((FAIL+1))
fi

echo
echo "context-load self-test fixtures: $PASS pass, $FAIL fail"
[ "$FAIL" -eq 0 ]
