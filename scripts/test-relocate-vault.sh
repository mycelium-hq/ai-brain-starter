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
#   - BACKUP GATE (MYC-2382): a backup-less full relocate REFUSES (vault not
#     moved, remedy named); a verified off-machine backup lets it PROCEED;
#     --force overrides the gate on the same no-backup condition.
#   - CLOUD MOVE-OUT (MYC-2401): a vault whose only off-machine copy is the
#     cloud-sync it's being moved OUT of REFUSES (that copy doesn't survive the
#     move); a cloud vault with a surviving backup (archive/TM/git-remote) still
#     PROCEEDS.
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

# --- 7. BACKUP-FIRST GATE (MYC-2382): refuse a backup-less full relocate -------
# Moving a vault — often the one irreplaceable asset — with no off-machine backup
# is the nightmare failure. The full-relocate path must REFUSE unless a backup is
# verified (check-vault-backup.py) OR --force is passed. The no-backup signal is
# made hermetic with an empty backup-conf + the Time Machine probe skipped, so
# "no backup" is deterministic even on a dev Mac that has Time Machine set up.
NOBK_CONF="$TMP/no-backup-conf.json" ; echo '{}' > "$NOBK_CONF"

# 7a REFUSE: no backup, no --force -> refuses (rc!=0), vault NOT moved, names remedy.
gb_src="$TMP/gate-src" ; gb_dst="$TMP/gate-dst" ; mkdir -p "$gb_src" ; echo n > "$gb_src/n.md"
out="$(CLAUDE_CONFIG_DIR="$CFG" VAULT_BACKUP_CONF="$NOBK_CONF" VAULT_BACKUP_SKIP_TIMEMACHINE=1 \
       bash "$SCRIPT" "$gb_src" "$gb_dst" 2>&1)" ; rc=$?
[ "$rc" != 0 ] && pass "backup gate: refuses a backup-less move (rc=$rc)" \
               || fail "backup gate: expected a refusal, moved with rc=$rc"
{ [ -d "$gb_src" ] && [ ! -e "$gb_dst" ]; } && pass "backup gate: vault NOT moved on refusal" \
               || fail "backup gate: vault was moved despite the refusal"
echo "$out" | grep -qi 'backup' && pass "backup gate: refusal names the backup remedy" \
               || fail "backup gate: refusal output lacked a backup remedy: $out"

# 7b PROCEED: a verified vault-backup archive present, no --force -> moves.
ok_src="$TMP/gate-ok-src" ; ok_dst="$TMP/gate-ok-dst" ; mkdir -p "$ok_src" ; echo n > "$ok_src/n.md"
OK_RES="$(cd "$ok_src" && pwd -P)"   # the physical path relocate-vault.sh hands the guard
OK_DEST="$TMP/gate-backups" ; mkdir -p "$OK_DEST" ; touch "$OK_DEST/vault-backup-now.tar.gz"
OK_CONF="$TMP/ok-backup-conf.json"
printf '{"vaults": {"%s": {"dest": "%s", "archive_stem": "vault-backup"}}}\n' "$OK_RES" "$OK_DEST" > "$OK_CONF"
CLAUDE_CONFIG_DIR="$CFG" VAULT_BACKUP_CONF="$OK_CONF" VAULT_BACKUP_SKIP_TIMEMACHINE=1 \
  bash "$SCRIPT" "$ok_src" "$ok_dst" >/dev/null 2>&1 ; rc=$?
[ "$rc" = 0 ] && pass "backup gate: proceeds with a verified backup (rc=0)" \
             || fail "backup gate: a verified backup was still refused (rc=$rc)"
{ [ -d "$ok_dst" ] && [ -L "$ok_src" ]; } && pass "backup gate: verified backup -> moved + symlink left" \
             || fail "backup gate: verified backup did not relocate the vault"

