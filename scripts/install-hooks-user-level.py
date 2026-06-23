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
import re
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
    "ai-brain-starter/hooks/verify-session-close-cascade.py",
    "ai-brain-starter/hooks/lint-vault-frontmatter.py",
    "ai-brain-starter/hooks/log-skill-usage.py",
    "ai-brain-starter/hooks/first-week-checkin.py",
    "ai-brain-starter/hooks/migrate-to-user-level.py",
    "ai-brain-starter/hooks/inject-love-language-context.py",
    "ai-brain-starter/hooks/inject-meeting-workflow-on-trigger.py",
    "ai-brain-starter/scripts/session-end-hook.sh",
    "ai-brain-starter/scripts/email-gate-hook.py",
    "ai-brain-starter/scripts/post-update-email-ask.py",
    "ai-brain-starter/⚙️ Meta/scripts/graph-context-hook.sh",
    # Legacy session-start context loaders shipped via ai-brain-starter:
    "SESSION START: CLAUDE.md is already auto-loaded",
    ".ai-brain-starter-last-update",
    # Worktree-lifecycle hooks (cleanup + footprint observability):
    "ai-brain-starter/hooks/snapshot-pending-work-on-stop.py",
    "ai-brain-starter/hooks/surface-orphan-worktree-snapshots.py",
    "ai-brain-starter/hooks/remove-ended-worktree.py",
    "ai-brain-starter/hooks/enforce-worktree-cap.py",
    "ai-brain-starter/hooks/worktree-footprint-signal.py",
    # Auto-remediation (the FIX side of the surfacing hooks):
    "ai-brain-starter/hooks/remediate-runaway-procs.py",
    # Write-time secret guard:
    "ai-brain-starter/hooks/block-secret-in-note.py",
    # Context-budget measurer (always-loaded text layer; MYC-619):
    "ai-brain-starter/hooks/context-budget-measure.py",
    # Vault-in-worktree melt tripwire (3-channel detect; SessionStart + tool-time + dedup):
    "ai-brain-starter/hooks/warn-vault-session-in-worktree.py",
    # Memory-routing nudge (team learning written to tool-private memory → shared brain):
    "ai-brain-starter/hooks/warn-learning-to-tool-private-memory.py",
]

# Path-divergence-robust matching: an ai-brain-starter hook may be wired at the
# skill path (~/.claude/skills/ai-brain-starter/hooks/) OR copied into the user
# hooks dir (~/.claude/hooks/). Dedup must recognize both as the same hook by
# SCRIPT BASENAME, else a re-run duplicates every hook a hand-maintained config
# wired at the user-hooks path. Only OUR script basenames are matched this way.
ABS_OWNED_BASENAMES = {
    "detect-closing-signal.py", "verify-session-close-cascade.py",
    "lint-vault-frontmatter.py", "log-skill-usage.py",
    "first-week-checkin.py", "migrate-to-user-level.py",
    "inject-love-language-context.py", "inject-meeting-workflow-on-trigger.py",
    "session-end-hook.sh", "email-gate-hook.py", "graph-context-hook.sh",
    "post-update-email-ask.py",
    "snapshot-pending-work-on-stop.py", "surface-orphan-worktree-snapshots.py",
    "remove-ended-worktree.py", "enforce-worktree-cap.py",
    "worktree-footprint-signal.py", "remediate-runaway-procs.py",
    "block-secret-in-note.py", "context-budget-measure.py",
    "warn-vault-session-in-worktree.py", "warn-learning-to-tool-private-memory.py",
}

# Hooks ai-brain-starter USED TO ship and has deliberately RETIRED. The
# installer actively REMOVES any of these still wired in a user's
# settings.json — merge_hooks() only adds/replaces template hooks, it never
# deletes one that's gone from the template, so without this step a retired
# hook stays wired (and keeps firing) forever on every existing install.
# This is what un-nags users who installed before a hook was removed.
# When retiring a hook: add its fingerprint AND basename here, keep it in the
# ABS_* lists above (so uninstall still recognizes it), and never reuse a
# retired basename for a new hook.
ABS_RETIRED_FINGERPRINTS = [
    # Retired 2026-06-03: fired on EVERY prompt of EVERY session and nagged
    # for an email forever until a marker existed — a stealth reversal of
    # docs/adr/0002-no-email-gate.md. Replaced by post-update-email-ask.py
    # (asks at most once, only after a git pull, when no email is on file).
    "ai-brain-starter/scripts/email-gate-hook.py",
]
ABS_RETIRED_BASENAMES = {
    "email-gate-hook.py",
}

