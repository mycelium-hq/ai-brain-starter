#!/usr/bin/env bash
# vault-backup.sh — one-command, provider-agnostic, off-machine backup for a brain vault.
#
# The gap this closes: a brain in active daily use whose only copy is the local
# disk it runs on. The hourly git auto-snapshot is LOCAL-only (it refuses to run
# with a remote) — so without this, "I have snapshots" still means one disk
# failure = everything gone. This writes ONE compressed archive per run to a
# destination you already have (an external disk, or a Google Drive / Dropbox /
# OneDrive folder — your choice), so it is genuinely off-machine. One file, not
# the churning git object tree, so a cloud folder syncs it without a storm.
#
#   setup   pick a destination (+ optional encryption + a daily schedule), then
#           take the first snapshot immediately.
#   run     take one snapshot now (what the schedule calls; non-interactive).
#   verify  restore the newest snapshot to a temp dir and confirm it actually
#           extracts — a backup you have never restored is a hope, not a backup.
#   status  show where backups go, how fresh they are, and the canonical verdict.
#
# Provider-agnostic: the destination is any folder path you give it. Encryption
# (--encrypt) is optional and uses gpg (or openssl) with the passphrase stored
# in your OS keychain, never in plaintext. Pure POSIX-ish bash + python3 for the
# small JSON bits (python3 is already a hard dependency of this repo).
#
# Usage:
#   bash vault-backup.sh setup  [--vault PATH] [--dest DIR] [--encrypt] [--keep N] [--schedule daily|none]
#   bash vault-backup.sh run    [--vault PATH]
#   bash vault-backup.sh verify [--vault PATH]
#   bash vault-backup.sh status [--vault PATH]
#
# Config:  ~/.claude/.vault-backup.conf  (JSON, keyed by resolved vault path)
# Marker:  ~/.claude/.vault-backup-last  (ISO8601 of the last successful run)
set -uo pipefail

CONF="${VAULT_BACKUP_CONF:-$HOME/.claude/.vault-backup.conf}"
MARKER="${VAULT_BACKUP_MARKER:-$HOME/.claude/.vault-backup-last}"
KEYCHAIN_SERVICE="ai-brain-starter-vault-backup"
ARCHIVE_STEM="vault-backup"

# Dirs that are regenerable machine-exhaust — never worth backing up, and the
# exact churn that would bloat the archive. Notes + .git history are kept.
EXCLUDES=(
  "./.claude/worktrees" "./.smart-env" "./.codegraph" "./node_modules"
  "./.venv" "./__pycache__" "./.pytest_cache" "./.mypy_cache" "./.ruff_cache"
  "./.trash" "./.DS_Store"
)

# ---------- tiny ui helpers (no-op color if not a tty) ----------
if [ -t 1 ]; then G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; B=$'\033[1m'; N=$'\033[0m'
else G=''; Y=''; R=''; B=''; N=''; fi
say()  { echo "$*"; }
ok()   { echo "${G}OK${N}   $*"; }
warn() { echo "${Y}WARN${N} $*"; }
die()  { echo "${R}ERROR${N} $*" >&2; exit 1; }

iso_now() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

# ---------- json conf helpers (python3 is a repo dependency) ----------
conf_get() { # <vault-key> <field> -> value or empty
  python3 - "$CONF" "$1" "$2" <<'PY'
import json, sys
conf_path, key, field = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    d = json.load(open(conf_path))
except Exception:
    print(""); sys.exit(0)
e = (d.get("vaults") or {}).get(key) or {}
v = e.get(field, "")
print(v if v is not None else "")
PY
}

conf_set() { # <vault-key> <field=value>...  (values are strings unless int/bool-looking)
  local key="$1"; shift
  python3 - "$CONF" "$key" "$@" <<'PY'
import json, os, sys
conf_path, key = sys.argv[1], sys.argv[2]
pairs = sys.argv[3:]
try:
    d = json.load(open(conf_path))
except Exception:
    d = {}
d.setdefault("vaults", {})
e = d["vaults"].get(key, {})
for p in pairs:
    f, _, v = p.partition("=")
    if v in ("true", "false"):
        e[f] = (v == "true")
    elif v.isdigit():
        e[f] = int(v)
    else:
        e[f] = v
d["vaults"][key] = e
os.makedirs(os.path.dirname(conf_path), exist_ok=True)
tmp = conf_path + ".tmp"
json.dump(d, open(tmp, "w"), indent=2)
os.replace(tmp, conf_path)
PY
}

