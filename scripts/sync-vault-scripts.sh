#!/bin/bash
# exit-contract: NOT-A-CHECKER -- copies repo scripts into a vault; a
#   deployer

# sync-vault-scripts.sh — propagate updated vault-side scripts from the
# ai-brain-starter repo into the user's vault  <meta>/scripts/  directory.
#
# WHY THIS EXISTS
#   A vault's "<meta>/scripts/" folder is populated ONCE, at setup, by the
#   setup phases (Phase 5 copies the aggregators + graph hook, Phase 18 the
#   journal index, etc.). It is never re-synced. So when the repo ships a new
#   or fixed vault script — session-close-runner.sh, check-rule-conflicts.py,
#   drift-detection.py, passive-capture.py, … — it never reaches EXISTING
#   vaults. scripts/sync-skills.sh only syncs skill->~/.claude/skills; this is
#   the missing skill->vault half.
#
# CONTRACT (mirrors sync-skills.sh so the two behave identically)
#   - Idempotent: identical dest = no-op (no noise).
#   - Non-destructive: a dest that DIFFERS from the incoming repo file is backed
#     up to <file>.bak-YYYY-MM-DD-HHMM BEFORE being overwritten — local edits
#     are always recoverable.
#   - Maintainer-safe: a symlinked dest (live-editing the skill repo from the
#     vault) is skipped, never clobbered.
#   - Source-absent is non-fatal: a manifest entry not yet on this checkout
#     (e.g. session-close-runner.sh before #173 merges) is simply skipped.
#
# VAULT RESOLUTION (so it can run with zero args from the auto-update flow):
#   1. --vault PATH
#   2. $VAULT_ROOT
#   3. parse ~/.claude/settings.json — the installed hooks embed the vault path
#      (e.g. "<vault>/⚙️ Meta/scripts/session-end-hook.sh")
#   If none resolve, this is a NON-FATAL no-op (logs the reason, exits 0): a box
#   with no vault set up yet must not error during an auto-update.
#
# THE SOURCE MUST BE TRUSTWORTHY  ($ABS_CLONE_PATCHES_STASHED)
#   This script's whole job is "the repo is newer than the vault, push the repo
#   version". That is only true when the repo checkout actually holds what the
#   user expects it to hold.
#
#   bootstrap auto-stashes local uncommitted changes before its `git pull`. For
#   the ~40 seconds that follow, the checkout is a pristine origin/main with the
#   user's patches REMOVED — and running this script in that window copies the
#   UNPATCHED file over the patched one in the vault. Reported on Windows:
#   session-close-runner.sh and vault-safe-commit.sh in "⚙️ Meta/scripts" were
#   both reverted this way. The .bak is written faithfully and holds the good
#   version, which is precisely why nobody notices: the run reports "Updated: 2"
#   like any healthy update, and the regression is only visible by diffing a
#   backup nobody has a reason to open.
#
#   So bootstrap exports ABS_CLONE_PATCHES_STASHED=<stash message> around the
#   pull, and this script refuses to propagate while it is set. Stale-but-
#   working beats silently-regressed. The guard lives HERE rather than at the
#   call site because there are three call paths (bootstrap.ps1 directly,
#   bootstrap.sh -> sync-skills.sh -> sync-skills.py, and manual runs) and a
#   fourth would not know to re-implement it.
#
# USAGE
#   bash sync-vault-scripts.sh [--vault PATH] [--dry-run] [--quiet]
#
# EXIT: 0 = clean / nothing to do / vault not resolvable / source untrustworthy
#       (all non-fatal); 2 = a real copy or backup error occurred.

# Intentionally NOT using `set -u` — macOS bash 3.2 treats empty-array expansion
# as "unbound", which would false-positive on a clean first run (same reason as
# sync-skills.sh). pipefail is safe.
set -o pipefail

