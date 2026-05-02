#!/usr/bin/env python3
"""
Emit the SESSION START context as a JSON hookSpecificOutput payload.

Replaces a previous inline echo '{"hookSpecificOutput":...}' hook command
that triggered a known footgun on zsh: literal parentheses inside the
single-quoted JSON body were re-interpreted as subshell syntax in some
shell-runner contexts, blocking every UserPromptSubmit. Moving the JSON
into a Python script with json.dumps removes the shell-quoting surface
entirely.

Fires once per session via the `once: true` UserPromptSubmit hook.
"""
import json
import sys


CONTEXT = (
    "SESSION START: CLAUDE.md is already auto-loaded in your system prompt "
    "(do NOT re-read it). Read these two files: 1) Meta/Last Session.md "
    "2) Meta/Current Priorities.md.\n\n"
    "ALWAYS-ACTIVE RULES (apply every session, every message, regardless of "
    "work type):\n"
    "- Advisory panel: CLAUDE.md already contains the trigger rule. At ANY "
    "judgment moment, decisions, strategy, crises, trade-offs, client "
    "problems, cash flow, legal, fundraising, read advisory-panel.md and "
    "bring 3-5 voices BEFORE responding. Do not wait to be asked.\n"
    "- Efficiency rules (Meta/rules/efficiency.md): Contains 29+ rules "
    "including panel triggers, model routing, never-fabricate, humanizer, "
    "math and counting rules. Read on first session message.\n\n"
    "CONDITIONAL RULES (read when doing that type of work):\n"
    "- obsidian.md for vault edits\n"
    "- graphify.md for graph questions\n"
    "- tool-routing.md for task routing\n"
    "- meeting-workflow.md for meetings\n\n"
    "SESSION CLOSE: When the user says bye, done, thanks that's all, good "
    "night, ttyl, wrapping up, or equivalent in any language, the "
    "detect-closing-signal.py hook fires automatically and injects the "
    "full cascade with pre-resolved paths. Trust the injected context, "
    "don't re-read separate rule files.\n\n"
    "GRAPH ROUTING: If your vault has a knowledge graph, pick the right "
    "graph for the question scope BEFORE drilling into source files. Use "
    "/graphify query for targeted lookups instead of reading full reports. "
    "The keyword-triggered graph-context-hook.sh (if installed) will fire "
    "a second routing reminder with freshness info."
)


def main() -> int:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": CONTEXT,
        }
    }
    sys.stdout.write(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
