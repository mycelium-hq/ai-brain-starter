#!/usr/bin/env bash
# relocate-vault.sh — move a vault OUT of a consumer cloud-sync folder onto a
# local disk, leave a symlink so existing references keep resolving, AND migrate
# Claude Code's path-keyed state (session transcripts + the agent-memory symlink)
# so prior session history survives the move.
#
# WHY
# ---
# A git-backed Obsidian/AI-brain vault inside iCloud Drive / OneDrive / Dropbox /
# Google Drive / Box melts the OS sync daemon — the high-churn .git/ + per-session
# worktree checkouts generate millions of file events. The supported fix (Shape A
# in docs/CLOUD_SYNC.md) is to move the vault onto a local disk and leave a
# symlink. A RAW `mv` does the move but SILENTLY ORPHANS Claude Code history:
# Claude stores per-project state under <config>/projects/<key>, where <key> is
# the absolute cwd with every non-alphanumeric character replaced by '-'. Moving
# the vault changes the key, so every prior transcript reads "Session history
# unavailable ... no longer on disk" and the agent-memory symlink dangles. This
# helper does the move AND re-homes that state (copy, never move — old keys stay
# as a backup), so reopening Claude Code in the relocated vault shows the history.
#
# Pure bash + python3 (only for the key transform, to match Claude Code's
# char-wise semantics exactly). No third-party deps.
#
# Usage:
#   relocate-vault.sh <old-vault-path> <new-vault-path> [options]
#   relocate-vault.sh --migrate-claude-state <old-abs-path> <new-abs-path>
#     (state-only: the vault is already at the new path; just fix Claude history)
#
# Options:
#   --dry-run            print intended actions, change nothing
#   --no-symlink         do NOT leave a symlink at the old path (default leaves one)
#   --force              skip the soft gates (Obsidian-running, active-session).
#                        target-exists and source-already-a-symlink stay FATAL.
#   --config-dir <dir>   Claude Code config dir (default: $CLAUDE_CONFIG_DIR or ~/.claude)
#   -h, --help           this help
#
# Exit codes: 0 ok / no-op · 1 refused (gate) · 2 usage · 4 partial failure
set -euo pipefail

OLD="" ; NEW="" ; DRYRUN=0 ; FORCE=0 ; NOSYMLINK=0 ; MIGRATE_ONLY=0
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run|--dryrun) DRYRUN=1; shift;;
    --no-symlink) NOSYMLINK=1; shift;;
    --force) FORCE=1; shift;;
    --config-dir) CONFIG_DIR="${2:?--config-dir needs a path}"; shift 2;;
    --migrate-claude-state) MIGRATE_ONLY=1; shift;;
    -h|--help) sed -n '2,38p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    -*) echo "unknown option: $1" >&2; exit 2;;
    *) if [ -z "$OLD" ]; then OLD="$1"; elif [ -z "$NEW" ]; then NEW="$1"; else echo "unexpected arg: $1" >&2; exit 2; fi; shift;;
  esac
done

