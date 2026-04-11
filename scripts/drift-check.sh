#!/usr/bin/env bash
#
# drift-check.sh — detect file drift between the ai-brain-starter repo and
# the user's installed copies. READ-ONLY: never modifies anything.
#
# Why this exists:
#   update-check.sh only knows whether the user is BEHIND on commits. It does
#   NOT know whether files that were already installed in a prior release have
#   since drifted from the repo's version (because someone hand-edited a script
#   in the vault, or a previous sync only partially landed, or the user pulled
#   a sub-set of changes manually). Without drift-check, the only way to find
#   stale files is for a human to ask Claude "compare everything" — which is
#   exactly what we're automating away.
#
# What it checks:
#
#   Scope A — installed Claude skills:
#     For every skill bundled under $STARTER/skills/<skill>/, walk every file
#     and compare to ~/.claude/skills/<skill>/<rel-path>. Report any installed
#     file that differs from the repo version.
#
#   Scope B — vault-installed scripts (only if --vault PATH given):
#     For a curated list of scripts the starter copies into vaults during
#     /setup-brain (aggregate-sessions.py, aggregate-decisions.py,
#     graph-context-hook.sh, etc.), compare $VAULT/⚙️ Meta/scripts/<basename>
#     against $STARTER/scripts/<basename>. Annotate scripts that are known to
#     have hand-edited config blocks so the caller doesn't blindly overwrite.
#
#   Scope C — vault CLAUDE.md rule blocks (only if --vault given):
#     For every templates/rules/*.md, find its top-level heading inside
#     $VAULT/CLAUDE.md. If the heading is present but the block underneath
#     differs from the repo template, report drift. The block boundary is the
#     next top-level (#) heading or end-of-file.
#
# What it does NOT do:
#   - Modify files. Ever. drift-check is a detector, not a fixer.
#   - Decide what to update. The Claude session-start rule reads this output
#     and walks the user through each drift one by one — show diff, ask, back
#     up, then replace (or skip).
#
# Output format (stable, parseable):
#   STATUS: <OK | SKIPPED_TODAY | ERROR>
#   DRIFT_COUNT: <integer>
#   ---DRIFT_FILES---
#   <scope>|<installed_path>|<repo_source_path>|<note>
#   ...
#   ---END---
#
#   Scopes: skill | vault-script | vault-rule
#   Note: free-text annotation, may be empty. Used to flag hand-edited files
#         (e.g. graph-context-hook.sh) that need cherry-pick instead of
#         wholesale overwrite.
#
# Cooldown:
#   drift-check honors a once-per-day cooldown (mirrors update-check.sh) so
#   that session start isn't noisy. Pass --force to bypass.
#
# Usage:
#   bash drift-check.sh                        # skills scope only
#   bash drift-check.sh --vault "/path/to/vault"   # all three scopes
#   bash drift-check.sh --vault "..." --force      # bypass cooldown

set -uo pipefail

# Derive STARTER_DIR from the script's own location (scripts/drift-check.sh →
# parent dir is the repo root). This works whether the repo is installed at
# ~/.claude/skills/ai-brain-starter (end users) or somewhere else like
# ~/Desktop/ai-brain-starter (maintainer / fork developer).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STARTER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_DIR="$HOME/.claude/skills"
COOLDOWN_FILE="$HOME/.claude/.ai-brain-starter-drift-check-last-run"
TODAY="$(date +%Y-%m-%d)"
FORCE=0
VAULT=""

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --vault)
      VAULT="${2:-}"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    *)
      shift
      ;;
  esac
done

# Cooldown
if [[ $FORCE -eq 0 && -f "$COOLDOWN_FILE" ]]; then
  LAST="$(cat "$COOLDOWN_FILE" 2>/dev/null || echo '')"
  if [[ "$LAST" == "$TODAY" ]]; then
    echo "STATUS: SKIPPED_TODAY"
    exit 0
  fi
fi

# Repo guard
if [[ ! -d "$STARTER_DIR" ]]; then
  echo "STATUS: ERROR"
  echo "REASON: ai-brain-starter not installed at $STARTER_DIR"
  exit 0
fi

# Bash 3.2 — initialize as empty string and append; avoid array unbound issues
DRIFT_LINES=""
DRIFT_COUNT=0

add_drift() {
  # $1=scope $2=installed_path $3=repo_source_path $4=note
  DRIFT_LINES="${DRIFT_LINES}${1}|${2}|${3}|${4}"$'\n'
  DRIFT_COUNT=$((DRIFT_COUNT + 1))
}

