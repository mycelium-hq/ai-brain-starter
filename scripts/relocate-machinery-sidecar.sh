#!/usr/bin/env bash
# relocate-machinery-sidecar.sh — make a vault SAFE to keep inside iCloud / a
# cloud-sync folder by moving every churning machinery dir OUT of the synced
# tree into a local sidecar, leaving only tiny static pointers/symlinks behind.
#
# WHY
# ---
# A git-backed Obsidian vault inside iCloud Drive / Desktop & Documents melts the
# OS sync daemon — NOT because of the notes (markdown is tiny + low-churn) but
# because of the MACHINERY: a `.git` rewritten wholesale on `git gc`, per-session
# worktree checkouts (~thousands of files each), and search/index caches. The
# fix is not "turn iCloud off". The fix is: the vault MAY be synced; the
# machinery NEVER is. This script relocates the machinery and leaves the docs.
#
# CRITICAL: `.gitignore` does NOT stop iCloud. iCloud syncs the folder, not
# git's view of it. The bytes must physically leave the synced tree (relocate +
# symlink) or be flagged `.nosync` (iCloud ignores any name ending in .nosync).
#
# WHAT IT MOVES
#   .git              -> <sidecar>/git    via `git init --separate-git-dir`
#                        (leaves a one-line `.git` POINTER FILE — static, safe)
#   .claude/worktrees -> <sidecar>/worktrees  (relocate + symlink; MYC-543 layer)
#   caches            -> <sidecar>/cache/<name> (relocate + symlink, or .nosync)
#                        .smart-env .codegraph "⚙️ Meta/graphify-out"
#                        "⚙️ Meta/Sessions" "⚙️ Meta/Worktree Snapshots"
#                        "⚙️ Meta/logs"  (only those that exist as REAL dirs)
#
# SEQUENCING GOTCHA (verified): `git init --separate-git-dir` ORPHANS existing
# linked worktrees. So this REFUSES to run while any linked worktree or live
# Claude session exists, unless --force. After relocation it runs
# `git worktree repair`.
#
# SAFETY: idempotent (re-run = no-op report), reversible (--rollback reads the
# manifest and puts everything back), --dry-run changes nothing, and it never
# deletes content — only moves it and leaves a symlink/pointer.
#
# Pure bash + git + python3 (manifest JSON only). No third-party deps.
#
# Usage:
#   relocate-machinery-sidecar.sh <vault-path> [options]
#   relocate-machinery-sidecar.sh <vault-path> --rollback
#
# Options:
#   --sidecar <dir>   sidecar root (default: $BRAIN_SIDECAR or ~/.brain-sidecar)
#   --nosync          keep caches in-tree as <name>.nosync (iCloud-ignored) +
#                     symlink, instead of relocating them to the sidecar
#   --dry-run         print intended actions, change nothing
#   --rollback        reverse a previous relocation using the manifest
#   --force           proceed even if linked worktrees / live sessions exist
#                     (DANGEROUS: separate-git-dir orphans live worktrees)
#   --quiet           only print warnings/errors + the final summary line
#   -h, --help        this help
#
# Exit codes: 0 ok / no-op · 1 refused (live worktree/session) · 2 usage ·
#             3 not a git vault and could not init · 4 partial failure
set -euo pipefail

# ---- machinery the script relocates (relative to the vault root) -------------
CACHE_DIRS=(
  ".smart-env"
  ".codegraph"
  "⚙️ Meta/graphify-out"
  "graphify-out"
  "⚙️ Meta/Sessions"
  "⚙️ Meta/Worktree Snapshots"
  "⚙️ Meta/logs"
  ".obsidian/.smart-env"
)
WORKTREES_REL=".claude/worktrees"

# ---- arg parse --------------------------------------------------------------
VAULT="" ; SIDECAR="${BRAIN_SIDECAR:-${MYCELIUM_SIDECAR:-$HOME/.brain-sidecar}}"
NOSYNC=0 ; DRYRUN=0 ; ROLLBACK=0 ; FORCE=0 ; QUIET=0
while [ $# -gt 0 ]; do
  case "$1" in
    --sidecar) SIDECAR="${2:?--sidecar needs a path}"; shift 2;;
    --nosync) NOSYNC=1; shift;;
    --dry-run|--dryrun) DRYRUN=1; shift;;
    --rollback) ROLLBACK=1; shift;;
    --force) FORCE=1; shift;;
    --quiet) QUIET=1; shift;;
    -h|--help) sed -n '2,55p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    -*) echo "unknown option: $1" >&2; exit 2;;
    *) if [ -z "$VAULT" ]; then VAULT="$1"; else echo "unexpected arg: $1" >&2; exit 2; fi; shift;;
  esac
