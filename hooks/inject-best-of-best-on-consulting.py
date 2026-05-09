#!/usr/bin/env python3
"""
UserPromptSubmit hook: when consulting/pricing/packaging keywords appear in
the user's prompt, inject the "best of the best" lockout rule as
additionalContext BEFORE the assistant responds.

Use case: founders/operators who don't want capacity-gated decision trees
("Option A vs B based on Q3 capacity", "depending on your bandwidth")
when they ask about pricing, scoping, or packaging their work. The pattern
is: they want a pick + execute synthesis, not a menu they have to choose
from.

Pattern: vault-context.py. UserPromptSubmit → check prompt → optionally
inject additionalContext → exit 0 always (never block).

Bypass: prompt contains "BOB_BYPASS=1" or "ignore best-of-best".

Register in ~/.claude/settings.json under hooks.UserPromptSubmit:
    {
      "type": "command",
      "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/inject-best-of-best-on-consulting.py"
    }
"""
import json
import re
import sys

KEYWORDS = [
    r"\bconsulting\b",
    r"\bpricing\b",
    r"\bprice\b",
    r"\bpackage\b",
    r"\bpackaging\b",
    r"\btier\b",
    r"\btiering\b",
    r"\boffer\b",
    r"\boffering\b",
    r"\bsprint\b",
    r"\bscope\b",
    r"\bscoping\b",
    r"\bdeliverable\b",
    r"\bfee\b",
    r"\brate\b",
    r"\bretainer\b",
    r"\bproposal\b",
]

BYPASS_TOKENS = ["BOB_BYPASS=1", "ignore best-of-best"]

LOCKOUT_BLOCK = """[best-of-best lockout — auto-injected]
Consulting/pricing/packaging context detected. The "best of the best"
rule is in force:

- Cost, build time, calendar time, effort, install complexity are
  EXPLICITLY OUT OF FRAME. Never named, not even as caveat.
- Banned closes: "Option A vs B", "two paths", "either works",
  "want me to do X or Y?", "based on your Q3 capacity",
  "depending on sequencing", any capacity-gated decision tree.
- Pick + execute. ONE clarifying question allowed if an operational
  fact is missing. Synthesis ends with the pick, not the user's decision.
- Legitimate blockers only: technical infeasibility, security/safety,
  ethics, codified-rule conflict, external-party dependency.
  NOT capacity. NOT "later."

If you're drafting "Option A" / "two paths" / "capacity" /
"sequencing" / "Q3" / "based on your bandwidth" / "let me know
if you want" — stop, pick, ship."""


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    prompt = payload.get("prompt", "") or ""

    for token in BYPASS_TOKENS:
        if token in prompt:
            sys.exit(0)

    p = prompt.lower()
    if not any(re.search(kw, p) for kw in KEYWORDS):
        sys.exit(0)

    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": LOCKOUT_BLOCK,
        }
    }
    print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()
