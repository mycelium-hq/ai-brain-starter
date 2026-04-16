#!/bin/bash
# sync-skills.sh — propagate skill updates from the ai-brain-starter repo
# into the user's installed ~/.claude/skills/ directory.
#
# Runs after `git pull` on the starter repo. For each skill bundled in the repo
# (under skills/ or at the repo root), syncs every file into the corresponding
# installed skill folder. Never destroys user customizations without recovery:
# any installed file that differs from the incoming repo file is backed up to
# <file>.bak-YYYY-MM-DD-HHMM before being overwritten.
#
# Honors the NEVER-fail-silently rule: writes a structured summary to the
# starter repo's .sync.log and prints it to stdout so the session-start hook
# can surface it to Claude (who surfaces it to the user).
#
# Usage: bash ~/.claude/skills/ai-brain-starter/scripts/sync-skills.sh

# Intentionally not using `set -u` — macOS's bash 3.2 treats empty arrays as
# "unbound" when expanded, which would false-positive on first-run installs
# where nothing has been created/updated/backed up yet.

STARTER_DIR="$HOME/.claude/skills/ai-brain-starter"
INSTALL_DIR="$HOME/.claude/skills"
LOG_FILE="$STARTER_DIR/.sync.log"
STAMP="$(date +%Y-%m-%d-%H%M)"

# Guard: starter repo must exist
if [ ! -d "$STARTER_DIR" ]; then
  echo "ERROR: ai-brain-starter repo not found at $STARTER_DIR" >&2
  exit 1
fi

# Guard: install directory must exist (mkdir if needed)
mkdir -p "$INSTALL_DIR" || {
  echo "ERROR: could not create install dir $INSTALL_DIR" >&2
  exit 1
}

# Track what happened for the summary
declare -a UPDATED=()
declare -a BACKED_UP=()
declare -a CREATED=()
declare -a SKIPPED=()
declare -a ERRORS=()

# Sync a single file from source to destination.
# If dest exists and differs from source, back it up first.
# If dest doesn't exist, just copy.
# If dest exists and matches source, do nothing (no-op).
sync_file() {
  local src="$1"
  local dest="$2"
  local skill_name="$3"

  if [ ! -f "$src" ]; then
    return 0
  fi

  if [ -f "$dest" ]; then
    if cmp -s "$src" "$dest"; then
      # Identical — no-op, no noise
      return 0
    fi
    # Differs — back up before overwriting
    local bak="${dest}.bak-${STAMP}"
    if cp "$dest" "$bak" 2>/dev/null; then
      BACKED_UP+=("$bak")
    else
      ERRORS+=("could not back up $dest before overwrite")
      return 1
    fi
    if cp "$src" "$dest" 2>/dev/null; then
      UPDATED+=("$skill_name: $(basename "$dest")")
    else
      ERRORS+=("could not overwrite $dest (backup still at $bak)")
      return 1
    fi
  else
    # Doesn't exist — fresh copy
    mkdir -p "$(dirname "$dest")"
    if cp "$src" "$dest" 2>/dev/null; then
      CREATED+=("$skill_name: $(basename "$dest")")
    else
      ERRORS+=("could not create $dest")
      return 1
    fi
  fi
}

# Sync an entire skill folder: every file and subdirectory, recursively.
sync_skill_folder() {
  # Strip any trailing slash from source_dir/dest_dir. Callers pass
  # `$STARTER_DIR/skills/*/` which expands to paths ending in `/`; combined
  # with the `/` we append in the strip pattern below, that would produce `//`
  # and fail to match, leaving rel_path equal to the full absolute path.
  # Result: files copied to $dest_dir/Users/<user>/<abspath>/... instead of
  # $dest_dir/<file>. See 2026-04-16 humanizer pollution incident.
  local source_dir="${1%/}"
  local dest_dir="${2%/}"
  local skill_name="$3"

  if [ ! -d "$source_dir" ]; then
    return 0
  fi

  mkdir -p "$dest_dir"

  # Walk every file in the source, preserving relative paths
  while IFS= read -r -d '' src_file; do
    local rel_path="${src_file#"$source_dir/"}"
    # Defensive guard: if the strip somehow didn't work, refuse to write an
    # absolute-path-masquerading-as-relative. Catches future regressions.
    if [[ "$rel_path" = /* ]]; then
      ERRORS+=("sync_skill_folder: abs path leaked for $src_file (source_dir=$source_dir) — skipping")
      continue
    fi
    local dest_file="$dest_dir/$rel_path"
    sync_file "$src_file" "$dest_file" "$skill_name"
  done < <(find "$source_dir" -type f -print0 2>/dev/null)
}

# --- Sync skills under $STARTER_DIR/skills/ ---
# This picks up graphify, meeting-todos, patterns, and anything else bundled.
# Note: the repo also has a legacy `meeting-todos/` at the root level (older
# copy). We intentionally sync from skills/meeting-todos/ only, since that's
# the canonical location maintained going forward.
if [ -d "$STARTER_DIR/skills" ]; then
  for skill_dir in "$STARTER_DIR/skills"/*/; do
    [ -d "$skill_dir" ] || continue
    skill_name=$(basename "$skill_dir")
    sync_skill_folder "$skill_dir" "$INSTALL_DIR/$skill_name" "$skill_name"
  done
fi

# --- Write summary log + stdout ---
{
  echo "=== sync-skills.sh run at $STAMP ==="
  echo "Created: ${#CREATED[@]} file(s)"
  for f in "${CREATED[@]}"; do echo "  + $f"; done
  echo "Updated: ${#UPDATED[@]} file(s)"
  for f in "${UPDATED[@]}"; do echo "  ~ $f"; done
  echo "Backed up: ${#BACKED_UP[@]} file(s) (local customizations preserved)"
  for f in "${BACKED_UP[@]}"; do echo "  b $f"; done
  echo "Errors: ${#ERRORS[@]}"
  for f in "${ERRORS[@]}"; do echo "  ! $f"; done
  echo ""
} | tee -a "$LOG_FILE"

# Exit non-zero if any errors, so the hook can surface them
if [ "${#ERRORS[@]}" -gt 0 ]; then
  exit 2
fi
exit 0
