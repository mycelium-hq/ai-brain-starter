#!/usr/bin/env python3
"""synth.py: turn a resolved Slack thread markdown export into a typed memory entry.

Reads a single Slack thread markdown file. Classifies it as a decision,
exception, or workflow using deterministic signals. Writes the result
to Meta/Decisions/<sha8>.md, Meta/Exceptions/<sha8>.md, or
Meta/Workflows/<sha8>.md, conforming to the matching schema in
templates/schemas/.

Synthesis path: heuristic-first, operator-refined. The script never calls
an external LLM. The operator runs this from a Claude Code session and
the model refines the output in-session if needed.

Idempotent: <sha8> is derived from the thread root ts or URL, so re-running
overwrites the same file.

Usage:
    python3 synth.py <thread-path> --vault-root <vault> \
        [--classify-as decision|exception|workflow] [--dry-run] [--force]

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
    read_existing_or_none,
    render_frontmatter,
    sha8,
    split_frontmatter,
    write_typed_memory,
)


THREAD_URL_PATTERNS = [
    re.compile(r"https://[a-z0-9.\-]+\.slack\.com/archives/[A-Z0-9]+/p\d+"),
    re.compile(r"slack://channel\?team=[^&]+&id=[A-Z0-9]+&message=\d+"),
]

ROOT_TS_PATTERNS = [
    re.compile(r"\b(?:root_ts|thread_ts|ts)[:=]\s*\"?(\d{10}\.\d{6})\"?", re.I),
    re.compile(r"\bp(\d{10})(\d{6})\b"),
]

USER_LINE_PATTERN = re.compile(r"^\*\*([^*]+?)\*\*", re.M)
NUMBERED_LIST_PATTERN = re.compile(r"^\s*(\d+)\.\s+", re.M)
STEP_KEYWORD_PATTERN = re.compile(r"\bstep\s*\d+\b", re.I)

DECISION_HITS = [
    re.compile(r"\b(?:let'?s\s+go\s+with|we\s+picked|decided\s+to|going\s+with|agreed|approved|locked\s+in|consensus)\b", re.I),
    re.compile(r"\b(?:final\s+answer|we'?re\s+going\s+to|sounds\s+good|let'?s\s+do\s+it|approved\s+by)\b", re.I),
]

EXCEPTION_HITS = [
    re.compile(r"\bexception\b", re.I),
    re.compile(r"\b(?:we\s+don'?t|skip|override|deviate|carve\s*-?\s*out)\b", re.I),
    re.compile(r"\b(?:one\s*-?\s*off|for\s+this\s+(?:client|case|customer)\s+only|special\s+case)\b", re.I),
]

WORKFLOW_HITS = [
    STEP_KEYWORD_PATTERN,
    re.compile(r"\b(?:first[,\s].*then[,\s].*(?:finally|last(?:ly)?))\b", re.I | re.S),
    re.compile(r"\bprocedure\b", re.I),
    re.compile(r"\brun\s*book\b", re.I),
]


def extract_thread_url(meta: dict[str, Any], text: str) -> str | None:
    for key in ("thread_url", "permalink", "url", "source_url"):
        if key in meta and meta[key]:
            return str(meta[key])
    for pat in THREAD_URL_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(0)
    return None


def extract_root_ts(meta: dict[str, Any], text: str) -> str | None:
    for pat in ROOT_TS_PATTERNS:
        m = pat.search(text)
        if m:
            if m.lastindex and m.lastindex >= 2:
                return f"{m.group(1)}.{m.group(2)}"
            return m.group(1) if m.lastindex else m.group(0)
    for key in ("root_ts", "thread_ts", "ts"):
        if key in meta and meta[key]:
            return str(meta[key])
    return None


def count_hits(patterns: list[re.Pattern], text: str) -> int:
    return sum(len(p.findall(text)) for p in patterns)


def count_numbered_steps(text: str) -> int:
    matches = NUMBERED_LIST_PATTERN.findall(text)
    seen = set()
    consecutive = 0
    last = 0
    for m in matches:
        n = int(m)
        if n == last + 1:
            consecutive += 1
        else:
            consecutive = 1
        last = n
        seen.add(n)
    return max(consecutive, len(seen))


def classify(text: str) -> tuple[str, dict[str, int]]:
    decision_score = count_hits(DECISION_HITS, text)
    exception_score = count_hits(EXCEPTION_HITS, text)
    workflow_score = count_hits(WORKFLOW_HITS, text) + (count_numbered_steps(text) if count_numbered_steps(text) >= 3 else 0)

    scores = {
        "decision": decision_score,
        "exception": exception_score,
        "workflow": workflow_score,
    }
    if all(v == 0 for v in scores.values()):
        return "decision", scores
    cls = max(scores.items(), key=lambda kv: (kv[1], kv[0] == "decision"))
    return cls[0], scores


def extract_summary(text: str, max_len: int = 240) -> str:
    body_lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith(("---", "#", "**"))]
    if not body_lines:
        return "Resolved Slack thread (no parseable summary)"
    summary = " ".join(body_lines[:3])
    if len(summary) > max_len:
        summary = summary[: max_len - 3] + "..."
    return summary


def extract_steps_from_thread(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        m = re.match(r"^\s*(\d+)\.\s+(.+)$", line)
        if m:
            n = int(m.group(1))
            desc = m.group(2).strip()
            if desc and len(desc) > 3:
                out.append({"step_number": n, "description": desc})
    if not out:
        out = [{"step_number": 1, "description": extract_summary(text, 200)}]
    return out


def build_meta_decision(summary: str, file_sha: str, thread_url: str | None, root_ts: str | None, now: str) -> dict[str, Any]:
    return {
        "type": "decision",
        "decision_date": now[:10],
        "creationDate": now,
        "stakes": "medium",
        "speed": "deliberate",
        "outcome": None,
        "pattern": None,
        "memory_class": "episodic",
        "sha8": file_sha,
        "source_thread_url": thread_url or root_ts or "",
        "confidence": 0.6,
        "freshness_days": 180,
        "last_verified": now[:10],
        "source_count": 1,
        "provenance": [
            {
                "source_type": "slack",
                "source_id": root_ts or "",
                "source_url": thread_url or "",
                "captured_at": now,
            }
        ],
        "entity_ids": {"slack": root_ts or ""},
    }


def build_meta_exception(summary: str, file_sha: str, thread_url: str | None, root_ts: str | None, now: str) -> dict[str, Any]:
    return {
        "type": "exception",
        "exception_summary": summary,
        "frequency_observed": 1,
        "owner": None,
        "approved_by": None,
        "memory_class": "procedural",
        "sha8": file_sha,
        "source_thread_url": thread_url or root_ts or "",
        "creationDate": now,
        "confidence": 0.6,
        "freshness_days": 180,
        "last_verified": now[:10],
        "source_count": 1,
        "provenance": [
            {
                "source_type": "slack",
                "source_id": root_ts or "",
                "source_url": thread_url or "",
                "captured_at": now,
            }
        ],
        "entity_ids": {"slack": root_ts or ""},
    }


def build_meta_workflow(name: str, steps: list[dict[str, Any]], file_sha: str, thread_url: str | None, root_ts: str | None, now: str) -> dict[str, Any]:
    return {
        "type": "workflow",
        "name": name,
        "steps": steps,
        "memory_class": "procedural",
        "sha8": file_sha,
        "source_thread_url": thread_url or root_ts or "",
        "creationDate": now,
        "confidence": 0.6,
        "freshness_days": 180,
        "last_verified": now[:10],
        "source_count": 1,
        "provenance": [
            {
                "source_type": "slack",
                "source_id": root_ts or "",
                "source_url": thread_url or "",
                "captured_at": now,
            }
        ],
        "entity_ids": {"slack": root_ts or ""},
    }


def synth(thread_path: Path, vault_root: Path, classify_override: str | None, dry_run: bool, force: bool) -> Path | None:
    text = thread_path.read_text(encoding="utf-8")
    meta_in, body = split_frontmatter(text)
    full_text = body or text

    thread_url = extract_thread_url(meta_in, text)
    root_ts = extract_root_ts(meta_in, text)
    seed = root_ts or thread_url or thread_path.stem
    file_sha = sha8(seed)

    classification = classify_override or classify(full_text)[0]
    summary = extract_summary(full_text)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    if classification == "decision":
        out_dir = vault_root / "Meta" / "Decisions"
        meta_out = build_meta_decision(summary, file_sha, thread_url, root_ts, now)
        body_out = f"# Decision\n\n{summary}\n\nSee Slack thread for full context.\n"
    elif classification == "exception":
        out_dir = vault_root / "Meta" / "Exceptions"
        meta_out = build_meta_exception(summary, file_sha, thread_url, root_ts, now)
        body_out = f"# Exception\n\n{summary}\n\nSee Slack thread for full context.\n"
    elif classification == "workflow":
        out_dir = vault_root / "Meta" / "Workflows"
        steps = extract_steps_from_thread(full_text)
        title_match = re.search(r"^#\s+(?:Resolved\s+thread:\s*)?(.+?)\s*$", full_text, re.M)
        if title_match:
            name = title_match.group(1).strip()
        else:
            name = thread_path.stem.replace("-", " ").replace("_", " ").title()
        if len(name) > 80 or re.match(r"^\w+\s*\(\d", name):
            name = thread_path.stem.replace("-", " ").replace("_", " ").title()
        meta_out = build_meta_workflow(name, steps, file_sha, thread_url, root_ts, now)
        body_out = f"# {name}\n\n{summary}\n\n## Steps\n\n"
        for step in steps:
            body_out += f"{step['step_number']}. {step['description']}\n"
    else:
        print(f"unknown classification: {classification}", file=sys.stderr)
        return None

    out_path = out_dir / f"{file_sha}.md"

    if out_path.exists() and not force:
        existing_meta = read_existing_or_none(out_path)
        if existing_meta and existing_meta.get("hand_edited"):
            print(f"[skip] {out_path} hand-edited (set hand_edited:false or pass --force)")
            return None

    if dry_run:
        rendered = render_frontmatter(meta_out) + body_out
        print(f"[dry-run] would write {out_path}")
        print(rendered[:400])
        return out_path

    written = write_typed_memory(
        vault_root=vault_root,
        memory_type=classification,
        content=body_out,
        frontmatter=meta_out,
        idempotency_key=seed,
    )
    print(f"[wrote] {written} (classified as {classification})")
    return Path(written)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("thread_path", type=Path, help="Slack thread markdown file")
    parser.add_argument("--vault-root", type=Path, default=Path.cwd())
    parser.add_argument("--classify-as", choices=["decision", "exception", "workflow"], default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Overwrite hand-edited files")
    args = parser.parse_args()

    if not args.thread_path.exists():
        print(f"path not found: {args.thread_path}", file=sys.stderr)
        return 2
    if args.thread_path.is_dir():
        print(f"thread path must be a single file, not a folder", file=sys.stderr)
        return 2

    result = synth(args.thread_path, args.vault_root, args.classify_as, args.dry_run, args.force)
    return 0 if result is not None else 1


if __name__ == "__main__":
    sys.exit(main())
