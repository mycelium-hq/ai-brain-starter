#!/usr/bin/env bash
# Regression guard for scripts/claude_performance_digest.py — secret
# redaction on captured tool-error text (MYC-4635).
#
# Raw tool-error text from a session JSONL flowed unredacted into the
# error_patterns dict key, the "RECURRING ERROR" prescription string, and
# then into Claude To-dos.md (the digest's investigation-item sink): three
# sessions sharing the same key-bearing error is enough to cross the
# recurring-error threshold and persist the raw secret into that file.
#
# Runs a COPY of the real script against a fully sandboxed HOME plus a
# self-contained "skill root", so VAULT_ROOT / PROJECTS_ROOT / MEMORY_FILE
# never touch the real ~/.claude or a real vault. claude_performance_digest.py
# is self-locating (SCRIPT_DIR = its own directory; VAULT_ROOT =
# SCRIPT_DIR.parent.parent; its _lib imports resolve SCRIPT_DIR.parent/hooks),
# so the sandbox mirrors that arithmetic
# under one tmpdir:
#
#   $TMP/skill/scripts/claude_performance_digest.py   <- SCRIPT_DIR
#   $TMP/skill/hooks/_lib/{secret_patterns,safe_read}.py <- SCRIPT_DIR.parent/hooks/_lib
#   $TMP/⚙️ Meta/...                                    <- VAULT_ROOT/⚙️ Meta (script creates it)
#   $TMP/home/.claude/projects/...                     <- PROJECTS_ROOT (via sandbox_home)
#
# Two assertions (positive + negative control, per "a guard earns trust only
# by failing on the thing it catches"):
#   (a) POSITIVE + LEAK CONTROL: three synthetic sessions sharing the same
#       key-bearing tool error cross the recurring-error threshold, and the
#       to-do written to Claude To-dos.md carries the redaction marker but
#       NOT the raw credential.
#   (b) NEGATIVE CONTROL: a benign recurring error (paths + a URL, no
#       secret) survives byte-identical in the same file.
#
# Bash-script test per the tests/integration/ convention.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_SRC="$ROOT/scripts/claude_performance_digest.py"
SECRET_PATTERNS_SRC="$ROOT/hooks/_lib/secret_patterns.py"
SAFE_READ_SRC="$ROOT/hooks/_lib/safe_read.py"

# shellcheck source=tests/integration/lib/sandbox_home.sh
. "$ROOT/tests/integration/lib/sandbox_home.sh"
# shellcheck source=tests/integration/lib/real_python.sh
. "$ROOT/tests/integration/lib/real_python.sh"
ensure_real_python

fail=0
pass() { echo "  PASS  $1"; }
bad() { echo "  FAIL  $1"; fail=1; }

