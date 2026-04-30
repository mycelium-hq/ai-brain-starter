#!/usr/bin/env python3
"""
test-closing-signals.py — fixture-based test harness for the close detector.

Validates that hooks/detect-closing-signal.py classifies real-world inputs
correctly across English, Spanish, Portuguese, emoji-only, ambiguous, and
adversarial cases.

Run:
  python3 scripts/test-closing-signals.py
  python3 scripts/test-closing-signals.py --verbose
  python3 scripts/test-closing-signals.py --fixture <name>

Exits 0 on all-pass, 1 on any failure. CI-runnable.

Each fixture is one prompt + the expected confidence level:
  "explicit"        — slash command or a definite close keyword
  "high_confidence" — natural-language close
  "ambiguous"       — could be close or transition; user confirmation needed
  "emoji_only"      — emoji-only farewell
  None              — should NOT match (e.g., transitions, code blocks, quotes)

The harness exercises the detector by piping fake hook input to the script
and parsing the JSON response.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DETECTOR = REPO / "hooks" / "detect-closing-signal.py"

# (id, prompt, expected_confidence_or_None)
FIXTURES: list[tuple[str, str, str | None]] = [
    # === Explicit slash commands ===
    ("en-explicit-close", "/close", "explicit"),
    ("en-explicit-wrap", "/wrap-up", "explicit"),
    ("en-explicit-bye-cmd", "/bye", "explicit"),
    ("es-explicit-cerrar", "/cerrar", "explicit"),
    ("pt-explicit-fechar", "/fechar", "explicit"),

    # === English high-confidence natural language ===
    ("en-bye", "bye", "high_confidence"),
    ("en-bye-bang", "bye!", "high_confidence"),
    ("en-ok-bye", "ok bye", "high_confidence"),
    ("en-okay-bye", "okay bye", "high_confidence"),
    ("en-thanks-thats-all", "thanks, that's all", "high_confidence"),
    ("en-im-done", "i'm done", "high_confidence"),
    ("en-im-out", "I'm out", "high_confidence"),
    ("en-good-night", "good night", "high_confidence"),
    ("en-goodnight", "goodnight", "high_confidence"),
    ("en-ttyl", "ttyl", "high_confidence"),
    ("en-cya", "cya", "high_confidence"),
    ("en-talk-later", "talk to you later", "high_confidence"),
    ("en-talk-tomorrow", "talk tomorrow", "high_confidence"),
    ("en-wrapping-up", "wrapping up", "high_confidence"),
    ("en-thats-all-today", "that's all for today", "high_confidence"),
    ("en-calling-it", "calling it a day", "high_confidence"),
    ("en-k-bye", "k bye", "high_confidence"),
    ("en-k-thx", "k thx", "high_confidence"),
    ("en-gn", "gn", "high_confidence"),
    ("en-thanks-just", "thanks", "high_confidence"),

    # === Spanish high-confidence ===
    ("es-chao", "chao", "high_confidence"),
    ("es-chau", "chau", "high_confidence"),
    ("es-ok-chao", "ok chao", "high_confidence"),
    ("es-nos-vemos", "nos vemos", "high_confidence"),
    ("es-hasta-luego", "hasta luego", "high_confidence"),
    ("es-hasta-manana", "hasta mañana", "high_confidence"),
    ("es-listo-gracias", "listo, gracias", "high_confidence"),
    ("es-eso-es-todo", "eso es todo", "high_confidence"),
    ("es-buenas-noches", "buenas noches", "high_confidence"),
    ("es-me-voy", "me voy", "high_confidence"),
    ("es-listo-alone", "listo", "high_confidence"),
    ("es-gracias-alone", "gracias", "high_confidence"),

    # === Portuguese high-confidence ===
    ("pt-tchau", "tchau", "high_confidence"),
    ("pt-ate-logo", "até logo", "high_confidence"),
    ("pt-ate-amanha", "até amanhã", "high_confidence"),
    ("pt-valeu", "valeu", "high_confidence"),
    ("pt-falou", "falou", "high_confidence"),
    ("pt-boa-noite", "boa noite", "high_confidence"),
    ("pt-pronto", "pronto", "high_confidence"),
    ("pt-obrigado", "obrigado", "high_confidence"),

    # === Emoji-only ===
    ("emoji-wave", "👋", "emoji_only"),
    ("emoji-pray", "🙏", "emoji_only"),
    ("emoji-peace", "✌️", "emoji_only"),

    # === Ambiguous (should ask "wrapping up?") ===
    ("amb-en-ok", "ok", "ambiguous"),
    ("amb-en-cool", "cool", "ambiguous"),
    ("amb-en-great", "great", "ambiguous"),
    ("amb-en-perfect", "perfect", "ambiguous"),
    ("amb-en-sounds-good", "sounds good", "ambiguous"),
    ("amb-es-dale", "dale", "ambiguous"),
    ("amb-es-bueno", "bueno", "ambiguous"),
    ("amb-pt-beleza", "beleza", "ambiguous"),

    # === False positives — should NOT match ===
    ("neg-mid-conv", "now lets keep going on the other thing", None),
    ("neg-ok-now-do", "okay now do X", None),
    ("neg-ok-lets", "ok let's continue with the next file", None),
    ("neg-ok-so", "ok so the next step is", None),
    ("neg-bye-quoted", 'how do I say "bye" in formal english?', None),
    ("neg-say-bye-to", "we have to say bye to that feature", None),
    ("neg-done-with", "i'm done with the auth module, lets move on", None),
    ("neg-listo-para", "listo para empezar el siguiente paso", None),
    ("neg-listo-el", "listo el primero, sigamos con el segundo", None),
    ("neg-pronto-para", "pronto para começar a próxima parte", None),
    ("neg-empty", "", None),
    ("neg-question", "what does ttyl mean?", None),
    ("neg-code-block", "```python\ndef bye():\n    pass\n```", None),
    ("neg-explanation", "the bye function returns None", None),
    ("neg-ok-then", "ok, then let's plan the rollout", None),
    ("neg-ok-now", "ok now I want to refactor", None),
    ("neg-bueno-entonces", "bueno, entonces sigamos", None),
    ("neg-beleza-agora", "beleza, agora vamos para o próximo", None),
]


def run_detector(prompt: str) -> dict:
    """Pipe prompt through the detector hook, return parsed JSON."""
    with tempfile.TemporaryDirectory() as tmp:
        hook_input = json.dumps({
            "prompt": prompt,
            "session_id": "test-harness",
            "cwd": tmp,
        })
        env = {**os.environ}
        env["CLOSING_SIGNAL_DETECTION"] = "regex"  # never call Haiku in tests
        env.pop("ANTHROPIC_API_KEY", None)
        try:
            proc = subprocess.run(
                [sys.executable, str(DETECTOR)],
                input=hook_input,
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return {"_error": "timeout"}
        try:
            return json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            return {"_error": "non-json output", "_raw": proc.stdout}


def detected_confidence(result: dict) -> str | None:
    """Extract confidence level from the detector's response."""
    ctx = (result.get("hookSpecificOutput") or {}).get("additionalContext", "")
    if not ctx:
        return None
    if "confidence: explicit" in ctx:
        return "explicit"
    if "confidence: high_confidence" in ctx:
        return "high_confidence"
    if "confidence: ambiguous" in ctx:
        return "ambiguous"
    if "confidence: emoji_only" in ctx:
        return "emoji_only"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--fixture", help="run only the named fixture")
    args = ap.parse_args()

    if not DETECTOR.is_file():
        print(f"FAIL: detector not found at {DETECTOR}")
        return 1

    fixtures = FIXTURES
    if args.fixture:
        fixtures = [f for f in FIXTURES if f[0] == args.fixture]
        if not fixtures:
            print(f"FAIL: fixture not found: {args.fixture}")
            return 1

    passed = 0
    failed = 0
    failures = []

    for fid, prompt, expected in fixtures:
        result = run_detector(prompt)
        actual = detected_confidence(result)
        ok = actual == expected
        if args.verbose or not ok:
            tag = "PASS" if ok else "FAIL"
            print(f"[{tag}] {fid}: prompt={prompt!r} expected={expected!r} actual={actual!r}")
        if ok:
            passed += 1
        else:
            failed += 1
            failures.append((fid, prompt, expected, actual))

    total = passed + failed
    print(f"\n{passed}/{total} passed, {failed} failed.")

    if failures:
        print("\nFailures:")
        for fid, prompt, expected, actual in failures:
            print(f"  {fid}: prompt={prompt!r} expected={expected!r} actual={actual!r}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
