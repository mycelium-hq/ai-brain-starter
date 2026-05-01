#!/usr/bin/env python3
"""query.py: parse Meta/RESOLVER.md and answer a natural-language question.

The skill itself does NOT call an LLM. It parses the rendered resolver
index into a structured candidate list, runs deterministic token-overlap
scoring against the question, and emits a single JSON document the host
Claude session reads.

Match kinds:
  decisive  - exactly one rule scores >= DECISIVE_THRESHOLD
  ranked    - multiple rules with non-zero score, sorted by score desc
  none      - no rule scored above zero

CLI:
  python3 query.py <question> --vault-root PATH [--limit N]

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


DECISIVE_THRESHOLD = 0.55
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'-]*")
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for",
    "how", "i", "in", "is", "it", "of", "on", "or", "that", "the", "this",
    "to", "we", "what", "when", "where", "who", "with", "you", "your",
    "should", "would", "could", "can", "must", "shall", "will", "may",
    "rule", "rules", "policy", "case", "cases", "thing", "stuff",
}


def find_meta_dir(vault_root: Path) -> Path | None:
    """Locate the Meta folder under the vault. Plain or emoji-prefixed."""
    if not vault_root.is_dir():
        return None
    for child in sorted(vault_root.iterdir()):
        if child.is_dir() and child.name.endswith("Meta"):
            return child
    return None


def parse_resolver(text: str) -> dict[str, Any]:
    """Extract frontmatter + rule rows from RESOLVER.md."""
    fm_text = ""
    body = text
    if text.startswith("---"):
        m = re.match(r"^---\n(.*?)\n---\s*", text, re.DOTALL)
        if m:
            fm_text = m.group(1)
            body = text[m.end():]

    fm: dict[str, Any] = {}
    for line in fm_text.splitlines():
        m = re.match(r"^([\w\-]+):\s*(.+?)\s*$", line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            if val.isdigit():
                fm[key] = int(val)
            else:
                fm[key] = val.strip('"').strip("'")

    rules = parse_rules_table(body)
    return {"frontmatter": fm, "rules": rules}


def parse_rules_table(body: str) -> list[dict[str, Any]]:
    """Pull each row out of the `## Rules` markdown table."""
    rules: list[dict[str, Any]] = []
    section = re.search(r"^##\s+Rules\s*$", body, re.M)
    if not section:
        return rules
    after = body[section.end():]
    next_h2 = re.search(r"^##\s+\S", after, re.M)
    table_text = after[: next_h2.start()] if next_h2 else after

    header_seen = False
    for line in table_text.splitlines():
        line = line.strip()
        if not line or not line.startswith("|"):
            continue
        if re.match(r"^\|[\s\-]+\|", line):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if not header_seen:
            header_seen = True
            continue
        if len(cells) < 8:
            continue
        if cells[0].lower() == "(no rules found)":
            continue
        rule = {
            "rule_id": cells[0],
            "type": cells[1],
            "status": cells[2],
            "last_verified": cells[3],
            "freshness_days": cells[4],
            "owner": cells[5],
            "source_path": _strip_link(cells[6]),
            "skill_link": _strip_link(cells[7]) if len(cells) > 7 else "",
            "superseded_by": _strip_backticks(cells[8]) if len(cells) > 8 else "",
            "branch_merge_with": _strip_backticks(cells[9]) if len(cells) > 9 else "",
        }
        rules.append(rule)
    return rules


def _strip_link(value: str) -> str:
    """Convert `[[Path]]` to `Path`, strip surrounding noise."""
    v = value.strip()
    m = re.match(r"^\[\[(.+?)\]\]\s*$", v)
    if m:
        return m.group(1).strip()
    return v


def _strip_backticks(value: str) -> str:
    v = value.strip()
    if v.startswith("`") and v.endswith("`"):
        return v[1:-1].strip()
    return v


def tokenize(text: str) -> set[str]:
    """Lowercase, drop stopwords, keep alphanumeric stems of length >= 3."""
    out: set[str] = set()
    for m in TOKEN_RE.finditer((text or "").lower()):
        tok = m.group(0)
        if len(tok) < 3:
            continue
        if tok in STOPWORDS:
            continue
        out.add(tok)
    return out


def haystack_for_rule(rule: dict[str, Any]) -> set[str]:
    """Tokens drawn from every searchable surface of a rule row."""
    parts: list[str] = []
    for key in ("rule_id", "type", "owner", "source_path", "skill_link", "superseded_by"):
        v = rule.get(key)
        if isinstance(v, str):
            parts.append(v)
    parts.append(rule.get("source_path", "").replace("/", " ").replace("-", " "))
    return tokenize(" ".join(parts))


def score_rule(question_tokens: set[str], rule: dict[str, Any]) -> float:
    """Token overlap divided by question token count, weighted toward
    active rules and demoted for stale or superseded ones.
    """
    if not question_tokens:
        return 0.0
    hay = haystack_for_rule(rule)
    if not hay:
        return 0.0
    overlap = len(question_tokens & hay)
    if overlap == 0:
        return 0.0
    base = overlap / len(question_tokens)
    status = rule.get("status", "")
    if status == "active":
        weight = 1.0
    elif status == "under-review":
        weight = 0.85
    elif status == "stale":
        weight = 0.65
    elif status == "superseded":
        weight = 0.40
    else:
        weight = 0.55
    return base * weight


def rank_rules(question: str, rules: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Score every rule, return the top `limit` with non-zero score."""
    qtokens = tokenize(question)
    scored: list[tuple[float, dict[str, Any]]] = []
    for r in rules:
        s = score_rule(qtokens, r)
        if s > 0:
            scored.append((s, r))
    scored.sort(key=lambda t: (-t[0], t[1]["rule_id"]))
    out: list[dict[str, Any]] = []
    for s, r in scored[:limit]:
        copy = dict(r)
        copy["score"] = round(s, 4)
        out.append(copy)
    return out


