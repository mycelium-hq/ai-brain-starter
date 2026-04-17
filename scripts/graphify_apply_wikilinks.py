#!/usr/bin/env python3
"""
graphify_apply_wikilinks.py — interactively approve and apply wikilinks.

Reads WIKILINK_GAPS.md (edit it first to remove unwanted rows), shows each
candidate with context from the vault, prompts for approval, and inserts
[[wikilinks]] into the first occurrence per file.

For single first names, prompts for the full name and uses alias syntax:
    [[George Trimis|George]]

Usage:
    python3 graphify_apply_wikilinks.py [options]

    --report PATH       Path to WIKILINK_GAPS.md (auto-detected if omitted)
    --vault-root PATH   Vault root (default: current directory)
    --dry-run           Show changes without writing files
"""

import argparse
import re
import sys
from pathlib import Path

SKIP_PARTS = {"⚙️ Meta", "Archive", "🗄 Archive", "_review_alternate_drafts"}

# Matches an existing [[wikilink]] so we don't double-link
EXISTING_LINK_RE = re.compile(r'\[\[[^\]]+\]\]')


def load_report(report_path: Path) -> list[dict]:
    """Parse WIKILINK_GAPS.md table rows into dicts."""
    terms = []
    for line in report_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        # Columns: # | Entity | Type | Connections | Note
        if len(parts) < 4 or parts[0] in ("#", "---", ""):
            continue
        try:
            int(parts[0])  # first col must be a row number
        except ValueError:
            continue
        terms.append({
            "label": parts[1],
            "type": parts[2],
            "degree": int(parts[3]) if parts[3].isdigit() else 0,
            "needs_disambiguation": "first name" in parts[4].lower() if len(parts) > 4 else False,
        })
    return terms


def find_contexts(vault: Path, search_term: str, max_results: int = 3) -> list[tuple[Path, str, int]]:
    """
    Find files with unlinked occurrences of search_term.
    Returns list of (file, snippet, char_offset) tuples.
    Skips occurrences already inside [[...]].
    """
    # Word-boundary search, case-insensitive
    pattern = re.compile(r'\b' + re.escape(search_term) + r'\b', re.IGNORECASE)
    results = []

    for md in vault.rglob("*.md"):
        if any(part in SKIP_PARTS for part in md.parts):
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        # Build set of spans already inside wikilinks
        linked_spans = set()
        for m in EXISTING_LINK_RE.finditer(text):
            linked_spans.add((m.start(), m.end()))

        for m in pattern.finditer(text):
            # Skip if inside an existing wikilink
            if any(s <= m.start() and m.end() <= e for s, e in linked_spans):
                continue
            start = max(0, m.start() - 90)
            end = min(len(text), m.end() + 90)
            snippet = "..." + text[start:end].replace("\n", " ").strip() + "..."
            results.append((md, snippet, m.start()))
            if len(results) >= max_results:
                return results

    return results


def apply_wikilink(
    vault: Path,
    search_term: str,
    link_target: str,
    display: str,
    dry_run: bool,
) -> int:
    """
    Insert [[link_target|display]] (or [[term]]) as first occurrence per file.
    Skips occurrences already inside [[...]].
    Returns count of files modified.
    """
    is_alias = link_target != display
    replacement = f"[[{link_target}|{display}]]" if is_alias else f"[[{search_term}]]"
    pattern = re.compile(r'\b' + re.escape(search_term) + r'\b', re.IGNORECASE)
    modified = 0

    for md in vault.rglob("*.md"):
        if any(part in SKIP_PARTS for part in md.parts):
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        # Build set of spans already inside wikilinks
        linked_spans = set()
        for lm in EXISTING_LINK_RE.finditer(text):
            linked_spans.add((lm.start(), lm.end()))

        # Find first unlinked occurrence
        for m in pattern.finditer(text):
            if any(s <= m.start() and m.end() <= e for s, e in linked_spans):
                continue
            # Replace this first occurrence
            new_text = text[: m.start()] + replacement + text[m.end() :]
            if dry_run:
                print(f"  [DRY RUN] {md.name}: '{m.group()}' → {replacement}")
            else:
                md.write_text(new_text, encoding="utf-8")
            modified += 1
            break  # first occurrence per file only

    return modified


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--report", default=None, metavar="PATH",
                        help="Path to WIKILINK_GAPS.md")
    parser.add_argument("--vault-root", default=".", metavar="PATH")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing files")
    args = parser.parse_args()

    vault = Path(args.vault_root).resolve()

    # Find report
    if args.report:
        report_path = Path(args.report)
    else:
        for candidate in [
            vault / "⚙️ Meta/graphify-out/WIKILINK_GAPS.md",
            vault / "graphify-out/WIKILINK_GAPS.md",
        ]:
            if candidate.exists():
                report_path = candidate
                break
        else:
            sys.exit("ERROR: WIKILINK_GAPS.md not found. Use --report to specify.")

    terms = load_report(report_path)
    if not terms:
        sys.exit("No terms found in the report. Check formatting or re-run graphify_wikilink_gaps.py.")

    print(f"Loaded {len(terms)} candidates from {report_path.name}")
    if args.dry_run:
        print("[DRY RUN — no files will be modified]\n")
    print("Commands: y = add wikilink | n = skip | q = quit\n")
    print("-" * 60)

    applied: list[dict] = []
    skipped: list[str] = []

    for i, term_info in enumerate(terms, 1):
        label = term_info["label"]
        print(f"\n[{i}/{len(terms)}] {label}  ({term_info['type']}, {term_info['degree']} connections)")

        # Show context snippets
        contexts = find_contexts(vault, label)
        if not contexts:
            print("  (no unlinked occurrences found — already linked or not in vault)")
            skipped.append(label)
            continue
        for _, snippet, _ in contexts[:2]:
            print(f"  > {snippet}")

        # Flag disambiguation need
        if term_info["needs_disambiguation"]:
            print(f"  ⚠ Looks like a first name. You'll be prompted for the full name.")

        # Prompt
        try:
            choice = input("  Add wikilink? [y/n/q]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            break

        if choice == "q":
            print("Quitting.")
            break
        elif choice != "y":
            skipped.append(label)
            continue

        # Handle first-name disambiguation
        link_target = label
        display = label
        if term_info["needs_disambiguation"]:
            try:
                full_name = input(
                    f"  Full name for [[Full Name|{label}]]? "
                    f"(Enter to use '{label}' as-is): "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                full_name = ""
            if full_name:
                link_target = full_name
                display = label

        count = apply_wikilink(vault, label, link_target, display, args.dry_run)
        tag = f"[[{link_target}|{display}]]" if link_target != display else f"[[{label}]]"
        print(f"  {tag} — linked in {count} file(s)")
        applied.append({"tag": tag, "files": count})

    # Summary
    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Done.")
    print(f"  Applied: {len(applied)}  |  Skipped: {len(skipped)}")
    if applied:
        print("\n  Applied wikilinks:")
        for a in applied:
            print(f"    {a['tag']} — {a['files']} file(s)")


if __name__ == "__main__":
    main()