say()  { printf '%s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*" >&2; }
die()  { printf 'relocate-vault: REFUSE — %s\n' "$1" >&2; exit "${2:-1}"; }

# abspath/pathkey via python3 so the key transform matches Claude Code's JS
# `cwd.replace(/[^a-zA-Z0-9]/g, "-")` for spaces, dots, slashes, and the ⚙️
# variation-selector exactly. A byte-wise `sed` would mis-key multibyte paths.
abspath() { python3 -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$1"; }
# projkey: Claude Code's per-project dir name = the absolute cwd run through
# `replace(/[^A-Za-z0-9]/g, "-")`. cwd is the PHYSICAL path (getcwd resolves
# symlinks), so resolve the ANCESTRY — but NEVER follow a leaf symlink: post-move
# the old leaf IS the symlink we leave behind, and following it would key the new
# path. Resolve dirname, keep basename literal. Matches both before and after the
# move, and the two modes (full relocate / state-only) compute the same key.
projkey() { python3 -c 'import os,re,sys
p = os.path.abspath(os.path.expanduser(sys.argv[1]))
resolved = os.path.join(os.path.realpath(os.path.dirname(p)), os.path.basename(p))
print(re.sub(r"[^a-zA-Z0-9]", "-", resolved))' "$1"; }

# ---- migrate Claude Code path-keyed state (sessions + agent memory) -----------
# Copies <config>/projects/<oldkey>* -> <newkey>* (prefix swap preserves every
# sub-key suffix verbatim — worktree subdirs etc.) and re-homes the agent-memory
# symlink under the new base key. Copy, never move: old keys remain a backup.
# Fail LOUD when zero keys match (don't silently report "0 migrated").
migrate_claude_state() {  # $1=old-abs  $2=new-abs
  local old="$1" new="$2"
  local projdir="$CONFIG_DIR/projects"
  if [ ! -d "$projdir" ]; then
    say "  · no Claude Code projects dir ($projdir) — nothing to migrate"
    return 0
  fi
  local oldkey newkey
  oldkey="$(projkey "$old")"
  newkey="$(projkey "$new")"
  if [ "$oldkey" = "$newkey" ]; then
    say "  · old and new path keys are identical — nothing to migrate"
    return 0
  fi

  local matched=0 keys=0 files=0
  local d nb nd before after
  while IFS= read -r d; do
    [ -d "$d" ] || continue
    matched=$((matched + 1))
    nb="$(basename "$d" | sed "s#^${oldkey}#${newkey}#")"
    nd="$projdir/$nb"
    if [ "$DRYRUN" = 1 ]; then
      say "  · would migrate $(basename "$d") -> $nb"
      keys=$((keys + 1))
      continue
    fi
    mkdir -p "$nd"
    before="$(find "$nd" -maxdepth 1 -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' ')"
    find "$d" -maxdepth 1 -name '*.jsonl' -exec cp -np {} "$nd"/ \; 2>/dev/null || true
    after="$(find "$nd" -maxdepth 1 -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' ')"
    keys=$((keys + 1))
    files=$((files + after - before))
  done < <(find "$projdir" -maxdepth 1 -type d -name "${oldkey}*" 2>/dev/null)

  if [ "$matched" = 0 ]; then
    warn "  · no Claude Code session history found under old key '${oldkey}*' in $projdir."
    warn "    Nothing to migrate, OR the path-key encoding differs from what was expected —"
    warn "    inspect $projdir if you expected prior sessions here."
    return 0
  fi
  if [ "$DRYRUN" = 1 ]; then
    say "  · would migrate transcripts across $keys project key(s) -> new path key"
  else
    say "  · migrated $files transcript(s) across $keys project key(s) -> new path key"
  fi

  # Re-home the agent-memory symlink under the new base key. Prefer repointing
  # an existing old-key symlink (handles any memory layout); fall back to the
  # ai-brain-starter convention "⚙️ Meta/Agent Memory".
  local oldmem newmem target
  oldmem="$projdir/$oldkey/memory"
  newmem="$projdir/$newkey/memory"
  if [ ! -e "$newmem" ]; then
    if [ -L "$oldmem" ]; then
      target="$(readlink "$oldmem")"
      case "$target" in
        "$old"/*) target="$new/${target#"$old"/}";;
        "$old")   target="$new";;
      esac
    else
      target="$new/⚙️ Meta/Agent Memory"
    fi
    if [ -d "$target" ]; then
      if [ "$DRYRUN" = 1 ]; then
        say "  · would re-link agent-memory -> $target"
      else
        mkdir -p "$projdir/$newkey"
        ln -s "$target" "$newmem"
        say "  · agent-memory re-linked -> $target"
      fi
    fi
  fi
}

# =============================================================================
# state-only mode: the vault is already at the new path; just fix Claude history
# =============================================================================
if [ "$MIGRATE_ONLY" = 1 ]; then
  if [ -z "$OLD" ] || [ -z "$NEW" ]; then
    echo "usage: $(basename "$0") --migrate-claude-state <old-abs-path> <new-abs-path>" >&2
    exit 2
  fi
  OLD_ABS="$(abspath "$OLD")"
  NEW_ABS="$(abspath "$NEW")"
  say "relocate-vault: migrating Claude Code state only ($OLD_ABS -> $NEW_ABS)"
  migrate_claude_state "$OLD_ABS" "$NEW_ABS"
  exit 0
fi

# =============================================================================
# full relocate
# =============================================================================
if [ -z "$OLD" ] || [ -z "$NEW" ]; then
  echo "usage: $(basename "$0") <old-vault-path> <new-vault-path> [--dry-run] [--force] [--no-symlink]" >&2
  exit 2
fi
[ -e "$OLD" ] || die "source '$OLD' not found (already moved?)"
if [ -L "$OLD" ]; then die "source '$OLD' is already a symlink (already relocated?)"; fi
[ -d "$OLD" ] || die "source '$OLD' is not a directory"

OLD_ABS="$(cd "$OLD" && pwd -P)"   # physical path, BEFORE the move
NEW_ABS="$(abspath "$NEW")"
[ "$OLD_ABS" != "$NEW_ABS" ] || die "source and target are the same path"
if [ -e "$NEW_ABS" ]; then die "target '$NEW_ABS' already exists (will not overwrite)"; fi

# Soft gates — skippable with --force.
if [ "$FORCE" != 1 ]; then
  if command -v pgrep >/dev/null 2>&1 && pgrep -x Obsidian >/dev/null 2>&1; then
    die "Obsidian is running — quit it first (moving an open vault is unsafe), or pass --force"
  fi
  if [ -d "$OLD_ABS/.claude/worktrees" ]; then
    active="$(find "$OLD_ABS/.claude/worktrees" -type f -mmin -10 2>/dev/null | head -1 || true)"
    if [ -n "$active" ]; then
      die "an active Claude session is writing under .claude/worktrees (touched <10 min) — close it, or pass --force"
    fi
  fi
fi

say ""
say "relocate-vault: BACK UP FIRST. A vault is often your one irreplaceable asset."
say "  Stand up + VERIFY an off-machine backup before moving:"
say "    bash scripts/vault-backup.sh setup && bash scripts/vault-backup.sh verify"
say ""

if [ "$DRYRUN" = 1 ]; then
  say "DRY  would: mv '$OLD_ABS' -> '$NEW_ABS'"
  [ "$NOSYMLINK" = 1 ] || say "DRY  would: ln -s '$NEW_ABS' '$OLD_ABS'"
  migrate_claude_state "$OLD_ABS" "$NEW_ABS"
  say "DRY-RUN complete — no changes made."
  exit 0
fi

say "relocate-vault: moving '$OLD_ABS' -> '$NEW_ABS'"
mkdir -p "$(dirname "$NEW_ABS")"
mv "$OLD_ABS" "$NEW_ABS"
[ -d "$NEW_ABS" ] || die "POST: '$NEW_ABS' missing after move" 4

if [ "$NOSYMLINK" != 1 ]; then
  ln -s "$NEW_ABS" "$OLD_ABS"
  if [ -L "$OLD_ABS" ] && [ "$(readlink "$OLD_ABS")" = "$NEW_ABS" ]; then
    say "relocate-vault: left symlink '$OLD_ABS' -> '$NEW_ABS' (old references keep resolving; the sync daemon follows the tiny symlink, not the churn)"
  else
    warn "POST: expected symlink not in place at $OLD_ABS"
  fi
fi

say "relocate-vault: migrating Claude Code session history + agent memory ..."
migrate_claude_state "$OLD_ABS" "$NEW_ABS"

say ""
say "relocate-vault: DONE."
say "  - Vault now lives at:  $NEW_ABS   (outside the sync folder)"
[ "$NOSYMLINK" = 1 ] || say "  - Old path is a symlink: $OLD_ABS -> $NEW_ABS   (scripts/hooks/CLAUDE.md keep working)"
say "  - Reopen Obsidian; if it lost the vault, open $NEW_ABS"
say "  - Reopen Claude Code in the vault — prior sessions appear in the picker"
say "    (history was re-homed to the new path key; the old keys are kept as a backup)"
say "  - Re-run a backup against the new path:  VAULT_ROOT=\"$NEW_ABS\" bash scripts/vault-backup.sh"
