#!/usr/bin/env python3
"""Negative + positive controls for block-scratchpad-cross-agent-clobber.py.

A guard earns trust only by FAILING on the thing it catches. The anchor case is
a real incident (2026-09-17). One session ran 114 subagents across 12+ git
worktrees. Claude Code hands every subagent the SAME `scratchpad_dir` as its
parent -- measured from the live PreToolUse payload: `scratchpad_dir`,
`session_id` and `transcript_path` are all byte-identical parent-to-subagent,
and only `agent_id` differs. There is no per-agent directory anywhere in the
path. So three agents wrote `verify-run.log` and two wrote `fix-commit-msg.txt`
into ONE directory. Ground truth of the damage: a commit message was read back
carrying a DIFFERENT PR's content, and a verify log reported a TypeScript error
from a file in a different checkout. A sibling's green reads exactly like yours.

Cases 1-6   the clobber and its variants (the guard must DENY).
Cases 7-13  self-rewrites, reads, off-scratchpad writes, bypass (must ALLOW).
Case 14     the shell-variable form, which slipped past the FIRST production run
            of this guard and is therefore the regression that matters most.

Drives the hook as a PROCESS over stdin/stdout -- the pure decision core passing
does not prove the wiring does.

Stdlib only. Exit 0 = all pass.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "block-scratchpad-cross-agent-clobber.py"

FAILURES: list[str] = []


def decide(scratch: Path, agent, *, command=None, file_path=None, tool="Bash", env=None):
    ti = {"command": command} if command is not None else {"file_path": file_path}
    payload = {"scratchpad_dir": str(scratch), "tool_name": tool,
               "cwd": str(scratch.parent), "tool_input": ti}
    if agent:
        payload["agent_id"] = agent
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True, env=env,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, f"hook must always exit 0, got {r.returncode}: {r.stderr[:200]}"
    return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"]


def check(label, got, want):
    if got == want:
        print(f"  [PASS] {label}")
    else:
        print(f"  [FAIL] {label}: got {got}, want {want}")
        FAILURES.append(label)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="sp-clobber-test-"))
    s = tmp / "scratchpad"
    s.mkdir()
    log = s / "verify-run.log"
    msg = s / "commit-msg.txt"

    # --- the guard must FIRE -------------------------------------------------
    check("1 agent A claims verify-run.log", decide(s, "AAA", command=f"npm run verify > {log}"), "allow")
    check("2 agent B truncating clobber", decide(s, "BBB", command=f"npm run verify > {log}"), "deny")
    check("3 agent B appending clobber", decide(s, "BBB", command=f"echo x >> {log}"), "deny")
    check("4 agent B via tee", decide(s, "BBB", command=f"npm run verify | tee {log}"), "deny")
    check("5 Write tool claim then clobber",
          decide(s, "CCC", file_path=str(msg), tool="Write"), "allow")
    check("6 Write tool foreign clobber",
          decide(s, "DDD", file_path=str(msg), tool="Write"), "deny")

    # --- the guard must STAY SILENT -----------------------------------------
    check("7 agent A self-rewrite (retry loop)", decide(s, "AAA", command=f"npm run verify > {log}"), "allow")
    check("8 agent A self-append", decide(s, "AAA", command=f"echo more >> {log}"), "allow")
    check("9 foreign READ is never blocked", decide(s, "BBB", command=f"cat {log}"), "allow")
    check("10 write outside the scratchpad", decide(s, "BBB", command=f"echo x > {tmp}/other.log"), "allow")
    check("11 /dev/null is never claimed", decide(s, "BBB", command="echo x > /dev/null"), "allow")
    check("12 unrelated command", decide(s, "BBB", command="git status --porcelain"), "allow")
    check("13 inline bypass is honored",
          decide(s, "BBB", command=f"SCRATCHPAD_CLOBBER_BYPASS=1 npm run verify > {log}"), "allow")

    # --- 14. REGRESSION: the form that slipped past the first production run --
    vlog = "vars-run.log"
    pre = f"SP={s}"
    check("14a shell-var claim", decide(s, "FFF", command=f"{pre}; echo a > $SP/{vlog}"), "allow")
    check("14b shell-var clobber", decide(s, "GGG", command=f"{pre}; echo b > $SP/{vlog}"), "deny")
    check("14c braced shell-var clobber", decide(s, "GGG", command=f'{pre}; echo b > "${{SP}}/{vlog}"'), "deny")
    check("14d shell-var self-rewrite", decide(s, "FFF", command=f"{pre}; echo c > $SP/{vlog}"), "allow")

    # --- the parent session is an owner exactly like any subagent ------------
    pf = s / "parent-notes.md"
    check("15 main session claims", decide(s, None, command=f"echo x > {pf}"), "allow")
    check("16 subagent clobbers main", decide(s, "EEE", command=f"echo y > {pf}"), "deny")

    shutil.rmtree(tmp, ignore_errors=True)
    if FAILURES:
        print(f"\nFAILED: {len(FAILURES)} case(s): {', '.join(FAILURES)}")
        return 1
    print("\nAll cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