realpath_py() { python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"; }

slug_for() { # <vault-path> -> stable short slug for keychain acct / plist name
  local base hash
  base="$(basename "$1" | tr ' /' '__')"
  hash="$(printf '%s' "$1" | (md5 2>/dev/null || md5sum 2>/dev/null) | tr -d ' -' | cut -c1-8)"
  printf '%s-%s' "$base" "$hash"
}

# ---------- vault resolution ----------
resolve_vault() { # echoes resolved vault path; dies if not a dir
  local v="${1:-}"
  if [ -z "$v" ]; then v="${VAULT_PATH:-$PWD}"; fi
  [ -d "$v" ] || die "vault path is not a directory: $v"
  realpath_py "$v"
}

# ---------- passphrase (keychain-backed) ----------
store_passphrase() { # <slug> <passphrase>
  local acct="$1" pass="$2"
  if command -v security >/dev/null 2>&1; then        # macOS Keychain
    security add-generic-password -a "$acct" -s "$KEYCHAIN_SERVICE" -w "$pass" -U >/dev/null 2>&1 \
      && { echo "keychain"; return 0; }
  fi
  if command -v secret-tool >/dev/null 2>&1; then      # Linux libsecret
    printf '%s' "$pass" | secret-tool store --label="$KEYCHAIN_SERVICE" \
      service "$KEYCHAIN_SERVICE" account "$acct" >/dev/null 2>&1 \
      && { echo "secret-tool"; return 0; }
  fi
  # Fallback: 0600 file. Loud about it — this is weaker than a keychain.
  local pf="$HOME/.claude/.vault-backup-pass-$acct"
  ( umask 077; printf '%s' "$pass" > "$pf" )
  warn "No OS keychain found; passphrase stored in $pf (chmod 600). A keychain is safer." >&2
  echo "file:$pf"
}

get_passphrase() { # <slug> <store-kind> -> passphrase on stdout (non-interactive)
  local acct="$1" kind="$2"
  case "$kind" in
    keychain)     security find-generic-password -a "$acct" -s "$KEYCHAIN_SERVICE" -w 2>/dev/null ;;
    secret-tool)  secret-tool lookup service "$KEYCHAIN_SERVICE" account "$acct" 2>/dev/null ;;
    file:*)       cat "${kind#file:}" 2>/dev/null ;;
    *)            return 1 ;;
  esac
}

# ---------- the archive ----------
make_archive() { # <vault> <out-base-no-ext> <encrypt 0|1> <slug> <store-kind> -> echoes final path
  local vault="$1" outbase="$2" enc="$3" acct="$4" kind="$5"
  local excl=() e
  for e in "${EXCLUDES[@]}"; do excl+=("--exclude=$e"); done
  # Always exclude any prior archives that happen to live under the vault.
  excl+=("--exclude=./*.tar.gz" "--exclude=./*.tar.gz.gpg" "--exclude=./*.tar.gz.enc")

  if [ "$enc" = "1" ]; then
    local pass; pass="$(get_passphrase "$acct" "$kind")"
    [ -n "$pass" ] || die "could not read backup passphrase from $kind"
    if command -v gpg >/dev/null 2>&1; then
      local out="$outbase.tar.gz.gpg"
      tar -cz "${excl[@]}" -C "$vault" . 2>/dev/null \
        | gpg --batch --yes --pinentry-mode loopback --passphrase "$pass" \
              -c --cipher-algo AES256 -o "$out" 2>/dev/null \
        && { echo "$out"; return 0; }
      die "gpg encryption failed"
    elif command -v openssl >/dev/null 2>&1; then
      local out="$outbase.tar.gz.enc"
      tar -cz "${excl[@]}" -C "$vault" . 2>/dev/null \
        | openssl enc -aes-256-cbc -pbkdf2 -salt -pass "pass:$pass" -out "$out" 2>/dev/null \
        && { echo "$out"; return 0; }
      die "openssl encryption failed"
    else
      die "--encrypt needs gpg or openssl; neither found"
    fi
  else
    local out="$outbase.tar.gz"
    tar -czf "$out" "${excl[@]}" -C "$vault" . 2>/dev/null && { echo "$out"; return 0; }
    die "tar failed"
  fi
}