# Source repo = the checkout this script lives in (scripts/..), so it works from
# the installed skill, a dev checkout, or CI alike. $STARTER_DIR overrides.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STARTER_DIR="${STARTER_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
STAMP="$(date +%Y-%m-%d-%H%M)"
DRY_RUN=0
QUIET=0
VAULT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --vault) VAULT="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --quiet) QUIET=1; shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "sync-vault-scripts.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

# --- Manifest: the scripts a RUNNING vault invokes from <meta>/scripts/. ------
# EXPLICIT allow-list, never a glob over scripts/ (which is mostly repo tooling
# — ci.sh, install-*.py, test-*.sh — that must NEVER land in a vault). Every
# entry must be import-closed: stdlib-only, OR its local-module dependencies are
# listed here too, else it crashes at runtime in the vault. The self-test
# tests/integration/test_vault_script_sync.sh enforces import-closure.
VAULT_SCRIPTS=(
  "_meta_resolver.py"          # shared meta-folder resolver (deterministic keystone)
  "_project_key.py"            # shared project-key resolver (dep of check-rule-conflicts.py)
  "_floors.py"                 # shared floor vocabulary (dep of build-journal-index.py)
  "_session_close_guard.sh"    # shared git-dir/index-lock resolver — sourced by BOTH
                               # vault-safe-commit.sh and session-end-hook.sh. Omitting
                               # it shipped the consumers without their dependency: the
                               # commit wrapper fell to a fail-closed stub and EVERY vault
                               # commit refused (it is the only route past the raw-git
                               # block guard), while session-end-hook fell to "defer" and
                               # silently no-opped every session-end snapshot. Section 1b
                               # of test_vault_script_sync.sh now fails on this class.
  "aggregate-sessions.py"      # session-close: Last Session.md index
  "aggregate-decisions.py"     # session-close: Decision Log index
  "session-close-runner.sh"    # session-close: deterministic aggregation runner (#173)
  "vault-safe-commit.sh"       # session-close: targeted-path commit helper
  "session-end-hook.sh"        # Stop-hook body
  "write-hook.sh"              # PostToolUse(Write)-hook body
  "graph-context-hook.sh"      # UserPromptSubmit graph-routing hook body
  "build-journal-index.py"     # insights: journal index builder
  "journal-preflight.py"       # daily-journal Step 0: pulls every context source (stdlib-only; message/rescuetime fetchers optional, degrades honestly)
  "check-rule-conflicts.py"    # rule maintenance
  "drift-detection.py"         # rule / CLAUDE.md drift detection
  "passive-capture.py"         # instinct-engine passive capture (opt-in)
)

CREATED=(); UPDATED=(); BACKED_UP=(); SKIPPED=(); ABSENT=(); ERRORS=()

note() { [ "$QUIET" -eq 1 ] || echo "$1"; }

# --- REFUSE to propagate from a knowingly-degraded checkout --------------------
# See "THE SOURCE MUST BE TRUSTWORTHY" in the header. Deliberately printed even
# under --quiet: the whole failure mode is that this step looks like a normal
# update, and bootstrap calls it with --quiet.
if [ -n "${ABS_CLONE_PATCHES_STASHED:-}" ]; then
  echo "sync-vault-scripts: SKIPPED — not propagating to the vault."
  echo "  This bootstrap run stashed your local changes to $STARTER_DIR before"
  echo "  pulling, so the scripts here are currently the UNPATCHED upstream copies."
  echo "  Copying them into the vault would overwrite your patched vault scripts"
  echo "  with the versions you patched them to fix. Your vault is untouched."
  echo "  Your changes are in: git stash -> ${ABS_CLONE_PATCHES_STASHED}"
  echo "  To restore them and then sync the vault:"
  echo "    cd \"$STARTER_DIR\" && git stash pop && bash scripts/sync-vault-scripts.sh"
  exit 0
fi

