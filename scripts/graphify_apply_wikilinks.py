#!/usr/bin/env python3
"""
graphify_apply_wikilinks.py — interactively approve and apply wikilinks.

Reads WIKILINK_GAPS.md (edit it first to remove unwanted rows), shows each
candidate with context from the vault, prompts for approval, and inserts
[[wikilinks]] into the first occurrence per file.

After applying a wikilink, if the entity has no existing note it offers to
create a stub note seeded with REAL verbatim excerpts from vault mentions:
  - People  → 👤 CRM/<Name>.md  (CRM format + real quotes + backlinks Dataview)
  - Concepts → 📝 Notes/<Name>.md  (concept format + real quotes + backlinks Dataview)

No summarization, no hallucination — only text pulled directly from your notes.
The Dataview block auto-populates the full backlink list in Obsidian.

For single first names, prompts for the full name and uses alias syntax:
    [[George Trimis|George]]

Usage:
    python3 graphify_apply_wikilinks.py [options]

    --report PATH         Path to WIKILINK_GAPS.md (auto-detected if omitted)
    --vault-root PATH     Vault root (default: current directory)
    --people-dir PATH     Where to create person stubs (default: 👤 CRM)
    --concepts-dir PATH   Where to create concept stubs (default: 📝 Notes)
    --dry-run             Show changes without writing files
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

SKIP_PARTS = {"⚙️ Meta", "Archive", "🗄 Archive", "_review_alternate_drafts"}
EXISTING_LINK_RE = re.compile(r'\[\[[^\]]+\]\]')

DATAVIEW_BACKLINKS = '''\
```dataviewjs
const name = dv.current().file.name;
const linked = dv.pages(`[[${name}]]`)
  .where(p => !p.file.path.includes("_meta"))
  .sort(p => p.creationDate || p.file.mtime, "desc");
const rows = linked.map(p => {
  const date = p.creationDate
    ? String(p.creationDate).slice(0,10)
    : p.file.mtime.toFormat("yyyy-MM-dd");
  const folder = p.file.folder.split("/").pop();
  return [p.file.link, date, folder];
});
dv.paragraph(`**${rows.length} mentions**`);
dv.table(["File", "Date", "Source"], rows);
```'''


# ---------------------------------------------------------------------------
# Vault mention extraction
# ---------------------------------------------------------------------------

def collect_mentions(vault: Path, search_term: str, max_per_file: int = 2, max_total: int = 10) -> list[tuple[str, str]]:
    """
    Find ALL mentions of search_term across vault (linked and unlinked).
    Returns list of (source_file_stem, verbatim_sentence) tuples.
    Pulls the full sentence containing the match, not just a character window.
    """
    # Match inside or outside wikilinks — we want all occurrences
    pattern = re.compile(r'\b' + re.escape(search_term) + r'\b', re.IGNORECASE)
    # Split into sentences on . ! ? or newline
    sentence_split = re.compile(r'(?<=[.!?\n])\s+')
    results = []

    for md in sorted(vault.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        if any(part in SKIP_PARTS for part in md.parts):
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        # Strip wikilink markup for cleaner quotes: [[X|Y]] → Y, [[X]] → X
        clean = re.sub(r'\[\[(?:[^\]|]+\|)?([^\]]+)\]\]', r'\1', text)

        file_hits = 0
        for m in pattern.finditer(clean):
            if file_hits >= max_per_file:
                break
            # Grab the sentence: scan backward to sentence start, forward to end
            start = max(0, m.start())
            # Walk back to sentence boundary
            s = clean.rfind('\n', 0, start)
            s = s + 1 if s >= 0 else 0
            # Walk forward to sentence boundary
            e = len(clean)
            for ch in '.!?\n':
                pos = clean.find(ch, m.end())
                if pos >= 0:
                    e = min(e, pos + 1)
            sentence = clean[s:e].strip()
            # Skip very short or very long extracts, skip pure frontmatter lines
            if len(sentence) < 20 or len(sentence) > 400 or sentence.startswith('---'):
                continue
            results.append((md.stem, sentence))
            file_hits += 1

        if len(results) >= max_total:
            break

    return results[:max_total]


# ---------------------------------------------------------------------------
# Stub note templates
# ---------------------------------------------------------------------------

def _format_quotes(mentions: list[tuple[str, str]]) -> str:
    if not mentions:
        return ""
    lines = []
    for source, sentence in mentions:
        lines.append(f"> {sentence}\n> — *{source}*\n")
    return "\n".join(lines)


def person_stub(name: str, first_name: str, mentions: list[tuple[str, str]]) -> str:
    aliases = f"\n- {first_name}" if first_name and first_name != name else ""
    quotes = _format_quotes(mentions)
    from_notes = f"\n## From your notes\n\n{quotes}" if quotes else ""
    return f"""\
---
creationDate: {date.today()}
aliases:{aliases}
type: person
relationship:
company:
status: active
last_interaction: {date.today()}
next_step: ''
priority:
---
{from_notes}

## Context
-

## Interactions

{DATAVIEW_BACKLINKS}
"""


def concept_stub(name: str, mentions: list[tuple[str, str]]) -> str:
    quotes = _format_quotes(mentions)
    from_notes = f"\n## From your notes\n\n{quotes}" if quotes else ""
    return f"""\
---
creationDate: {date.today()}
aliases: []
type: concept
---
{from_notes}

## All Entries