rotate() { # <dest> <keep>
  local dest="$1" keep="$2" f
  # newest-first; delete everything past $keep
  ls -1t "$dest"/$ARCHIVE_STEM-* 2>/dev/null | tail -n +"$((keep+1))" | while IFS= read -r f; do
    [ -n "$f" ] && rm -f "$f"
  done
}

human_size() { # <file>
  if [ "$(uname)" = "Darwin" ]; then stat -f %z "$1" 2>/dev/null; else stat -c %s "$1" 2>/dev/null; fi \
    | awk '{ s=$1; u="B"; if(s>1073741824){s/=1073741824;u="GB"} else if(s>1048576){s/=1048576;u="MB"} else if(s>1024){s/=1024;u="KB"} printf "%.1f%s", s, u }'
}

# ============================ subcommands ============================

cmd_setup() {
  local vault="" dest="" encrypt=0 keep=7 schedule="daily"
  while [ $# -gt 0 ]; do
    case "$1" in
      --vault) vault="$2"; shift 2;;
      --dest) dest="$2"; shift 2;;
      --encrypt) encrypt=1; shift;;
      --keep) keep="$2"; shift 2;;
      --schedule) schedule="$2"; shift 2;;
      *) die "unknown setup arg: $1";;
    esac
  done
  vault="$(resolve_vault "$vault")"
  say "${B}Backing up:${N} $vault"

  # Destination — prompt if not given.
  if [ -z "$dest" ]; then
    say ""
    say "Where should the off-machine backup go? Give a folder you already have"
    say "somewhere OTHER than this machine's single disk — an external drive, or a"
    say "Google Drive / Dropbox / OneDrive folder (one daily file syncs fine; it is"
    say "the churning vault that must not go in cloud sync, not a single archive)."
    printf "Destination folder: "
    read -r dest
    [ -n "$dest" ] || die "no destination given"
  fi
  # Expand ~ and resolve.
  dest="${dest/#\~/$HOME}"
  mkdir -p "$dest" 2>/dev/null || die "could not create destination: $dest"
  dest="$(realpath_py "$dest")"

  # Refuse a destination INSIDE the vault — that is not off-machine at all.
  case "$dest/" in
    "$vault/"*) die "destination is inside the vault ($dest). Pick a folder off this machine.";;
  esac
  # Nudge (don't block) if the destination is not obviously off-machine.
  if printf '%s' "$dest" | grep -Eq '/(OneDrive|Dropbox|Google ?Drive|CloudStorage|Box|Mobile Documents)/|/Volumes/'; then
    ok "Destination looks off-machine (cloud folder or external volume)."
  else
    warn "Destination $dest may be on this same disk. That protects against accidental"
    warn "deletion but NOT against disk failure. An external drive or cloud folder is safer."
  fi

  local slug store_kind=""; slug="$(slug_for "$vault")"

  # Encryption passphrase (stored in keychain), if requested.
  if [ "$encrypt" = "1" ]; then
    command -v gpg >/dev/null 2>&1 || command -v openssl >/dev/null 2>&1 \
      || die "--encrypt needs gpg or openssl installed"
    local p1 p2
    printf "Set a backup passphrase (kept in your OS keychain, never in plaintext): "
    read -rs p1; echo
    printf "Confirm passphrase: "
    read -rs p2; echo
    [ -n "$p1" ] || die "empty passphrase"
    [ "$p1" = "$p2" ] || die "passphrases do not match"
    store_kind="$(store_passphrase "$slug" "$p1")"
    ok "Passphrase stored ($store_kind). Daily runs read it from there, no prompt."
  fi

  # Persist config.
  conf_set "$vault" \
    "dest=$dest" "archive_stem=$ARCHIVE_STEM" "encrypt=$([ "$encrypt" = 1 ] && echo true || echo false)" \
    "keep=$keep" "keychain_account=$slug" "store_kind=$store_kind"
  ok "Saved config -> $CONF"

  # First snapshot immediately, so there is no configured-but-empty gap.
  say ""
  say "${B}Taking the first snapshot...${N}"
  cmd_run --vault "$vault" || die "first snapshot failed"

  # Schedule the daily run.
  if [ "$schedule" = "daily" ]; then
    install_schedule "$vault" "$slug" && ok "Daily backup scheduled (03:00 local)." \
      || warn "Could not install an automatic schedule; run \`vault-backup.sh run\` yourself or add a cron job."
  else
    say "No schedule installed (--schedule none). Run \`vault-backup.sh run\` when you want a snapshot."
  fi

  say ""
  ok "${B}Backup is live.${N} Now prove it restores (do this once):"
  say "    bash $0 verify --vault \"$vault\""
}

