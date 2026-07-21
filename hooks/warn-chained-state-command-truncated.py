#!/usr/bin/env python3
"""PreToolUse(Bash) warn. One call chains a state-changing command after `&&`
AND pipes the result through `tail`/`head`.

That exact shape hides failure. `&&` short-circuits, so an early step's denial
or error kills the rest of the chain — and `tail -3` then shows only the last
few lines, which are the ERROR text of whichever step died. The agent reads a
plausible-looking tail, infers every earlier step succeeded, and reports the
whole chain as landed. Nothing in the visible output says otherwise.

Warn only, never block: the shape is often legitimate (a long build piped to
`tail` for brevity). The point is to make the agent read the exit status and
re-read the remote instead of trusting the tail. The Stop-side guard
(check-fabricated-verification.py, Detector C) is what actually enforces the
read-of-record before a landed-state claim.

Bypass: CHAINED_STATE_CMD_BYPASS=1.
"""

from __future__ import annotations

import json
import os
import re
import sys

# State-changing commands whose success cannot be inferred from a truncated tail.
STATE_CMD = re.compile(
    r"\bgit\s+commit\b|\bgit\s+push\b|\bgh\s+pr\s+create\b|\bgh\s+pr\s+merge\b"
    r"|\bgh\s+release\s+create\b|\bgit\s+tag\s+-\w*\s*\S|\bgh\s+api\s+.*-X\s*(?:POST|PATCH|PUT|DELETE)",
    re.IGNORECASE,
)
# A truncating filter on the OUTPUT of the pipeline.
TRUNCATE = re.compile(r"\|\s*(?:tail|head)\b", re.IGNORECASE)
# `&&` chaining (not `&` backgrounding, not `||`).
CHAIN = re.compile(r"(?<!&)&&(?!&)")


def main() -> None:
    if os.environ.get("CHAINED_STATE_CMD_BYPASS") == "1":
        sys.exit(0)
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if data.get("tool_name") != "Bash":
        sys.exit(0)
    cmd = ""
    tin = data.get("tool_input")
    if isinstance(tin, dict):
        cmd = str(tin.get("command", ""))
    if not cmd:
        sys.exit(0)

    if not CHAIN.search(cmd) or not TRUNCATE.search(cmd):
        sys.exit(0)

    # The state command must sit in a segment AFTER a `&&` — that is the one
    # whose success gets inferred rather than observed.
    segments = CHAIN.split(cmd)
    if len(segments) < 2:
        sys.exit(0)
    hits = sorted({m.group(0).strip() for seg in segments[1:] for m in STATE_CMD.finditer(seg)})
    if not hits:
        sys.exit(0)

    msg = (
        "This one Bash call chains a state-changing command after `&&` and pipes the result "
        f"through tail/head: {', '.join(hits)}.\n"
        "`&&` short-circuits, so if an earlier step fails or a PreToolUse gate denies it, the "
        "later steps NEVER RUN — and the truncated tail you read will be that failure's error "
        "text, which looks like ordinary output. Do not infer the earlier steps succeeded.\n"
        "Either split the chain into separate calls, or read the full output and then confirm "
        "the end state from the system of record: `git rev-parse origin/<branch>` for a push, "
        "`gh pr view <n> --json headRefOid,state` for a PR. Bypass: CHAINED_STATE_CMD_BYPASS=1."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": msg,
        },
        "systemMessage": msg,
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
