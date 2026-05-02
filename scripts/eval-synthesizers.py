#!/usr/bin/env python3
"""eval-synthesizers.py: golden-pair eval for synth-pr-to-sop and synth-thread-to-sop.

Walks tests/eval/fixtures/*/, runs the matching synthesizer in default
operator-driven mode (no LLM cost), and scores the produced typed-memory
file against the fixture's expected.json.

Score per fixture (0-100):
  - 60 pts: required frontmatter keys present + matching expected values.
  - 25 pts: body keyword overlap.
  - 15 pts: step count + step ordering hint match (if specified).

Output: a markdown summary table on stdout. Exit code 0 unless a fixture
errors at runtime; bad scores never block the script (the operator decides
the threshold).

Run:
    python3 scripts/eval-synthesizers.py
    python3 scripts/eval-synthesizers.py --fixtures-dir tests/eval/fixtures
    python3 scripts/eval-synthesizers.py --fail-below 70   # exit 1 if any score < 70
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SYNTH_PR = REPO_ROOT / "skills" / "synth-pr-to-sop" / "synth.py"
SYNTH_THREAD = REPO_ROOT / "skills" / "synth-thread-to-sop" / "synth.py"


def load_fixture(folder: Path) -> tuple[Path, dict[str, Any]]:
    input_md = folder / "input.md"
    expected_json = folder / "expected.json"
    if not input_md.exists() or not expected_json.exists():
        raise FileNotFoundError(f"fixture missing files: {folder}")
    expected = json.loads(expected_json.read_text())
    return input_md, expected


def run_synth_pr(input_md: Path, vault_root: Path) -> Path | None:
    cmd = [sys.executable, str(SYNTH_PR), str(input_md), "--vault-root", str(vault_root)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return None
    out = vault_root / "Meta" / "Workflows"
    files = list(out.glob("*.md"))
    return files[0] if files else None


def run_synth_thread(input_md: Path, vault_root: Path) -> Path | None:
    cmd = [sys.executable, str(SYNTH_THREAD), str(input_md), "--vault-root", str(vault_root)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return None
    for sub in ("Decisions", "Exceptions", "Workflows"):
        d = vault_root / "Meta" / sub
        if d.exists():
            files = list(d.glob("*.md"))
            if files:
                return files[0]
    return None


def split_md(text: str) -> tuple[dict[str, Any], str]:
    """Tiny YAML frontmatter splitter. Avoids hard dep on pyyaml."""
    if not text.startswith("---\n"):
        return {}, text
    end_idx = text.find("\n---\n", 4)
    if end_idx == -1:
        return {}, text
    raw_fm = text[4:end_idx]
    body = text[end_idx + 5:]
    fm: dict[str, Any] = {}
    for line in raw_fm.splitlines():
        if ":" not in line or line.startswith(("  ", "-")):
            continue
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip().strip("'\"")
    return fm, body


def count_steps(body: str) -> int:
    n = 0
    for line in body.splitlines():
        s = line.strip()
        if s and (s[0].isdigit() and "." in s[:4]):
            n += 1
    return n


def keyword_hit_rate(body: str, keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    body_lower = body.lower()
    hits = sum(1 for kw in keywords if kw.lower() in body_lower)
    return hits / len(keywords)


def step_order_hint_match(body: str, hints: list[str]) -> float:
    """Each successive hint must appear after the previous one in the body."""
    if not hints:
        return 1.0
    body_lower = body.lower()
    last_pos = -1
    matched = 0
    for h in hints:
        pos = body_lower.find(h.lower(), last_pos + 1)
        if pos == -1:
            continue
        last_pos = pos
        matched += 1
    return matched / len(hints)


def score_fixture(produced_path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    produced_text = produced_path.read_text()
    fm, body = split_md(produced_text)

    # 60 pts: frontmatter completeness + value match
    must_have = expected.get("frontmatter_must_have", [])
    present_count = sum(1 for k in must_have if k in fm)
    completeness = present_count / max(1, len(must_have))

    expected_values = expected.get("expected_field_values", {})
    value_matches = sum(
        1 for k, v in expected_values.items()
        if str(fm.get(k, "")).strip().strip("'\"") == str(v).strip()
    )
    value_match_rate = value_matches / max(1, len(expected_values)) if expected_values else 1.0

    fm_score = (completeness * 0.6 + value_match_rate * 0.4) * 60

    # 25 pts: body keyword hit rate
    body_score = keyword_hit_rate(produced_text, expected.get("body_keywords", [])) * 25

    # 15 pts: step count + step order
    step_score = 0.0
    min_steps = expected.get("min_step_count")
    if min_steps:
        actual_steps = count_steps(body)
        step_count_factor = min(actual_steps / max(1, min_steps), 1.0)
        step_score += step_count_factor * 7.5
    else:
        step_score += 7.5
    hints = expected.get("step_order_hint", [])
    if hints:
        step_score += step_order_hint_match(body, hints) * 7.5
    else:
        step_score += 7.5

    total = fm_score + body_score + step_score
    return {
        "score": round(total, 1),
        "fm_score": round(fm_score, 1),
        "body_score": round(body_score, 1),
        "step_score": round(step_score, 1),
        "frontmatter_keys_present": present_count,
        "frontmatter_keys_total": len(must_have),
        "produced_path": str(produced_path),
    }


def run_one_fixture(fixture_dir: Path, work_root: Path) -> dict[str, Any]:
    input_md, expected = load_fixture(fixture_dir)
    vault = work_root / fixture_dir.name
    vault.mkdir(parents=True, exist_ok=True)

    synth_kind = expected.get("synth")
    if synth_kind == "pr":
        produced = run_synth_pr(input_md, vault)
    elif synth_kind == "thread":
        produced = run_synth_thread(input_md, vault)
    else:
        return {"name": fixture_dir.name, "error": f"unknown synth kind: {synth_kind}", "score": 0}

    if produced is None:
        return {"name": fixture_dir.name, "error": "synthesizer did not produce a file", "score": 0}

    scored = score_fixture(produced, expected)
    scored["name"] = fixture_dir.name
    scored["synth"] = synth_kind
    return scored


def render_summary(results: list[dict[str, Any]]) -> str:
    lines = [
        "| Fixture | Synth | Score | FM | Body | Steps | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if r.get("error"):
            lines.append(f"| {r['name']} | {r.get('synth','-')} | 0 | - | - | - | ERROR: {r['error']} |")
            continue
        lines.append(
            f"| {r['name']} | {r['synth']} | "
            f"**{r['score']}** | "
            f"{r['fm_score']} | "
            f"{r['body_score']} | "
            f"{r['step_score']} | "
            f"{r['frontmatter_keys_present']}/{r['frontmatter_keys_total']} fm keys |"
        )
    if results:
        avg = sum(r.get("score", 0) for r in results) / len(results)
        lines.append("")
        lines.append(f"**Avg score:** {avg:.1f}/100 across {len(results)} fixtures")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=REPO_ROOT / "tests" / "eval" / "fixtures",
    )
    parser.add_argument(
        "--fail-below",
        type=float,
        default=None,
        help="Exit 1 if any fixture scores below this threshold (default: never fail).",
    )
    parser.add_argument("--work-root", type=Path, default=None)
    parser.add_argument("--keep-work", action="store_true", help="Don't clean up work dir on exit")
    args = parser.parse_args()

    if not args.fixtures_dir.exists():
        print(f"fixtures dir not found: {args.fixtures_dir}", file=sys.stderr)
        return 2

    work_root = args.work_root or Path(tempfile.mkdtemp(prefix="abs-eval-"))
    work_root.mkdir(parents=True, exist_ok=True)

    fixtures = sorted([d for d in args.fixtures_dir.iterdir() if d.is_dir()])
    if not fixtures:
        print(f"no fixture folders under {args.fixtures_dir}", file=sys.stderr)
        return 2

    results = [run_one_fixture(f, work_root) for f in fixtures]
    print(render_summary(results))

    if not args.keep_work:
        shutil.rmtree(work_root, ignore_errors=True)

    if args.fail_below is not None:
        bad = [r for r in results if r.get("score", 0) < args.fail_below]
        if bad:
            print(f"\nFAIL: {len(bad)} fixture(s) below {args.fail_below}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
