#!/usr/bin/env python3
"""
vault-insight-engine.py — post-extraction mind-blower surface.

Reads every file's frontmatter, computes cross-type patterns that would be
hard to spot by hand, and prints the top N "huh, I didn't know that" findings.

Zero LLM. Pure math: surprise = low observed frequency × high signal strength.
All claims are backed by file paths you can open to verify.

Writes a markdown summary to ⚙️ Meta/Second-Brain Insights.md.

Runs after /second-brain-mapping. Safe to run standalone.

Each insight category is a pluggable function. Add a new finder → new insight.
"""
import argparse
import glob
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "extractors"))

from _base import VAULT, SKIP_PARTS, iso_date_from  # noqa: E402

# Insight report location: override with INSIGHTS_OUTPUT env var.
# Default: picks the first folder that exists: Meta, ⚙️ Meta, else vault root.
def _default_output_path():
    env = os.environ.get("INSIGHTS_OUTPUT")
    if env:
        return env
    for candidate in ("⚙️ Meta", "Meta"):
        p = os.path.join(VAULT, candidate)
        if os.path.isdir(p):
            return os.path.join(p, "Second-Brain Insights.md")
    return os.path.join(VAULT, "Second-Brain Insights.md")


OUTPUT_PATH = _default_output_path()

# Names to filter out of person-based insights (self-references, templates).
# Populate SELF_REFERENCE_NAMES env var (comma-separated) with your own variants.
SELF_REFERENCE_NAMES = set(
    filter(None, os.environ.get("SELF_REFERENCE_NAMES", "").split(","))
)


def _is_self_reference(name):
    if not SELF_REFERENCE_NAMES:
        return False
    if name in SELF_REFERENCE_NAMES:
        return True
    # Also catch variants: if any self-ref name is a prefix, treat as self-ref.
    name_lower = name.lower()
    return any(name_lower.startswith(s.lower().split()[0]) for s in SELF_REFERENCE_NAMES if s)


def load_vault_index():
    """One-pass scan: for every file, return (filepath, type, frontmatter dict)."""
    index = []
    for fp in glob.glob(os.path.join(VAULT, "**", "*.md"), recursive=True):
        parts = set(fp.split(os.sep))
        if parts & SKIP_PARTS:
            continue
        try:
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue
        if not content.startswith("---"):
            continue
        end = content.find("\n---", 3)
        if end == -1:
            continue
        try:
            fm = yaml.safe_load(content[3:end]) or {}
        except Exception:
            continue
        doc_type = (fm.get("type") or "").strip().lower().replace("-", "_")
        if not doc_type:
            continue
        index.append({"path": fp, "type": doc_type, "fm": fm})
    return index


# ── Insight finders ──────────────────────────────────────────────────

def lucky_charm_people(index, min_mentions=8, high_floor_pct=0.75):
    """People who appear in journals with high-floor ratio above threshold."""
    people = [x for x in index if x["type"] == "person"]
    out = []
    seen_names = set()
    for p in people:
        name = os.path.splitext(os.path.basename(p["path"]))[0]
        if _is_self_reference(name) or name in seen_names:
            continue
        fm = p["fm"]
        count = fm.get("person_journal_mention_count") or 0
        if count < min_mentions:
            continue
        floors = fm.get("person_floor_cooccurrence") or []
        if not floors:
            continue
        try:
            nums = [int(f) for f in floors]
        except Exception:
            continue
        if not nums:
            continue
        high = sum(1 for n in nums if n >= 12)
        ratio = high / len(nums)
        if ratio >= high_floor_pct:
            seen_names.add(name)
            out.append({
                "name": name,
                "mentions": count,
                "top_floors": floors[:3],
                "ratio": ratio,
            })
    return sorted(out, key=lambda r: -r["mentions"])[:5]


def drag_people(index, min_mentions=8, low_floor_pct=0.6):
    """People who mostly appear in low-floor journals (floor_num ≤ 6)."""
    people = [x for x in index if x["type"] == "person"]
    out = []
    seen_names = set()
    for p in people:
        name = os.path.splitext(os.path.basename(p["path"]))[0]
        if _is_self_reference(name) or name in seen_names:
            continue
        fm = p["fm"]
        count = fm.get("person_journal_mention_count") or 0
        if count < min_mentions:
            continue
        floors = fm.get("person_floor_cooccurrence") or []
        try:
            nums = [int(f) for f in floors]
        except Exception:
            continue
        if not nums:
            continue
        low = sum(1 for n in nums if n <= 6)
        ratio = low / len(nums)
        if ratio >= low_floor_pct:
            seen_names.add(name)
            out.append({
                "name": name,
                "mentions": count,
                "top_floors": floors[:3],
                "ratio": ratio,
            })
    return sorted(out, key=lambda r: -r["ratio"])[:5]


