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

Defaults assume a vault layout like:
    vault-root/
      Journals/                ← --journal-dir
        2026-04-11.md
        2026-04-10.md
      Meta/                    ← --meta-dir (where the index is written)

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault-root", default=".",
                    help="Vault root directory (default: current working directory)")
    ap.add_argument("--journal-dir", default="Journals",
                    help="Journal subfolder relative to vault root (default: Journals)")
    ap.add_argument("--meta-dir", default="Meta",
                    help="Meta subfolder where the index is written (default: Meta)")
    args = ap.parse_args()

    vault = os.path.abspath(args.vault_root)
    journal_dir = os.path.join(vault, args.journal_dir)
    meta_dir = os.path.join(vault, args.meta_dir)

    if not os.path.isdir(journal_dir):
        print(f"journal directory not found: {journal_dir}", file=sys.stderr)
        sys.exit(1)
    os.makedirs(meta_dir, exist_ok=True)

    output_path = os.path.join(meta_dir, "journal-index.json")
    entries = []

    for fname in os.listdir(journal_dir):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(journal_dir, fname)
        if os.path.isdir(fpath):
            continue
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                in_fm = False
                meta = {}
                for i, line in enumerate(f):
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
                    entry = {
                        "file": fname,
                        "date": meta["creationDate"][:10],
                    }
                    if "floor" in meta:
                        entry["floor"] = meta["floor"]
                    if "floor_level" in meta:
                        entry["floor_level"] = meta["floor_level"]
                    entries.append(entry)
        except Exception:
            pass

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
    main()
