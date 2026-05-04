#!/usr/bin/env python3
"""Hookify rule regression harness (template).

Pipes test payloads into the hookify PreToolUse hook and asserts each rule
either fires or stays silent as expected. Catches three classes of bug:

  1. Rule references a non-existent operator (e.g. regex_not_match) →
     condition silently always False → rule never fires.
  2. YAML parse errors from unquoted patterns → rule dropped at load time.
  3. Pattern logic regressions after a rule edit.

USAGE
  1. Copy this file to your vault under scripts/ or ~/.claude/scripts/.
  2. Set VAULT_ROOT below to your vault's absolute path.
  3. Set HOOKIFY_PRETOOLUSE_PATH to the path of the hookify pretooluse.py
     hook (the one your settings.json invokes).
  4. Edit TESTS to cover your rules. Each entry is:
        (rule_name, tool_type, file_path, content, expect_fire, label)
     `rule_name` is the `name:` field from the rule's frontmatter. The harness
     greps the hook's stdout for that string to decide whether the rule fired.
  5. Run: `python3 hookify-rule-tests.py` from the vault root.
     Exit 0 = all pass. Exit 1 = at least one failure.

DESIGN NOTES
- Tests run in a subprocess so the hook sees a clean environment, including
  CWD. The harness sets cwd=VAULT_ROOT because hookify's load_rules() uses a
  relative glob `.claude/hookify.*.local.md`.
- Triggering strings inside content can self-trigger the rule under test.
  When that happens, write the content via Path.write_text() to a temp file
  and reference it indirectly, OR base64-encode the trigger and decode at
  send time. Both approaches are fine; the included example uses plain text
  for clarity.
- The harness does NOT modify the rule files. It only sends synthetic
  tool_input payloads to the hook.

EXIT CODES
  0: all tests pass
  1: one or more failures (details printed)
  2: configuration error (wrong VAULT_ROOT or missing hookify hook)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────
# Edit these two paths for your environment.

VAULT_ROOT = Path(os.environ.get("VAULT_ROOT", Path.home() / "vault"))
HOOKIFY_PRETOOLUSE_PATH = Path(
    os.environ.get(
        "HOOKIFY_PRETOOLUSE_PATH",
        Path.home()
        / ".claude"
        / "plugins"
        / "local"
        / "hookify-plugin"
        / "hooks"
        / "pretooluse.py",
    )
)


# ── Test definitions ──────────────────────────────────────────────────────────
# Each test: (rule_name, tool_type, file_path, content, expect_fire, label)
#
# rule_name: the `name:` field from your hookify rule's frontmatter
# tool_type: "Write" | "Edit" | "MultiEdit" | "Bash"
# file_path: absolute path the synthetic write would target
# content:   for Write/Edit, the content the tool would write
# expect_fire: True if the rule should fire on this input, False if it should stay silent
# label:     short description shown in test output

# Example test list. Replace with tests for your own rules.
TESTS: list[tuple[str, str, str, str, bool, str]] = [
    # voice-no-exclamation should fire on exclamation mark in prose
    (
        "warn-exclamation-marks",
        "Write",
        str(VAULT_ROOT / "Notes" / "draft.md"),
        "This is great content! Ready to ship.",
        True,
        "exclamation in prose: fires",
    ),
    # voice-no-exclamation should NOT fire when content has no exclamation
    (
        "warn-exclamation-marks",
        "Write",
        str(VAULT_ROOT / "Notes" / "draft.md"),
        "This is great content. Ready to ship.",
        False,
        "no exclamation: silent",
    ),
    # no-duplicate-h1 should fire on `# Title` at start of content
    # (the rule's pattern `^# .+` is anchored to string start, not line start)
    (
        "no-duplicate-h1",
        "Write",
        str(VAULT_ROOT / "Notes" / "draft.md"),
        "# Duplicate Title\n\nBody.",
        True,
        "H1 at content start: fires",
    ),
    # no-duplicate-h1 should NOT fire when content starts with H2
    (
        "no-duplicate-h1",
        "Write",
        str(VAULT_ROOT / "Notes" / "draft.md"),
        "## Section\n\nBody.",
        False,
        "H2 only: silent",
    ),
]


# ── Harness ────────────────────────────────────────────────────────────────────
def run_test(
    rule_name: str,
    tool_type: str,
    file_path: str,
    content: str,
    expect_fire: bool,
    label: str,
) -> tuple[bool, str]:
    """Run one test. Returns (passed, message)."""
    if tool_type in ("Write",):
        tool_input = {"file_path": file_path, "content": content}
    elif tool_type in ("Edit",):
        # Edit uses old_string/new_string; we put content in new_string
        tool_input = {"file_path": file_path, "old_string": "", "new_string": content}
    elif tool_type in ("MultiEdit",):
        tool_input = {
            "file_path": file_path,
            "edits": [{"old_string": "", "new_string": content}],
        }
    elif tool_type == "Bash":
        tool_input = {"command": content}
    else:
        return False, f"unknown tool_type: {tool_type}"

    payload = {"tool_name": tool_type, "tool_input": tool_input}

    try:
        proc = subprocess.run(
            ["python3", str(HOOKIFY_PRETOOLUSE_PATH)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=str(VAULT_ROOT),
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return False, f"hook timed out after 10s"
    except FileNotFoundError:
        return False, f"hookify hook not found at {HOOKIFY_PRETOOLUSE_PATH}"

    fired = rule_name in proc.stdout
    passed = fired == expect_fire

    if passed:
        return True, ""
    if expect_fire:
        return False, (
            f"expected fire, got silence. stdout: {proc.stdout[:200]!r} "
            f"stderr: {proc.stderr[:200]!r}"
        )
    return False, f"expected silence, got fire. stdout: {proc.stdout[:200]!r}"


def main() -> int:
    # Sanity checks
    if not VAULT_ROOT.exists():
        print(f"❌ VAULT_ROOT does not exist: {VAULT_ROOT}", file=sys.stderr)
        print(
            "   Set VAULT_ROOT env var or edit the constant at the top of this file.",
            file=sys.stderr,
        )
        return 2
    if not HOOKIFY_PRETOOLUSE_PATH.exists():
        print(
            f"❌ Hookify pretooluse hook not found: {HOOKIFY_PRETOOLUSE_PATH}",
            file=sys.stderr,
        )
        print(
            "   Set HOOKIFY_PRETOOLUSE_PATH env var or edit the constant.",
            file=sys.stderr,
        )
        return 2

    print(f"Testing {len(TESTS)} hookify rule cases against {HOOKIFY_PRETOOLUSE_PATH}")
    print(f"CWD: {VAULT_ROOT}\n")

    passed = 0
    failed = 0
    for rule_name, tool_type, file_path, content, expect_fire, label in TESTS:
        ok, msg = run_test(rule_name, tool_type, file_path, content, expect_fire, label)
        marker = "✓" if ok else "✗"
        print(f"  {marker} [{rule_name}] {label}")
        if not ok:
            print(f"      {msg}")
            failed += 1
        else:
            passed += 1

    print(f"\n{passed}/{len(TESTS)} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
