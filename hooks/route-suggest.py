#!/usr/bin/env python3
"""
UserPromptSubmit hook: classify the prompt and print a one-line
model/tool routing suggestion. Never auto-switches — just nudges.

Design goal: you flipped your settings.json default to a mid-tier model
(e.g. `sonnet`). Most sessions don't need the expensive model. This hook
reads every prompt and prints a short [route nudge] when the prompt
looks like it belongs elsewhere:
  - opus   -> strategy, panel, architecture, first-principles work
  - haiku  -> trivial edits (rename, move, typo, one-liner)
  - minimax/cheap -> grunt-work text (extraction, bulk tagging,
                     boilerplate, transcript summaries)

Silent when no confident match. The running model still can't switch
itself, but you (the user) see the nudge and can run `/model ...` or
shell out to a cheaper tool.

Wire into settings.json:
  "UserPromptSubmit": [{
    "matcher": "",
    "hooks": [{
      "type": "command",
      "command": "python3 /absolute/path/to/route-suggest.py"
    }]
  }]
"""
from __future__ import annotations

import json
import re
import sys


def classify(prompt: str) -> str | None:
    p = prompt.lower().strip()
    if len(p) < 2:
        return None

    opus_signals = [
        r"\bpanel\b", r"\bdeconstruct\b", r"\barchitect",
        r"\bstrategy\b", r"\bstrategic\b", r"\bshould (i|we)\b",
        r"\btrade[- ]?off", r"\bprincipl", r"\bpitch\b",
        r"\bnarrative\b", r"\bfirst principles\b",
    ]
    minimax_signals = [
        r"\bextract\b", r"\bbulk tag", r"\bclassif",
        r"\bboilerplate\b", r"\btranscribe\b",
        r"\bsummari[sz]e this\b", r"\breformat\b",
        r"\bconvert to (json|csv|markdown|yaml)\b",
    ]
    haiku_signals = [
        r"^(rename|move|delete|fix typo|typo|add comma|lowercase|uppercase)",
        r"\bone[- ]liner?\b", r"\bquick (fix|rename|edit)\b",
    ]

    def any_hit(patterns):
        return any(re.search(x, p) for x in patterns)

    if any_hit(opus_signals):
        return "opus"
    if any_hit(minimax_signals):
        return "minimax"
    if any_hit(haiku_signals) and len(p) < 120:
        return "haiku"
    return None


def suggestion_text(route: str) -> str:
    if route == "opus":
        return ("[route nudge] Looks like strategy/panel/architecture work. "
                "If this turn needs deep reasoning, run `/model opus` before answering.")
    if route == "haiku":
        return ("[route nudge] Looks trivial. Consider `/model haiku` "
                "to save tokens; re-raise if it gets gnarly.")
    if route == "minimax":
        return ("[route nudge] Looks like grunt-work text. Consider shelling "
                "out to a cheap model (minimax, local, etc.) instead of burning "
                "frontier-model tokens.")
    return ""


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    prompt = payload.get("prompt", "") or ""
    route = classify(prompt)
    if not route:
        sys.exit(0)

    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": suggestion_text(route),
        }
    }
    print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()
