#!/usr/bin/env python3
"""Monthly vault maintenance scan.

Checks for common vault hygiene issues and writes a Markdown report.
Designed to run on a schedule (monthly recommended) via Claude Code
scheduled tasks or cron.

Checks performed:
  1. Inbox overdue - files in Inbox/ older than 7 days
  2. Naming issues - filenames longer than 60 chars or starting lowercase
  3. Stray binaries - images/PDFs/docs outside designated folders
  4. Backup accumulation - .bak / .backup_ files
  5. Empty folders
  6. Large folders - any folder with 500+ files
  7. Graphify backup count - graph.json.backup_* files (target: <=3)

Usage:
  python3 vault_maintenance.py --vault-root /path/to/vault

The report is written to {vault-root}/Meta/Maintenance Report.md
(auto-detects whether Meta uses an emoji prefix).
"""

import argparse
import os
import time
from datetime import datetime
from pathlib import Path

SKIP_DIRS = {".git", ".claude", "node_modules", "graphify-input", ".obsidian"}

# Default folders where binaries are expected (relative to vault root).
# Override with --binary-allowed flag.
DEFAULT_BINARY_ALLOWED = [
    "Media",
    "Pics",
    "Attachments",
    "Meta/Attachments",
    "Archive",
]

BINARY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".psd",
                     ".docx", ".xlsx", ".xls", ".pptx", ".mp4", ".mov",
                     ".key", ".numbers", ".pages", ".mobi", ".xd"}

INBOX_MAX_AGE_DAYS = 7


def find_meta_dir(vault_root: Path) -> Path:
    """Auto-detect the Meta folder (with or without emoji prefix)."""
    for candidate in vault_root.iterdir():
        if candidate.is_dir() and candidate.name.endswith("Meta"):
            return candidate
    return vault_root / "Meta"


def find_inbox_dir(vault_root: Path) -> Path:
    """Auto-detect the Inbox folder (with or without emoji prefix)."""
    for candidate in vault_root.iterdir():
        if candidate.is_dir() and "Inbox" in candidate.name:
            return candidate
    return vault_root / "Inbox"


def should_skip(path: Path, vault_root: Path) -> bool:
    """Return True if this path is inside a directory we skip."""
    rel = path.relative_to(vault_root)
    return any(part in SKIP_DIRS for part in rel.parts)


def is_binary_allowed(rel_dir: str, allowed_prefixes: list[str]) -> bool:
    """Check if a directory is in the binary-allowed list."""
    for prefix in allowed_prefixes:
        if rel_dir == prefix or rel_dir.startswith(prefix + "/"):
            return True
        # Also match emoji-prefixed versions (e.g. "Media" matches "📸 Media")
        dir_basename = rel_dir.split("/")[0] if "/" in rel_dir else rel_dir
        if dir_basename.endswith(prefix):
            return True
    return False


def check_inbox_overdue(vault_root: Path) -> list[str]:
    inbox = find_inbox_dir(vault_root)
    if not inbox.exists():
        return []
    cutoff = time.time() - INBOX_MAX_AGE_DAYS * 86400
    results = []
    for f in inbox.iterdir():
        if f.is_file() and f.name != "README.md" and f.stat().st_mtime < cutoff:
            age_days = int((time.time() - f.stat().st_mtime) / 86400)
            results.append(f"- `{f.name}` ({age_days} days old)")
    results.sort()
    return results


def check_naming_issues(vault_root: Path) -> list[str]:
    results = []
    for root, dirs, files in os.walk(vault_root):
        root_path = Path(root)
        if should_skip(root_path, vault_root):
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if fname.startswith("."):
                continue
            stem = Path(fname).stem
            if len(fname) > 60:
                results.append(f"- Too long: `{fname}`")
            elif stem and stem[0].islower() and stem != "README":
                results.append(f"- Lowercase start: `{fname}`")
    results.sort()
    return results


def check_stray_binaries(vault_root: Path, allowed: list[str]) -> list[str]:
    results = []
    for root, dirs, files in os.walk(vault_root):
        root_path = Path(root)
        if should_skip(root_path, vault_root):
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel_dir = root_path.relative_to(vault_root).as_posix()
        for fname in files:
            ext = Path(fname).suffix.lower()
            if ext not in BINARY_EXTENSIONS:
                continue
            if rel_dir != "." and is_binary_allowed(rel_dir, allowed):
                continue
            loc = f"{rel_dir}/{fname}" if rel_dir != "." else fname
            results.append(f"- `{loc}`")
    results.sort()
    return results


