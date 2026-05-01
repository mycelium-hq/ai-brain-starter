#!/usr/bin/env python3
"""extract_rules_from_dump.py

Structured-signal-first extractor that reads a company knowledge dump
(Slack export, Notion export, GDocs export, or any markdown folder) and
emits signals.json plus a folder scaffold of draft rules.

Per Build Standards Rule 4a: deterministic parsing first, model synthesis
only on residuals. This script never calls an LLM. It produces signals
the parent skill (Claude in the calling session) uses to draft the rules.

Usage:
    python3 extract_rules_from_dump.py --dump <path> --out <out-dir> [--max-files N]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# --- Detection ---------------------------------------------------------------

def detect_input_type(dump: Path) -> str:
    if dump.is_file() and dump.suffix.lower() == ".zip":
        with zipfile.ZipFile(dump) as zf:
            names = set(zf.namelist())
            if any(n.endswith("users.json") for n in names) and any(
                n.endswith("channels.json") for n in names
            ):
                return "slack"
            if any(n.endswith(".html") for n in names) and any(
                n.endswith(".docx") for n in names
            ):
                return "gdocs"
            if any(n.endswith(".md") for n in names):
                return "notion"
        return "mixed"
    if dump.is_dir():
        md_count = sum(1 for _ in dump.rglob("*.md"))
        if md_count >= 5:
            return "markdown"
    return "mixed"

# --- Phrase extraction (shared) ----------------------------------------------

DECISION_PATTERNS = [
    re.compile(r"\b(?:we|i)\s+(?:never|don't|do not|can't|cannot)\s+(.{3,80}?)(?:[.!?\n]|$)", re.I),
    re.compile(r"\b(?:always|never)\s+(.{3,80}?)(?:[.!?\n]|$)", re.I),
    re.compile(r"\brule(?:\s+is)?\s*[:\-]?\s*(.{5,120}?)(?:[.!?\n]|$)", re.I),
    re.compile(r"\bpolicy(?:\s+is)?\s*[:\-]?\s*(.{5,120}?)(?:[.!?\n]|$)", re.I),
    re.compile(r"\bmust\s+(.{3,80}?)(?:[.!?\n]|$)", re.I),
]

PROCESS_CHANNEL_HINTS = re.compile(
    r"#(refunds?|incidents?|pricing|escalations?|approvals?|on[-_]?call|security|legal|compliance)",
    re.I,
)

def harvest_phrases(text: str) -> list[str]:
    out: list[str] = []
    for pat in DECISION_PATTERNS:
        for m in pat.finditer(text):
            phrase = m.group(0).strip()
            if 8 <= len(phrase) <= 200:
                out.append(phrase)
    return out

# --- Slack ------------------------------------------------------------------

def parse_slack(zpath: Path, max_files: int) -> dict[str, Any]:
    users: dict[str, str] = {}
    channels: list[str] = []
    msg_count = 0
    user_msg_count: Counter[str] = Counter()
    channel_msg_count: Counter[str] = Counter()
    decisions: list[dict[str, str]] = []
    process_owners: dict[str, Counter[str]] = defaultdict(Counter)

    with zipfile.ZipFile(zpath) as zf:
        for n in zf.namelist():
            if n.endswith("users.json"):
                for u in json.loads(zf.read(n)):
                    users[u.get("id", "")] = u.get("real_name") or u.get("name") or u.get("id", "")
            if n.endswith("channels.json"):
                channels = [c.get("name", "") for c in json.loads(zf.read(n))]

        for n in zf.namelist():
            if msg_count >= max_files * 200:
                break
            if not n.endswith(".json") or n.endswith("users.json") or n.endswith("channels.json"):
                continue
            channel = n.split("/")[0] if "/" in n else "_root"
            try:
                msgs = json.loads(zf.read(n))
            except Exception:
                continue
            for m in msgs if isinstance(msgs, list) else []:
                msg_count += 1
                txt = (m.get("text") or "").strip()
                uid = m.get("user", "")
                if uid:
                    user_msg_count[users.get(uid, uid)] += 1
                channel_msg_count[channel] += 1
                if not txt:
                    continue
                for p in harvest_phrases(txt):
                    decisions.append({"phrase": p, "channel": channel, "by": users.get(uid, uid)})
                if PROCESS_CHANNEL_HINTS.search("#" + channel):
                    process_owners[channel][users.get(uid, uid)] += 1

    return {
        "input_type": "slack",
        "stats": {"messages": msg_count, "users": len(users), "channels": len(channels)},
        "entities": {
            "people": [{"name": n, "messages": c} for n, c in user_msg_count.most_common(50)],
            "channels": [{"name": n, "messages": c} for n, c in channel_msg_count.most_common(50)],
        },
        "decision_phrases": decisions[:500],
        "process_owners": {
            ch: [{"name": u, "messages": c} for u, c in counter.most_common(5)]
            for ch, counter in process_owners.items()
        },
    }

# --- Notion / Markdown -------------------------------------------------------

FRONT_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.M)
WIKILINK_RE = re.compile(r"\[\[([^\]\|]+)(?:\|[^\]]*)?\]\]")

def parse_markdown_files(files: list[Path], max_files: int) -> dict[str, Any]:
    files = files[:max_files]
    folders: Counter[str] = Counter()
    headings: Counter[str] = Counter()
    frontmatter_fields: Counter[str] = Counter()
    wikilinks: Counter[str] = Counter()
    decisions: list[dict[str, str]] = []
    title_ngrams: Counter[str] = Counter()

    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        folders[f.parent.name] += 1
        title_ngrams[" ".join(f.stem.split()[:3])] += 1
        fm = FRONT_RE.match(text)
        if fm:
            for line in fm.group(1).splitlines():
                if ":" in line:
                    frontmatter_fields[line.split(":", 1)[0].strip()] += 1
        for _, h in HEADING_RE.findall(text):
            headings[h.strip().lower()[:80]] += 1
        for w in WIKILINK_RE.findall(text):
            wikilinks[w.strip()] += 1
        for p in harvest_phrases(text):
            decisions.append({"phrase": p, "file": str(f.name)})

    return {
        "stats": {"files": len(files)},
        "entities": {
            "folders": [{"name": n, "files": c} for n, c in folders.most_common(50)],
            "frequent_links": [{"name": n, "refs": c} for n, c in wikilinks.most_common(50)],
        },
        "templates": {
            "recurring_headings": [{"text": h, "count": c} for h, c in headings.most_common(30) if c >= 3],
            "frontmatter_fields": [{"field": f, "count": c} for f, c in frontmatter_fields.most_common(30)],
            "title_ngrams": [{"text": t, "count": c} for t, c in title_ngrams.most_common(20) if c >= 3],
        },
        "decision_phrases": decisions[:500],
    }

def parse_notion_zip(zpath: Path, max_files: int) -> dict[str, Any]:
    out_dir = zpath.parent / (zpath.stem + "_unzipped")
    out_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(out_dir)
    md_files = list(out_dir.rglob("*.md"))
    res = parse_markdown_files(md_files, max_files)
    res["input_type"] = "notion"
    return res

def parse_markdown_dir(d: Path, max_files: int) -> dict[str, Any]:
    md_files = list(d.rglob("*.md"))
    res = parse_markdown_files(md_files, max_files)
    res["input_type"] = "markdown"
    return res

# --- GDocs (Takeout html/docx, light pass) ----------------------------------

def parse_gdocs_zip(zpath: Path, max_files: int) -> dict[str, Any]:
    titles: Counter[str] = Counter()
    folders: Counter[str] = Counter()
    with zipfile.ZipFile(zpath) as zf:
        for n in zf.namelist()[: max_files * 4]:
            stem = Path(n).stem
            if not stem or stem.startswith("."):
                continue
            titles[" ".join(stem.split()[:4])] += 1
            folders[Path(n).parent.name] += 1
    return {
        "input_type": "gdocs",
        "stats": {"items": sum(titles.values())},
        "entities": {
            "folders": [{"name": n, "items": c} for n, c in folders.most_common(30)],
            "title_ngrams": [{"text": t, "count": c} for t, c in titles.most_common(30) if c >= 2],
        },
        "decision_phrases": [],
    }

# --- Synthesis: rule candidates from signals --------------------------------

def candidate_rules(signals: dict[str, Any]) -> dict[str, Any]:
    decisions = signals.get("decision_phrases", [])
    phrase_counts: Counter[str] = Counter(d["phrase"].lower() for d in decisions)
    hookify_candidates = []
    for phrase, count in phrase_counts.most_common(30):
        if count >= 3:
            hookify_candidates.append({
                "source_phrase": phrase[:200],
                "occurrences": count,
                "confidence": "high" if count >= 5 else "medium",
            })

    skill_candidates = []
    for h in signals.get("templates", {}).get("recurring_headings", []):
        if h["count"] >= 5:
            skill_candidates.append({
                "name": "_".join(h["text"].split()[:3]).lower(),
                "evidence_heading": h["text"],
                "occurrences": h["count"],
                "confidence": "high" if h["count"] >= 10 else "medium",
            })

    authority_candidates = []
    for ch, owners in signals.get("process_owners", {}).items():
        if owners and owners[0]["messages"] >= 5:
            authority_candidates.append({
                "process": ch,
                "inferred_owner": owners[0]["name"],
                "evidence_messages": owners[0]["messages"],
                "confidence": "high" if owners[0]["messages"] >= 10 else "medium",
            })

    return {
        "hookify_candidates": hookify_candidates,
        "skill_candidates": skill_candidates,
        "authority_candidates": authority_candidates,
    }

# --- Main -------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-files", type=int, default=2000)
    args = ap.parse_args()

    dump = Path(args.dump).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "hookify-rules").mkdir(exist_ok=True)
    (out / "skills").mkdir(exist_ok=True)
    (out / "hookify-rules" / "_low-confidence").mkdir(exist_ok=True)

    if not dump.exists():
        print(f"dump path not found: {dump}", file=sys.stderr)
        return 2

    kind = detect_input_type(dump)
    if kind == "slack":
        signals = parse_slack(dump, args.max_files)
    elif kind == "notion":
        signals = parse_notion_zip(dump, args.max_files)
    elif kind == "gdocs":
        signals = parse_gdocs_zip(dump, args.max_files)
    elif kind == "markdown":
        signals = parse_markdown_dir(dump, args.max_files)
    else:
        if dump.is_dir():
            signals = parse_markdown_dir(dump, args.max_files)
        else:
            print(f"unsupported dump shape: {dump}", file=sys.stderr)
            return 3

    signals["candidates"] = candidate_rules(signals)
    (out / "signals.json").write_text(json.dumps(signals, indent=2, ensure_ascii=False))

    n_hook = len(signals["candidates"]["hookify_candidates"])
    n_skill = len(signals["candidates"]["skill_candidates"])
    n_auth = len(signals["candidates"]["authority_candidates"])
    n_dec = len(signals.get("decision_phrases", []))
    summary = (
        f"# Extraction signals\n\n"
        f"- Input type: **{signals.get('input_type','?')}**\n"
        f"- Decision phrases harvested: {n_dec}\n"
        f"- Hookify candidates (>=3 occurrences): {n_hook}\n"
        f"- Skill candidates (>=5 heading recurrences): {n_skill}\n"
        f"- Authority candidates: {n_auth}\n\n"
        f"Next: parent skill drafts CLAUDE.md, hookify-rules/, skills/, REVIEW.md from signals.json.\n"
    )
    (out / "extraction-report.md").write_text(summary)
    print(summary)
    print(f"signals.json -> {out / 'signals.json'}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