_SCRIPT_RE = re.compile(r"([\w.-]+\.(?:py|sh))")


def _owned_basenames(cmd: str) -> set[str]:
    """Owned ai-brain-starter script basenames referenced in a command."""
    return {os.path.basename(m) for m in _SCRIPT_RE.findall(cmd)} & ABS_OWNED_BASENAMES


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
    if any(fp in command for fp in ABS_FINGERPRINTS):
        return True
    if any(fp in command for fp in ABS_RETIRED_FINGERPRINTS):
        return True
    return bool(_owned_basenames(command))


def is_same_command(a: str, b: str) -> bool:
    """Two commands count as the same hook if they share an ABS fingerprint OR
    an owned script basename (so a skill-path entry and a ~/.claude/hooks/ entry
    for the same script dedup to one), else if the literal text matches."""
    for fp in ABS_FINGERPRINTS:
        if fp in a and fp in b:
            return True
    if _owned_basenames(a) & _owned_basenames(b):
        return True
    return a.strip() == b.strip()


def _hook_depends_on_vault(command: str) -> bool:
    """True if a hook command can only run once the user's vault exists: it
    references a [VAULT_PATH]/... path AND carries no ~/.claude home fallback.

    The three vault-content hooks (graph-context-hook.sh, session-end-hook.sh,
    write-hook.sh) live inside the vault at '[VAULT_PATH]/⚙️ Meta/scripts/' as a
    single clause with no fallback. detect-closing-signal, by contrast, chains
    '... || python3 ~/.claude/skills/...', so it runs fine with no vault and its
    [VAULT_PATH]/.claude/skills/... clause resolves correctly under $HOME."""
    return "[VAULT_PATH]" in command and "~/.claude" not in command


def normalize_path_substitutions(template: dict, vault_path: str | None) -> dict:
    """Resolve [VAULT_PATH] in template hook commands.

    WITH a vault path: substitute the real, resolved vault path everywhere.

    WITHOUT one (bootstrap time, before /setup-brain creates the vault): OMIT
    every hook that depends on the vault (see _hook_depends_on_vault), then
    substitute $HOME for any surviving [VAULT_PATH] (the fallback hooks, whose
    [VAULT_PATH]/.claude/skills/... clause resolves correctly under $HOME).

    Why omit rather than substitute $HOME for the vault-content hooks: pointing
    them at $HOME produces dead '$HOME/⚙️ Meta/scripts/...' commands that error on
    every prompt / write / session-end and force a "how do you want to remove
    these?" decision on a non-technical user mid-install (MYC-739, surfaced by
    the 2026-06-09 install workshop). /setup-brain (phase-05) wires these three
    with the REAL vault path once it exists. Deferring them here is exactly what
    phase-00-install.md documents ("Bootstrap does NOT touch Hooks")."""
    if not vault_path:
        pruned = json.loads(json.dumps(template, ensure_ascii=False))  # deep copy
        for event in list((pruned.get("hooks") or {}).keys()):
            surviving_groups = []
            for group in pruned["hooks"][event]:
                group["hooks"] = [
                    h for h in group.get("hooks", [])
                    if not _hook_depends_on_vault(h.get("command", ""))
                ]
                if group["hooks"]:
                    surviving_groups.append(group)
            if surviving_groups:
                pruned["hooks"][event] = surviving_groups
            else:
                # Every hook in this event depended on the vault (e.g. the
                # PostToolUse(Write) group is only the vault write-hook). Drop
                # the now-empty event rather than leave a bare "Event": [].
                del pruned["hooks"][event]
        s = json.dumps(pruned, ensure_ascii=False)
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


def _is_retired(command: str) -> bool:
    """True if a command runs a RETIRED ai-brain-starter hook."""
    if not command:
        return False
    if any(fp in command for fp in ABS_RETIRED_FINGERPRINTS):
        return True
    found = {os.path.basename(m) for m in _SCRIPT_RE.findall(command)}
    return bool(found & ABS_RETIRED_BASENAMES)