def dormant_concepts(index, min_historical=5):
    """Concepts marked dormant with historical weight."""
    concepts = [x for x in index if x["type"] == "concept"]
    out = []
    for c in concepts:
        fm = c["fm"]
        if not fm.get("concept_dormant"):
            continue
        mentions = fm.get("concept_mention_count") or 0
        if mentions < min_historical:
            continue
        out.append({
            "name": os.path.splitext(os.path.basename(c["path"]))[0],
            "mentions": mentions,
            "last": fm.get("concept_last_mentioned_iso"),
            "first": fm.get("concept_first_seen_iso"),
        })
    return sorted(out, key=lambda r: -r["mentions"])[:7]


def resurrection_candidates(index, recent_days=30):
    """Concepts marked dormant but that show up in recent ai_chats — you're
    thinking about them again; the vault concept note hasn't caught up."""
    # Build set of concepts touched in recent ai_chats
    cutoff = (date.today() - timedelta(days=recent_days)).isoformat()
    recent_concepts = set()
    for x in index:
        if x["type"] != "ai_chat":
            continue
        d = x["fm"].get("chat_date_iso")
        if not d or d < cutoff:
            continue
        for c in (x["fm"].get("chat_concepts_touched") or []):
            recent_concepts.add(str(c).strip())
    # Intersect with dormant concepts
    out = []
    for x in index:
        if x["type"] != "concept":
            continue
        name = os.path.splitext(os.path.basename(x["path"]))[0]
        if x["fm"].get("concept_dormant") and name in recent_concepts:
            out.append({
                "name": name,
                "last_vault": x["fm"].get("concept_last_mentioned_iso"),
                "mentions": x["fm"].get("concept_mention_count"),
            })
    return out[:7]


def deep_processing_streaks(index, word_threshold=800, floor_ceiling=8, min_streak=3):
    """Consecutive-ish days of long journal entries on low floors."""
    journals = sorted(
        [x for x in index if x["type"] == "journal"
         and (x["fm"].get("word_count") or 0) >= word_threshold
         and x["fm"].get("floor_num") is not None
         and x["fm"]["floor_num"] <= floor_ceiling
         and x["fm"].get("date_iso")],
        key=lambda r: r["fm"]["date_iso"],
    )
    if not journals:
        return []
    # Group by within-7-day runs
    streaks = []
    current = [journals[0]]
    for j in journals[1:]:
        prev_d = datetime.fromisoformat(current[-1]["fm"]["date_iso"]).date()
        this_d = datetime.fromisoformat(j["fm"]["date_iso"]).date()
        if (this_d - prev_d).days <= 10:
            current.append(j)
        else:
            if len(current) >= min_streak:
                streaks.append(current)
            current = [j]
    if len(current) >= min_streak:
        streaks.append(current)
    # Render each streak
    out = []
    for s in streaks[-5:]:
        out.append({
            "start": s[0]["fm"]["date_iso"],
            "end": s[-1]["fm"]["date_iso"],
            "entries": len(s),
            "avg_words": sum(x["fm"].get("word_count") or 0 for x in s) // len(s),
            "avg_floor": sum(x["fm"]["floor_num"] for x in s) / len(s),
        })
    return out


def highly_rated_books(index, min_rating=4):
    """Best books you've recorded. Easy mind-blower: a list of the greatest hits."""
    books = [x for x in index if x["type"] == "book"]
    out = []
    for b in books:
        r = b["fm"].get("book_rating_1_5")
        if r and r >= min_rating:
            out.append({
                "title": os.path.splitext(os.path.basename(b["path"]))[0],
                "rating": r,
                "author": b["fm"].get("book_author"),
                "themes": (b["fm"].get("book_themes") or [])[:3],
            })
    return sorted(out, key=lambda r: (-r["rating"], r["title"]))[:12]


