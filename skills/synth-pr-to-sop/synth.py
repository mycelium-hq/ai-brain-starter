#!/usr/bin/env python3
"""synth.py: turn a merged-PR markdown export into a typed workflow file.

Reads a single PR markdown file or a folder of them. Extracts headers,
bullets, and any explicit step lists into a workflow.json-conforming
markdown file at <vault-root>/Meta/Workflows/<sha8>.md.

Synthesis path: heuristic-first, operator-refined. The script never calls
an external LLM. The operator runs this from a Claude Code session and
the model refines the output in-session if needed.

Idempotent: <sha8> is derived from the PR ID, so re-running on the same
PR overwrites the same file.

Usage:
    python3 synth.py <pr-path> --vault-root <vault> [--dry-run] [--force]

Stdlib + PyYAML only. Shared helpers come from skills/_shared/connector_utils.py.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path
from typing import Any

# _shared is a sibling directory; add it to sys.path so we can import.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_shared"))
from connector_utils import (
    canonicalize_entity,
    extract_entity_mentions,
    load_entity_aliases,
    read_existing_or_none,
    render_frontmatter,
    sha8,
    split_frontmatter,
    write_typed_memory,
)
import llm_synth  # noqa: E402  (only imported when --use-llm is set; safe to import unconditionally — graceful when deps missing)


PR_ID_PATTERNS = [
    re.compile(r"#(\d+)\b"),
    re.compile(r"PR[\s\-_:]*(\d+)", re.I),
    re.compile(r"pull/(\d+)"),
]

TITLE_PATTERNS = [
    re.compile(r"^#\s+(.+?)\s*$", re.M),
    re.compile(r"^Title:\s*(.+?)\s*$", re.M | re.I),
]

STEP_HEADER_PATTERNS = [
    re.compile(r"^##+\s*(?:Step\s*\d+|Steps?|Procedure|How|Process)\b", re.M | re.I),
    re.compile(r"^##+\s*(?:Implementation|Workflow)\b", re.M | re.I),
]

OWNER_PATTERN = re.compile(r"@([A-Za-z0-9_\-]+)")
STEP_NUMBER_PATTERN = re.compile(r"^\s*(?:[-*]\s+)?(?:\d+\.|\([0-9]+\)|Step\s*\d+:?)\s*", re.I)


def read_pr_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_pr_id(text: str, fallback_filename: str) -> str:
    for pat in PR_ID_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1)
    base = Path(fallback_filename).stem
    return base


def extract_title(text: str, fallback: str) -> str:
    for pat in TITLE_PATTERNS:
        m = pat.search(text)
        if m:
            title = m.group(1).strip()
            title = re.sub(r"^\[(?:closed|merged|draft)\]\s*", "", title, flags=re.I)
            return title
    return fallback


def find_steps_section(body: str) -> str:
    for pat in STEP_HEADER_PATTERNS:
        m = pat.search(body)
        if m:
            start = m.end()
            tail = body[start:]
            stop_match = re.search(r"^##+\s+", tail, re.M)
            if stop_match:
                return tail[: stop_match.start()]
            return tail
    return ""


def parse_steps(body: str) -> list[dict[str, Any]]:
    steps_section = find_steps_section(body)
    candidates: list[str] = []

    if steps_section:
        for line in steps_section.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("- ", "* ", "1.", "2.", "3.")) or re.match(r"^\d+\.", stripped):
                cleaned = STEP_NUMBER_PATTERN.sub("", stripped).strip()
                cleaned = re.sub(r"^[-*]\s*", "", cleaned).strip()
                if cleaned and len(cleaned) > 3:
                    candidates.append(cleaned)

    if not candidates:
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("- ", "* ")):
                cleaned = re.sub(r"^[-*]\s*", "", stripped).strip()
                if cleaned and len(cleaned) > 3 and not cleaned.startswith("[ ]"):
                    candidates.append(cleaned)
                if len(candidates) >= 12:
                    break

    if not candidates:
        candidates = ["See source PR for procedure"]

    out: list[dict[str, Any]] = []
    for i, text in enumerate(candidates[:20], start=1):
        owners = OWNER_PATTERN.findall(text)
        step: dict[str, Any] = {
            "step_number": i,
            "description": text,
        }
        if owners:
            step["owner"] = owners[0]
        out.append(step)
    return out


def detect_topic(text: str, body: str) -> str | None:
    for marker in ("Topic:", "topic:", "Area:", "area:"):
        idx = text.find(marker)
        if idx >= 0:
            line = text[idx:].splitlines()[0]
            value = line.split(":", 1)[1].strip()
            if value:
                return value.lower().replace(" ", "-")
    body_lower = body.lower()
    keyword_to_topic = {
        "deploy": "deploy",
        "release": "release",
        "onboarding": "onboarding",
        "incident": "incident-response",
        "security": "security",
        "review": "code-review",
        "testing": "testing",
    }
    for kw, topic in keyword_to_topic.items():
        if kw in body_lower:
            return topic
    return None


def build_body(name: str, steps: list[dict[str, Any]], pr_id: str, source_path: Path) -> str:
    lines = [f"# {name}", "", f"Synthesized from PR `{pr_id}` ({source_path.name}).", "", "## Steps", ""]
    for step in steps:
        owner_tag = f" ({step['owner']})" if "owner" in step else ""
        lines.append(f"{step['step_number']}. {step['description']}{owner_tag}")
    lines.append("")
    lines.append("## Refinement notes")
    lines.append("")
    lines.append("Operator-driven LLM refinement (Claude Code session) goes here. Add owners, failure modes, edge cases as the procedure matures.")
    lines.append("")
    return "\n".join(lines)


def build_entity_mentions(
    raw_text: str,
    title: str,
    aliases: dict[str, str],
) -> list[dict[str, str]]:
    """Scan body and title for capitalized phrases, fold each into the alias
    index. Emit one entry per unique raw mention with both raw_mention and
    canonical_entity. Stable sort by raw_mention.
    """
    seen_raw: set[str] = set()
    out: list[dict[str, str]] = []
    candidates = extract_entity_mentions(title or "") + extract_entity_mentions(raw_text or "")
    for raw in candidates:
        if raw in seen_raw:
            continue
        seen_raw.add(raw)
        canonical = canonicalize_entity(raw, aliases)
        out.append({
            "raw_mention": raw,
            "canonical_entity": canonical,
        })
    out.sort(key=lambda d: d["raw_mention"])
    return out


def synth_one(pr_path: Path, vault_root: Path, dry_run: bool, force: bool, use_llm: bool = False) -> Path | None:
    text = read_pr_markdown(pr_path)
    _meta_in, body = split_frontmatter(text)
    pr_id = extract_pr_id(text, pr_path.name)
    title = extract_title(text, pr_path.stem)
    steps = parse_steps(body or text)
    topic = detect_topic(text, body or text)

    llm_summary = None
    if use_llm:
        refined, err = llm_synth.refine_extraction(
            raw_text=body or text,
            memory_type="workflow",
            kind="merged GitHub PR",
        )
        if err:
            print(f"[--use-llm warning] {err}; falling back to heuristic only", file=sys.stderr)
        elif refined:
            if isinstance(refined.get("title"), str) and refined["title"].strip():
                title = refined["title"].strip()
            llm_steps = refined.get("steps")
            if isinstance(llm_steps, list) and llm_steps:
                cleaned: list[dict[str, Any]] = []
                for i, raw in enumerate(llm_steps[:20], start=1):
                    if not isinstance(raw, dict):
                        continue
                    desc = raw.get("description") or raw.get("text")
                    if not isinstance(desc, str) or not desc.strip():
                        continue
                    step: dict[str, Any] = {
                        "step_number": int(raw.get("step_number") or i),
                        "description": desc.strip(),
                    }
                    if raw.get("owner"):
                        step["owner"] = str(raw["owner"]).lstrip("@")
                    cleaned.append(step)
                if cleaned:
                    steps = cleaned
            llm_summary = refined.get("summary") if isinstance(refined.get("summary"), str) else None

    file_sha = sha8(pr_id)
    out_path = vault_root / "Meta" / "Workflows" / f"{file_sha}.md"

    if out_path.exists() and not force:
        existing_meta = read_existing_or_none(out_path)
        if existing_meta and existing_meta.get("hand_edited"):
            print(f"[skip] {out_path} hand-edited (set hand_edited:false or pass --force)")
            return None

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    aliases = load_entity_aliases(vault_root)
    entity_mentions = build_entity_mentions(body or text, title, aliases)

    meta_out: dict[str, Any] = {
        "type": "workflow",
        "name": title,
        "steps": steps,
        "source_pr_id": pr_id,
        "sha8": file_sha,
        "memory_class": "procedural",
        "creationDate": now,
        "provenance": [
            {
                "source_type": "github",
                "source_id": pr_id,
                "captured_at": now,
            }
        ],
        "confidence": 0.6,
        "freshness_days": 90,
        "last_verified": now[:10],
        "source_count": 1,
        "entity_ids": {"github_pr": pr_id},
    }
    if entity_mentions:
        meta_out["entity_mentions"] = entity_mentions
    if topic:
        meta_out["topic"] = topic
    if llm_summary:
        meta_out["llm_summary"] = llm_summary
        meta_out["synthesis_mode"] = "llm-refined"
    else:
        meta_out["synthesis_mode"] = "heuristic"

    body_out = build_body(title, steps, pr_id, pr_path)

    if dry_run:
        rendered = render_frontmatter(meta_out) + body_out
        print(f"[dry-run] would write {out_path}")
        print(rendered[:400])
        return out_path

    written = write_typed_memory(
        vault_root=vault_root,
        memory_type="workflow",
        content=body_out,
        frontmatter=meta_out,
        idempotency_key=pr_id,
    )
    print(f"[wrote] {written}")
    return Path(written)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr_path", type=Path, help="PR markdown file or folder")
    parser.add_argument("--vault-root", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Overwrite hand-edited files")
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Refine extraction via Anthropic API (claude-haiku-4-5). Requires `pip install anthropic` and ANTHROPIC_API_KEY. Default off; heuristic-only.",
    )
    args = parser.parse_args()

    if not args.pr_path.exists():
        print(f"path not found: {args.pr_path}", file=sys.stderr)
        return 2

    if args.pr_path.is_file():
        targets = [args.pr_path]
    else:
        targets = sorted(args.pr_path.rglob("*.md"))
        if not targets:
            print(f"no .md files under {args.pr_path}", file=sys.stderr)
            return 2

    written = 0
    for t in targets:
        result = synth_one(t, args.vault_root, args.dry_run, args.force, use_llm=args.use_llm)
        if result is not None:
            written += 1

    print(f"\nprocessed {len(targets)} file(s), wrote {written} workflow(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
