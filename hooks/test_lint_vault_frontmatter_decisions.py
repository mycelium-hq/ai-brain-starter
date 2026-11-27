#!/usr/bin/env python3
"""lint-vault-frontmatter must lint only direct children of Decisions/ as decisions.

detect_type() used to return "decision" for any path with a "Decisions" part,
so a note in a subfolder (for example Decisions/Analyses/x.md, a worked analysis
with its own `type:`) was held to the decision schema and its write was denied.
Nothing else in the kit treats those files as decisions: vault-schema-validator.py
and aggregate-decisions.py both read Decisions/*.md only. The hook was the one
place that disagreed, and it is the one that blocks writes.

Covered:
  1. detect_type: Decisions/x.md -> "decision"
  2. detect_type: Decisions/<sub>/x.md -> None
  3. detect_type: Sessions/x.md and journal paths keep their types
  4. end to end: a top-level decision with an unclosed '---' is still denied
  5. end to end: the same content in a Decisions subfolder is not denied
  6. end to end: a subfolder note with its own type is not denied

Cases 4 to 6 stop before the PyYAML import, so they run without PyYAML.

Run: python3 hooks/test_lint_vault_frontmatter_decisions.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "lint-vault-frontmatter.py"


def load_hook():
    spec = importlib.util.spec_from_file_location("lint_vault_frontmatter", HOOK)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def run_hook(file_path: str, content: str) -> str:
    payload = {"tool_name": "Write", "tool_input": {"file_path": file_path, "content": content}}
    env = dict(os.environ)
    env.pop("VAULT_LINT_BYPASS", None)
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert r.returncode == 0, f"hook exited {r.returncode}: {r.stderr}"
    return r.stdout.strip()


def is_deny(out: str) -> bool:
    if not out:
        return False
    data = json.loads(out)
    return data.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def main() -> int:
    failures = []

    def check(name: str, ok: bool) -> None:
        print(("PASS " if ok else "FAIL ") + name)
        if not ok:
            failures.append(name)

    mod = load_hook()
    with tempfile.TemporaryDirectory() as tmp:
        meta = Path(tmp) / "Meta"
        top = str(meta / "Decisions" / "2026-01-01-choice.md")
        sub = str(meta / "Decisions" / "Analyses" / "2026-01-01-analysis.md")
        session = str(meta / "Sessions" / "2026-01-01T10-00-main.md")
        journal = str(Path(tmp) / "Journals" / "2026-01-01.md")

        check("1 top-level decision is a decision", mod.detect_type(top) == "decision")
        check("2 decision subfolder is not a decision", mod.detect_type(sub) is None)
        check("3a session keeps its type", mod.detect_type(session) == "session")
        check("3b journal keeps its type", mod.detect_type(journal) == "journal")

        unclosed = "---\ntype: decision\nnever closed\n"
        check("4 unclosed frontmatter at top level is denied", is_deny(run_hook(top, unclosed)))
        check("5 same content in a subfolder is not denied", not is_deny(run_hook(sub, unclosed)))

        own_type = "---\ntype: analysis\ndate: 2026-01-01\n---\n\nBody.\n"
        check("6 subfolder note with its own type is not denied", not is_deny(run_hook(sub, own_type)))

    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