{DATAVIEW_BACKLINKS}
"""


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def load_report(report_path: Path) -> list[dict]:
    terms = []
    for line in report_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 4 or parts[0] in ("#", "---", ""):
            continue
        try:
            int(parts[0])
        except ValueError:
            continue
        terms.append({
            "label": parts[1],
            "type": parts[2],
            "degree": int(parts[3]) if parts[3].isdigit() else 0,
            "needs_disambiguation": "first name" in parts[4].lower() if len(parts) > 4 else False,
        })
    return terms


def find_note(vault: Path, name: str) -> Path | None:
    stem = name.lower()
    for md in vault.rglob("*.md"):
        if any(part in SKIP_PARTS for part in md.parts):
            continue
        if md.stem.lower() == stem:
            return md
    return None


def find_contexts(vault: Path, search_term: str, max_results: int = 2) -> list[tuple[Path, str]]:
    """Show preview snippets during approval prompt (unlinked only)."""
    pattern = re.compile(r'\b' + re.escape(search_term) + r'\b', re.IGNORECASE)
    results = []
    for md in vault.rglob("*.md"):
        if any(part in SKIP_PARTS for part in md.parts):
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        linked_spans = {(m.start(), m.end()) for m in EXISTING_LINK_RE.finditer(text)}
        for m in pattern.finditer(text):
            if any(s <= m.start() and m.end() <= e for s, e in linked_spans):
                continue
            start = max(0, m.start() - 90)
            end = min(len(text), m.end() + 90)
            snippet = "..." + text[start:end].replace("\n", " ").strip() + "..."
            results.append((md, snippet))
            if len(results) >= max_results:
                return results
    return results


def apply_wikilink(vault: Path, search_term: str, link_target: str, display: str, dry_run: bool) -> int:
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
        linked_spans = {(m.start(), m.end()) for m in EXISTING_LINK_RE.finditer(text)}
        for m in pattern.finditer(text):
            if any(s <= m.start() and m.end() <= e for s, e in linked_spans):
                continue
            new_text = text[: m.start()] + replacement + text[m.end():]
            if dry_run:
                print(f"  [DRY RUN] {md.name}: '{m.group()}' → {replacement}")
            else:
                md.write_text(new_text, encoding="utf-8")
            modified += 1
            break
    return modified


def create_stub(
    vault: Path,
    note_name: str,
    ntype: str,
    first_name: str,
    mentions: list[tuple[str, str]],
    people_dir: str,
    concepts_dir: str,
    dry_run: bool,
) -> Path | None:
    is_person = ntype.lower() == "person" or (
        len(note_name.split()) >= 2
        and all(w[0].isupper() for w in note_name.split() if w)
        and note_name.replace(" ", "").replace("-", "").isalpha()
    )
    if is_person:
        folder = vault / people_dir
        content = person_stub(note_name, first_name, mentions)
    else:
        folder = vault / concepts_dir
        content = concept_stub(note_name, mentions)

    note_path = folder / f"{note_name}.md"
    if dry_run:
        print(f"  [DRY RUN] Would create: {note_path.relative_to(vault)}")
        print(f"  [DRY RUN] Seeded with {len(mentions)} verbatim quote(s) from vault")
        return note_path
    folder.mkdir(parents=True, exist_ok=True)
    note_path.write_text(content, encoding="utf-8")
    return note_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--report", default=None, metavar="PATH")
    parser.add_argument("--vault-root", default=".", metavar="PATH")
    parser.add_argument("--people-dir", default="👤 CRM", metavar="PATH")
    parser.add_argument("--concepts-dir", default="📝 Notes", metavar="PATH")
    parser.add_argument("--dry-run", action="store_true")
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
        sys.exit("No terms found. Re-run graphify_wikilink_gaps.py first.")

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

        contexts = find_contexts(vault, label)
        if not contexts:
            print("  (no unlinked occurrences — already linked or not in vault)")
            skipped.append(label)
            continue
        for _, snippet in contexts:
            print(f"  > {snippet}")

        if term_info["needs_disambiguation"]:
            print("  ⚠ Looks like a first name. You'll be prompted for the full name.")

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

        # First-name disambiguation
        link_target = label
        display = label
        first_name = ""
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
                first_name = label

        count = apply_wikilink(vault, label, link_target, display, args.dry_run)
        tag = f"[[{link_target}|{display}]]" if link_target != display else f"[[{label}]]"
        print(f"  {tag} — linked in {count} file(s)")

        # Offer stub note creation if no existing note
        existing = find_note(vault, link_target)
        if existing:
            print(f"  Note exists: {existing.relative_to(vault)}")
        else:
            # Collect real quotes from vault before asking
            mentions = collect_mentions(vault, label)
            print(f"  Found {len(mentions)} mention(s) across vault to seed the note")
            try:
                stub_choice = input(f"  No note for '{link_target}'. Create stub? [y/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                stub_choice = "n"
            if stub_choice == "y":
                stub_path = create_stub(
                    vault, link_target, term_info["type"], first_name,
                    mentions, args.people_dir, args.concepts_dir, args.dry_run,
                )
                if stub_path:
                    rel = stub_path.relative_to(vault) if not args.dry_run else stub_path
                    print(f"  Created: {rel}")

        applied.append({"tag": tag, "files": count})

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Done.")
    print(f"  Applied: {len(applied)}  |  Skipped: {len(skipped)}")
    if applied:
        print("\n  Applied wikilinks:")
        for a in applied:
            print(f"    {a['tag']} — {a['files']} file(s)")


if __name__ == "__main__":
    main()