# 7c FORCE OVERRIDE: no backup but --force -> moves (same no-backup condition as 7a).
fb_src="$TMP/gate-force-src" ; fb_dst="$TMP/gate-force-dst" ; mkdir -p "$fb_src" ; echo n > "$fb_src/n.md"
CLAUDE_CONFIG_DIR="$CFG" VAULT_BACKUP_CONF="$NOBK_CONF" VAULT_BACKUP_SKIP_TIMEMACHINE=1 \
  bash "$SCRIPT" "$fb_src" "$fb_dst" --force >/dev/null 2>&1 ; rc=$?
[ "$rc" = 0 ] && pass "backup gate: --force overrides the gate (rc=0)" \
             || fail "backup gate: --force did not override the gate (rc=$rc)"
[ -d "$fb_dst" ] && pass "backup gate: --force -> vault moved despite no backup" \
             || fail "backup gate: --force did not move the vault"

# --- 8. BACKUP GATE x CLOUD (MYC-2401): a cloud copy doesn't count for a move-OUT
# relocate moves the vault OUT of the cloud root and leaves a symlink, so the cloud
# copy is gone post-move. The gate passes --ignore-cloud, so a vault whose ONLY
# off-machine copy is the cloud it's fleeing must REFUSE (else we green-light the
# move citing the very backup the move destroys). A SURVIVING backup still proceeds.
# 8a a vault inside a cloud root with NO surviving backup -> REFUSE.
cl_src="$TMP/OneDrive/Cloud Vault" ; cl_dst="$TMP/cloud-local"
mkdir -p "$cl_src" ; echo n > "$cl_src/n.md"
out="$(CLAUDE_CONFIG_DIR="$CFG" VAULT_BACKUP_CONF="$NOBK_CONF" VAULT_BACKUP_SKIP_TIMEMACHINE=1 \
       bash "$SCRIPT" "$cl_src" "$cl_dst" 2>&1)" ; rc=$?
[ "$rc" != 0 ] && pass "cloud move-out, no surviving backup -> refuses (rc=$rc)" \
               || fail "cloud move-out should refuse (cloud copy doesn't survive), got rc=$rc"
{ [ -d "$cl_src" ] && [ ! -e "$cl_dst" ]; } && pass "cloud move-out refusal: vault NOT moved" \
               || fail "cloud move-out: vault moved despite no surviving backup"
echo "$out" | grep -qi 'cloud' && pass "cloud move-out refusal: explains the cloud copy won't survive" \
               || fail "cloud move-out refusal should mention the cloud copy: $out"

# 8b same cloud vault but WITH a surviving vault-backup archive -> proceeds.
cl2_src="$TMP/OneDrive/Cloud Vault 2" ; cl2_dst="$TMP/cloud-local-2"
mkdir -p "$cl2_src" ; echo n > "$cl2_src/n.md"
CL2_RES="$(cd "$cl2_src" && pwd -P)"
CL2_DEST="$TMP/cloud2-backups" ; mkdir -p "$CL2_DEST" ; touch "$CL2_DEST/vault-backup-now.tar.gz"
CL2_CONF="$TMP/cloud2-conf.json"
printf '{"vaults": {"%s": {"dest": "%s", "archive_stem": "vault-backup"}}}\n' "$CL2_RES" "$CL2_DEST" > "$CL2_CONF"
CLAUDE_CONFIG_DIR="$CFG" VAULT_BACKUP_CONF="$CL2_CONF" VAULT_BACKUP_SKIP_TIMEMACHINE=1 \
  bash "$SCRIPT" "$cl2_src" "$cl2_dst" >/dev/null 2>&1 ; rc=$?
[ "$rc" = 0 ] && pass "cloud vault WITH a surviving archive -> proceeds (rc=0)" \
             || fail "cloud vault with a surviving archive should proceed, got rc=$rc"
{ [ -d "$cl2_dst" ] && [ -L "$cl2_src" ]; } && pass "cloud+archive move-out: moved + symlink left" \
             || fail "cloud+archive: did not relocate"

echo
if [ "$fails" -gt 0 ]; then echo "FAILED: $fails"; exit 1; fi
echo "ALL TESTS PASSED"
