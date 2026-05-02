#!/usr/bin/env python3
"""
Emit the PRE-COMPACT systemMessage as a JSON payload.

Same root cause as session-start-context.py: the original inline
echo '{"continue":true,"systemMessage":"...(by anyone)...(type: discovery)..."}'
contained literal parentheses inside a single-quoted JSON string. When the
hook runner passes the command through certain shell-runner contexts
(notably zsh on some Claude Code versions), those parens get re-interpreted
as subshell syntax and the hook crashes. Moving the JSON content to a
Python script with json.dumps eliminates the shell-quoting surface entirely.
"""
import json
import sys


SYSTEM_MESSAGE = (
    "BEFORE COMPACTING: You are about to lose context. Before compaction "
    "proceeds, update Meta/Last Session.md with: what was done, what is "
    "pending, and any decisions made. VERBATIM RULE: For commitments by "
    "anyone, preserve EXACT words used, not summaries. For key decisions, "
    "keep the original reasoning phrasing. Also preserve file paths and "
    "specific details you will need after compaction. Save any non-obvious "
    "technical discoveries as memory files of type discovery."
)


def main() -> int:
    payload = {
        "continue": True,
        "systemMessage": SYSTEM_MESSAGE,
    }
    sys.stdout.write(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