# --- pick a REAL python interpreter -------------------------------------------
# Under git-bash / MSYS on Windows a bare `python3` on PATH is usually the
# Microsoft Store app-execution-alias shim: it satisfies `command -v`, but
# prints nothing and pops the Store, so the resolver call came back EMPTY and
# this script misread it as "no Meta folder" and silently no-opped (issue
# #375). Trust only a candidate that actually reports major version 3. (The
# .ps1 twin, #313, still probes py/python/python3 with `-c`.)
#
# The same failure has a second cause on macOS/Linux: a Claude Code plugin can
# put a WRAPPER named `python3` (and `python`) ahead of the real interpreter on
# PATH. trailofbits/modern-python refuses the call outright ("Use
# `uv run python3 ...` instead"). Both candidates then satisfy `command -v`,
# both fail the probe, `py` does not exist off Windows, and PY_CMD ended up
# EMPTY: the script reported "no vault resolved" or "no Meta folder", called it
# non-fatal and exited 0, and its automated callers pass --quiet, so not even
# that line showed. journal-preflight.py never reached the vault, leaving the
# /journal Step-0 guard asking for a script that had never shipped (measured
# 2026-08-30).
#
# The ladder follows pick_python() in bootstrap.sh. AI_BRAIN_PYTHON comes
# first, read as ONE path the way bootstrap reads it (spaces included), and is
# reported when it does not work. Then the bare names, then VERSIONED names,
# which the shim dir does not ship (it carries python, python3, pip, pip3, pipx
# and uv), then the usual absolute install locations, each skipped where it
# does not exist, so a Mac whose only real Python is the system one is still
# found. A path already probed with the same arguments is not probed again:
# bare `python3` is often /usr/bin/python3, which the ladder also names
# outright. Unlike bootstrap it
# keeps `python` and the Windows `py` launcher and accepts any 3.x, as the code
# it replaced did. The launcher's `-3` lives in PY_ARGS, so PY_CMD stays a
# single path that callers quote.
#
# The probe runs a FILE, never `-c` or `-`: the asymmetric shim shape
# documented in tests/integration/lib/real_python.sh forwards `-c`/`-`/`-m` to
# the real interpreter and refuses only a script path, so a `-c` probe would
# ADOPT such a wrapper and then die at the `_meta_resolver.py` call below. The
# sentinel, not the exit code, is what decides -- a wrapper that exits 0
# without running the file never prints it and is rejected. When no probe
# file can be written (mktemp on a stale TMPDIR, a full or read-only temp dir)
# it says so and probes on stdin instead of giving up: weaker, but no worse
# than the `-c` probe this replaced, which needed no file at all.
PY_CMD=""
PY_ARGS=""
_probe_python() {  # $1 interpreter path, $2 "" or "-3", $3 probe file ("" = stdin)
  local out
  if [ -n "$3" ]; then
    # shellcheck disable=SC2086  # $2 is "" or "-3"; word-splitting intended
    out="$("$1" $2 "$3" 2>/dev/null | head -n1 | tr -d '\r')"
  else
    # shellcheck disable=SC2086  # $2 is "" or "-3"; word-splitting intended
    out="$(printf '%s\n' 'import sys' 'if sys.version_info[0] == 3:' \
             '    print("__ai_brain_python_ok__")' \
           | "$1" $2 - 2>/dev/null | head -n1 | tr -d '\r')"
  fi
  [ "$out" = "__ai_brain_python_ok__" ]
}
_pick_python() {
  local cand args resolved tried=":" probe_dir="" probe=""
  probe_dir="$(mktemp -d 2>/dev/null)" || probe_dir=""
  if [ -n "$probe_dir" ]; then
    probe="$probe_dir/ai_brain_sync_probe.py"
    # 2>/dev/null comes FIRST so a failing `>` (read-only or full temp dir)
    # cannot print its own error ahead of the WARN below.
    printf '%s\n' 'import sys' 'if sys.version_info[0] == 3:' \
      '    print("__ai_brain_python_ok__")' 2>/dev/null > "$probe" || probe=""
  fi
  if [ -z "$probe" ]; then
    echo "sync-vault-scripts: WARN: could not write a Python probe file to a" \
      "temp dir; probing on stdin instead, which a python3 wrapper that" \
      "refuses only script files can pass." >&2
  fi
  if [ -n "${AI_BRAIN_PYTHON:-}" ]; then
    resolved="$(command -v "$AI_BRAIN_PYTHON" 2>/dev/null || true)"
    [ -z "$resolved" ] || tried="$tried$resolved|:"
    if [ -n "$resolved" ] && _probe_python "$resolved" "" "$probe"; then
      PY_CMD="$resolved"
    else
      echo "sync-vault-scripts: WARN: AI_BRAIN_PYTHON=$AI_BRAIN_PYTHON is not" \
        "a working Python 3; ignoring it." >&2
    fi
  fi
  if [ -z "$PY_CMD" ]; then
    for cand in python3 python py \
                python3.15 python3.14 python3.13 python3.12 python3.11 \
                python3.10 python3.9 \
                /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
      resolved="$(command -v "$cand" 2>/dev/null || true)"
      [ -n "$resolved" ] || continue
      args=""
      # The Windows launcher needs -3 to guarantee a Python 3 interpreter.
      if [ "$cand" = "py" ]; then args="-3"; fi
      # One probe per path AND args: the launcher named by AI_BRAIN_PYTHON,
      # probed bare, must not block its own -3 probe here.
      case "$tried" in *":$resolved|$args:"*) continue ;; esac
      tried="$tried$resolved|$args:"
      if _probe_python "$resolved" "$args" "$probe"; then
        PY_CMD="$resolved"
        PY_ARGS="$args"
        break
      fi
    done
  fi
  [ -z "$probe_dir" ] || rm -rf "$probe_dir"
  [ -n "$PY_CMD" ]
}
_pick_python || true

