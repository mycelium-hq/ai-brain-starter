#!/usr/bin/env python3
"""
graphify_apply_wikilinks.py — interactively approve and apply wikilinks.

Reads WIKILINK_GAPS.md (edit it first to remove unwanted rows), shows each
candidate with context from the vault, prompts for approval, and inserts
[[wikilinks]] into the first occurrence per file.

After applying a wikilink, if the entity has no existing note it offers to
create a stub note. The stub is seeded by:
  1. Collecting real vault mentions (up to 40 for people, 15 for concepts)
  2. Calling Claude API to synthesize a Context section from only that text
     — no hallucination, Claude only sees sentences actually written in vault

  - People  → 👤 CRM/<Name>.md  (CRM format + synthesized context + Dataview)
  - Concepts → 📝 Notes/<Name>.md  (concept format + synthesized context + Dataview)

Requires: pip install anthropic
Env var:  ANTHROPIC_API_KEY

For single first names, prompts for the full name and uses alias syntax:
    [[George Trimis|George]]

Usage:
    python3 graphify_apply_wikilinks.py [options]

    --report PATH         Path to WIKILINK_GAPS.md (auto-detected if omitted)
    --vault-root PATH     Vault root (default: current directory)
    --people-dir PATH     Where to create person stubs (default: 👤 CRM)
    --concepts-dir PATH   Where to create concept stubs (default: 📝 Notes)
    --dry-run             Show changes without writing files

Maintenance runbook:
    1. Always run with --dry-run first. Review the proposed insertions before
       committing. Graph-derived labels occasionally include phrase fragments
       that look like concepts but over-match inline text.
    2. Hard guard: this script refuses to write path-form wikilinks
       ([[folder/Name]]). If a label or user-supplied full name contains "/",
       the slashes are stripped before writing. Path-form links break Obsidian's
       alias resolution and pollute the graph.
    3. FileNotFoundError / OSError on rglob is caught per-file. Dangling
       references (git-deleted stubs, temp files) skip cleanly.
    4. Pairs with graphify_wikilink_gaps.py — run gaps.py first to produce
       WIKILINK_GAPS.md, edit to remove unwanted rows, then run this script.
    5. If a graph node label is a multi-word phrase rather than a named concept,
       delete it from WIKILINK_GAPS.md before applying. Phrase-title notes
       produce aggressive matches across the vault.
    6. Companion audit: wikilink_misfire_audit.py detects and fixes path-form
       wikilinks if anything slips through. Run it after big apply passes.
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

def collect_mentions(
    vault: Path,
    search_term: str,
    max_per_file: int = 2,
    max_total: int | None = None,
    chronological: bool = False,
) -> list[tuple[str, str]]:
    """
    Find mentions of search_term across vault (linked and unlinked).
    Returns list of (source_file_stem, verbatim_sentence) tuples.

    max_total=None: collect all mentions (use for journal people).
    chronological=True: sort files oldest→newest (captures relationship arc).
    chronological=False: sort newest→oldest (default, good for concepts).
    """
    pattern = re.compile(r'\b' + re.escape(search_term) + r'\b', re.IGNORECASE)
    results = []

    files = sorted(
        vault.rglob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=not chronological,
    )

    for md in files:
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
            s = clean.rfind('\n', 0, m.start())
            s = s + 1 if s >= 0 else 0
            e = len(clean)
            for ch in '.!?\n':
                pos = clean.find(ch, m.end())
                if pos >= 0:
                    e = min(e, pos + 1)
            sentence = clean[s:e].strip()
            if len(sentence) < 20 or len(sentence) > 400 or sentence.startswith('---'):
                continue
            results.append((md.stem, sentence))
            file_hits += 1

        if max_total is not None and len(results) >= max_total:
            break

    return results if max_total is None else results[:max_total]


# ---------------------------------------------------------------------------
# Claude API synthesis
# ---------------------------------------------------------------------------

def synthesize_context(name: str, ntype: str, mentions: list[tuple[str, str]]) -> str:
    """
    Call Claude API to synthesize a ## Context section from real vault mentions.
    Input is only text pulled from the vault — Claude adds no outside knowledge.
    Returns bullet-point lines ready to paste into the note.
    Falls back to a blank bullet if anthropic is not installed or API fails.
    """
    if not mentions:
        return "-"

    try:
        import anthropic
    except ImportError:
        print("  ⚠ anthropic not installed — Context will be blank. Run: pip install anthropic")
        return "-"

    excerpts = "\n".join(
        f"[{source}] {sentence}" for source, sentence in mentions
    )

    n = len(mentions)

    if ntype.lower() == "person":
        # Scale detail to mention count: few mentions = brief (book author),
        # many mentions = full arc (journal person)
        if n >= 30:
            bullet_range = "8-15"
            depth_instruction = (
                "This person appears extensively in the journals. Write a detailed, "
                "narrative-quality context: how the relationship entered the vault owner's life, "
                "each distinct phase, key turning points, contradictions, emotional texture, "
                "and current status. Surface blind spots and coaching opportunities plainly."
            )
        elif n >= 10:
            bullet_range = "5-8"
            depth_instruction = (
                "Capture the relationship arc, key moments, emotional texture, and current status."
            )
        else:
            bullet_range = "3-5"
            depth_instruction = (
                "Capture who this person is and their role in the vault owner's life."
            )

        prompt = f"""\
