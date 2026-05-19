"""NVIDIA-vs-Claude comparison harness.

Before flipping any pipeline from Claude to a Tier-2 model (NVIDIA / Llama /
Qwen / DeepSeek / Nemotron), run this against real samples and require
>=90% agreement. Match rates use either an LLM-as-judge for free-form text
or structural equality for JSON outputs.

The no-silent-fallbacks rule: pass the comparison at >=90% match-rate or
don't ship. Anything less hides quality drift behind a cheaper price tag.

API:
  run_compare(name, samples, claude_fn, nvidia_fn, mode="text"|"json", threshold=0.9)

  samples: list[dict]. Each sample: {"input": Any, optionally "label": str}
  claude_fn(input) -> str | dict | list  -- the existing Claude pipeline
  nvidia_fn(input) -> str | dict | list  -- the new NVIDIA pipeline (or any
                                            Tier-2 alternative; the name is
                                            historical, not prescriptive)

  mode="text"  -> LLM-as-judge scores semantic similarity (0-1)
  mode="json"  -> deep equality on shared keys; missing keys -> 0; extras -> 0.5

Text mode requires a judge callable. By default the harness tries to import
`_claude_router.call_claude_json` from the same scripts directory; pass
`judge_fn=...` to plug in any other JSON-returning LLM caller.

Output: per-sample score, mean, pass/fail vs threshold. Returns dict with
match_rate, decisions list, samples list. Exit 1 on fail when run as __main__.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any, Callable, Optional

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


JUDGE_SYSTEM = (
    "You are an automated scoring judge. Compare a candidate response against a "
    "reference response and score semantic equivalence on a 0.0-1.0 scale. "
    "1.0 = same meaning, same key facts, same structure. "
    "0.7-0.9 = same gist, minor differences in phrasing or one missing detail. "
    "0.4-0.6 = partial overlap; major facts differ or are missing. "
    "0.0-0.3 = substantively different or hallucinated. "
    "Return ONLY a JSON object: {\"score\": float, \"reason\": \"<one sentence>\"}. "
    "No prose outside the JSON."
)


def _default_judge(system: str, user: str) -> dict:
    """Default judge: try to use a co-located _claude_router. Raise if absent."""
    try:
        from _claude_router import call_claude_json  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "Text-mode comparison needs a judge callable. Either install a "
            "_claude_router module next to this file, or pass judge_fn=... to "
            "run_compare. The judge must accept (system: str, user: str) and "
            "return a dict with 'score' (float) and 'reason' (str)."
        ) from e
    return call_claude_json(system=system, user=user, max_tokens=200)


def _judge_text(
    reference: str,
    candidate: str,
    judge_fn: Optional[Callable[[str, str], dict]] = None,
) -> tuple[float, str]:
    """Score candidate against reference using an LLM as judge."""
    user_msg = (
        f"# Reference (baseline)\n{reference}\n\n"
        f"# Candidate (Tier-2 alternative)\n{candidate}\n\n"
        "Score the candidate against the reference."
    )
    judge = judge_fn or _default_judge
    try:
        verdict = judge(JUDGE_SYSTEM, user_msg)
        if not isinstance(verdict, dict):
            return 0.0, f"judge returned non-dict: {verdict!r:.80}"
        score = float(verdict.get("score", 0.0))
        reason = str(verdict.get("reason", ""))[:200]
        return max(0.0, min(1.0, score)), reason
    except Exception as e:
        return 0.0, f"judge failed: {e}"


def _score_json(reference: Any, candidate: Any) -> tuple[float, str]:
    """Structural equality score. Handles dict/list/scalar."""
    if reference == candidate:
        return 1.0, "exact match"
    if isinstance(reference, dict) and isinstance(candidate, dict):
        ref_keys = set(reference.keys())
        cand_keys = set(candidate.keys())
        if not ref_keys:
            return (1.0 if not cand_keys else 0.5, "ref empty dict")
        per_key = []
        for key in ref_keys:
            if key not in candidate:
                per_key.append(0.0)
            else:
                sub_score, _ = _score_json(reference[key], candidate[key])
                per_key.append(sub_score)
        extras = cand_keys - ref_keys
        extra_penalty = 0.0 if not extras else 0.1
        score = max(0.0, statistics.mean(per_key) - extra_penalty)
        return score, f"dict: {len(ref_keys)} keys, extras={len(extras)}"
    if isinstance(reference, list) and isinstance(candidate, list):
        if not reference:
            return (1.0 if not candidate else 0.5, "ref empty list")
        if not candidate:
            return 0.0, "candidate empty list, ref had items"
        ref_set = {json.dumps(x, sort_keys=True, default=str) for x in reference}
        cand_set = {json.dumps(x, sort_keys=True, default=str) for x in candidate}
        if not ref_set:
            return 1.0, "ref unhashable, exact-eq path"
        overlap = ref_set & cand_set
        missing = ref_set - cand_set
        extras = cand_set - ref_set
        recall = len(overlap) / len(ref_set)
        precision = len(overlap) / max(1, len(cand_set))
        f1 = (2 * recall * precision / (recall + precision)) if (recall + precision) else 0.0
        return f1, f"list F1: recall={recall:.2f}, precision={precision:.2f}, missing={len(missing)}, extras={len(extras)}"
    if reference is None and candidate is None:
        return 1.0, "both null"
    if isinstance(reference, str) and isinstance(candidate, str):
        if reference.strip().lower() == candidate.strip().lower():
            return 1.0, "case-insensitive str match"
        return 0.0, f"str mismatch: ref={reference[:40]!r} cand={candidate[:40]!r}"
    return 0.0, f"type mismatch: ref={type(reference).__name__} cand={type(candidate).__name__}"


def run_compare(
    name: str,
    samples: list[dict],
    claude_fn: Callable[[Any], Any],
    nvidia_fn: Callable[[Any], Any],
    mode: str = "text",
    threshold: float = 0.9,
    verbose: bool = True,
    judge_fn: Optional[Callable[[str, str], dict]] = None,
) -> dict:
    """Compare claude_fn vs nvidia_fn on samples. Return summary + per-sample.

    Each sample must have an "input" key. Optional "label" key for human reference.
    """
    if mode not in ("text", "json"):
        raise ValueError(f"mode must be 'text' or 'json', got {mode!r}")

    per_sample = []
    for i, sample in enumerate(samples, 1):
        label = sample.get("label", f"sample-{i}")
        inp = sample["input"]
        try:
            ref = claude_fn(inp)
        except Exception as e:
            per_sample.append({"label": label, "score": 0.0, "reason": f"claude failed: {e}"})
            continue
        try:
            cand = nvidia_fn(inp)
        except Exception as e:
            per_sample.append({"label": label, "score": 0.0, "reason": f"nvidia failed: {e}"})
            continue
        if mode == "text":
            ref_str = ref if isinstance(ref, str) else json.dumps(ref, sort_keys=True, default=str)
            cand_str = cand if isinstance(cand, str) else json.dumps(cand, sort_keys=True, default=str)
            score, reason = _judge_text(ref_str, cand_str, judge_fn=judge_fn)
        else:
            score, reason = _score_json(ref, cand)
        per_sample.append({"label": label, "score": round(score, 3), "reason": reason})
        if verbose:
            print(f"  [{i}/{len(samples)}] {label}: {score:.2f}  ({reason})")

    if per_sample:
        match_rate = round(statistics.mean(s["score"] for s in per_sample), 3)
    else:
        match_rate = 0.0
    passed = match_rate >= threshold

    summary = {
        "name": name,
        "mode": mode,
        "n_samples": len(samples),
        "threshold": threshold,
        "match_rate": match_rate,
        "passed": passed,
        "samples": per_sample,
    }
    if verbose:
        verdict = "PASS" if passed else "FAIL"
        print(f"\n{name}: {verdict}  match_rate={match_rate:.3f}  threshold={threshold:.2f}  ({len(samples)} samples)")
    return summary


if __name__ == "__main__":
    # Harness self-test: confirm the threshold gate behaves correctly.
    def claude_fn(text):
        return {"sentiment": "positive" if "love" in text else "negative"}

    def nvidia_fn(text):
        return {"sentiment": "positive" if "love" in text else "negative"}

    samples = [
        {"input": "I love this", "label": "pos-1"},
        {"input": "This is terrible", "label": "neg-1"},
        {"input": "It's great but not loved", "label": "edge-1"},
    ]
    result = run_compare("self-test", samples, claude_fn, nvidia_fn, mode="json", threshold=0.9)
    assert result["passed"], f"self-test failed unexpectedly: {result}"
    print("\nharness self-test: PASS")
    sys.exit(0)
