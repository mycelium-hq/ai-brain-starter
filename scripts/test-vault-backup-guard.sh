#!/usr/bin/env bash
# Negative-control test for check-vault-backup.py (the no-off-machine-backup guard).
# A guard earns trust only by failing on the thing it catches: this asserts
# NO_BACKUP (exit 1) for a bare local vault, and BACKED_UP (exit 0) for every
# real off-machine-copy path (configured archive, cloud-sync location).
# If it only ever passed, it would be worthless — so we assert BOTH polarities.
# Run: bash scripts/test-vault-backup-guard.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/check-vault-backup.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0

# Isolate from the real config + force a clean conf per case via $VAULT_BACKUP_CONF.
CONF="$TMP/conf.json"
export VAULT_BACKUP_CONF="$CONF"
echo '{}' > "$CONF"
# Neutralize the machine-wide Time Machine probe so "bare vault -> NO_BACKUP"
# is deterministic even when the test host itself has Time Machine configured.
export VAULT_BACKUP_SKIP_TIMEMACHINE=1

run() { # path  -> prints porcelain token, sets RC
  VAULT_BACKUP_CONF="$CONF" python3 "$CHECK" --porcelain "$1" 2>/dev/null
}

assert_token() { # label  want-prefix  path
  local label="$1" want="$2" p="$3" got
  got="$(run "$p")"
  case "$got" in
    "$want"*) echo "PASS  $label  ($got)";;
    *)        echo "FAIL  $label  want=$want got=$got"; fails=$((fails+1));;
  esac
}

assert_rc() { # label  want-rc  path
  local label="$1" want="$2" p="$3"
  run "$p" >/dev/null 2>&1; local rc=$?
  [ "$rc" = "$want" ] && echo "PASS  $label (rc=$rc)" || { echo "FAIL  $label want-rc=$want got-rc=$rc"; fails=$((fails+1)); }
}

# ---- NEGATIVE CONTROL: a bare local vault with no backup of any kind ----
# The lived-incident case: real notes, a single disk, nothing off-machine.
BARE="$TMP/Brain"
mkdir -p "$BARE"
echo "# a note" > "$BARE/note.md"
assert_token "bare local vault -> NO_BACKUP"  "NO_BACKUP"  "$BARE"
assert_rc    "NO_BACKUP exits 1"              1            "$BARE"

# ---- POSITIVE: vault-backup configured WITH a real archive in a reachable dest ----
DEST="$TMP/backups"
mkdir -p "$DEST"
RES="$(cd "$BARE" && pwd)"   # detector resolves the path; key the conf on the resolved form
# write a fake current archive for this vault
touch "$DEST/vault-backup-$(date +%Y%m%d).tar.gz"
cat > "$CONF" <<EOF
{"vaults": {"$RES": {"dest": "$DEST", "archive_stem": "vault-backup"}}}
EOF
assert_token "configured + archive -> BACKED_UP:vault-backup"  "BACKED_UP:vault-backup"  "$BARE"
assert_rc    "BACKED_UP exits 0"                                0                         "$BARE"

# ---- EDGE: configured but NO archive landed yet (or dest empty) -> still nudges ----
echo '{}' > "$CONF"
DEST2="$TMP/empty-dest"
mkdir -p "$DEST2"
cat > "$CONF" <<EOF
{"vaults": {"$RES": {"dest": "$DEST2", "archive_stem": "vault-backup"}}}
EOF
assert_token "configured, no archive -> NO_BACKUP:configured-not-run"  "NO_BACKUP:configured-not-run"  "$BARE"
assert_rc    "configured-not-run still exits 1"                         1                               "$BARE"

# ---- POSITIVE: a vault inside a cloud-sync root counts as an off-machine copy ----
echo '{}' > "$CONF"
CLOUD="$TMP/OneDrive/Brain"
mkdir -p "$CLOUD"
assert_token "cloud-sync vault -> BACKED_UP:cloud"  "BACKED_UP:cloud"  "$CLOUD"
assert_rc    "cloud-sync exits 0"                   0                  "$CLOUD"

# ---- --ignore-cloud (MYC-2401): a cloud-only copy does NOT count for a caller
# about to REMOVE it (relocate-vault.sh moves the vault out + leaves a symlink,
# so the cloud copy is gone post-move). The default still counts cloud (above);
# only --ignore-cloud flips it. A guard that approved a move citing the very copy
# the move destroys would leave the user with zero backup. ----
echo '{}' > "$CONF"
ic="$(VAULT_BACKUP_CONF="$CONF" python3 "$CHECK" --porcelain --ignore-cloud "$CLOUD" 2>/dev/null)"
case "$ic" in
  NO_BACKUP*) echo "PASS  --ignore-cloud: cloud-only vault -> $ic";;
  *)          echo "FAIL  --ignore-cloud: want NO_BACKUP got $ic"; fails=$((fails+1));;
esac
# --ignore-cloud must NOT suppress a REAL surviving backup (an archive present).
ICDEST="$TMP/ic-backups" ; mkdir -p "$ICDEST" ; touch "$ICDEST/vault-backup-$(date +%Y%m%d).tar.gz"
ICRES="$(cd "$CLOUD" && pwd -P)"
cat > "$CONF" <<EOF
{"vaults": {"$ICRES": {"dest": "$ICDEST", "archive_stem": "vault-backup"}}}
EOF
ic2="$(VAULT_BACKUP_CONF="$CONF" python3 "$CHECK" --porcelain --ignore-cloud "$CLOUD" 2>/dev/null)"
case "$ic2" in
  BACKED_UP:vault-backup*) echo "PASS  --ignore-cloud keeps a surviving archive -> $ic2";;
  *)                       echo "FAIL  --ignore-cloud suppressed a real archive: got $ic2"; fails=$((fails+1));;
esac

echo
if [ "$fails" -gt 0 ]; then echo "FAILED: $fails"; exit 1; fi
echo "ALL TESTS PASSED"