[ -f "$SCRIPT_SRC" ] || { echo "::error::script not found at $SCRIPT_SRC"; exit 1; }
[ -f "$SECRET_PATTERNS_SRC" ] || { echo "::error::secret_patterns.py not found at $SECRET_PATTERNS_SRC"; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/skill/scripts" "$TMP/skill/hooks/_lib"
cp "$SCRIPT_SRC" "$TMP/skill/scripts/claude_performance_digest.py"
cp "$SECRET_PATTERNS_SRC" "$TMP/skill/hooks/_lib/secret_patterns.py"
cp "$SAFE_READ_SRC" "$TMP/skill/hooks/_lib/safe_read.py"
DIGEST="$TMP/skill/scripts/claude_performance_digest.py"
TODO_FILE="$TMP/⚙️ Meta/Claude To-dos.md"
DIGEST_LOG="$TMP/digest_stdout.log"

sandbox_home "$TMP/home"
PROJECT_DIR="$HOME/.claude/projects/testproj"
mkdir -p "$PROJECT_DIR"

# write_session <path> <error-text> — the record shape the digest's parser
# READS: an assistant turn with one Bash tool_use, then a top-level
# `tool_result` record. Current Claude Code transcripts carry errors inside a
# `type:"user"` record's `content[]` instead, which the parser does not read
# today (tracked separately), so this pins the redaction seam, not the parser.
# The assistant turn stays because a fixture with only the tool_result line drives
# generate_report()'s total_turns to 0 and hits an unrelated pre-existing
# ZeroDivisionError in the Project Allocation section (line ~460) that has
# nothing to do with redaction — this fixture shape avoids that path
# entirely rather than masking it.
write_session() {
  local path="$1" err="$2"
  python3 - "$path" "$err" <<'PY'
import json, sys
path, err = sys.argv[1], sys.argv[2]
assistant_rec = {
    "type": "assistant",
    "message": {
        "model": "claude-sonnet-4-5",
        "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "run-something"}}],
    },
    "timestamp": "2026-01-01T00:00:00Z",
}
tool_result_rec = {"type": "tool_result", "message": {"content": [
    {"is_error": True, "text": err, "tool_use_id": "t1"}
]}}
with open(path, "w", encoding="utf-8") as f:
    f.write(json.dumps(assistant_rec) + "\n")
    f.write(json.dumps(tool_result_rec) + "\n")
PY
}

run_digest() {
  python3 "$DIGEST" --days 7 >"$DIGEST_LOG" 2>&1 || true
}

show_log_on_fail() {
  echo "    --- digest run output ---" >&2
  sed 's/^/    /' "$DIGEST_LOG" >&2 || true
}

# --- (a) POSITIVE + LEAK CONTROL: postgres connection-string password -------
# A failing DB command that echoes a connection string is a realistic shape
# for a recurring tool error; the password portion is the credential.
#
# Kept to well under 80 chars TOTAL (including the password) on purpose:
# generate_report() builds the error_patterns dict key as error_text[:80] (a
# PRE-EXISTING, unrelated truncation this test does not touch). A specimen
# that straddles that boundary lets a partial credential survive the cut and
# still read as "not persisted" by an exact-match grep — the exact
# "truncation can cut a secret in half" failure mode this fix closes. Fitting
# the whole specimen inside 80 chars makes the leak check unambiguous.
PG_PASSWORD="Hunter2_$(printf 'Z%.0s' $(seq 1 12))"
ERR_TEXT="conn failed: postgres://appuser:${PG_PASSWORD}@db:5432/prod"
rm -f "$PROJECT_DIR"/*.jsonl 2>/dev/null || true
rm -rf "$TMP/⚙️ Meta" 2>/dev/null || true
write_session "$PROJECT_DIR/session-1.jsonl" "$ERR_TEXT"
write_session "$PROJECT_DIR/session-2.jsonl" "$ERR_TEXT"
write_session "$PROJECT_DIR/session-3.jsonl" "$ERR_TEXT"
run_digest

if [ -f "$TODO_FILE" ]; then
  if grep -q "REDACTED pg password" "$TODO_FILE"; then
    pass "(a.1) recurring-error to-do carries the redaction marker"
  else
    bad "(a.1) recurring-error to-do is missing the redaction marker"
    show_log_on_fail
  fi
  if grep -qF "$PG_PASSWORD" "$TODO_FILE"; then
    bad "(a.2) LEAK: raw postgres password persisted in Claude To-dos.md"
  else
    pass "(a.2) raw postgres password NOT persisted"
  fi
else
  bad "(a) no to-do file written at all (\$TODO_FILE=$TODO_FILE) -- recurring-error threshold not reached"
  show_log_on_fail
fi

# --- (b) NEGATIVE CONTROL: benign recurring error survives byte-identical --
rm -f "$PROJECT_DIR"/*.jsonl 2>/dev/null || true
rm -f "$TODO_FILE" 2>/dev/null || true
# Kept under 80 chars on purpose: generate_report() truncates error_text to
# error_text[:80] to build the error_patterns dict key (a PRE-EXISTING,
# unrelated truncation this test does not touch), so a longer benign string
# would never appear in full downstream and would look like a false failure.
BENIGN_ERR="ENOENT: open '/Users/dev/project/config.json' (see docs/errors.md#enoent)"
write_session "$PROJECT_DIR/session-4.jsonl" "$BENIGN_ERR"
write_session "$PROJECT_DIR/session-5.jsonl" "$BENIGN_ERR"
write_session "$PROJECT_DIR/session-6.jsonl" "$BENIGN_ERR"
run_digest

if [ -f "$TODO_FILE" ]; then
  if grep -qF "$BENIGN_ERR" "$TODO_FILE"; then
    pass "(b.1) benign recurring error text survives byte-identical"
  else
    bad "(b.1) benign error text was altered by redaction (over-matching bug)"
    show_log_on_fail
  fi
  if grep -q "REDACTED" "$TODO_FILE"; then
    bad "(b.2) benign to-do unexpectedly carries a redaction marker"
  else
    pass "(b.2) no false-positive redaction on benign content"
  fi
else
  bad "(b) no to-do file written at all (\$TODO_FILE=$TODO_FILE) -- recurring-error threshold not reached"
  show_log_on_fail
fi

# --- (c) DEDUPE reads a symlinked CLAUDE.md, and refuses on an unreadable one -
# safe_read refuses symlinks, so the dedupe must read the resolved target;
# an existing CLAUDE.md it cannot read must stop rule writes (None), never
# fall through to a duplicate rule.
mkdir -p "$HOME/.claude"
printf 'already shipped: performance_verbose_agents\n' > "$HOME/.claude/real-claude.md"
ln -sf "$HOME/.claude/real-claude.md" "$HOME/.claude/CLAUDE.md"
DEDUPE="$(python3 - "$DIGEST" "$TMP" <<'PY'
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("digest", sys.argv[1])
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
text = mod._load_dedupe_sources(Path(sys.argv[2]))
print("NONE" if text is None else ("TAG" if "performance_verbose_agents" in text else "MISSING"))
PY
)"
[ "$DEDUPE" = "TAG" ] && pass "(c.1) dedupe reads a symlinked CLAUDE.md" || bad "(c.1) dedupe on a symlinked CLAUDE.md returned $DEDUPE"
chmod 000 "$HOME/.claude/real-claude.md"
if [ -r "$HOME/.claude/real-claude.md" ]; then
  # root, or a filesystem without POSIX modes (Windows): the fixture cannot
  # make the file unreadable here, so this case cannot be measured on this host.
  DEDUPE="SKIP"
else
DEDUPE="$(python3 - "$DIGEST" "$TMP" <<'PY'
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("digest", sys.argv[1])
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
text = mod._load_dedupe_sources(Path(sys.argv[2]))
print("NONE" if text is None else "TEXT")
PY
)"
fi
chmod 644 "$HOME/.claude/real-claude.md"
case "$DEDUPE" in
  NONE) pass "(c.2) an unreadable CLAUDE.md stops rule writes" ;;
  SKIP) echo "  SKIP  (c.2) chmod 000 does not revoke reads on this host (root or no POSIX modes)" ;;
  *)    bad "(c.2) unreadable CLAUDE.md returned $DEDUPE, not None" ;;
esac

# --- (c.3) a symlink-loop CLAUDE.md must not crash the dedupe (resolve()
# raises RuntimeError on Python 3.9; the loop is treated as unreadable).
rm -f "$HOME/.claude/CLAUDE.md" "$HOME/.claude/loop-a"
ln -s "$HOME/.claude/loop-a" "$HOME/.claude/CLAUDE.md"
ln -s "$HOME/.claude/CLAUDE.md" "$HOME/.claude/loop-a"
LOOP="$(python3 - "$DIGEST" "$TMP" 2>&1 <<'PY'
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("digest", sys.argv[1])
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
mod._load_dedupe_sources(Path(sys.argv[2]))
print("NO-CRASH")
PY
)"
rm -f "$HOME/.claude/CLAUDE.md" "$HOME/.claude/loop-a"
case "$LOOP" in
  *NO-CRASH*) pass "(c.3) a symlink-loop CLAUDE.md does not crash the dedupe" ;;
  *)          bad "(c.3) a symlink-loop CLAUDE.md crashed the dedupe: ${LOOP##*$'\n'}" ;;
esac

echo
if [ "$fail" = "0" ]; then
  echo "test_claude_performance_digest_redaction: all assertions passed"
else
  echo "::error::test_claude_performance_digest_redaction: one or more assertions failed"
fi
exit "$fail"