done
[ -n "$VAULT" ] || { echo "usage: $(basename "$0") <vault-path> [options]" >&2; exit 2; }
[ -d "$VAULT" ] || { echo "not a directory: $VAULT" >&2; exit 2; }

# absolutize (portable realpath: cd + pwd -P)
VAULT="$(cd "$VAULT" && pwd -P)"
case "$SIDECAR" in /*) :;; ~*) SIDECAR="${SIDECAR/#\~/$HOME}";; *) SIDECAR="$PWD/$SIDECAR";; esac

# per-vault slug = sanitized basename + short abspath hash (collision-safe)
_base="$(basename "$VAULT")"
_slug="$(printf '%s' "$_base" | tr -c 'A-Za-z0-9._-' '-' | sed 's/-\{2,\}/-/g; s/^-//; s/-$//')"
_hash="$(printf '%s' "$VAULT" | (shasum 2>/dev/null || sha1sum) | cut -c1-8)"
SLUG="${_slug:-vault}-${_hash}"

SIDE_GIT="$SIDECAR/git/$SLUG"
SIDE_CACHE="$SIDECAR/cache/$SLUG"
SIDE_WT="$SIDECAR/worktrees/$SLUG"
MANIFEST="$SIDECAR/manifests/$SLUG.json"

say()  { [ "$QUIET" = 1 ] || printf '%s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*" >&2; }
err()  { printf 'ERROR %s\n' "$*" >&2; }
run()  { if [ "$DRYRUN" = 1 ]; then printf 'DRY   %s\n' "$*"; else eval "$@"; fi; }

# ---- manifest helpers (python3 for safe JSON over emoji/space paths) ---------
PYBIN="$(command -v python3 || command -v python || true)"
[ -n "$PYBIN" ] || { err "python3 required for the manifest"; exit 4; }

_manifest_records="$(mktemp)"   # TSV staging: type<TAB>vault_rel<TAB>target<TAB>mode
trap 'rm -f "$_manifest_records"' EXIT
record() { printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" >> "$_manifest_records"; }

write_manifest() {
  [ "$DRYRUN" = 1 ] && return 0
  mkdir -p "$(dirname "$MANIFEST")"
  VAULT="$VAULT" SIDECAR="$SIDECAR" SLUG="$SLUG" NOSYNC="$NOSYNC" \
  REC="$_manifest_records" MAN="$MANIFEST" "$PYBIN" - <<'PY'
import json, os
recs = []
with open(os.environ["REC"], encoding="utf-8") as f:
    for line in f:
        line = line.rstrip("\n")
        if not line:
            continue
        parts = line.split("\t")
        while len(parts) < 4:
            parts.append("")
        recs.append({"type": parts[0], "vault_rel": parts[1],
                     "target": parts[2], "mode": parts[3]})
doc = {
    "schema": "machinery-sidecar/1",
    "vault": os.environ["VAULT"],
    "sidecar": os.environ["SIDECAR"],
    "slug": os.environ["SLUG"],
    "nosync": os.environ["NOSYNC"] == "1",
    "moves": recs,
}
os.makedirs(os.path.dirname(os.environ["MAN"]), exist_ok=True)
with open(os.environ["MAN"], "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)
    f.write("\n")
PY
}

# ---- live-worktree / live-session guard -------------------------------------
linked_worktrees() {
  # Registered LINKED worktrees = every "worktree " porcelain block EXCEPT the
  # first (the first is always the MAIN worktree). Filtering by "!= $VAULT" is
  # WRONG after --separate-git-dir: git then reports the main worktree's path as
  # the separated gitdir, not the vault, so the main would masquerade as linked.
  git -C "$VAULT" worktree list --porcelain 2>/dev/null \
    | awk '/^worktree /{n++; if (n>1) print substr($0,10)}'
}
live_sessions() {
  local lock="$VAULT/.claude/.session-lock.json"
  [ -f "$lock" ] || return 0
  SELF_PID="$$" LOCK="$lock" "$PYBIN" - <<'PY'
import json, os, time
lock = os.environ["LOCK"]
try:
    data = json.load(open(lock, encoding="utf-8"))
except Exception:
    raise SystemExit(0)
sessions = data.get("sessions", {}) if isinstance(data, dict) else {}
cut = time.time() - 35 * 60
self_pid = int(os.environ.get("SELF_PID", "0") or 0)
n = 0
for s in sessions.values():
    if not isinstance(s, dict):
        continue
    pid = s.get("pid")
    la = s.get("last_activity_at")
    alive = False
    if isinstance(pid, int) and pid > 0 and pid != self_pid:
        try:
            os.kill(pid, 0); alive = True
        except ProcessLookupError:
            alive = False
        except Exception:
            alive = True
    recent = isinstance(la, (int, float)) and la >= cut
    if alive or recent:
        n += 1
print(n)
PY
}

guard_no_live() {
  local wts ; wts="$(linked_worktrees || true)"
  local sess ; sess="$(live_sessions || echo 0)"; sess="${sess:-0}"
  if [ -n "$wts" ] || [ "$sess" -gt 0 ] 2>/dev/null; then
    if [ "$FORCE" = 1 ]; then
      warn "linked worktrees and/or $sess live session(s) present — proceeding under --force (separate-git-dir will orphan live worktrees)"
      return 0
    fi
    err "refusing: relocation must run in a no-live-worktree window."
    [ -n "$wts" ] && { err "  linked worktrees still registered:"; printf '    %s\n' "$wts" >&2; }
    [ "$sess" -gt 0 ] 2>/dev/null && err "  $sess live Claude session(s) in $VAULT/.claude/.session-lock.json"
    err "  close all sessions + 'git worktree remove' scratch trees, then re-run. Override: --force"
    return 1
  fi
}

# =============================================================================
# ROLLBACK
# =============================================================================
do_rollback() {
  [ -f "$MANIFEST" ] || { err "no manifest at $MANIFEST — nothing to roll back"; exit 2; }
  say "Rolling back machinery sidecar for: $VAULT"
  say "  manifest: $MANIFEST"
  # iterate moves in REVERSE order
  MAN="$MANIFEST" "$PYBIN" - <<'PY' > "$_manifest_records"
import json, os
doc = json.load(open(os.environ["MAN"], encoding="utf-8"))
for m in reversed(doc.get("moves", [])):
    print("\t".join([m.get("type",""), m.get("vault_rel",""),
                     m.get("target",""), m.get("mode","")]))
PY
  local rc=0
  while IFS=$'\t' read -r typ rel target mode; do
    [ -n "$typ" ] || continue
    case "$typ" in
      git)
        local ptr="$VAULT/.git"
        if [ -f "$ptr" ] && [ -d "$target" ]; then
          run "rm -f \"$ptr\""
          run "mv \"$target\" \"$ptr\""
          run "git -C \"$VAULT\" config --unset core.worktree" || true
          run "git -C \"$VAULT\" worktree repair >/dev/null 2>&1" || true
          say "  restored .git (dir) from $target"
        else
          warn "  git rollback skipped (ptr present=$( [ -f "$ptr" ] && echo y || echo n ), gitdir present=$( [ -d "$target" ] && echo y || echo n ))"
        fi
        ;;
      cache|worktrees)
        local link="$VAULT/$rel"
        if [ -L "$link" ]; then run "rm -f \"$link\""; fi
        if [ "$mode" = "nosync" ]; then
          local ns="$VAULT/${rel}.nosync"
          [ -e "$ns" ] && run "mv \"$ns\" \"$link\"" || warn "  missing nosync source: $ns"
        else
          [ -e "$target" ] && run "mkdir -p \"$(dirname "$link")\" && mv \"$target\" \"$link\"" \
                           || warn "  missing sidecar source: $target"
        fi
        say "  restored $rel"
        ;;
    esac
  done < "$_manifest_records"
  if [ "$DRYRUN" != 1 ]; then run "rm -f \"$MANIFEST\""; fi
  say "Rollback complete."
  return $rc
}

# =============================================================================
# RELOCATE one cache/worktree dir (relocate+symlink, or nosync+symlink)
# =============================================================================
relocate_dir() {  # $1 = vault-relative path, $2 = explicit sidecar destination, $3 = record-type
  local rel="$1" dst="$2" rtype="$3"
  local src="$VAULT/$rel"
  if [ -L "$src" ]; then say "  · $rel already a symlink — skip"; return 0; fi
  if [ ! -e "$src" ]; then return 0; fi          # absent → nothing to do
  if [ "$NOSYNC" = 1 ]; then
    local ns="$VAULT/${rel}.nosync"
    if [ -e "$ns" ]; then warn "  · $rel.nosync already exists — skip"; return 0; fi
    run "mv \"$src\" \"$ns\""
    run "ln -s \"$(basename "$rel").nosync\" \"$src\""
    record "$rtype" "$rel" "$ns" "nosync"
    say "  · $rel -> ${rel}.nosync (iCloud-ignored) + symlink"
  else
    if [ -e "$dst" ]; then run "mv \"$dst\" \"$dst.bak-$(date +%s)\""; warn "  · prior sidecar copy at $dst backed up"; fi
    run "mkdir -p \"$(dirname "$dst")\""
    run "mv \"$src\" \"$dst\""
    run "ln -s \"$dst\" \"$src\""
    record "$rtype" "$rel" "$dst" "relocate"
    say "  · $rel -> $dst + symlink"
  fi
}

# =============================================================================
# RELOCATE .git via --separate-git-dir
# =============================================================================
relocate_git() {
  local gitpath="$VAULT/.git"
  if [ -f "$gitpath" ]; then
    local cur; cur="$(sed -n 's/^gitdir: //p' "$gitpath" | head -1)"
    say "  · .git already a pointer (-> ${cur:-?}) — skip"
    return 0
  fi
  if [ -d "$gitpath" ]; then
    run "mkdir -p \"$(dirname "$SIDE_GIT")\""
    run "git -C \"$VAULT\" init --separate-git-dir \"$SIDE_GIT\" >/dev/null"
    if [ "$DRYRUN" != 1 ] && [ ! -f "$gitpath" ]; then
      err "  separate-git-dir did not produce a .git pointer file"; return 4
    fi
    run "git -C \"$VAULT\" worktree repair >/dev/null 2>&1" || true
    record "git" ".git" "$SIDE_GIT" "separated"
    say "  · .git -> $SIDE_GIT (pointer file left in vault)"
    return 0
  fi
  # no .git at all → fresh repo with a separated gitdir
  run "mkdir -p \"$(dirname "$SIDE_GIT")\""
  run "git -C \"$VAULT\" init --separate-git-dir \"$SIDE_GIT\" >/dev/null"
  record "git" ".git" "$SIDE_GIT" "fresh-init"
  say "  · initialized fresh repo with gitdir at $SIDE_GIT"
}

# =============================================================================
# MAIN
# =============================================================================
if [ "$ROLLBACK" = 1 ]; then do_rollback; exit $?; fi

# detection is informational here — the whole point is iCloud is ALLOWED
CLOUD=""
if [ -f "$VAULT/.git" ] || command -v python3 >/dev/null; then :; fi
_sa="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$_sa/check-cloud-sync.py" ]; then
  CLOUD="$(python3 "$_sa/check-cloud-sync.py" --porcelain "$VAULT" 2>/dev/null || true)"
fi

say "Machinery-sidecar relocation"
say "  vault   : $VAULT"
say "  sidecar : $SIDECAR  (slug: $SLUG)"
case "$CLOUD" in
  CLOUD_SYNC_RISK*) say "  cloud   : ${CLOUD#CLOUD_SYNC_RISK:} — relocating machinery so the docs can sync safely";;
  OK_LOCAL)         say "  cloud   : local disk (machinery relocation still valid; reduces in-tree churn)";;
esac
[ "$NOSYNC" = 1 ] && say "  mode    : --nosync (caches stay in-tree as .nosync)"
[ "$DRYRUN" = 1 ] && say "  mode    : --dry-run (no changes)"

guard_no_live || exit 1

say "Relocating .git ..."
relocate_git || exit 4

say "Relocating worktrees ..."
relocate_dir "$WORKTREES_REL" "$SIDE_WT" "worktrees" || true

say "Relocating caches ..."
for rel in "${CACHE_DIRS[@]}"; do
  relocate_dir "$rel" "$SIDE_CACHE/$rel" "cache" || true
done

write_manifest
if [ "$DRYRUN" = 1 ]; then
  say "DRY-RUN complete — no changes made. Manifest would be: $MANIFEST"
else
  say "Done. Manifest: $MANIFEST"
  say "Reverse anytime: $(basename "$0") \"$VAULT\" --rollback"
fi