def high_priority_neglected_contacts(index, stale_days=60):
    """High-priority CRM contacts not mentioned in journal in >N days."""
    cutoff = (date.today() - timedelta(days=stale_days)).isoformat()
    out = []
    seen_names = set()
    for p in index:
        if p["type"] != "person":
            continue
        if p["fm"].get("person_priority") != "high":
            continue
        name = os.path.splitext(os.path.basename(p["path"]))[0]
        if _is_self_reference(name) or name in seen_names:
            continue
        last = p["fm"].get("person_last_journal_iso")
        if last is None or last < cutoff:
            seen_names.add(name)
            out.append({
                "name": name,
                "last": last or "never",
                "next_step": p["fm"].get("person_next_step"),
            })
    return out[:10]


def concept_theme_crossovers(index, min_overlap=3):
    """Concepts that appear as themes across multiple book ratings + journal
    concepts_extracted — the real 'this keeps showing up in your life' signals."""
    # Pool: wikilink targets appearing in book themes AND journal concepts AND writing themes
    book_themes = Counter()
    journal_concepts = Counter()
    writing_themes = Counter()
    for x in index:
        if x["type"] == "book":
            for t in (x["fm"].get("book_themes") or []):
                book_themes[t] += 1
        elif x["type"] == "journal":
            for t in (x["fm"].get("concepts_extracted") or []):
                journal_concepts[t] += 1
        elif x["type"] == "writing_draft":
            for t in (x["fm"].get("draft_themes") or []):
                writing_themes[t] += 1
    # Find concepts present in at least 2 of the 3 channels above threshold
    all_concepts = set(book_themes) | set(journal_concepts) | set(writing_themes)
    out = []
    for c in all_concepts:
        b = book_themes.get(c, 0)
        j = journal_concepts.get(c, 0)
        w = writing_themes.get(c, 0)
        channels_hit = sum(1 for n in (b, j, w) if n >= min_overlap)
        if channels_hit < 2:
            continue
        out.append({
            "concept": c,
            "book_hits": b,
            "journal_hits": j,
            "writing_hits": w,
            "cross_score": b * j + b * w + j * w,
        })
    return sorted(out, key=lambda r: -r["cross_score"])[:10]


# ── Report rendering ─────────────────────────────────────────────────