cmd_run() {
  local vault=""
  while [ $# -gt 0 ]; do case "$1" in --vault) vault="$2"; shift 2;; *) shift;; esac; done
  vault="$(resolve_vault "$vault")"
  local dest; dest="$(conf_get "$vault" dest)"
  [ -n "$dest" ] || die "vault not configured for backup. Run: bash $0 setup --vault \"$vault\""
  [ -d "$dest" ] || die "backup destination is unreachable: $dest (external disk unplugged?)"
  local enc encbool keep slug kind
  encbool="$(conf_get "$vault" encrypt)"; enc=$([ "$encbool" = "True" ] || [ "$encbool" = "true" ] && echo 1 || echo 0)
  keep="$(conf_get "$vault" keep)"; [ -n "$keep" ] || keep=7
  slug="$(conf_get "$vault" keychain_account)"; [ -n "$slug" ] || slug="$(slug_for "$vault")"
  kind="$(conf_get "$vault" store_kind)"

  local stamp outbase out
  stamp="$(date +%Y%m%d-%H%M%S)"
  outbase="$dest/$ARCHIVE_STEM-$stamp"
  out="$(make_archive "$vault" "$outbase" "$enc" "$slug" "$kind")" || exit 1

  # Integrity sanity-check before declaring success.
  local sz; sz="$(human_size "$out")"
  if [ "$enc" = "0" ]; then
    tar -tzf "$out" >/dev/null 2>&1 || { rm -f "$out"; die "archive failed integrity check (corrupt tar.gz)"; }
  else
    # Can't list without decrypting; assert it is non-trivially sized.
    local bytes; bytes="$(if [ "$(uname)" = Darwin ]; then stat -f %z "$out"; else stat -c %s "$out"; fi)"
    [ "${bytes:-0}" -gt 256 ] || { rm -f "$out"; die "encrypted archive is suspiciously small"; }
  fi

  rotate "$dest" "$keep"
  conf_set "$vault" "last=$(iso_now)"
  ( umask 077; iso_now > "$MARKER" ) 2>/dev/null || true
  ok "Snapshot: $out ($sz)"
}

cmd_verify() {
  local vault=""
  while [ $# -gt 0 ]; do case "$1" in --vault) vault="$2"; shift 2;; *) shift;; esac; done
  vault="$(resolve_vault "$vault")"
  local dest; dest="$(conf_get "$vault" dest)"
  [ -n "$dest" ] || die "vault not configured. Run setup first."
  local newest
  newest="$(ls -1t "$dest"/$ARCHIVE_STEM-* 2>/dev/null | head -1)"
  [ -n "$newest" ] || die "no snapshot found in $dest. Run: bash $0 run --vault \"$vault\""

  local tmp; tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  say "Restoring ${B}$newest${N} to a temp dir to prove it actually works..."

  case "$newest" in
    *.tar.gz)
      tar -xzf "$newest" -C "$tmp" 2>/dev/null || die "restore FAILED: archive did not extract" ;;
    *.tar.gz.gpg)
      local slug kind pass; slug="$(conf_get "$vault" keychain_account)"; kind="$(conf_get "$vault" store_kind)"
      pass="$(get_passphrase "$slug" "$kind")"; [ -n "$pass" ] || die "no passphrase to decrypt"
      gpg --batch --yes --pinentry-mode loopback --passphrase "$pass" -d "$newest" 2>/dev/null \
        | tar -xz -C "$tmp" 2>/dev/null || die "restore FAILED: could not decrypt + extract" ;;
    *.tar.gz.enc)
      local slug kind pass; slug="$(conf_get "$vault" keychain_account)"; kind="$(conf_get "$vault" store_kind)"
      pass="$(get_passphrase "$slug" "$kind")"; [ -n "$pass" ] || die "no passphrase to decrypt"
      openssl enc -d -aes-256-cbc -pbkdf2 -pass "pass:$pass" -in "$newest" 2>/dev/null \
        | tar -xz -C "$tmp" 2>/dev/null || die "restore FAILED: could not decrypt + extract" ;;
    *) die "unrecognized archive type: $newest" ;;
  esac

  local count; count="$(find "$tmp" -type f 2>/dev/null | wc -l | tr -d ' ')"
  [ "$count" -gt 0 ] || die "restore produced ZERO files — the backup is empty/broken"
  # Prefer a meaningful sentinel if the vault has one.
  local sentinel=""
  [ -f "$tmp/CLAUDE.md" ] && sentinel="CLAUDE.md"
  conf_set "$vault" "last_verify=$(iso_now)"
  ok "Restore verified: extracted $count file(s)${sentinel:+, $sentinel present}. Your backup actually restores."
}

