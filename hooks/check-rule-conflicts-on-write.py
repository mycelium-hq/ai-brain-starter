#!/usr/bin/env python3
"""
check-rule-conflicts-on-write.py — PostToolUse hook that runs the conflict
detector after Edit/Write to codified-rule paths.

Engram-inspired (github.com/Gentleman-Programming/engram). The full
detector lives at ⚙️ Meta/scripts/check-rule-conflicts.py. This hook
wraps it so conflicts auto-surface on every codified-rule edit, without
requiring the user to remember to run --scan-all.

Why PostToolUse, not PreToolUse:
- The detector compares the just-written file against the existing
  corpus. PreToolUse runs BEFORE the write, so the new content isn't
  on disk yet (it's in tool_input, but the detector reads from disk
  to handle frontmatter parsing, multiline content, etc.).
- PostToolUse runs after the write lands. If conflicts surface, the
  user gets a systemMessage and can decide to revert or keep.
- The detector is fast (<1s for keyword-anchor); the hook timeout
  (10s default) is comfortable.

Output: standard hook JSON. systemMessage carries any conflicts
detected. Always exits 0 — never blocks operations on hook errors.
"""

import json
import os
import re
import subprocess
import sys


CODIFIED_RULE_PATTERNS = (
    r"CLAUDE\.md$",
    r"⚙️ Meta/rules/.*\.md$",
    r"⚙️ Meta/Build Standards\.md$",
    r"⚙️ Meta/MCP Build Runbook\.md$",
    r"⚙️ Meta/Critical Failure Inventory\.md$",
    r"/memory/feedback_.*\.md$",
    r"/memory/discovery_.*\.md$",
    r"/memory/project_.*\.md$",
    r"/memory/reference_.*\.md$",
)


def is_codified_rule_path(file_path: str) -> bool:
    if not file_path:
        return False
    for pattern in CODIFIED_RULE_PATTERNS:
        if re.search(pattern, file_path):
            return True
    return False


def find_vault_root(file_path: str) -> str:
    """Walk up from the edited file to find the vault root (contains CLAUDE.md)."""
    if not file_path:
        return ""
    cur = os.path.dirname(os.path.abspath(file_path))
    while cur and cur != "/":
        if os.path.exists(os.path.join(cur, "CLAUDE.md")) and os.path.exists(os.path.join(cur, "⚙️ Meta")):
            return cur
        cur = os.path.dirname(cur)
    return ""


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({}))
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name not in ("Write", "Edit", "MultiEdit"):
        print(json.dumps({}))
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not is_codified_rule_path(file_path):
        print(json.dumps({}))
        sys.exit(0)

    vault_root = find_vault_root(file_path)
    if not vault_root:
        print(json.dumps({}))
        sys.exit(0)

    detector = os.path.join(vault_root, "⚙️ Meta", "scripts", "check-rule-conflicts.py")
    if not os.path.exists(detector):
        print(json.dumps({}))
        sys.exit(0)

    # Run keyword-anchor mode against the just-written file.
    # Skip semantic mode here (would add latency + cost on every edit);
    # semantic runs at session-close --scan-all instead.
    try:
        env = dict(os.environ)
        env["VAULT_ROOT"] = vault_root
        result = subprocess.run(
            ["python3", detector, file_path, "--json"],
            capture_output=True,
            text=True,
            timeout=8,
            env=env,
        )
    except (subprocess.TimeoutExpired, OSError):
        print(json.dumps({}))
        sys.exit(0)

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(json.dumps({}))
        sys.exit(0)

    keyword_count = payload.get("keyword_conflict_count", 0)
    if keyword_count == 0:
        print(json.dumps({}))
        sys.exit(0)

    # Build a Matuschak/Jackie-style question for each conflict
    conflicts = payload.get("keyword_conflicts", [])
    msgs = []
    for c in conflicts[:3]:  # Cap at 3 to avoid notification overflow
        new_loc = f"{os.path.basename(c['new']['file'])}:{c['new']['line_no']}"
        old_loc = f"{os.path.basename(c['existing']['file'])}:{c['existing']['line_no']}"
        new_quote = c['new']['line_text'][:150]
        old_quote = c['existing']['line_text'][:150]
        conf = c['confidence']
        msgs.append(
            f"You wrote in `{new_loc}`: \"{new_quote}\". "
            f"You wrote earlier in `{old_loc}`: \"{old_quote}\". "
            f"(confidence {conf:.2f}) Did you mean to revise the earlier rule?"
        )

    extra = ""
    if len(conflicts) > 3:
        extra = f"\n\n+{len(conflicts) - 3} more candidate conflicts. Run `python3 \"{detector}\" --scan-all` for full report."

    system_message = (
        f"**[rule-conflict detector]** {keyword_count} candidate conflict(s) "
        f"in `{os.path.basename(file_path)}`:\n\n"
        + "\n\n".join(msgs)
        + extra
    )

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": system_message,
        },
        "systemMessage": system_message,
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
