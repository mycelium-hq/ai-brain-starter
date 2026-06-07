#!/usr/bin/env bash
# Negative-control test for scripts/relocate-vault.sh — the vault relocation +
# Claude Code path-keyed state migration helper (MYC-511 item 4).
#
# A guard earns trust only by failing on the thing it catches. This asserts:
#   - POSITIVE: transcripts copy from the old path key to the new key (base +
#     sub-keys), the agent-memory symlink re-homes, old keys are preserved.
#   - NO-OP DETECTOR: 0 transcripts under the new key BEFORE migration, N after
#     (a silently-broken key transform would leave it 0 -> this test goes red).
#   - FAIL-LOUD: a zero-match key prints "no Claude Code session history" and
#     exits 0 (nothing to do), never a silent success.
#   - REFUSALS: full relocate refuses when the target exists and when the source
#     is already a symlink (both fatal even under --force).
#   - HAPPY PATH: a full move relocates the dir, leaves the symlink, migrates
#     history; --no-symlink omits the symlink.
# Hermetic: a temp HOME-like sandbox + an isolated --config-dir; the real
# ~/.claude is never touched.
# Run: bash scripts/test-relocate-vault.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/relocate-vault.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; fails=$((fails + 1)); }

# Mirror the script's projkey EXACTLY (resolve ancestry, keep leaf literal) so
# fixtures land at the same key the script computes, even where $TMPDIR resolves
# /var -> /private/var on macOS.
pathkey() { python3 -c 'import os,re,sys
p = os.path.abspath(os.path.expanduser(sys.argv[1]))
resolved = os.path.join(os.path.realpath(os.path.dirname(p)), os.path.basename(p))
print(re.sub(r"[^a-zA-Z0-9]", "-", resolved))' "$1"; }

CFG="$TMP/.claude"
PROJ="$CFG/projects"
jsonl_count() { find "$1" -maxdepth 1 -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' '; }

# --- 1. POSITIVE + NO-OP DETECTOR: --migrate-claude-state copies old -> new ----
# The old path has a SPACE -> exercises the non-alphanumeric key transform that
# the reference [/ ]->- sed would also handle, but a dotted/emoji path needs the
# full [^A-Za-z0-9]->- rule this helper uses.
OLD="$TMP/Desktop/My Vault"
NEW="$TMP/brain"
mkdir -p "$OLD/⚙️ Meta/Agent Memory" "$NEW/⚙️ Meta/Agent Memory"
OLDKEY="$(pathkey "$OLD")"
NEWKEY="$(pathkey "$NEW")"
mkdir -p "$PROJ/$OLDKEY" "$PROJ/${OLDKEY}--claude-worktrees-foo"
echo '{"x":1}' > "$PROJ/$OLDKEY/sess1.jsonl"
echo '{"x":2}' > "$PROJ/${OLDKEY}--claude-worktrees-foo/sess2.jsonl"

before="$(jsonl_count "$PROJ/$NEWKEY")"
[ "$before" = 0 ] && pass "no-op detector: 0 transcripts under new key before migration" \
                  || fail "no-op detector: expected 0 before, got $before"

CLAUDE_CONFIG_DIR="$CFG" bash "$SCRIPT" --migrate-claude-state "$OLD" "$NEW" >/dev/null 2>&1

a1="$(jsonl_count "$PROJ/$NEWKEY")"
[ "$a1" = 1 ] && pass "base-key transcript migrated (sess1)" || fail "base-key migrate: want 1 got $a1"
a2="$(jsonl_count "$PROJ/${NEWKEY}--claude-worktrees-foo")"
[ "$a2" = 1 ] && pass "sub-key transcript migrated (sess2)" || fail "sub-key migrate: want 1 got $a2"
[ -L "$PROJ/$NEWKEY/memory" ] && pass "agent-memory symlink re-homed" || fail "agent-memory symlink missing"
[ -f "$PROJ/$OLDKEY/sess1.jsonl" ] && pass "old key preserved (copy, not move)" || fail "old key was destroyed (should be a backup)"

# --- 2. FAIL-LOUD: a zero-match key warns + exits 0 (never a silent success) ---
out="$(CLAUDE_CONFIG_DIR="$CFG" bash "$SCRIPT" --migrate-claude-state "$TMP/nothing-here" "$TMP/elsewhere" 2>&1)"
rc=$?
echo "$out" | grep -qi 'no Claude Code session history' \
  && pass "zero-match: fails loud (warns, not silent)" \
  || fail "zero-match: expected a loud warning, got: $out"
[ "$rc" = 0 ] && pass "zero-match: exits 0 (nothing to do, not a crash)" || fail "zero-match: want rc=0 got $rc"

# --- 3. REFUSAL: full relocate refuses when the target already exists ----------
src="$TMP/src-vault" ; dst="$TMP/dst-exists" ; mkdir -p "$src" "$dst"
CLAUDE_CONFIG_DIR="$CFG" bash "$SCRIPT" "$src" "$dst" --force >/dev/null 2>&1
rc=$?
[ "$rc" = 1 ] && pass "refuses when target exists (rc=1, fatal even under --force)" \
             || fail "target-exists: want rc=1 got $rc"

# --- 4. REFUSAL: refuses when the source is already a symlink ------------------
realdir="$TMP/realdir" ; linkdir="$TMP/linkdir" ; mkdir -p "$realdir" ; ln -s "$realdir" "$linkdir"
CLAUDE_CONFIG_DIR="$CFG" bash "$SCRIPT" "$linkdir" "$TMP/new-from-link" --force >/dev/null 2>&1
rc=$?
[ "$rc" = 1 ] && pass "refuses when source already a symlink (rc=1)" || fail "source-symlink: want rc=1 got $rc"

# --- 5. HAPPY PATH: move dir, leave symlink, migrate history -------------------
hv="$TMP/Desktop/Happy Vault" ; nv="$TMP/local-brain"
mkdir -p "$hv/⚙️ Meta/Agent Memory" ; echo "note" > "$hv/note.md"
HK="$(pathkey "$hv")" ; NK="$(pathkey "$nv")"
mkdir -p "$PROJ/$HK" ; echo '{"s":1}' > "$PROJ/$HK/h.jsonl"
CLAUDE_CONFIG_DIR="$CFG" bash "$SCRIPT" "$hv" "$nv" --force >/dev/null 2>&1
rc=$?
[ "$rc" = 0 ] && pass "happy path exits 0" || fail "happy path rc=$rc"
{ [ -d "$nv" ] && [ -f "$nv/note.md" ]; } && pass "vault moved to new local path" || fail "vault not at new path"
{ [ -L "$hv" ] && [ "$(readlink "$hv")" = "$nv" ]; } && pass "symlink left at old path" || fail "symlink not left at old path"
hh="$(jsonl_count "$PROJ/$NK")"
[ "$hh" = 1 ] && pass "happy path migrated session history" || fail "happy path history not migrated (want 1 got $hh)"

# --- 6. --no-symlink omits the symlink ----------------------------------------
nsv="$TMP/Desktop/NoSym Vault" ; nsn="$TMP/nosym-brain" ; mkdir -p "$nsv"
CLAUDE_CONFIG_DIR="$CFG" bash "$SCRIPT" "$nsv" "$nsn" --force --no-symlink >/dev/null 2>&1
{ [ -d "$nsn" ] && [ ! -e "$nsv" ]; } && pass "--no-symlink leaves nothing at the old path" || fail "--no-symlink left something at old path"

echo
if [ "$fails" -gt 0 ]; then echo "FAILED: $fails"; exit 1; fi
echo "ALL TESTS PASSED"
