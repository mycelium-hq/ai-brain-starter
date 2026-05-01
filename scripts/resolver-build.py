#!/usr/bin/env python3
"""
resolver-build.py builds Meta/RESOLVER.md, the Bi-Temporal Resolver index.

RESOLVER.md is the single file that routes natural-language queries to
executable skills with current policy constraints. It is the catalect
aggregator across the four typed-memory primitives that carry routable
rules: decisions, workflows, exceptions, facts.

Each row in the rendered table represents one rule with its bi-temporal
status:

  validity-time     = decision_date / last_verified (when the rule
                      describes the world)
  transaction-time  = git commit time of the source file (when the rule
                      was written into the vault)

Status logic:
  active        = last_verified is set and (today - last_verified) <= freshness_days
  stale         = last_verified is set and (today - last_verified) > freshness_days
  superseded    = same pattern + overlapping subject as another rule with a
                  more recent last_verified (validity-time precedence)
  under-review  = outcome field is non-blank but pattern field is empty
                  (decision resolved but lesson not yet extracted)
  unknown       = neither last_verified nor outcome/pattern signal applies

Conflict detection:
  Two rules conflict when they share the same `pattern` field AND their
  subjects overlap. Subject is derived from the source file's first H1
  plus the frontmatter `topic` or `subject` field. Overlap is a simple
  case-folded keyword match. Among a conflicting set, the rule with the
  most recent `last_verified` wins; older rules are marked
  status: superseded with a `superseded_by` field naming the winner.

The aggregator walks Meta/Decisions/, Meta/Workflows/, Meta/Exceptions/,
Meta/Facts/ inside --vault-root, parses YAML frontmatter on every .md file,
and emits a single Meta/RESOLVER.md as a stable, single-Read-readable index.

Usage:
  python3 scripts/resolver-build.py --vault-root PATH [--out PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path
from typing import Any


# Folder names the aggregator walks. The auto-detect supports both
# emoji-prefixed ("⚙️ Meta") and plain ("Meta") layouts.
META_BASENAMES = ("Meta",)
TYPED_FOLDERS = ("Decisions", "Workflows", "Exceptions", "Facts")
TYPE_BY_FOLDER = {
    "Decisions": "decision",
    "Workflows": "workflow",
    "Exceptions": "exception",
    "Facts": "fact",
}


def find_meta_dir(vault_root: Path) -> Path | None:
    """Auto-detect the Meta folder. Supports '⚙️ Meta' and 'Meta'."""
    if not vault_root.is_dir():
        return None
    for child in sorted(vault_root.iterdir()):
        if child.is_dir() and child.name.endswith("Meta"):
            return child
    return None


def parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Return the YAML frontmatter dict, or None if missing/unparseable."""
    if not text.startswith("---"):
        return None
    m = re.match(r"^---\n(.*?)\n---\s*", text, re.DOTALL)
    if not m:
        return None
    try:
        import yaml  # PyYAML
    except ImportError:
        print("ERROR: PyYAML required (pip install pyyaml)", file=sys.stderr)
        sys.exit(1)
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return _stringify_dates(data)


def _stringify_dates(obj: Any) -> Any:
    """PyYAML auto-converts dates; we want strings for date arithmetic."""
    if isinstance(obj, dict):
        return {k: _stringify_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_stringify_dates(v) for v in obj]
    if isinstance(obj, dt.datetime):
        return obj.isoformat()
    if isinstance(obj, dt.date):
        return obj.isoformat()
    return obj


def parse_iso_date(value: Any) -> dt.date | None:
    """Best-effort parse of an ISO-style date or datetime string."""
    if not isinstance(value, str) or not value:
        return None
    s = value.strip()
    if len(s) >= 10:
        head = s[:10]
        try:
            return dt.date.fromisoformat(head)
        except ValueError:
            return None
    return None


