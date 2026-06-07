#!/usr/bin/env bash
#
# scripts/test-agentic-os.sh - invariant + negative-control suite for the
# agentic-os/ client install primitive (MYC-254).
#
# It exercises the REAL template under agentic-os/ plus poisoned fixtures, so the
# two declarative safety invariants are proven to FAIL on a violation (not just
# pass on the happy path - a guard only seen pass is worthless):
#
#   - a read-only planner that declares a mutating tool (Write) is REJECTED;
#   - a paths-scoped rule matches the right language and stays silent on a non-match.
#
# Plus an install smoke (INSTALL.sh drops the full layout into a fresh target) and
# the declarative-kernel discipline (kernel + each agent < 100 lines).
#
# Wired into scripts/ci.sh via tests/integration/test_agentic_os.sh.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
AOS="$ROOT/agentic-os"
PY="${PYTHON:-python3}"

pass=0
fail=0
note() { printf '       %s\n' "$1"; }
ok()   { pass=$((pass + 1)); printf 'ok   - %s\n' "$1"; }
bad()  { fail=$((fail + 1)); printf 'FAIL - %s\n' "$1"; }

tmp_bad="$(mktemp -d)"
tmp_target="$(mktemp -d)"
cleanup() { rm -rf "$tmp_bad" "$tmp_target"; }
trap cleanup EXIT

# ---- 1. validator: the real agents/ pass (planner/reviewer read-only, resolver read-write)
if "$PY" "$AOS/bin/validate_agents.py" "$AOS/agents" >/dev/null 2>&1; then
  ok "validate_agents: real agents/ pass"
else
  bad "validate_agents: real agents/ should pass but did not"
  "$PY" "$AOS/bin/validate_agents.py" "$AOS/agents" 2>&1 | sed 's/^/       /' || true
fi

# ---- 2. NEGATIVE CONTROL: a read-only planner that declares Write is REJECTED
cp "$AOS/tests/fixtures/bad_planner.md" "$tmp_bad/planner.md"
if "$PY" "$AOS/bin/validate_agents.py" "$tmp_bad" >/dev/null 2>&1; then
  bad "NEGATIVE CONTROL: a read-only planner declaring Write was ACCEPTED (guard is dead)"
else
  ok "NEGATIVE CONTROL: read-only planner declaring Write is REJECTED"
fi

# ---- 3. paths-scoped rule matches the right language
ts_out="$("$PY" "$AOS/bin/paths_scoped_rules.py" --path src/components/Button.ts 2>/dev/null || true)"
if printf '%s' "$ts_out" | grep -q "typescript"; then
  ok "paths_scoped_rules: **/*.ts surfaces the typescript rule"
else
  bad "paths_scoped_rules: **/*.ts did not surface the typescript rule"
fi
py_out="$("$PY" "$AOS/bin/paths_scoped_rules.py" --path app/main.py 2>/dev/null || true)"
if printf '%s' "$py_out" | grep -q "python"; then
  ok "paths_scoped_rules: **/*.py surfaces the python rule"
else
  bad "paths_scoped_rules: **/*.py did not surface the python rule"
fi

# ---- 4. NEGATIVE CONTROL: a non-code path surfaces NO language rule (silent, exit 0)
md_out="$("$PY" "$AOS/bin/paths_scoped_rules.py" --path notes/todo.md 2>/dev/null || true)"
if [ -z "$md_out" ]; then
  ok "NEGATIVE CONTROL: non-code path surfaces no rule (silent no-op)"
else
  bad "NEGATIVE CONTROL: non-code path wrongly surfaced a rule: $md_out"
fi

# ---- 5. install smoke: INSTALL.sh drops the full layout into a fresh target
bash "$AOS/INSTALL.sh" "$tmp_target" >/dev/null 2>&1 || true
expect=(
  "CLAUDE.md"
  ".claude/agents/planner.md"
  ".claude/agents/reviewer.md"
  ".claude/agents/resolver.md"
  ".claude/contexts/dev.md"
  ".claude/contexts/review.md"
  ".claude/contexts/research.md"
  ".claude/contexts/security.md"
  ".claude/rules/typescript/hooks.md"
  ".claude/rules/python/hooks.md"
  ".claude/hooks/paths_scoped_rules.py"
  "data/README.md"
)
missing=0
for rel in "${expect[@]}"; do
  if [ ! -f "$tmp_target/$rel" ]; then
    note "missing after install: $rel"
    missing=$((missing + 1))
  fi
done
if [ "$missing" -eq 0 ]; then
  ok "INSTALL.sh: full layout (kernel + 3 agents + 4 contexts + 2 lang rules + hook + data) dropped"
else
  bad "INSTALL.sh: $missing expected file(s) missing"
fi

# ---- 6. installed agents still validate clean (the dropped specs keep the safety boundary)
if "$PY" "$AOS/bin/validate_agents.py" "$tmp_target/.claude/agents" >/dev/null 2>&1; then
  ok "post-install: dropped agents/ validate clean (tool-surface boundary survived the copy)"
else
  bad "post-install: dropped agents/ failed validation"
fi

# ---- 7. declarative-kernel discipline: kernel + each agent < 100 lines
overflow=0
while IFS= read -r f; do
  n="$(wc -l <"$f" | tr -d ' ')"
  if [ "$n" -ge 100 ]; then
    note "over 100 lines ($n): ${f#"$AOS"/}"
    overflow=$((overflow + 1))
  fi
done < <(find "$AOS/agents" "$AOS/kernel" -name '*.md')
if [ "$overflow" -eq 0 ]; then
  ok "declarative-kernel discipline: kernel + each agent under 100 lines"
else
  bad "$overflow kernel/agent file(s) >= 100 lines"
fi

echo
echo "agentic-os suite: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
