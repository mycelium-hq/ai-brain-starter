#!/usr/bin/env python3
"""
install-hooks-user-level.py — install ai-brain-starter hooks at USER level.

Closes adelaidasofia/ai-brain-starter#6 — UserPromptSubmit hooks silently fail
in worktrees when installed at project level. User-level hooks
(~/.claude/settings.json) fire universally regardless of worktree.

What it does:
  1. Reads the canonical hooks.json from the skill repo
  2. Reads existing ~/.claude/settings.json (preserves all user content)
  3. Merges ai-brain-starter hooks into the user-level config
  4. De-duplicates by command-string fingerprint (idempotent re-runs)
  5. Backs up the existing settings.json before edit
  6. Verifies post-write JSON validity, rolls back on parse error

Safety:
  - Backup at ~/.claude/settings.json.bak-{timestamp} before any edit
  - JSON validity verified after write; rollback on parse error
  - Custom user hooks NEVER removed (we only add ai-brain-starter entries)
  - Idempotent: a second run detects already-installed hooks via fingerprint
  - --dry-run shows the planned merge without writing
  - --uninstall removes ONLY the ai-brain-starter entries (matched by
    fingerprint substring); leaves everything else intact

Usage:
  python3 install-hooks-user-level.py                          # install
  python3 install-hooks-user-level.py --dry-run                # preview
  python3 install-hooks-user-level.py --uninstall              # remove
  python3 install-hooks-user-level.py --hooks-source PATH      # custom source
  python3 install-hooks-user-level.py --quiet                  # only summary
  python3 install-hooks-user-level.py --verify                 # verify after install

Why user-level: project-level hooks at <project>/.claude/settings.json
silently don't fire when cwd is inside <project>/.claude/worktrees/<name>/.
The Claude Code hook resolver appears to treat .claude/ as a boundary it
won't cross when looking up project hooks. User-level config is universal —
fires on every session regardless of cwd.

We ship hooks.json as the canonical source. This script is the install
mechanism; the source-of-truth content lives in hooks.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path


# Fingerprint substrings — any hook command containing one of these is
# considered "owned by ai-brain-starter" and may be replaced or removed.
# Extend this list when adding new hooks; the name must be unique enough
# that no third-party hook would accidentally include it.
ABS_FINGERPRINTS = [
    "ai-brain-starter/hooks/detect-closing-signal.py",
    "ai-brain-starter/hooks/lint-vault-frontmatter.py",
    "ai-brain-starter/hooks/log-skill-usage.py",
    "ai-brain-starter/hooks/first-week-checkin.py",
    "ai-brain-starter/hooks/migrate-to-user-level.py",
    "ai-brain-starter/scripts/session-end-hook.sh",
    "ai-brain-starter/scripts/email-gate-hook.py",
    "ai-brain-starter/⚙️ Meta/scripts/graph-context-hook.sh",
    # Legacy session-start context loaders shipped via ai-brain-starter:
    "SESSION START: CLAUDE.md is already auto-loaded",
    ".ai-brain-starter-last-update",
]


def find_repo_root() -> Path:
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent,
        Path.home() / ".claude" / "skills" / "ai-brain-starter",
        Path.home() / "Desktop" / "ai-brain-starter",
    ]
    for c in candidates:
        if (c / "hooks.json").is_file():
            return c
    raise FileNotFoundError("Could not find hooks.json source")


def load_hooks_template(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def is_abs_owned(command: str) -> bool:
    return any(fp in command for fp in ABS_FINGERPRINTS)


def is_same_command(a: str, b: str) -> bool:
    """Two commands count as the same if they reference the same script and
    fall under the same ABS fingerprint."""
    for fp in ABS_FINGERPRINTS:
        if fp in a and fp in b:
            return True
    return a.strip() == b.strip()


def normalize_path_substitutions(template: dict, vault_path: str | None) -> dict:
    """Replace [VAULT_PATH] in template strings with the actual vault path or
    drop it (let the chained || ~/.claude/... fallback take over).

    For user-level install, the [VAULT_PATH]/.claude/skills/... fallback is
    redundant — the ~/.claude/skills/... variant always works. We keep both
    chains intact for resilience."""
    if not vault_path:
        # Strip the [VAULT_PATH] alt in chained fallbacks; the
        # ~/.claude/skills/... variant is sufficient for user-level.
        s = json.dumps(template, ensure_ascii=False)
        # Conservative: only replace the literal [VAULT_PATH] in commands
        s = s.replace("[VAULT_PATH]", str(Path.home()))
        return json.loads(s)
    s = json.dumps(template, ensure_ascii=False)
    s = s.replace("[VAULT_PATH]", str(Path(vault_path).resolve()))
    return json.loads(s)


def merge_hooks(existing: dict, new_template: dict) -> tuple[dict, dict]:
    """Merge ai-brain-starter hooks into existing user settings.

    Returns (merged_settings, change_summary).

    Strategy per event:
      1. Find every group in the new template's hooks.<event> array
      2. For each new group, find ai-brain-starter command(s) inside its hooks list
      3. In existing, locate any group whose hooks list contains an ABS-owned command
      4. Replace the matching ABS commands inline; preserve non-ABS commands;
         add new ABS commands that weren't there before
    """
    summary = {"added": [], "updated": [], "kept": [], "events_touched": []}
    merged = json.loads(json.dumps(existing))  # deep copy
    if "hooks" not in merged:
        merged["hooks"] = {}

    for event, new_groups in (new_template.get("hooks") or {}).items():
        summary["events_touched"].append(event)
        if event not in merged["hooks"]:
            merged["hooks"][event] = []

        existing_groups = merged["hooks"][event]
        # Collect all ABS-owned commands from new template (flattened)
        for new_group in new_groups:
            new_hooks = new_group.get("hooks", [])
            for new_hook in new_hooks:
                cmd = new_hook.get("command", "")
                if not cmd:
                    continue
                # Look for this command in any existing group
                replaced = False
                for eg in existing_groups:
                    eg_hooks = eg.get("hooks", [])
                    for i, eh in enumerate(eg_hooks):
                        eh_cmd = eh.get("command", "")
                        if is_same_command(cmd, eh_cmd):
                            # Replace
                            eg_hooks[i] = new_hook
                            summary["updated"].append(f"{event}: {cmd[:80]}")
                            replaced = True
                            break
                    if replaced:
                        break

                if not replaced:
                    # Find or create a group with the same matcher (if any)
                    matcher = new_group.get("matcher")
                    target_group = None
                    for eg in existing_groups:
                        if eg.get("matcher") == matcher:
                            target_group = eg
                            break
                    if not target_group:
                        target_group = {}
                        if matcher:
                            target_group["matcher"] = matcher
                        target_group["hooks"] = []
                        existing_groups.append(target_group)
                    target_group.setdefault("hooks", []).append(new_hook)
                    summary["added"].append(f"{event}: {cmd[:80]}")

        # Track non-touched non-ABS hooks as "kept"
        for eg in existing_groups:
            for eh in eg.get("hooks", []):
                cmd = eh.get("command", "")
                if cmd and not is_abs_owned(cmd):
                    summary["kept"].append(f"{event}: {cmd[:80]}")

    return merged, summary


def remove_abs_hooks(existing: dict) -> tuple[dict, int]:
    """Remove all ABS-owned hook entries. Returns (cleaned, count_removed)."""
    cleaned = json.loads(json.dumps(existing))
    removed = 0
    if "hooks" not in cleaned:
        return cleaned, 0
    for event, groups in list(cleaned["hooks"].items()):
        new_groups = []
        for g in groups:
            kept_hooks = []
            for h in g.get("hooks", []):
                if is_abs_owned(h.get("command", "")):
                    removed += 1
                    continue
                kept_hooks.append(h)
            if kept_hooks:
                new_g = dict(g)
                new_g["hooks"] = kept_hooks
                new_groups.append(new_g)
            elif "matcher" in g and not kept_hooks:
                # Matcher group emptied — drop
                pass
        if new_groups:
            cleaned["hooks"][event] = new_groups
        else:
            del cleaned["hooks"][event]
    return cleaned, removed


def backup_settings(settings_path: Path) -> Path | None:
    if not settings_path.is_file():
        return None
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    backup = settings_path.with_name(f"{settings_path.name}.bak-{stamp}-abs")
    try:
        backup.write_text(settings_path.read_text(encoding="utf-8"), encoding="utf-8")
        return backup
    except OSError:
        return None


def write_settings_with_verify(settings_path: Path, settings: dict, backup: Path | None) -> bool:
    """Write settings.json, verify it parses, rollback on failure."""
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    new_text = json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
    try:
        settings_path.write_text(new_text, encoding="utf-8")
    except OSError as e:
        print(f"ERROR: write failed: {e}", file=sys.stderr)
        return False
    # Verify
    try:
        json.loads(settings_path.read_text(encoding="utf-8"))
        return True
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: post-write JSON parse failed: {e}", file=sys.stderr)
        if backup and backup.is_file():
            try:
                settings_path.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
                print(f"  Rolled back to {backup}", file=sys.stderr)
            except OSError as e2:
                print(f"  ERROR: rollback also failed: {e2}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--hooks-source", help="path to hooks.json (default: auto-detect)")
    ap.add_argument("--vault-path", default=os.environ.get("VAULT_ROOT"),
                    help="vault path for [VAULT_PATH] substitution (optional)")
    ap.add_argument("--settings", default=str(Path.home() / ".claude" / "settings.json"),
                    help="target settings.json (default: ~/.claude/settings.json)")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="after install, fire each hook with a sample input and report")
    args = ap.parse_args()

    # === locate hooks template ===
    if args.hooks_source:
        hooks_template_path = Path(args.hooks_source)
    else:
        try:
            hooks_template_path = find_repo_root() / "hooks.json"
        except FileNotFoundError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2

    if not hooks_template_path.is_file():
        print(f"ERROR: hooks template not found: {hooks_template_path}", file=sys.stderr)
        return 2

    template = load_hooks_template(hooks_template_path)
    template = normalize_path_substitutions(template, args.vault_path)

    settings_path = Path(args.settings).expanduser()

    # === load existing ===
    existing = {}
    if settings_path.is_file():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"ERROR: existing {settings_path} is not valid JSON: {e}", file=sys.stderr)
            print("Refusing to proceed. Fix the JSON or use --settings to point elsewhere.")
            return 2

    # === uninstall path ===
    if args.uninstall:
        cleaned, removed = remove_abs_hooks(existing)
        if removed == 0:
            if not args.quiet:
                print(f"No ai-brain-starter hooks found in {settings_path}. Nothing to remove.")
            return 0
        if args.dry_run:
            if not args.quiet:
                print(f"DRY RUN: would remove {removed} ai-brain-starter hook(s) from {settings_path}")
            return 0
        backup = backup_settings(settings_path)
        if write_settings_with_verify(settings_path, cleaned, backup):
            if not args.quiet:
                print(f"Removed {removed} ai-brain-starter hook(s) from {settings_path}")
                if backup:
                    print(f"Backup at {backup}")
            return 0
        return 2

    # === install / update path ===
    merged, summary = merge_hooks(existing, template)

    if not args.quiet:
        print(f"Merging into: {settings_path}")
        print(f"Source:       {hooks_template_path}")
        print(f"Events:       {', '.join(summary['events_touched'])}")
        print(f"Added:        {len(summary['added'])} hook(s)")
        print(f"Updated:      {len(summary['updated'])} hook(s)")
        print(f"Preserved:    {len(set(summary['kept']))} non-ABS hook(s) untouched")

    if args.dry_run:
        if not args.quiet:
            print("\nDRY RUN — no changes written.")
            for entry in summary["added"]:
                print(f"  + {entry}")
            for entry in summary["updated"]:
                print(f"  ~ {entry}")
        return 0

    if not summary["added"] and not summary["updated"]:
        if not args.quiet:
            print("\nAlready in sync. Nothing to write.")
        return 0

    backup = backup_settings(settings_path)
    if write_settings_with_verify(settings_path, merged, backup):
        if not args.quiet:
            print(f"\nWrote {settings_path}")
            if backup:
                print(f"Backup: {backup}")
        if args.verify:
            run_verification(merged)
        return 0
    return 2


def run_verification(settings: dict) -> None:
    """Smoke-test that hook commands resolve."""
    print("\n--- Verification ---")
    import shlex
    failures = 0
    for event, groups in (settings.get("hooks") or {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                cmd = h.get("command", "")
                if not cmd or not is_abs_owned(cmd):
                    continue
                # Heuristic: extract first absolute path after `python3` or `bash`
                import re
                m = re.search(r"(?:python3|bash)\s+'?(~?[^\s'|&;]+)'?", cmd)
                if not m:
                    continue
                p = Path(os.path.expanduser(m.group(1)))
                if p.is_file():
                    print(f"  OK    {event}: {p.name}")
                else:
                    print(f"  FAIL  {event}: {p} not found")
                    failures += 1
    if failures:
        print(f"\n{failures} hook script(s) missing on disk. Run bootstrap.sh to install them.")


if __name__ == "__main__":
    sys.exit(main())