def check_backup_files(vault_root: Path) -> list[str]:
    results = []
    for root, dirs, files in os.walk(vault_root):
        root_path = Path(root)
        if should_skip(root_path, vault_root):
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel_dir = root_path.relative_to(vault_root).as_posix()
        for fname in files:
            if ".bak" in fname or ".backup_" in fname:
                loc = f"{rel_dir}/{fname}" if rel_dir != "." else fname
                results.append(f"- `{loc}`")
    results.sort()
    return results


def check_empty_folders(vault_root: Path) -> list[str]:
    results = []
    for root, dirs, files in os.walk(vault_root):
        root_path = Path(root)
        if should_skip(root_path, vault_root):
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if not dirs and not files and root_path != vault_root:
            rel = root_path.relative_to(vault_root).as_posix()
            results.append(f"- `{rel}/`")
    results.sort()
    return results


def check_large_folders(vault_root: Path, threshold: int = 500) -> list[str]:
    results = []
    for root, dirs, files in os.walk(vault_root):
        root_path = Path(root)
        if should_skip(root_path, vault_root):
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if len(files) >= threshold:
            rel = root_path.relative_to(vault_root).as_posix()
            results.append(f"- `{rel}/` ({len(files)} files)")
    results.sort()
    return results


def check_graphify_backups(vault_root: Path) -> list[str]:
    out_dir = vault_root / "graphify-out"
    if not out_dir.exists():
        return []
    return [f"- `{b.name}`" for b in sorted(out_dir.glob("graph.json.backup_*"))]


def generate_report(vault_root: Path, binary_allowed: list[str]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")

    inbox = check_inbox_overdue(vault_root)
    naming = check_naming_issues(vault_root)
    binaries = check_stray_binaries(vault_root, binary_allowed)
    backups = check_backup_files(vault_root)
    empty = check_empty_folders(vault_root)
    large = check_large_folders(vault_root)
    graphify = check_graphify_backups(vault_root)

    categories = sum(1 for lst in [inbox, naming, binaries, backups, empty, large] if lst)
    total = len(inbox) + len(naming) + len(binaries) + len(backups) + len(empty) + len(large)

    s = []
    s.append(f"---\ncreationDate: {today}\ntype: meta\n---\n")
    s.append(f"# Vault Maintenance Report - {today}\n")
    s.append("## Summary")
    s.append(f"- {total} issues found across {categories} categories\n")

    for title, items, empty_msg in [
        ("Inbox Overdue", inbox, "No overdue files."),
        ("Naming Issues", naming, "No naming issues."),
        ("Stray Binaries", binaries, "No stray binaries."),
        ("Backup Accumulation", backups, "No backup files found."),
        ("Empty Folders", empty, "No empty folders."),
        ("Large Folders", large, "No folders with 500+ files."),
    ]:
        s.append(f"## {title} ({len(items)})")
        s.append("\n".join(items) if items else empty_msg)
        s.append("")

    s.append("## Graphify Backup Count")
    s.append(f"{len(graphify)} backups found (target: <=3)")
    if graphify:
        s.append("\n".join(graphify))
    s.append("")

    return "\n".join(s)


def main():
    parser = argparse.ArgumentParser(description="Vault maintenance scan")
    parser.add_argument("--vault-root", type=Path, required=True,
                        help="Path to the Obsidian vault root")
    parser.add_argument("--binary-allowed", nargs="*", default=None,
                        help="Folder prefixes where binaries are expected "
                             "(default: Media, Pics, Attachments, Archive)")
    args = parser.parse_args()

    vault_root = args.vault_root.resolve()
    if not vault_root.is_dir():
        print(f"Error: vault root not found at {vault_root}")
        raise SystemExit(1)

    binary_allowed = args.binary_allowed or DEFAULT_BINARY_ALLOWED

    report = generate_report(vault_root, binary_allowed)

    meta_dir = find_meta_dir(vault_root)
    report_path = meta_dir / "Maintenance Report.md"
    report_path.write_text(report, encoding="utf-8")

    print(f"Vault maintenance scan complete for: {vault_root}")
    print(f"Report written to: {report_path}")


if __name__ == "__main__":
    main()
