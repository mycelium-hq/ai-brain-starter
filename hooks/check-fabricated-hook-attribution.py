#!/usr/bin/env python3
"""Stop hook. Block claims like "[X] hook fired" when X is not in recent hookify-blocks.log.

Bypass: FAB_HOOK_CHECK_BYPASS=1.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

WINDOW_SEC = 600
LOG_PATH = Path.home() / ".claude" / "hookify-blocks.log"

CLAIM_PATTERNS = [
    re.compile(
        r"(?:^|[^a-zA-Z`/-])"
        r"(?:the\s+)?"
        r"([a-z][a-z0-9]*(?:[-_][a-z0-9]+)+|em.dash|em-dash)"
        r"\s+(?:hook|rule)\s+"
        r"(fired|caught|blocked|flagged|prevented|stopped|triggered)\b",
        re.IGNORECASE,
    ),
]


def main() -> None:
    if os.environ.get("FAB_HOOK_CHECK_BYPASS") == "1":
        sys.exit(0)
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if data.get("stop_hook_active"):
        sys.exit(0)
    transcript_path = data.get("transcript_path", "")
    if not transcript_path or not Path(transcript_path).exists():
        sys.exit(0)
    last_text = _last_assistant_text(transcript_path)
    if not last_text:
        sys.exit(0)
    claimed = _extract_claims(last_text)
    if not claimed:
        sys.exit(0)
    recent = _recent_rule_names()
    fabricated = sorted(
        c for c in claimed if not _matches_any(c, recent)
    )
    if not fabricated:
        sys.exit(0)
    msg = (
        f"Hook attribution check: assistant claims {fabricated} fired, but no matching "
        f"rule name appears in ~/.claude/hookify-blocks.log within last "
        f"{WINDOW_SEC // 60} minutes. Recent fires: "
        f"{sorted(recent) or 'none'}. Either quote the verbatim rule name from the actual "
        f"tool error in this turn, or say 'a hookify rule blocked this' without naming a "
        f"specific rule. Bypass for forensic discussion: FAB_HOOK_CHECK_BYPASS=1."
    )
    print(json.dumps({"decision": "block", "reason": msg}))
    sys.exit(0)


def _last_assistant_text(transcript_path: str) -> str:
    text = ""
    try:
        with open(transcript_path) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "assistant":
                    continue
                msg = rec.get("message", {})
                content = msg.get("content", [])
                if not isinstance(content, list):
                    continue
                parts = [
                    c.get("text", "")
                    for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                ]
                if parts:
                    text = "\n".join(parts)
    except Exception:
        return ""
    return text


def _extract_claims(text: str) -> set:
    claims = set()
    for pat in CLAIM_PATTERNS:
        for m in pat.finditer(text):
            if _is_quoted(text, m.start(1)):
                continue
            name = m.group(1).lower().replace("em.dash", "em-dash").replace(" ", "-")
            claims.add(name)
    return claims


def _is_quoted(text: str, span_start: int) -> bool:
    window = text[max(0, span_start - 120) : span_start]
    quotes = (
        window.count('"')
        + window.count("'")
        + window.count("“")
        + window.count("”")
        + window.count("‘")
        + window.count("’")
        + window.count("`")
    )
    return quotes % 2 == 1


def _recent_rule_names() -> set:
    if not LOG_PATH.exists():
        return set()
    cutoff = time.time() - WINDOW_SEC
    names = set()
    try:
        with open(LOG_PATH) as f:
            for line in f:
                parts = line.split("\t")
                if len(parts) < 5:
                    continue
                try:
                    ts = datetime.datetime.fromisoformat(parts[0]).timestamp()
                except ValueError:
                    continue
                if ts < cutoff:
                    continue
                msg_field = "\t".join(parts[4:])
                m = re.search(r"\*\*\[([a-z0-9][a-z0-9_-]*)\]\*\*", msg_field)
                if m:
                    names.add(m.group(1).lower())
    except Exception:
        return set()
    return names


def _matches_any(claim: str, recent: set) -> bool:
    if claim in recent:
        return True
    for r in recent:
        if r == claim or r.endswith(f"-{claim}") or claim.endswith(f"-{r}"):
            return True
        if claim in r or r in claim:
            return True
    return False


if __name__ == "__main__":
    main()
