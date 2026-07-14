#!/usr/bin/env python3
"""Build a date index of all journal entries for fast lookup by the insights skill.

Reads YAML frontmatter from every .md file in your journal directory and emits
a sorted JSON index of {file, date, floor, floor_level} entries. The insights
skill (and any /weekly or /monthly review) uses this index to scan thousands
of journal entries in milliseconds without re-reading every file.

Run weekly via cron, or manually after a journaling session.

Usage:
    python3 build-journal-index.py [--vault-root .] [--journal-dir Journals]

The output is written to:
    <vault-root>/<meta-dir>/journal-index.json

The Meta folder (where the index is written) is auto-detected via the shared
_meta_resolver, so both "⚙️ Meta" and plain "Meta" layouts work. It must already
exist — the script fails loud rather than creating a stray folder. Layout:
    vault-root/
      Journals/                ← --journal-dir
        2026-04-11.md
        2026-04-10.md
      ⚙️ Meta/ (or Meta/)       ← auto-detected; where the index is written

Expected frontmatter fields (only `creationDate` is required):
    ---
    creationDate: 2026-04-11
    floor: Courage
    floor_level: middle
    ---
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
from _meta_resolver import find_meta_dir  # noqa: E402
from _lib.safe_read import safe_read_text  # noqa: E402

# Read bounds for the shared safe_read primitive. Journal frontmatter sits in
# the first lines; safe_read hands back the whole (size-capped) file. 1 MB is
# far beyond any real single-day entry; anything larger is surfaced as skipped,
# never silently dropped.
READ_TIMEOUT = 5.0
MAX_JOURNAL_BYTES = 1_000_000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault-root", default=".",
                    help="Vault root directory (default: current working directory)")
    ap.add_argument("--journal-dir", default="Journals",
                    help="Journal subfolder relative to vault root (default: Journals)")
    ap.add_argument("--meta-dir", default=None,
                    help="Meta subfolder where the index is written. Default: auto-detect the "
                         "vault's Meta folder (handles '⚙️ Meta' and plain 'Meta'). The folder "
                         "must already exist; this script never creates it.")
    args = ap.parse_args()

    vault = os.path.abspath(args.vault_root)
    journal_dir = os.path.join(vault, args.journal_dir)

    if not os.path.isdir(journal_dir):
        print(f"journal directory not found: {journal_dir}", file=sys.stderr)
        sys.exit(1)

    # Resolve the Meta folder where the index is written. It must ALREADY exist —
    # never create it. A wrong --meta-dir (or the old hardcoded "Meta" default on an
    # emoji-prefixed "⚙️ Meta" vault) used to silently makedirs a stray folder and
    # let the real journal-index.json go stale. Fail loud instead.
    if args.meta_dir is not None:
        meta_dir = os.path.join(vault, args.meta_dir)
    else:
        resolved = find_meta_dir(Path(vault))
        meta_dir = str(resolved) if resolved is not None else ""

    if not meta_dir or not os.path.isdir(meta_dir):
        target = meta_dir or f"a 'Meta' or '⚙️ Meta' folder under {vault}"
        print(f"meta directory not found: {target}\n"
              f"Refusing to create it (silent creation is the stray-folder bug). Create the "
              f"Meta folder, or pass --meta-dir <name> for a non-standard layout.",
              file=sys.stderr)
        sys.exit(1)

    output_path = os.path.join(meta_dir, "journal-index.json")
    entries = []
    skipped = []

    # Recursive walk: indexes journals nested under year-month subfolders
    # (e.g. Journals/2026-04/2026-04-15.md), not just top-level files.
    for root, _dirs, files in os.walk(journal_dir):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(root, fname)
            # Bounded, symlink-refusing read via the shared safe_read primitive
            # (regular files only, size-capped, timeout-bounded). Frontmatter is
            # in the first lines; safe_read hands back the whole capped file.
            res = safe_read_text(
                fpath, timeout=READ_TIMEOUT, max_bytes=MAX_JOURNAL_BYTES, errors="replace"
            )
            if not res.ok:
                skipped.append((os.path.relpath(fpath, journal_dir), res.status))
                continue
            in_fm = False
            meta = {}
            for i, line in enumerate(res.text.splitlines()):
                if i == 0 and line.strip() == "---":
                    in_fm = True
                    continue
                if in_fm:
                    if line.strip() == "---":
                        break
                    if ": " in line:
                        k, v = line.split(": ", 1)
                        meta[k.strip()] = v.strip().strip("'\"")
                if i > 15:
                    break
            if "creationDate" in meta:
                # Store path relative to journal_dir so subfoldered entries
                # with colliding basenames stay distinct.
                entry = {
                    "file": os.path.relpath(fpath, journal_dir),
                    "date": meta["creationDate"][:10],
                }
                if "floor" in meta:
                    entry["floor"] = meta["floor"]
                if "floor_level" in meta:
                    entry["floor_level"] = meta["floor_level"]
                entries.append(entry)

    if skipped:
        preview = ", ".join(f"{f} [{s}]" for f, s in skipped[:5])
        more = " ..." if len(skipped) > 5 else ""
        print(f"  note: skipped {len(skipped)} unreadable file(s): {preview}{more}",
              file=sys.stderr)
    entries.sort(key=lambda x: x["date"])
    output = {
        "total": len(entries),
        "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "entries": entries,
    }
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Indexed {len(entries)} entries → {output_path}")
    if entries:
        print(f"  date range: {entries[0]['date']} → {entries[-1]['date']}")


if __name__ == "__main__":
    # Windows cp1252-console safety (#313): force UTF-8 so a non-ASCII print can't crash.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass
    main()