# --- Resolve the vault root ---------------------------------------------------
resolve_vault_from_settings() {
  local settings="$HOME/.claude/settings.json"
  [ -f "$settings" ] || return 1
  [ -n "$PY_CMD" ] || return 1
  # shellcheck disable=SC2086  # PY_ARGS is "" or "-3" (py launcher); word-splitting intended
  "$PY_CMD" $PY_ARGS - "$settings" <<'PY' 2>/dev/null
import json, re, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    sys.exit(1)
for _ev, groups in (data.get("hooks") or {}).items():
    for g in groups:
        for h in g.get("hooks", []):
            cmd = h.get("command", "")
            # The installed hook commands embed the absolute vault path right
            # before the meta-folder + /scripts/. Grab the longest such prefix.
            # POSIX root, Windows drive letter or UNC share, either separator -
            # byte-identical to heal-journal-guard.py's _VAULT_FROM_CMD_RE (its
            # self-test pins the parity) and to the copy in the .ps1 sibling.
            m = re.search(r"((?:[A-Za-z]:)?[\\/][^'\"]+?)[\\/](?:⚙️ Meta|Meta)[\\/]scripts[\\/]", cmd)
            if m:
                print(m.group(1))
                sys.exit(0)
sys.exit(1)
PY
}

if [ -z "$VAULT" ]; then VAULT="${VAULT_ROOT:-}"; fi
if [ -z "$VAULT" ]; then VAULT="$(resolve_vault_from_settings || true)"; fi

if [ -z "$VAULT" ] || [ ! -d "$VAULT" ]; then
  note "sync-vault-scripts: no vault resolved (--vault / \$VAULT_ROOT / settings.json all empty) — skipping (non-fatal)."
  exit 0
fi

