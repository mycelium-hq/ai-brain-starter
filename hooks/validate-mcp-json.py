#!/usr/bin/env python3
"""PreToolUse hook that blocks Write/Edit on .mcp.json if the result fails json.loads.

Catches a silent-fail bug: Claude Code quietly drops malformed .mcp.json files,
which disables every MCP registered inside. A single misplaced brace and the
entire MCP stack goes dark with no error surfaced.

Hook contract (Claude Code PreToolUse):
  stdin: JSON with tool_name, tool_input
  stdout: JSON with hookSpecificOutput.permissionDecision = "allow" | "deny"
  exit 0 always (decision conveyed in JSON, not exit code)

Acts only on Write and Edit tools targeting paths ending in .mcp.json. Everything
else is approved without comment.

For Edit, re-reads the file and applies the substitution to validate the final
shape. Write is the common case and is handled fully.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path


def allow():
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }))
    sys.exit(0)


def deny(reason: str):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()
        return

    tool_name = payload.get("tool_name") or payload.get("toolName") or ""
    tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
    file_path = tool_input.get("file_path") or tool_input.get("filePath") or ""

    if not file_path.endswith(".mcp.json"):
        allow()
        return

    if tool_name == "Write":
        content = tool_input.get("content", "")
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            deny(
                f"Write to {file_path} would create malformed JSON: "
                f"{e.msg} at line {e.lineno} col {e.colno}. "
                f"Claude Code silently drops invalid .mcp.json files, which would "
                f"disable every MCP registered inside. "
                f"Validate with `python3 -c \"import json; json.loads(open('{file_path}').read())\"` before saving."
            )
            return
        allow()
        return

    if tool_name == "Edit":
        old_s = tool_input.get("old_string", "")
        new_s = tool_input.get("new_string", "")
        try:
            original = Path(file_path).read_text(encoding="utf-8")
            if tool_input.get("replace_all"):
                result = original.replace(old_s, new_s)
            else:
                if original.count(old_s) != 1:
                    allow()
                    return
                result = original.replace(old_s, new_s, 1)
            try:
                json.loads(result)
            except json.JSONDecodeError as e:
                deny(
                    f"Edit to {file_path} would produce malformed JSON: "
                    f"{e.msg} at line {e.lineno} col {e.colno}."
                )
                return
        except Exception:
            allow()
            return
        allow()
        return

    allow()


if __name__ == "__main__":
    main()
