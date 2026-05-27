#!/usr/bin/env bash
# Regression test for install-hooks-user-level.py --fail-on-missing.
#
# Bug class: SILENT-STRAND-DIVERGENT-FORK. bootstrap.sh skips the skill
# update when the local clone is on a divergent fork (local commits not
# on origin/main AND origin/main has commits not on the clone). The
# installer then writes new hook entries from hooks.json into
# settings.json regardless — entries that reference scripts the local
# fork doesn't have on disk. The hook runtime swallows the resulting
# `python3: can't open file` via the `2>/dev/null || echo {continue:true}`
# wrapping in hooks.json. Users see no error, the meeting cascade and
# other UserPromptSubmit hooks silently never fire.
#
# This test asserts:
#   1. With every referenced script present, verification exits 0.
#   2. With a script missing, --fail-on-missing exits 1.
#   3. The failure output names the missing path AND the git-pull
#      recovery hint, so users can act on it without grep.
#   4. Gated commands (`[ -f X ] && python3 X ...`) are NOT flagged
#      even if X is missing — that's the intentionally-optional case.
#   5. Without --fail-on-missing, the installer still exits 0 even
#      when scripts are missing (back-compat — only opt-in is fatal).
#
# Self-contained. Exit 0 = pass.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALLER="$REPO_ROOT/scripts/install-hooks-user-level.py"

fail() {
    echo "FAIL: $1" >&2
    exit 1
}

[[ -f "$INSTALLER" ]] || fail "installer missing at $INSTALLER"

# Throwaway HOME so we don't touch the real ~/.claude/settings.json.
TMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME"' EXIT

# Throwaway "skill repo" containing a minimal hooks.json that references
# only files we control. The installer's ABS_FINGERPRINT list is
# substring-based (`ai-brain-starter/hooks/...`) so we point inside a
# fake ai-brain-starter dir at TMP_HOME.
SKILL_DIR="$TMP_HOME/.claude/skills/ai-brain-starter"
mkdir -p "$SKILL_DIR/hooks"
mkdir -p "$SKILL_DIR/scripts"

# Two scripts: one we'll create, one we'll leave missing to simulate
# the divergent-fork strand.
EXISTING_SCRIPT="$SKILL_DIR/hooks/detect-closing-signal.py"
MISSING_SCRIPT="$SKILL_DIR/hooks/inject-meeting-workflow-on-trigger.py"
GATED_SCRIPT="$SKILL_DIR/hooks/lint-vault-frontmatter.py"  # we'll leave this missing too but gated

cat > "$EXISTING_SCRIPT" <<'EOF'
#!/usr/bin/env python3
print('{"continue": true}')
EOF
chmod +x "$EXISTING_SCRIPT"
# Deliberately don't create MISSING_SCRIPT or GATED_SCRIPT.

# Minimal hooks.json — direct invocation of existing + missing + gated form.
cat > "$SKILL_DIR/hooks.json" <<EOF
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 $EXISTING_SCRIPT 2>/dev/null || echo '{\"continue\":true}'"
          },
          {
            "type": "command",
            "command": "python3 $MISSING_SCRIPT 2>/dev/null || echo '{\"continue\":true}'"
          },
          {
            "type": "command",
            "command": "[ -f $GATED_SCRIPT ] && python3 $GATED_SCRIPT 2>/dev/null || echo '{\"continue\":true}'"
          }
        ]
      }
    ]
  }
}
EOF

SETTINGS_PATH="$TMP_HOME/.claude/settings.json"
echo "{}" > "$SETTINGS_PATH"

# Case A: with MISSING_SCRIPT absent, --fail-on-missing should exit 1
set +e
OUT=$(python3 "$INSTALLER" --hooks-source "$SKILL_DIR/hooks.json" --settings "$SETTINGS_PATH" --fail-on-missing 2>&1)
RC=$?
set -e

[[ $RC -eq 1 ]] || fail "expected exit 1 with missing required script, got $RC. Output:\n$OUT"
echo "$OUT" | grep -q "FAIL.*hook(s) — script not on disk" || \
    fail "expected FAIL line in output. Got:\n$OUT"
echo "$OUT" | grep -qF "$MISSING_SCRIPT" || \
    fail "expected missing path '$MISSING_SCRIPT' in output. Got:\n$OUT"
echo "$OUT" | grep -q "git pull --rebase origin main" || \
    fail "expected git pull --rebase recovery hint in output. Got:\n$OUT"
# Gated script (lint-vault-frontmatter.py with `[ -f X ] &&`) must NOT
# appear in the FAIL block; the SKIP block is where it belongs.
# Extract everything from the FAIL line up to (but not including) the
# next blank line — that's the FAIL block, exclusive of the SKIP block above.
FAIL_BLOCK=$(echo "$OUT" | awk '/FAIL.*hook\(s\) — script not on disk/,/^$/')
if echo "$FAIL_BLOCK" | grep -qF "$GATED_SCRIPT"; then
    fail "gated optional script wrongly listed under FAIL. Got:\n$FAIL_BLOCK"
fi
# Symmetric check: the SKIP block MUST contain the gated script (positive case)
SKIP_BLOCK=$(echo "$OUT" | awk '/SKIP.*hook\(s\) — optional/,/FAIL/' | grep -v "^.*FAIL")
echo "$SKIP_BLOCK" | grep -qF "$GATED_SCRIPT" || \
    fail "gated optional script missing from SKIP block. Got:\n$SKIP_BLOCK"

# Case B: without --fail-on-missing, installer still exits 0 (back-compat).
# Reset settings.json so the merge fires fresh.
echo "{}" > "$SETTINGS_PATH"
set +e
python3 "$INSTALLER" --hooks-source "$SKILL_DIR/hooks.json" --settings "$SETTINGS_PATH" --quiet > /dev/null 2>&1
RC=$?
set -e
[[ $RC -eq 0 ]] || fail "expected exit 0 without --fail-on-missing, got $RC"

# Case C: create the missing script, re-run --fail-on-missing, expect exit 0.
cat > "$MISSING_SCRIPT" <<'EOF'
#!/usr/bin/env python3
print('{"continue": true}')
EOF
echo "{}" > "$SETTINGS_PATH"
set +e
python3 "$INSTALLER" --hooks-source "$SKILL_DIR/hooks.json" --settings "$SETTINGS_PATH" --fail-on-missing --quiet > /dev/null 2>&1
RC=$?
set -e
[[ $RC -eq 0 ]] || fail "expected exit 0 with all required scripts present, got $RC"

# Case D: --verify (without --fail-on-missing) should print the report but exit 0
# even when scripts are missing — matches existing back-compat semantics.
rm -f "$MISSING_SCRIPT"
echo "{}" > "$SETTINGS_PATH"
set +e
OUT=$(python3 "$INSTALLER" --hooks-source "$SKILL_DIR/hooks.json" --settings "$SETTINGS_PATH" --verify 2>&1)
RC=$?
set -e
[[ $RC -eq 0 ]] || fail "expected exit 0 with --verify alone, got $RC"
echo "$OUT" | grep -q "FAIL.*hook(s) — script not on disk" || \
    fail "expected FAIL line under --verify even though exit is 0. Got:\n$OUT"

echo "PASS: install-hooks-user-level.py --fail-on-missing surfaces divergent-fork strands; gated commands respected; back-compat preserved"