You are writing a CRM note inside a personal Obsidian vault. Based ONLY on the following \
excerpts from the vault owner's own notes (oldest to newest), write {bullet_range} bullet points.

{depth_instruction}

Rules:
- Use ONLY information present in the excerpts. Do not add any outside knowledge.
- Write in third person about {name}.
- Be specific and direct. No filler. No hedging.
- If the relationship is complicated or contradictory, say so plainly.
- Facts only — this is for coaching and blind-spot detection, not flattery.

Excerpts ({n} total, chronological):
{excerpts}

Return only the bullet points, each starting with -"""
    else:
        prompt = f"""\
You are writing a concept note inside a personal Obsidian vault. Based ONLY on the following \
excerpts from the vault owner's own notes, write 3-5 concise bullet points capturing:
- How the vault owner uses or defines the concept "{name}"
- What it connects to or comes up alongside
- Any recurring pattern in how it appears

Rules:
- Use ONLY information present in the excerpts. Do not add any outside knowledge.
- Be specific and direct. No filler.

Excerpts:
{excerpts}

Return only the bullet points, each starting with -"""

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"  ⚠ Claude API call failed ({e}) — Context will be blank")
        return "-"


# ---------------------------------------------------------------------------
# Stub note templates
# ---------------------------------------------------------------------------

def person_stub(name: str, first_name: str, context_bullets: str) -> str:
    aliases = f"\n- {first_name}" if first_name and first_name != name else ""
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

## Context
{context_bullets}

## Interactions

{DATAVIEW_BACKLINKS}
"""


def concept_stub(name: str, context_bullets: str) -> str:
    return f"""\
---
creationDate: {date.today()}
aliases: []
type: concept
---

## Context
{context_bullets}

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
    # Hard guard: never write path-form wikilinks. They break Obsidian alias
    # resolution and require a separate audit pass to clean up. Strip slashes
    # from link_target and fall back to basename if a path slipped through.
    if "/" in link_target:
        print(f"  ⚠ path-form link_target '{link_target}' — using basename only")
        link_target = link_target.rsplit("/", 1)[-1]
    if "/" in search_term:
        print(f"  ⚠ path-form search_term '{search_term}' — refusing to apply")
        return 0
    if "/" in display:
        display = display.rsplit("/", 1)[-1]

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
    people_dir: str,
    concepts_dir: str,
    dry_run: bool,
) -> Path | None:
    # Hard guard: note_name must not contain path separators. A "/" would
    # silently create a subdirectory under CRM/ or Notes/ and orphan the stub.
    if "/" in note_name:
        print(f"  ⚠ path-form note_name '{note_name}' — using basename only")
        note_name = note_name.rsplit("/", 1)[-1]
    is_person = ntype.lower() == "person" or (
        len(note_name.split()) >= 2
        and all(w[0].isupper() for w in note_name.split() if w)
        and note_name.replace(" ", "").replace("-", "").isalpha()
    )

    # Collect mentions with settings tuned to entity type
    if is_person:
        # No cap — read every mention chronologically so Claude sees the full arc.
        # For journal people (Vanessa, George) this can be 50-200+ mentions.
        # For book authors this naturally returns a handful.
        mentions = collect_mentions(
            vault, first_name or note_name,
            max_per_file=3, max_total=None, chronological=True,
        )
        # Also search by full name if we started from first name, merge deduped
        if first_name:
            full_mentions = collect_mentions(
                vault, note_name,
                max_per_file=3, max_total=None, chronological=True,
            )
            seen_stems = {s for s, _ in mentions}
            for s, t in full_mentions:
                if s not in seen_stems:
                    mentions.append((s, t))
            # Re-sort merged list by file mtime ascending
            stem_to_mtime = {
                md.stem: md.stat().st_mtime
                for md in vault.rglob("*.md")
                if not any(p in SKIP_PARTS for p in md.parts)
            }
            mentions.sort(key=lambda x: stem_to_mtime.get(x[0], 0))
    else:
        mentions = collect_mentions(
            vault, note_name,
            max_per_file=2, max_total=15, chronological=False,
        )

    print(f"  Synthesizing context from {len(mentions)} vault mention(s)...")
    context_bullets = synthesize_context(note_name, ntype, mentions)

    if is_person:
        folder = vault / people_dir
        content = person_stub(note_name, first_name, context_bullets)
    else:
        folder = vault / concepts_dir
        content = concept_stub(note_name, context_bullets)

    note_path = folder / f"{note_name}.md"
    if dry_run:
        print(f"  [DRY RUN] Would create: {note_path.relative_to(vault)}")
        print(f"  [DRY RUN] Context preview:\n{context_bullets}")
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
            # Sanitize: reject path-form input. User may paste "👤 CRM/Diego".
            if "/" in full_name:
                print(f"  ⚠ '/' in full name — stripping path prefix")
                full_name = full_name.rsplit("/", 1)[-1].strip()
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
            try:
                stub_choice = input(f"  No note for '{link_target}'. Create stub? [y/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                stub_choice = "n"
            if stub_choice == "y":
                stub_path = create_stub(
                    vault, link_target, term_info["type"], first_name,
                    args.people_dir, args.concepts_dir, args.dry_run,
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
