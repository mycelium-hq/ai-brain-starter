#!/usr/bin/env python3
"""
rotate-meta-archives.py - move old Sessions/ and Decisions/ stubs into
Archive/YYYY-MM/ subfolders so the live folders stay small.

Without rotation, Sessions/ and Decisions/ accumulate forever (one new file
per session-close). After a few months you have hundreds of stubs in a
single flat folder, and Obsidian's file list becomes unusable. Rotation
keeps the live folders bounded by month while preserving full history.

Retention by filename ISO prefix (YYYY-MM-DDTHH-MM-...):
  - Sessions:  keep current month + previous month (older -> Archive)
  - Decisions: keep current month + previous 2 months (older -> Archive)

Usage:
  VAULT_ROOT=/path/to/vault python3 scripts/rotate-meta-archives.py
  python3 scripts/rotate-meta-archives.py --dry-run

Idempotent. Safe to run on a cron, a session-close hook, or by hand.

Environment variables:
  VAULT_ROOT  - absolute path to the Obsidian vault root.
                Defaults to two levels above this script (Meta/scripts/).
"""
import argparse
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path

VAULT = Path(os.environ.get("VAULT_ROOT", str(Path(__file__).resolve().parents[2])))
META = VAULT / "Meta"

ISO_PREFIX = re.compile(r"^(\d{4})-(\d{2})-\d{2}T")


def months_to_keep(today: date, previous: int) -> set:
    """Return YYYY-MM strings for current month plus N previous months."""
    keep = set()
    y, m = today.year, today.month
    for _ in range(previous + 1):
        keep.add(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return keep


def rotate(folder: Path, previous_months: int, archive_root: Path, dry_run: bool) -> int:
    if not folder.exists():
        return 0
    keep = months_to_keep(date.today(), previous_months)
    moved = 0
    for f in folder.glob("*.md"):
        m = ISO_PREFIX.match(f.name)
        if not m:
            continue
        ym = f"{m.group(1)}-{m.group(2)}"
        if ym in keep:
            continue
        target_dir = archive_root / ym
        if dry_run:
            print(f"[dry] {folder.name}/{f.name} -> Archive/{ym}/")
        else:
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), str(target_dir / f.name))
        moved += 1
    return moved


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sessions_moved = rotate(
        META / "Sessions",
        previous_months=1,
        archive_root=META / "Sessions" / "Archive",
        dry_run=args.dry_run,
    )
    decisions_moved = rotate(
        META / "Decisions",
        previous_months=2,
        archive_root=META / "Decisions" / "Archive",
        dry_run=args.dry_run,
    )
    tag = " (dry-run)" if args.dry_run else ""
    print(f"[rotate-meta-archives] Sessions moved: {sessions_moved}{tag}")
    print(f"[rotate-meta-archives] Decisions moved: {decisions_moved}{tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