def build_summary(matched: list[dict[str, Any]], match_kind: str, question: str) -> str:
    """One-liner the host session can render to the operator."""
    if match_kind == "none":
        return f"no rule matches this query: {question!r}"
    if match_kind == "decisive":
        r = matched[0]
        return (
            f"decisive match: rule_id={r['rule_id']!r} "
            f"(type={r['type']}, status={r['status']}, "
            f"score={r['score']})"
        )
    return (
        f"ranked candidates ({len(matched)}): top={matched[0]['rule_id']!r} "
        f"score={matched[0]['score']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", type=str, help="Natural-language question.")
    parser.add_argument(
        "--vault-root",
        type=Path,
        default=Path(os.environ.get("VAULT_ROOT", Path.cwd())),
    )
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    vault_root = args.vault_root.resolve()
    meta_dir = find_meta_dir(vault_root)
    if meta_dir is None:
        print(json.dumps({
            "error": f"no Meta folder under {vault_root}",
            "vault_root": str(vault_root),
            "match_kind": "none",
            "matched_rules": [],
            "summary": "vault has no Meta folder",
        }, indent=2))
        return 1

    resolver_path = meta_dir / "RESOLVER.md"
    if not resolver_path.is_file():
        print(json.dumps({
            "error": f"RESOLVER.md not found at {resolver_path}",
            "vault_root": str(vault_root),
            "match_kind": "none",
            "matched_rules": [],
            "summary": "RESOLVER.md missing; run scripts/resolver-build.py first",
        }, indent=2))
        return 1

    text = resolver_path.read_text(encoding="utf-8")
    parsed = parse_resolver(text)
    rules = parsed["rules"]

    ranked = rank_rules(args.question, rules, args.limit)

    if not ranked:
        match_kind = "none"
    elif len(ranked) == 1 and ranked[0]["score"] >= DECISIVE_THRESHOLD:
        match_kind = "decisive"
    elif (
        len(ranked) >= 2
        and ranked[0]["score"] >= DECISIVE_THRESHOLD
        and (ranked[0]["score"] - ranked[1]["score"]) >= 0.20
    ):
        match_kind = "decisive"
        ranked = ranked[:1]
    else:
        match_kind = "ranked"

    out = {
        "question": args.question,
        "vault_root": str(vault_root),
        "resolver_built_at": parsed["frontmatter"].get("last_built", ""),
        "rule_count": len(rules),
        "match_kind": match_kind,
        "matched_rules": ranked,
        "summary": build_summary(ranked, match_kind, args.question),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