def derive_status(fm: dict[str, Any], today: dt.date) -> str:
    """Map a frontmatter dict to one of: active, stale, under-review, unknown."""
    last_verified = parse_iso_date(fm.get("last_verified"))
    freshness = fm.get("freshness_days")
    if last_verified is not None and isinstance(freshness, int) and freshness >= 0:
        delta = (today - last_verified).days
        if delta > freshness:
            return "stale"
        return "active"

    outcome = fm.get("outcome")
    pattern = fm.get("pattern")
    if isinstance(outcome, str) and outcome.strip() and (
        pattern is None or (isinstance(pattern, str) and not pattern.strip())
    ):
        return "under-review"

    return "unknown"


def derive_rule_id(file_path: Path, fm: dict[str, Any]) -> str:
    """Stable rule_id: prefer explicit field, else file stem."""
    explicit = fm.get("rule_id") or fm.get("id") or fm.get("name")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    return file_path.stem


def derive_skill_link(fm: dict[str, Any]) -> str:
    """Pull an executable-skill pointer from common frontmatter fields."""
    for key in ("skill", "executable_skill", "routes_to", "skill_id"):
        val = fm.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def derive_first_h1(text: str) -> str:
    """Return the first H1 heading from the markdown body, lowercase."""
    body = text
    if text.startswith("---"):
        m = re.match(r"^---\n.*?\n---\s*", text, re.DOTALL)
        if m:
            body = text[m.end():]
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip().lower()
    return ""


def derive_subject_tokens(fm: dict[str, Any], h1: str) -> set[str]:
    """Return a set of normalized subject tokens for overlap matching.

    Tokens come from frontmatter `topic` or `subject` (string or list)
    and from the first H1 of the markdown body. All tokens are lower-cased
    and split on whitespace. Empty strings filtered out.
    """
    tokens: set[str] = set()
    for key in ("topic", "subject"):
        val = fm.get(key)
        if isinstance(val, str):
            for tok in val.lower().split():
                if tok:
                    tokens.add(tok)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    for tok in item.lower().split():
                        if tok:
                            tokens.add(tok)
    if h1:
        for tok in h1.split():
            if tok:
                tokens.add(tok)
    return tokens


def derive_pattern(fm: dict[str, Any]) -> str:
    """Return the normalized `pattern` field, or empty string."""
    val = fm.get("pattern")
    if isinstance(val, str):
        return val.strip().lower()
    return ""


def collect_rules(meta_dir: Path) -> list[dict[str, Any]]:
    """Walk the four typed-memory folders, emit one row per parseable file."""
    rules: list[dict[str, Any]] = []
    today = dt.date.today()

    for folder_name in TYPED_FOLDERS:
        folder = meta_dir / folder_name
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            fm = parse_frontmatter(text)
            if fm is None:
                continue

            h1 = derive_first_h1(text)
            rules.append({
                "rule_id": derive_rule_id(path, fm),
                "type": TYPE_BY_FOLDER[folder_name],
                "status": derive_status(fm, today),
                "last_verified": str(fm.get("last_verified") or ""),
                "last_verified_date": parse_iso_date(fm.get("last_verified")),
                "freshness_days": fm.get("freshness_days") if isinstance(
                    fm.get("freshness_days"), int
                ) else "",
                "owner": str(fm.get("owner") or ""),
                "source_path": str(path.relative_to(meta_dir.parent)),
                "skill_link": derive_skill_link(fm),
                "pattern": derive_pattern(fm),
                "subject_tokens": derive_subject_tokens(fm, h1),
                "h1": h1,
                "superseded_by": "",
            })

    return rules