def render_report(index, findings):
    lines = []
    lines.append("---")
    lines.append("type: report")
    lines.append(f"last_updated: {date.today().isoformat()}")
    lines.append("---")
    lines.append("")
    lines.append(f"*Auto-generated by `vault-insight-engine.py`. Zero LLM. Read-only rendering of your structured vault.*")
    lines.append("")
    lines.append(f"**Index size**: {len(index):,} typed files across {len(set(x['type'] for x in index))} types.")
    lines.append("")

    type_counts = Counter(x["type"] for x in index)
    lines.append("## Types indexed")
    lines.append("")
    lines.append("| Type | Count |")
    lines.append("|---|---:|")
    for t, n in type_counts.most_common():
        lines.append(f"| `{t}` | {n:,} |")
    lines.append("")

    # Findings sections — skip any with no results.
    sections = [
        ("Lucky-charm people — high-floor associations",
         "*People who, when they show up in your journals, the floor is usually ≥12 (Acceptance or above).*",
         findings["lucky_charm_people"],
         lambda r: f"- **{r['name']}** — {r['mentions']} mentions, {int(r['ratio']*100)}% on high floors (top floors seen: {', '.join(r['top_floors'])})"),

        ("Drag people — low-floor associations",
         "*People who correlate with floor ≤6 (Desire and below). Not necessarily toxic — could be reflecting shared struggles. Worth looking at.*",
         findings["drag_people"],
         lambda r: f"- **{r['name']}** — {r['mentions']} mentions, {int(r['ratio']*100)}% on low floors (top floors seen: {', '.join(r['top_floors'])})"),

        ("High-priority contacts going cold",
         "*CRM priority=high, not in journals for 60+ days. Warm them or demote them.*",
         findings["high_priority_neglected_contacts"],
         lambda r: f"- **{r['name']}** — last journal: {r['last']}" + (f" — next step: _{r['next_step']}_" if r.get('next_step') else "")),

        ("Dormant concepts with historical weight",
         "*Concepts not linked in 180+ days that once had 5+ mentions. Buried gold.*",
         findings["dormant_concepts"],
         lambda r: f"- **[[{r['name']}]]** — {r['mentions']} historical mentions, dormant since {r['last']}, first seen {r['first']}"),

        ("Resurrection candidates",
         "*Dormant concepts that surfaced in your AI chats in the last 30 days. You're thinking about them again — the vault node hasn't caught up.*",
         findings["resurrection_candidates"],
         lambda r: f"- **[[{r['name']}]]** — last logged {r['last_vault']} ({r['mentions']} historical mentions) but mentioned in recent AI chats"),

        ("Deep-processing streaks",
         "*Consecutive stretches of long journal entries on low floors. Active emotional work periods.*",
         findings["deep_processing_streaks"],
         lambda r: f"- **{r['start']} → {r['end']}** — {r['entries']} entries, avg {r['avg_words']} words, avg floor {r['avg_floor']:.1f}"),

        ("Highly rated books",
         "*Books you've rated 4–5. Pull from this list when advising anyone on reading.*",
         findings["highly_rated_books"],
         lambda r: f"- **{r['title']}** ({r['rating']}/5)" + (f" — _{r['author']}_" if r.get('author') else "") + (f" — themes: {', '.join(f'[[{t}]]' for t in r['themes'])}" if r.get('themes') else "")),

        ("Cross-channel concepts",
         "*Concepts that appear in your books, journals, AND writing drafts. The themes actually shaping your life.*",
         findings["concept_theme_crossovers"],
         lambda r: f"- **[[{r['concept']}]]** — books: {r['book_hits']}, journals: {r['journal_hits']}, writing drafts: {r['writing_hits']}"),
    ]

    for title, preamble, results, renderer in sections:
        lines.append(f"## {title}")
        lines.append("")
        lines.append(preamble)
        lines.append("")
        if not results:
            lines.append("*No results meet the threshold. Either the data is too thin or your thresholds are too strict.*")
        else:
            for r in results:
                lines.append(renderer(r))
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Run again anytime with: `python3 \"⚙️ Meta/scripts/vault-insight-engine.py\"`. Output writes to this file, overwriting.*")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=3, help="How many insights to print to stdout (default 3).")
    ap.add_argument("--quiet", action="store_true", help="Write file but don't print stdout summary.")
    args = ap.parse_args()

    print(f"vault-insight-engine  loading index…", flush=True)
    index = load_vault_index()
    print(f"  {len(index):,} typed files loaded across {len(set(x['type'] for x in index))} types.")

    findings = {
        "lucky_charm_people": lucky_charm_people(index),
        "drag_people": drag_people(index),
        "high_priority_neglected_contacts": high_priority_neglected_contacts(index),
        "dormant_concepts": dormant_concepts(index),
        "resurrection_candidates": resurrection_candidates(index),
        "deep_processing_streaks": deep_processing_streaks(index),
        "highly_rated_books": highly_rated_books(index),
        "concept_theme_crossovers": concept_theme_crossovers(index),
    }

    report = render_report(index, findings)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  report written: {OUTPUT_PATH}")

    if args.quiet:
        return

    # Short stdout summary: top 3 non-empty findings
    shown = 0
    section_titles = {
        "lucky_charm_people": "Lucky-charm people (high-floor)",
        "drag_people": "Drag people (low-floor)",
        "high_priority_neglected_contacts": "High-priority contacts going cold",
        "dormant_concepts": "Dormant concepts with historical weight",
        "resurrection_candidates": "Resurrection candidates",
        "deep_processing_streaks": "Deep-processing streaks",
        "highly_rated_books": "Highly rated books",
        "concept_theme_crossovers": "Cross-channel concepts",
    }
    print("\nTop findings (see full report for everything):")
    for key, title in section_titles.items():
        results = findings[key]
        if not results:
            continue
        print(f"\n  ▸ {title} ({len(results)} results)")
        for r in results[:3]:
            if key == "lucky_charm_people" or key == "drag_people":
                print(f"    • {r['name']}: {r['mentions']} mentions, {int(r['ratio']*100)}% matching")
            elif key == "high_priority_neglected_contacts":
                print(f"    • {r['name']}: last {r['last']}")
            elif key == "dormant_concepts":
                print(f"    • {r['name']}: {r['mentions']} historical, last {r['last']}")
            elif key == "resurrection_candidates":
                print(f"    • {r['name']}: vault last {r['last_vault']}, but in recent chats")
            elif key == "deep_processing_streaks":
                print(f"    • {r['start']} → {r['end']}: {r['entries']} entries, avg floor {r['avg_floor']:.1f}")
            elif key == "highly_rated_books":
                print(f"    • {r['title']} ({r['rating']}/5)")
            elif key == "concept_theme_crossovers":
                print(f"    • {r['concept']}: book×{r['book_hits']}, journal×{r['journal_hits']}, writing×{r['writing_hits']}")
        shown += 1
        if shown >= args.top:
            break


if __name__ == "__main__":
    main()