def retire_stale_hooks(existing: dict) -> tuple[dict, int]:
    """Remove every hook entry whose command runs a RETIRED hook.

    merge_hooks() only adds/replaces hooks present in the template — it never
    deletes one that's gone from the template. So a retired hook would stay
    wired in an existing user's settings.json and keep firing forever. This is
    the propagation step that actually un-wires a removed hook on the next
    install / auto-update. Returns (cleaned, count_removed).

    Groups emptied by retirement are dropped. Non-retired hooks (ours and the
    user's own) are preserved untouched."""
    cleaned = json.loads(json.dumps(existing))
    removed = 0
    if "hooks" not in cleaned:
        return cleaned, 0
    for event, groups in list(cleaned["hooks"].items()):
        new_groups = []
        for g in groups:
            hooks = g.get("hooks", [])
            kept = [h for h in hooks if not _is_retired(h.get("command", ""))]
            removed += len(hooks) - len(kept)
            if kept:
                ng = dict(g)
                ng["hooks"] = kept
                new_groups.append(ng)
            # else: group emptied by retirement -> drop it
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


def link_agent_memory_into_vault(vault_path: str, quiet: bool) -> None:
    """Symlink Claude Code's per-project memory dir into the vault so the
    user's "brain" actually accumulates in their vault, not in a hidden
    ~/.claude/ tool dir. Delegates to scripts/link-agent-memory.py (idempotent,
    loss-free). A failure here is the brain-durability bug recurring, so it is
    surfaced LOUDLY — but it never aborts the hook install.
    """
    import subprocess

    linker = Path(__file__).resolve().parent / "link-agent-memory.py"
    if not linker.is_file():
        print(f"WARNING: {linker} missing — Claude Code memory will NOT be linked "
              f"into the vault. Memory would strand in ~/.claude/.", file=sys.stderr)
        return
    cmd = [sys.executable, str(linker), "--vault", vault_path]
    if quiet:
        cmd.append("--quiet")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as e:  # noqa: BLE001 — never let this brick the install
        print(f"WARNING: linking memory into the vault failed to run: {e}", file=sys.stderr)
        return
    if result.stdout and not quiet:
        print(result.stdout, end="")
    if result.returncode != 0:
        print("WARNING: could NOT link Claude Code memory into the vault — memory "
              "would strand in ~/.claude/ instead of your brain. Details below; "
              f"re-run manually:\n  python3 {linker} --vault '{vault_path}'", file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)


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
                    help="after install, verify each referenced script exists on disk and report")
    ap.add_argument("--fail-on-missing", action="store_true",
                    help="exit nonzero if any required hook script is missing on disk "
                         "(implies --verify; used by bootstrap.sh to escalate divergent-fork strands)")
    args = ap.parse_args()

    # === make the vault the home of Claude Code's memory ===
    # Independent of the hooks install and idempotent, so do it first whenever a
    # vault path is known. This is the step that makes the "your brain lives in
    # your vault" promise true: without it, Claude Code's memory strands in
    # ~/.claude/projects/<key>/memory/, invisible in Obsidian.
    if args.vault_path and not args.dry_run and not args.uninstall:
        link_agent_memory_into_vault(args.vault_path, args.quiet)

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
    # Retire hooks deleted from the template but still wired in this user's
    # settings.json (merge never deletes). This un-wires removed hooks.
    merged, retired_count = retire_stale_hooks(merged)

    if not args.quiet:
        print(f"Merging into: {settings_path}")
        print(f"Source:       {hooks_template_path}")
        print(f"Events:       {', '.join(summary['events_touched'])}")
        print(f"Added:        {len(summary['added'])} hook(s)")
        print(f"Updated:      {len(summary['updated'])} hook(s)")
        print(f"Retired:      {retired_count} stale hook(s) removed")
        print(f"Preserved:    {len(set(summary['kept']))} non-ABS hook(s) untouched")

    if args.dry_run:
        if not args.quiet:
            print("\nDRY RUN — no changes written.")
            for entry in summary["added"]:
                print(f"  + {entry}")
            for entry in summary["updated"]:
                print(f"  ~ {entry}")
            if retired_count:
                print(f"  - retire {retired_count} stale hook(s)")
        return 0

    if not summary["added"] and not summary["updated"] and not retired_count:
        if not args.quiet:
            print("\nAlready in sync. Nothing to write.")
        return 0

    backup = backup_settings(settings_path)
    if write_settings_with_verify(settings_path, merged, backup):
        if not args.quiet:
            print(f"\nWrote {settings_path}")
            if backup:
                print(f"Backup: {backup}")
        if args.verify or args.fail_on_missing:
            rc = run_verification(merged, fail_on_missing=args.fail_on_missing)
            if rc != 0:
                return rc
        return 0
    return 2


