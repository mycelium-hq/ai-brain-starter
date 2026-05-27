#!/usr/bin/env bash
# Regression test for scripts/write-hook.sh — i18n meeting-folder match.
#
# Bug: write-hook.sh originally hardcoded `Meeting Notes/` and
# `Meeting-Notes/` as the only folder names that would trigger the
# /meeting-todos extraction prompt. Spanish users with `Reuniones/`,
# French users with `Réunions/`, anyone with a custom-named folder
# got no auto-extract — silent no-op, no signal that the cascade
# was wired for EN-only.
#
# This test asserts:
#   1. EN default ("Meeting Notes/") matches without any env var set.
#   2. EN default ("Meeting-Notes/") (hyphenated) matches.
#   3. Path NOT under any meeting folder does NOT match (negative).
#   4. With AI_BRAIN_MEETING_NOTES_DIR set, custom folders match
#      (Spanish, French, Chinese, multiple in one var).
#   5. With AI_BRAIN_MEETING_NOTES_DIR set, the EN defaults are
#      OVERRIDDEN — only the listed folders match.
#   6. Case-insensitivity: "meeting notes/" matches the default.
#   7. Trailing slash in the env var is tolerated.
#
# Self-contained. Exit 0 = pass.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$REPO_ROOT/scripts/write-hook.sh"

fail() {
    echo "FAIL: $1" >&2
    exit 1
}

# Helper: run the hook with a JSON tool_input.file_path and return the
# trigger phrase if matched, or empty string if not.
run_hook() {
    local path="$1"
    echo "{\"tool_input\":{\"file_path\":\"$path\"}}" | bash "$HOOK"
}

[[ -f "$HOOK" ]] || fail "hook missing at $HOOK"
[[ -x "$HOOK" ]] || chmod +x "$HOOK"

# 1. EN default — "Meeting Notes/" should match (unsetting env var).
unset AI_BRAIN_MEETING_NOTES_DIR
OUT=$(run_hook "/Users/x/vault/Team Folder/Meeting Notes/2026-05-27 - Weekly Sync.md")
echo "$OUT" | grep -q "Meeting note saved" || \
    fail "EN default 'Meeting Notes/' did not match. Got: $OUT"

# 2. EN default — "Meeting-Notes/" (hyphenated) should match.
unset AI_BRAIN_MEETING_NOTES_DIR
OUT=$(run_hook "/Users/x/vault/Meeting-Notes/2026-05-27.md")
echo "$OUT" | grep -q "Meeting note saved" || \
    fail "EN default 'Meeting-Notes/' did not match. Got: $OUT"

# 3. Negative — path NOT in any meeting folder.
unset AI_BRAIN_MEETING_NOTES_DIR
OUT=$(run_hook "/Users/x/vault/📓 Journals/2026-05-27.md")
echo "$OUT" | grep -q "Meeting note saved" && \
    fail "non-meeting path wrongly triggered the hook. Got: $OUT" || true
echo "$OUT" | grep -q "^{}$" || \
    fail "non-meeting path should emit {} (empty object). Got: $OUT"

# 4a. Custom env var — Spanish "Reuniones/" matches.
export AI_BRAIN_MEETING_NOTES_DIR="Reuniones:Reuniones-Notas"
OUT=$(run_hook "/Users/x/vault/Reuniones/2026-05-27 - Sync semanal.md")
echo "$OUT" | grep -q "Meeting note saved" || \
    fail "Spanish 'Reuniones/' did not match with env var. Got: $OUT"

# 4b. Custom env var — French "Réunions/" matches (multibyte safe).
export AI_BRAIN_MEETING_NOTES_DIR="Réunions"
OUT=$(run_hook "/Users/x/vault/Réunions/2026-05-27 - Réunion.md")
echo "$OUT" | grep -q "Meeting note saved" || \
    fail "French 'Réunions/' did not match with env var. Got: $OUT"

# 4c. Custom env var — Chinese folder matches.
export AI_BRAIN_MEETING_NOTES_DIR="会议笔记"
OUT=$(run_hook "/Users/x/vault/会议笔记/2026-05-27.md")
echo "$OUT" | grep -q "Meeting note saved" || \
    fail "Chinese '会议笔记/' did not match with env var. Got: $OUT"

# 4d. Multiple folders in one var.
export AI_BRAIN_MEETING_NOTES_DIR="Reuniones:Réunions:会议笔记"
OUT=$(run_hook "/Users/x/vault/Réunions/foo.md")
echo "$OUT" | grep -q "Meeting note saved" || \
    fail "Réunions (middle of list) did not match. Got: $OUT"

# 5. Env var OVERRIDES defaults — if the user sets it, "Meeting Notes/"
# alone should NOT match unless explicitly included.
export AI_BRAIN_MEETING_NOTES_DIR="Reuniones"
OUT=$(run_hook "/Users/x/vault/Meeting Notes/2026-05-27.md")
echo "$OUT" | grep -q "Meeting note saved" && \
    fail "Env var override should exclude 'Meeting Notes' if not listed. Got: $OUT" || true

# 6. Case-insensitivity — lowercase path against capitalized default.
unset AI_BRAIN_MEETING_NOTES_DIR
OUT=$(run_hook "/users/x/vault/meeting notes/2026-05-27.md")
echo "$OUT" | grep -q "Meeting note saved" || \
    fail "Case-insensitive match against default failed. Got: $OUT"

# 7. Trailing slash in env var is tolerated.
export AI_BRAIN_MEETING_NOTES_DIR="Reuniones/:Réunions/"
OUT=$(run_hook "/Users/x/vault/Reuniones/foo.md")
echo "$OUT" | grep -q "Meeting note saved" || \
    fail "Trailing slash in env var folder name broke matching. Got: $OUT"

unset AI_BRAIN_MEETING_NOTES_DIR
echo "PASS: write-hook.sh matches EN defaults, custom env var folders (ES/FR/ZH), overrides correctly, tolerates case + trailing slashes"