# ── Scope A — installed skills ────────────────────────────────────────────
if [[ -d "$STARTER_DIR/skills" ]]; then
  for skill_dir in "$STARTER_DIR/skills"/*/; do
    [[ -d "$skill_dir" ]] || continue
    skill_name=$(basename "$skill_dir")
    installed_skill_dir="$INSTALL_DIR/$skill_name"

    # If the skill isn't installed at all, that's not "drift" — it's a missing
    # install, which bootstrap.sh handles. Skip.
    [[ -d "$installed_skill_dir" ]] || continue

    while IFS= read -r -d '' src_file; do
      rel_path="${src_file#"$skill_dir"}"
      dest_file="$installed_skill_dir/$rel_path"
      if [[ -f "$dest_file" ]] && ! cmp -s "$src_file" "$dest_file"; then
        add_drift "skill" "$dest_file" "$src_file" ""
      fi
    done < <(find "$skill_dir" -type f -print0 2>/dev/null)
  done
fi

# ── Scope B — vault-installed scripts ─────────────────────────────────────
if [[ -n "$VAULT" && -d "$VAULT" ]]; then
  VAULT_SCRIPTS_DIR="$VAULT/⚙️ Meta/scripts"
  if [[ -d "$VAULT_SCRIPTS_DIR" ]]; then
    # Curated list of scripts that the starter installs into vaults via
    # /setup-brain. Anything outside this list is user-installed and should
    # not be touched by drift-check.
    VAULT_SCRIPT_NAMES="aggregate-sessions.py aggregate-decisions.py auto-wikilink.py build-journal-index.py graphify_dedupe_by_adjacency.py graph-context-hook.sh"

    for name in $VAULT_SCRIPT_NAMES; do
      src="$STARTER_DIR/scripts/$name"
      dest="$VAULT_SCRIPTS_DIR/$name"
      [[ -f "$src" && -f "$dest" ]] || continue
      if ! cmp -s "$src" "$dest"; then
        note=""
        # Files known to be hand-edited after install (CONFIG blocks, paths,
        # vault-specific values). For these, the caller MUST cherry-pick
        # repo changes into the user's file rather than overwriting.
        case "$name" in
          graph-context-hook.sh)
            note="hand-edited CONFIG block at top of file — cherry-pick changes, do NOT overwrite wholesale"
            ;;
        esac
        add_drift "vault-script" "$dest" "$src" "$note"
      fi
    done
  fi
fi

# ── Scope C — vault CLAUDE.md rule blocks ─────────────────────────────────
if [[ -n "$VAULT" && -f "$VAULT/CLAUDE.md" && -d "$STARTER_DIR/templates/rules" ]]; then
  for rule_file in "$STARTER_DIR/templates/rules"/*.md; do
    [[ -f "$rule_file" ]] || continue

    # Get the first H1 heading line from the template (e.g. "# Session start...")
    heading=$(grep -m1 '^# ' "$rule_file" 2>/dev/null || echo '')
    [[ -n "$heading" ]] || continue

    # Check whether that heading appears anywhere in the user's CLAUDE.md
    if ! grep -qxF "$heading" "$VAULT/CLAUDE.md" 2>/dev/null; then
      # Heading not present. The rule isn't installed (or has been removed by
      # the user). Don't report drift — bootstrap/setup-brain owns install.
      continue
    fi

    # Heading IS present. Extract the block from CLAUDE.md and compare to the
    # template content. Use python for clean block extraction + comparison.
    drift_result=$(python3 - "$VAULT/CLAUDE.md" "$rule_file" "$heading" <<'PY'
import sys
from pathlib import Path

vault_claude_md = Path(sys.argv[1])
template_path = Path(sys.argv[2])
heading = sys.argv[3]

claude_lines = vault_claude_md.read_text(encoding="utf-8").splitlines()
template_text = template_path.read_text(encoding="utf-8")

# Extract the installed block: from `heading` line up to (but not including)
# the next H1 heading, or end of file.
installed_block_lines = []
in_block = False
for line in claude_lines:
    if line == heading:
        in_block = True
        installed_block_lines.append(line)
        continue
    if in_block and line.startswith("# ") and line != heading:
        break
    if in_block:
        installed_block_lines.append(line)

# Defensive normalization to avoid false-positive drift on benign formatting
# differences. The diff that matters is content drift, not whitespace or
# editor conventions. Normalize both sides through the same pipeline:
#   1. Strip UTF-8 BOM (Windows editors love adding these)
#   2. Convert CRLF to LF (Windows editors save \r\n; the repo uses \n)
#   3. Strip trailing blank lines
#   4. Strip trailing markdown thematic breaks (---, ***, ___) — these are
#      CLAUDE.md visual separators between concatenated rule blocks, not
#      part of any individual rule template
#   5. Re-add a single trailing newline for consistency

def normalize_for_compare(text):
    # 1. BOM
    if text.startswith("\ufeff"):
        text = text[1:]
    # 2. Line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 3 & 4. Trailing blank lines and thematic breaks
    lines = text.split("\n")
    THEMATIC_BREAKS = {"---", "***", "___"}
    while lines and (lines[-1].strip() == "" or lines[-1].strip() in THEMATIC_BREAKS):
        lines.pop()
    # 5. Single trailing newline
    return "\n".join(lines) + "\n"

installed = normalize_for_compare("\n".join(installed_block_lines))
template = normalize_for_compare(template_text)

if installed != template:
    print("DRIFT")
PY
)

    if [[ "$drift_result" == "DRIFT" ]]; then
      add_drift "vault-rule" "$VAULT/CLAUDE.md" "$rule_file" "block heading: $heading"
    fi
  done
fi

# ── Output ─────────────────────────────────────────────────────────────────
echo "STATUS: OK"
echo "DRIFT_COUNT: $DRIFT_COUNT"
echo "---DRIFT_FILES---"
if [[ -n "$DRIFT_LINES" ]]; then
  printf "%s" "$DRIFT_LINES"
fi
echo "---END---"

# Record cooldown
echo "$TODAY" > "$COOLDOWN_FILE"

exit 0