cmd_status() {
  local vault=""
  while [ $# -gt 0 ]; do case "$1" in --vault) vault="$2"; shift 2;; *) shift;; esac; done
  vault="$(resolve_vault "$vault")"
  say "${B}Vault:${N} $vault"
  local dest; dest="$(conf_get "$vault" dest)"
  if [ -z "$dest" ]; then
    warn "No backup configured for this vault."
    say  "Set one up: bash $0 setup --vault \"$vault\""
  else
    say "${B}Destination:${N} $dest $([ -d "$dest" ] && echo "(reachable)" || echo "${R}(UNREACHABLE)${N}")"
    say "${B}Encrypted:${N}   $(conf_get "$vault" encrypt)    ${B}Keep:${N} $(conf_get "$vault" keep)"
    local last lastv n
    last="$(conf_get "$vault" last)"; lastv="$(conf_get "$vault" last_verify)"
    n="$(ls -1 "$dest"/$ARCHIVE_STEM-* 2>/dev/null | wc -l | tr -d ' ')"
    say "${B}Snapshots:${N}   ${n:-0} in destination"
    say "${B}Last run:${N}    ${last:-never}"
    say "${B}Last verify:${N} ${lastv:-never  (run: bash $0 verify)}"
  fi
  # Canonical verdict from the single source of truth.
  local checker; checker="$(cd "$(dirname "$0")" && pwd)/check-vault-backup.py"
  [ -f "$checker" ] && { say ""; python3 "$checker" "$vault" || true; }
}

# ---------- scheduling ----------
install_schedule() { # <vault> <slug>  -> 0 on success
  local vault="$1" slug="$2" self
  self="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
  case "$(uname)" in
    Darwin)
      local label="com.ai-brain-starter.vault-backup.$slug"
      local plist="$HOME/Library/LaunchAgents/$label.plist"
      mkdir -p "$HOME/Library/LaunchAgents"
      cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string><string>$self</string>
    <string>run</string><string>--vault</string><string>$vault</string>
  </array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardErrorPath</key><string>$HOME/.claude/.vault-backup.log</string>
  <key>StandardOutPath</key><string>$HOME/.claude/.vault-backup.log</string>
</dict></plist>
EOF
      launchctl bootstrap "gui/$(id -u)" "$plist" >/dev/null 2>&1 \
        || launchctl load "$plist" >/dev/null 2>&1 || true
      [ -f "$plist" ]
      ;;
    Linux)
      command -v crontab >/dev/null 2>&1 || return 1
      local line="0 3 * * * /bin/bash $self run --vault '$vault' >> \$HOME/.claude/.vault-backup.log 2>&1"
      local cur; cur="$(crontab -l 2>/dev/null)"
      printf '%s' "$cur" | grep -Fq "vault-backup.sh run --vault '$vault'" && return 0
      { printf '%s\n' "$cur"; printf '%s\n' "$line"; } | crontab - 2>/dev/null
      ;;
    *) return 1;;
  esac
}

# ============================ dispatch ============================
CMD="${1:-status}"; shift 2>/dev/null || true
case "$CMD" in
  setup)  cmd_setup "$@";;
  run)    cmd_run "$@";;
  verify) cmd_verify "$@";;
  status) cmd_status "$@";;
  -h|--help|help)
    sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) die "unknown command: $CMD (use setup|run|verify|status)";;
esac