def _is_gated_command(cmd: str, script_path: str) -> bool:
    """True if the command is wrapped in `[ -f <script> ] && ...` — meaning
    the script is intentionally optional and missing on disk is not a bug.
    The auto-update flow uses this for cross-vault portability."""
    import re
    # Match `[ -f <path> ]` where <path> is the same as the script being run.
    # Allow `~` prefix and arbitrary whitespace; match either bare or quoted.
    norm = script_path.replace("'", "").replace('"', "")
    pattern = re.compile(
        r"\[\s*-f\s+['\"]?" + re.escape(norm) + r"['\"]?\s*\]\s*&&"
    )
    return bool(pattern.search(cmd))


def verify_paths_on_disk(settings: dict) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Inspect every ABS-owned hook command in settings; verify the referenced
    script exists on disk. Distinguishes:

      - REQUIRED: command runs the script directly (`python3 <path> ...`).
        Script missing = silent hook failure at runtime.
      - OPTIONAL: command wraps in `[ -f <path> ] && ...`. Missing is fine;
        the guard suppresses the call.

    Returns (missing_required, missing_optional), each a list of
    (event, script_path, full_command_short).

    The full_command_short is the first 80 chars of the command for grep-friendly
    error output without dumping the entire 1500-char auto-update one-liner.
    """
    import re
    missing_required: list[tuple[str, str, str]] = []
    missing_optional: list[tuple[str, str, str]] = []
    # Match `python3 <path>` or `bash <path>` with optional quotes and ~ prefix.
    # Non-greedy stops at whitespace, quote, pipe, ampersand, semicolon.
    path_re = re.compile(r"(?:python3|bash)\s+['\"]?(~?[^\s'\"|&;]+)['\"]?")

    for event, groups in (settings.get("hooks") or {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                cmd = h.get("command", "")
                if not cmd or not is_abs_owned(cmd):
                    continue
                # Find every script path the command references — a single
                # hook may chain `python3 a.py && bash b.sh`.
                for m in path_re.finditer(cmd):
                    raw = m.group(1)
                    p = Path(os.path.expanduser(raw))
                    if p.is_file():
                        continue
                    short = cmd[:80] + ("…" if len(cmd) > 80 else "")
                    entry = (event, str(p), short)
                    if _is_gated_command(cmd, raw):
                        missing_optional.append(entry)
                    else:
                        missing_required.append(entry)
    return missing_required, missing_optional


def run_verification(settings: dict, fail_on_missing: bool = False) -> int:
    """Print verification report. Returns 0 if all required paths exist, 1 otherwise.

    With fail_on_missing=True, the caller should propagate the nonzero exit
    (used by bootstrap.sh to escalate a divergent-fork strand to `err`).
    """
    print("\n--- Verification ---")
    missing_required, missing_optional = verify_paths_on_disk(settings)
    ok_count = 0
    for event, groups in (settings.get("hooks") or {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                cmd = h.get("command", "")
                if cmd and is_abs_owned(cmd):
                    ok_count += 1
    # Print OK count rather than every entry to keep output scannable
    ok_count -= len(missing_required) + len(missing_optional)
    print(f"  OK     {ok_count} hook(s) — referenced scripts exist on disk")
    if missing_optional:
        print(f"  SKIP   {len(missing_optional)} hook(s) — optional (gated by [ -f ... ] guard):")
        for event, p, _short in missing_optional:
            print(f"           {event}: {p}")
    if missing_required:
        print(f"  FAIL   {len(missing_required)} hook(s) — script not on disk:")
        for event, p, short in missing_required:
            print(f"           {event}: {p}")
            print(f"             command: {short}")
        print()
        print("  Likely cause: ai-brain-starter clone is on a DIVERGENT FORK and")
        print("  bootstrap.sh skipped the pull, but the installer wrote new")
        print("  hook entries that reference files only present on origin/main.")
        print("  Recover:")
        print("    cd ~/.claude/skills/ai-brain-starter && git pull --rebase origin main")
        print("    python3 ~/.claude/skills/ai-brain-starter/scripts/install-hooks-user-level.py")
        if fail_on_missing:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