# --- Resolve the vault's meta dir via the SHARED resolver (decorated-first). ---
# The vault scripts live in the HUMAN meta folder ("⚙️ Meta"), which a naive
# "*Meta" glob would miss — plain machine "Meta" sorts first and would shadow it.
# _meta_resolver.py is the ONE source of truth for this (scripts/check-meta-
# resolution.sh bans re-implementing the glob in shell); it prefers whichever
# Meta variant holds a known human subfolder. Disambiguate on folders the human
# meta owns. It lives beside this script in the repo, so $SCRIPT_DIR resolves it.
# shellcheck disable=SC2086  # PY_ARGS is "" or "-3" (py launcher); word-splitting intended
META="$([ -n "$PY_CMD" ] && "$PY_CMD" $PY_ARGS "$SCRIPT_DIR/_meta_resolver.py" "$VAULT" scripts Decisions Sessions 2>/dev/null || true)"
if [ -z "$META" ]; then
  note "sync-vault-scripts: no Meta folder in $VAULT — skipping (non-fatal)."
  exit 0
fi

DEST_DIR="$META/scripts"

# Maintainer-safe: if the vault scripts dir is a symlink (live-editing the repo
# from the vault), do not touch it.
if [ -L "$DEST_DIR" ]; then
  note "sync-vault-scripts: $DEST_DIR is a symlink (managed elsewhere) — skipping."
  exit 0
fi

if [ "$DRY_RUN" -eq 0 ]; then mkdir -p "$DEST_DIR" 2>/dev/null || {
  echo "sync-vault-scripts: cannot create $DEST_DIR" >&2; exit 2; }
fi

# --- Sync one script: backup-on-diff, then copy (mirrors sync-skills.sh). ------
sync_one() {
  local name="$1"
  # Optional $2/$3 override the default scripts/<name> -> <meta>/scripts/<name>
  # mapping so the _lib package deps below travel through the SAME backup /
  # dry-run / symlink-skip semantics, instead of getting a second, weaker copy
  # path that would drift from this one.
  local src="${2:-$STARTER_DIR/scripts/$name}"
  local dest="${3:-$DEST_DIR/$name}"

  if [ ! -f "$src" ]; then
    ABSENT+=("$name (not on this checkout yet)")
    return 0
  fi
  if [ -L "$dest" ]; then
    SKIPPED+=("$name (symlinked dest, maintainer workflow)")
    return 0
  fi
  if [ -f "$dest" ]; then
    if cmp -s "$src" "$dest"; then
      return 0   # identical — no-op, no noise
    fi
    if [ "$DRY_RUN" -eq 1 ]; then
      UPDATED+=("$name (would update; backup -> ${name}.bak-${STAMP})")
      return 0
    fi
    local bak="${dest}.bak-${STAMP}"
    if cp "$dest" "$bak" 2>/dev/null; then
      BACKED_UP+=("$bak")
    else
      ERRORS+=("could not back up $dest before overwrite")
      return 1
    fi
    if cp "$src" "$dest" 2>/dev/null; then
      chmod +x "$dest" 2>/dev/null || true
      UPDATED+=("$name")
    else
      ERRORS+=("could not overwrite $dest (backup at $bak)")
      return 1
    fi
  else
    if [ "$DRY_RUN" -eq 1 ]; then
      CREATED+=("$name (would create)")
      return 0
    fi
    if cp "$src" "$dest" 2>/dev/null; then
      chmod +x "$dest" 2>/dev/null || true
      CREATED+=("$name")
    else
      ERRORS+=("could not create $dest")
      return 1
    fi
  fi
}

for s in "${VAULT_SCRIPTS[@]}"; do
  sync_one "$s"
done

