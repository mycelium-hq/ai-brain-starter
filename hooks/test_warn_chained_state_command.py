#!/usr/bin/env python3
"""Controls for warn-chained-state-command-truncated.py.

Fires on the exact shape that hid the incident: a state-changing command
chained after `&&` in one Bash call whose output is piped through tail/head.
Warn-only, so the assertion is on the presence of the advisory message, and on
the decision NEVER being a deny.

Stdlib only. Exit 0 = all pass.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "warn-chained-state-command-truncated.py")

PASS = 0
FAIL = 0


def run(command: str, tool_name: str = "Bash", env=None):
    payload = json.dumps({"tool_name": tool_name, "tool_input": {"command": command}})
    proc = subprocess.run([sys.executable, HOOK], input=payload,
                          capture_output=True, text=True, env=env)
    out = (proc.stdout or "").strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def expect_warn(label: str, command: str):
    global PASS, FAIL
    d = run(command)
    if not d:
        FAIL += 1
        print(f"FAIL  {label} :: no warning emitted")
        return
    decision = d.get("hookSpecificOutput", {}).get("permissionDecision")
    if decision != "allow":
        FAIL += 1
        print(f"FAIL  {label} :: warn hook must never deny (got {decision!r})")
        return
    PASS += 1
    print(f"PASS  {label}")


def expect_silent(label: str, command: str, tool_name: str = "Bash"):
    global PASS, FAIL
    d = run(command, tool_name=tool_name)
    if d:
        FAIL += 1
        print(f"FAIL  {label} :: false positive")
        return
    PASS += 1
    print(f"PASS  {label}")


# --- THE INCIDENT SHAPE ------------------------------------------------------
expect_warn(
    "1. the incident: add && commit && push && gh pr create | tail -3",
    "git add src/ && git commit -m 'fix' && git push origin br "
    "&& gh pr create --title x --body y | tail -3",
)
expect_warn(
    "2. push after && piped to tail",
    "npm test && git push origin main | tail -5",
)
expect_warn(
    "3. gh pr merge after && piped to head",
    "gh pr checks 144 && gh pr merge 144 --squash | head -2",
)
expect_warn(
    "4. gh release create after && piped to tail",
    "npm run build && gh release create v1.2.3 | tail -1",
)

# --- MUST NOT FIRE -----------------------------------------------------------
expect_silent(
    "5. chained push with NO truncation (full output visible)",
    "npm test && git push origin main",
)
expect_silent(
    "6. truncation but NO chaining (single command)",
    "git log --oneline | tail -20",
)
expect_silent(
    "7. state command FIRST, nothing inferred after it",
    "git push origin main | tail -3",
)
expect_silent(
    "8. read-only chain piped to tail",
    "git fetch && git log --oneline | tail -5",
)
expect_silent(
    "9. non-Bash tool",
    "git add . && git push origin main | tail -3",
    tool_name="Read",
)

# --- BYPASS ------------------------------------------------------------------
_env = dict(os.environ, CHAINED_STATE_CMD_BYPASS="1")
if run("git add . && git push origin br && gh pr create | tail -3", env=_env):
    FAIL += 1
    print("FAIL  10. CHAINED_STATE_CMD_BYPASS=1 :: still warned")
else:
    PASS += 1
    print("PASS  10. CHAINED_STATE_CMD_BYPASS=1 disables the warn")

print()
print(f"=== summary: {PASS} passed, {FAIL} failed ===")
sys.exit(1 if FAIL else 0)