def detect_conflicts(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find pairs of rules that share a non-empty `pattern` AND overlap on
    subject tokens.

    Returns a list of conflict records:
      {pattern, members: [rule_id, ...], winner_rule_id, superseded: [rule_id, ...]}

    Side effects on the input list: the older rule(s) in each conflict
    group get status='superseded' and superseded_by=winner_rule_id.
    """
    conflicts: list[dict[str, Any]] = []
    rules_by_pattern: dict[str, list[dict[str, Any]]] = {}
    for r in rules:
        if r["pattern"]:
            rules_by_pattern.setdefault(r["pattern"], []).append(r)

    seen_pairs: set[tuple[str, str]] = set()

    for pattern, group in rules_by_pattern.items():
        if len(group) < 2:
            continue
        # Build adjacency by subject-token overlap.
        # A pair conflicts when shared tokens > 0.
        n = len(group)
        adjacency: list[set[int]] = [set() for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                shared = group[i]["subject_tokens"] & group[j]["subject_tokens"]
                if shared:
                    adjacency[i].add(j)
                    adjacency[j].add(i)

        # Connected-component grouping.
        visited = [False] * n
        for start in range(n):
            if visited[start]:
                continue
            component: list[int] = []
            stack = [start]
            while stack:
                idx = stack.pop()
                if visited[idx]:
                    continue
                visited[idx] = True
                component.append(idx)
                for nb in adjacency[idx]:
                    if not visited[nb]:
                        stack.append(nb)
            if len(component) < 2:
                continue

            members = [group[i] for i in component]
            # Winner = most recent last_verified_date. Ties -> rule_id sort.
            def sort_key(r: dict[str, Any]) -> tuple:
                lvd = r.get("last_verified_date")
                # Rules without a date sort oldest.
                rank = lvd.toordinal() if lvd is not None else -1
                return (-rank, r["rule_id"])

            members_sorted = sorted(members, key=sort_key)
            winner = members_sorted[0]
            losers = members_sorted[1:]

            # Annotate losers in-place. Only override status if it would
            # demote (active/unknown/under-review -> superseded). We keep
            # 'stale' for visibility but still mark superseded_by.
            for loser in losers:
                loser["status"] = "superseded"
                loser["superseded_by"] = winner["rule_id"]

            # Stable de-dupe: skip if we have already seen this exact group.
            sig = tuple(sorted(m["rule_id"] for m in members))
            if sig in seen_pairs:
                continue
            seen_pairs.add(sig)

            conflicts.append({
                "pattern": pattern,
                "members": [m["rule_id"] for m in members_sorted],
                "winner_rule_id": winner["rule_id"],
                "winner_source": winner["source_path"],
                "winner_last_verified": winner["last_verified"],
                "superseded": [
                    {
                        "rule_id": m["rule_id"],
                        "source_path": m["source_path"],
                        "last_verified": m["last_verified"],
                    }
                    for m in losers
                ],
            })

    return conflicts


def render_resolver(
    rules: list[dict[str, Any]],
    vault_root: Path,
    conflicts: list[dict[str, Any]] | None = None,
) -> str:
    """Emit the stable RESOLVER.md body."""
    today = dt.date.today().isoformat()
    counts = {
        "active": 0,
        "stale": 0,
        "superseded": 0,
        "under-review": 0,
        "unknown": 0,
    }
    for r in rules:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    conflicts = conflicts or []

    lines: list[str] = []
    lines.append("---")
    lines.append("type: resolver")
    lines.append(f"last_built: {today}")
    lines.append(f"vault_root: {vault_root}")
    lines.append(f"conflict_count: {len(conflicts)}")
    lines.append("---")
    lines.append("")
    lines.append("# RESOLVER")
    lines.append("")
    lines.append(
        "RESOLVER.md is the single file that routes natural-language "
        "queries to executable skills with current policy constraints."
    )
    lines.append("")
    lines.append(
        "Auto-generated by `scripts/resolver-build.py`. Do not edit by "
        "hand. The aggregator walks `Meta/Decisions/`, `Meta/Workflows/`, "
        "`Meta/Exceptions/`, `Meta/Facts/`, parses YAML frontmatter on "
        "each `.md` file, and renders one row per rule. Rerun the script "
        "after any rule changes."
    )
    lines.append("")
    lines.append("## Bi-temporal model")
    lines.append("")
    lines.append(
        "Each row carries two clocks. The validity-time clock is "
        "`last_verified` (or `decision_date`): when the rule was last "
        "confirmed to describe the world. The transaction-time clock is "
        "the git commit time on the source file: when the rule was "
        "written into the vault. A rule is `stale` when "
        "`(today - last_verified) > freshness_days`, regardless of when "
        "it was committed."
    )
    lines.append("")
    lines.append(
        "When two rules collide on the same `pattern` and overlapping "
        "subject tokens, the one with the more recent `last_verified` "
        "wins. The older rule is marked `superseded` and the row carries "
        "a `superseded_by` pointer at the winner. Validity-time precedence."
    )
    lines.append("")
    lines.append("## Status counts")
    lines.append("")
    lines.append(f"- active: {counts['active']}")
    lines.append(f"- stale: {counts['stale']}")
    lines.append(f"- superseded: {counts['superseded']}")
    lines.append(f"- under-review: {counts['under-review']}")
    lines.append(f"- unknown: {counts['unknown']}")
    lines.append(f"- total rules: {len(rules)}")
    lines.append(f"- conflict groups: {len(conflicts)}")
    lines.append("")

    if conflicts:
        lines.append("## Conflicts")
        lines.append("")
        lines.append(
            "Each group below shares a `pattern` and overlaps on subject "
            "tokens. The winner row keeps its current status. Loser rows "
            "are marked `superseded` and carry `superseded_by` in the "
            "Rules table."
        )
        lines.append("")
        for c in conflicts:
            lines.append(f"### Pattern: `{c['pattern']}`")
            lines.append("")
            lines.append(
                f"- winner: `{c['winner_rule_id']}` "
                f"(last_verified {c['winner_last_verified'] or 'unknown'}) "
                f"[[{c['winner_source']}]]"
            )
            for loser in c["superseded"]:
                lines.append(
                    f"- superseded: `{loser['rule_id']}` "
                    f"(last_verified {loser['last_verified'] or 'unknown'}) "
                    f"[[{loser['source_path']}]]"
                )
            lines.append("")

    lines.append("## Rules")
    lines.append("")
    lines.append(
        "| rule_id | type | status | last_verified | freshness_days | "
        "owner | source | skill | superseded_by |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|"
    )

    if not rules:
        lines.append("| (no rules found) |  |  |  |  |  |  |  |  |")
    else:
        for r in sorted(
            rules,
            key=lambda x: (
                {
                    "stale": 0,
                    "superseded": 1,
                    "under-review": 2,
                    "active": 3,
                    "unknown": 4,
                }.get(x["status"], 5),
                x["type"],
                x["rule_id"],
            ),
        ):
            source_link = f"[[{r['source_path']}]]"
            skill = f"[[{r['skill_link']}]]" if r["skill_link"] else ""
            superseded_by = (
                f"`{r['superseded_by']}`" if r.get("superseded_by") else ""
            )
            lines.append(
                f"| {r['rule_id']} | {r['type']} | {r['status']} | "
                f"{r['last_verified']} | {r['freshness_days']} | "
                f"{r['owner']} | {source_link} | {skill} | {superseded_by} |"
            )

    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build Meta/RESOLVER.md from typed-memory primitives "
            "(decisions, workflows, exceptions, facts)."
        )
    )
    parser.add_argument(
        "--vault-root",
        type=Path,
        default=Path(os.environ.get("VAULT_ROOT", Path.cwd())),
        help="Vault root containing the Meta folder.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Override output path. Default: <meta>/RESOLVER.md.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the rendered file without writing to disk.",
    )
    args = parser.parse_args()

    vault_root = args.vault_root.resolve()
    meta_dir = find_meta_dir(vault_root)
    if meta_dir is None:
        print(
            f"ERROR: no Meta folder under {vault_root}.",
            file=sys.stderr,
        )
        return 1

    rules = collect_rules(meta_dir)
    conflicts = detect_conflicts(rules)
    rendered = render_resolver(rules, vault_root, conflicts)

    out_path = args.out if args.out is not None else (meta_dir / "RESOLVER.md")

    if args.dry_run:
        print(f"--- DRY RUN: would write {out_path} ---")
        print(rendered)
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(
        f"Wrote {out_path} ({len(rules)} rule(s), "
        f"{len(conflicts)} conflict group(s), "
        f"{len(rendered):,} bytes)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