# --- Package deps: hooks/_lib/ -> <meta>/scripts/_lib/ ------------------------
# The manifest above is a flat list of scripts/ FILENAMES, so it structurally
# cannot express a PACKAGE dependency. build-journal-index.py imports
# `_lib.safe_read` (the one audited bounded-read primitive), and because that
# package only ever existed at hooks/_lib/, the synced vault copy died at import
# with `ModuleNotFoundError: No module named '_lib'` — silently, since the
# insights skill runs the vault copy and nothing surfaced its exit code. The
# import-closure self-test could not see it either: it resolved deps only as
# scripts/<mod>.py, and a package directory is not a file.
#
# Mirroring the real module is the honest fix. The alternative — a try/except
# fallback with a hand-rolled reader — is explicitly refused by
# scripts/check-cloud-safe-file-walkers.py, whose negative control is "bogus
# safe_read module is not trusted": a recursive walker must reach the ONE
# audited primitive. safe_read.py is stdlib-only, so this costs the vault
# nothing. Every entry must likewise be stdlib-only or listed here.
VAULT_LIB_MODULES=(
  "__init__.py"     # makes _lib an importable package
  "safe_read.py"    # bounded, symlink-refusing read (dep of build-journal-index.py)
  "vault_root.py"   # canonical vault-root resolution (dep of drift-detection.py,
                     # compress-vault-doc.py -- #683 F4); stdlib-only (os, re, pathlib)
)
if [ "$DRY_RUN" -eq 0 ]; then
  mkdir -p "$DEST_DIR/_lib" 2>/dev/null || {
    echo "sync-vault-scripts: cannot create $DEST_DIR/_lib" >&2; exit 2; }
fi
for m in "${VAULT_LIB_MODULES[@]}"; do
  sync_one "_lib/$m" "$STARTER_DIR/hooks/_lib/$m" "$DEST_DIR/_lib/$m"
done

# --- Summary (to stdout + a discoverable vault-side log) ----------------------
LOG_FILE="$DEST_DIR/.vault-script-sync.log"
summary() {
  # NOT ${DRY_RUN:+...}: that expands when the var is merely SET AND NON-EMPTY,
  # and the default is the STRING "0" — non-empty — so this banner said
  # "(dry-run)" on every REAL run too, including the one that had just rewritten
  # files and left .bak copies behind. A sync that mutates a vault while
  # announcing itself as a dry run is the worst direction for this to fail: the
  # operator reads "(dry-run)", believes nothing happened, and re-runs or walks
  # away. Every other DRY_RUN site in this file tests `-eq 1`; match them.
  local dry_label=""
  [ "$DRY_RUN" -eq 1 ] && dry_label=" (dry-run)"
  echo "=== sync-vault-scripts.sh @ $STAMP$dry_label ==="
  echo "vault: $VAULT"
  echo "meta:  $META"
  echo "Created:   ${#CREATED[@]}";   for f in "${CREATED[@]:-}"; do [ -n "$f" ] && echo "  + $f"; done
  echo "Updated:   ${#UPDATED[@]}";   for f in "${UPDATED[@]:-}"; do [ -n "$f" ] && echo "  ~ $f"; done
  echo "Backed up: ${#BACKED_UP[@]} (local edits preserved)"; for f in "${BACKED_UP[@]:-}"; do [ -n "$f" ] && echo "  b $f"; done
  echo "Skipped:   ${#SKIPPED[@]}";   for f in "${SKIPPED[@]:-}"; do [ -n "$f" ] && echo "  s $f"; done
  echo "Absent:    ${#ABSENT[@]}";    for f in "${ABSENT[@]:-}"; do [ -n "$f" ] && echo "  . $f"; done
  echo "Errors:    ${#ERRORS[@]}";    for f in "${ERRORS[@]:-}"; do [ -n "$f" ] && echo "  ! $f"; done
  echo ""
}

changed=$(( ${#CREATED[@]} + ${#UPDATED[@]} + ${#BACKED_UP[@]} + ${#ERRORS[@]} ))
if [ "$DRY_RUN" -eq 1 ]; then
  summary
elif [ "$QUIET" -eq 1 ]; then
  summary >> "$LOG_FILE" 2>/dev/null || true
  [ "$changed" -gt 0 ] && summary   # surface to stdout only when something changed
else
  summary | tee -a "$LOG_FILE"
fi

if [ "${#ERRORS[@]}" -gt 0 ]; then exit 2; fi
exit 0
