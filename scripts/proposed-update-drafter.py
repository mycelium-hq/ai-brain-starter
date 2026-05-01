#!/usr/bin/env python3
"""
proposed-update-drafter.py surfaces downstream files when a rule changes.

When a typed-memory rule is updated (a decision is revised, a workflow's
freshness window shortens, a fact is reclassified), every downstream file
that references that rule needs a verification pass. This drafter walks
the vault for both wikilink and path references to the changed source
file, then prepends a proposed-update HTML comment block at the top of
each downstream file flagging the change and asking the owner to verify.

The comment block is idempotent on rule_id and changed_file path: re-
running the drafter on the same source replaces the prior block in place
rather than stacking duplicate banners.

Usage:
  python3 scripts/proposed-update-drafter.py \
      --vault-root /path/to/vault \
      --changed-file /path/to/Meta/Decisions/Foo.md
  python3 scripts/proposed-update-drafter.py \
      --vault-root /path/to/vault \
      --changed-file /path/to/Meta/Decisions/Foo.md \
      --dry-run
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path


SCAN_EXTENSIONS = {".md"}

BLOCK_BEGIN_PREFIX = "<!-- proposed-update:BEGIN "
BLOCK_END = "<!-- proposed-update:END -->"


def find_references(vault_root: Path, changed_file: Path) -> list[Path]:
    """Walk the vault and return every file that references changed_file.

    Matches three reference shapes:
      - [[stem]]              wikilink by file stem
      - [[relative/path]]     wikilink by path-form (without .md)
      - inline relative path  e.g. Meta/Decisions/Foo.md
    """
    stem = changed_file.stem
    rel_to_vault = ""
    try:
        rel_to_vault = str(changed_file.resolve().relative_to(vault_root.resolve()))
    except ValueError:
        rel_to_vault = ""

    rel_no_ext = rel_to_vault[:-3] if rel_to_vault.endswith(".md") else rel_to_vault

    candidates_wikilink: list[str] = [stem]
    if rel_no_ext:
        candidates_wikilink.append(rel_no_ext)
    candidates_path: list[str] = []
    if rel_to_vault:
        candidates_path.append(rel_to_vault)

    references: list[Path] = []
    changed_resolved = changed_file.resolve()

    for path in vault_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in SCAN_EXTENSIONS:
            continue
        if path.resolve() == changed_resolved:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        matched = False
        for cand in candidates_wikilink:
            pattern = r"\[\[" + re.escape(cand) + r"(\||\#|\]\])"
            if re.search(pattern, text):
                matched = True
                break
        if not matched:
            for cand in candidates_path:
                if cand and cand in text:
                    matched = True
                    break

        if matched:
            references.append(path)

    return sorted(set(references))


def build_block(changed_file_rel: str, today: str) -> str:
    rule_id = Path(changed_file_rel).stem
    return (
        f"{BLOCK_BEGIN_PREFIX}{rule_id} -->\n"
        f"<!-- proposed-update:CHANGED_FILE {changed_file_rel} -->\n"
        f"<!-- proposed-update:DRAFTED_AT {today} -->\n"
        f"> Proposed update: the source rule "
        f"`{changed_file_rel}` changed on {today}. This file references "
        f"that rule. Verify the reference is still accurate, then remove "
        f"this block.\n"
        f"{BLOCK_END}\n\n"
    )


def insert_or_replace_block(
    text: str, changed_file_rel: str, today: str
) -> tuple[str, str]:
    """Return (new_text, action) where action is 'inserted' or 'replaced'."""
    rule_id = Path(changed_file_rel).stem
    pattern = re.compile(
        re.escape(BLOCK_BEGIN_PREFIX + rule_id + " -->")
        + r".*?"
        + re.escape(BLOCK_END)
        + r"\n*",
        re.DOTALL,
    )
    block = build_block(changed_file_rel, today)
    if pattern.search(text):
        return pattern.sub(block, text, count=1), "replaced"
    if text.startswith("---"):
        end = text.find("\n---\n", 4)
        if end != -1:
            insertion = end + len("\n---\n")
            return text[:insertion] + "\n" + block + text[insertion:], "inserted"
    return block + text, "inserted"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepend proposed-update banners to every vault file that "
            "references a changed source rule."
        )
    )
    parser.add_argument(
        "--vault-root",
        type=Path,
        default=Path(os.environ.get("VAULT_ROOT", Path.cwd())),
    )
    parser.add_argument(
        "--changed-file",
        type=Path,
        required=True,
        help="Path to the source rule that changed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print which files would be updated without writing.",
    )
    args = parser.parse_args()

    vault_root = args.vault_root.resolve()
    changed = args.changed_file.resolve()
    if not vault_root.is_dir():
        print(f"ERROR: vault root not found: {vault_root}", file=sys.stderr)
        return 1
    if not changed.is_file():
        print(f"ERROR: changed file not found: {changed}", file=sys.stderr)
        return 1

    refs = find_references(vault_root, changed)
    today = dt.date.today().isoformat()
    try:
        changed_rel = str(changed.relative_to(vault_root))
    except ValueError:
        changed_rel = str(changed)

    if not refs:
        print(f"No downstream references to {changed_rel}.")
        return 0

    print(f"Found {len(refs)} reference(s) to {changed_rel}:")
    for ref in refs:
        print(f"  - {ref.relative_to(vault_root)}")

    if args.dry_run:
        print("--- DRY RUN: no files written ---")
        return 0

    for ref in refs:
        try:
            text = ref.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"  skip {ref}: {exc}", file=sys.stderr)
            continue
        new_text, action = insert_or_replace_block(text, changed_rel, today)
        ref.write_text(new_text, encoding="utf-8")
        print(f"  {action}: {ref.relative_to(vault_root)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
