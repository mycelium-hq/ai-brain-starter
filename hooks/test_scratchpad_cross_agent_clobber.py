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
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "block-scratchpad-cross-agent-clobber.py"

FAILURES: list[str] = []


def run(payload: dict, env=None) -> tuple[str, str]:
    """Drive the hook as a process. Returns (verdict, message).

    verdict is "allow" / "deny" / "warn" / "silent". The WARN tier speaks a
    different shape from the DENY tier -- additionalContext with no
    permissionDecision, the shape block-git-mutation-mid-operation.py already
    ships on PreToolUse -- so a helper that only ever read permissionDecision
    would KeyError on a warning and report it as a crash.
    """
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True, env=env,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, f"hook must always exit 0, got {r.returncode}: {r.stderr[:200]}"
    if not (r.stdout or "").strip():
        return "silent", ""
    hs = json.loads(r.stdout).get("hookSpecificOutput") or {}
    if "permissionDecision" in hs:
        return hs["permissionDecision"], hs.get("permissionDecisionReason") or ""
    if "additionalContext" in hs:
        return "warn", hs["additionalContext"]
    return "silent", ""


def decide(scratch: Path, agent, *, command=None, file_path=None, tool="Bash", env=None):
    ti = {"command": command} if command is not None else {"file_path": file_path}
    payload = {"scratchpad_dir": str(scratch), "tool_name": tool,
               "cwd": str(scratch.parent), "tool_input": ti}
    if agent:
        payload["agent_id"] = agent
    return run(payload, env=env)[0]


def tmp_decide(cfg: Path, session, *, command=None, file_path=None, tool="Bash",
               agent=None, scratch=None):
    """Drive the bare-/tmp tier. Keyed on session_id, ledger under CLAUDE_CONFIG_DIR.

    CLAUDE_CONFIG_DIR is threaded EXPLICITLY (never ambient) so these controls
    cannot read or write the real ~/.claude ledger.
    """
    ti = {"command": command} if command is not None else {"file_path": file_path}
    payload = {"tool_name": tool, "cwd": "/", "tool_input": ti, "session_id": session}
    if agent:
        payload["agent_id"] = agent
    if scratch:
        payload["scratchpad_dir"] = str(scratch)
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(cfg)}
    env.pop("SCRATCHPAD_CLOBBER_BYPASS", None)
    return run(payload, env=env)


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

    # ==== BARE /tmp TIER (MYC-4822) =========================================
    # The scratchpad is at least per-session. Bare /tmp is shared by EVERY
    # session on the machine, so it is the strictly more dangerous surface and
    # had no guard at all -- only prose, which was violated during the very
    # session that built the scratchpad guard: `/tmp/agent-attr-probe.jsonl`,
    # written here, received a payload from a DIFFERENT live session while this
    # session was reading the file as its own.
    #
    # WARN, never DENY: legitimate /tmp traffic is constant and a deny tier here
    # would teach bypass (rules/over-strict-verification-teaches-bypass.md).
    cfg = tmp / "claude-config"
    cfg.mkdir()
    recap = "/tmp/close-recap-mycelium.md"

    v, msg = tmp_decide(cfg, "sess-AAA", command=f"echo x > {recap}")
    check("17 session A claims a bare /tmp name", v, "allow")

    v, msg = tmp_decide(cfg, "sess-BBB", command=f"echo y > {recap}")
    check("18 session B collides -> WARN (never deny)", v, "warn")
    check("18a warning names the OTHER session", "sess-AAA" in msg, True)
    check("18b steer is the session scratchpad", "scratchpad" in msg.lower(), True)

    check("19 session A rewrites its own /tmp file -> silent",
          tmp_decide(cfg, "sess-AAA", command=f"echo z > {recap}")[0], "allow")

    # A subagent shares its parent's session_id, so it is the SAME owner. The
    # /tmp tier is cross-SESSION; keying it on agent_id would warn on every
    # subagent write of its own session's file.
    check("20 subagent of the owning session -> silent",
          tmp_decide(cfg, "sess-AAA", agent="sub-1", command=f"echo z > {recap}")[0], "allow")

    # --- governed by PROPERTY: a name carrying no disambiguator -------------
    # Never a denylist of known-bad names; the next generic name a script picks
    # must be covered without anyone adding it anywhere.
    for label, path in [
        ("21a mktemp dir", "/tmp/tmp.NvyF0REjpV/notes.md"),
        ("21b mktemp file", "/tmp/close-recap.7hQ2xR9d"),
        ("21c pid suffix", "/tmp/close-recap-mycelium-48213.md"),
        ("21d uuid", "/tmp/probe-2efc3bcd-c516-49ca-8d0c-3eda97bed550.jsonl"),
        ("21e epoch", "/tmp/verify-1758112233.log"),
    ]:
        check(f"{label} claim is silent",
              tmp_decide(cfg, "sess-CCC", command=f"echo a > {path}")[0], "allow")
        check(f"{label} second session still silent",
              tmp_decide(cfg, "sess-DDD", command=f"echo b > {path}")[0], "allow")

    # --- the Write tool is attributed the same way --------------------------
    body = "/tmp/pr-body.md"
    check("22 Write tool claims", tmp_decide(cfg, "sess-EEE", file_path=body, tool="Write")[0], "allow")
    check("23 Write tool cross-session collides",
          tmp_decide(cfg, "sess-FFF", file_path=body, tool="Write")[0], "warn")

    # --- reads and non-/tmp writes are never governed -----------------------
    check("24 a bare /tmp READ is never governed",
          tmp_decide(cfg, "sess-FFF", command=f"cat {recap}")[0], "allow")
    check("25 a write outside /tmp is never governed",
          tmp_decide(cfg, "sess-FFF", command=f"echo x > {tmp}/elsewhere.md")[0], "allow")

    # --- the ledger lives under ~/.claude, NEVER in the surface it governs ---
    check("26 ledger written under CLAUDE_CONFIG_DIR", (cfg / "tmp-owners.json").is_file(), True)
    check("27 no ledger dropped into /tmp", Path("/tmp/tmp-owners.json").exists(), False)

    # --- the scratchpad LIVES under /tmp on macOS ---------------------------
    # realpath($CLAUDE_CODE_TMPDIR | /tmp)/claude-<uid>/<cwd>/<sid>/scratchpad,
    # so a scratchpad path IS a /tmp path. The two tiers must not both fire on
    # it, and the scratchpad must keep DENY -- a downgrade to warn there would
    # be a silent regression of the shipped guard. Needs a REAL directory: the
    # scratchpad ledger is written inside it.
    sp2 = Path(tempfile.mkdtemp(prefix="sp-clobber-tmptier-", dir="/tmp"))
    dual = sp2 / "verify-run.log"
    check("28 scratchpad claim inside the /tmp tree",
          tmp_decide(cfg, "sess-GGG", agent="ag-1", command=f"echo a > {dual}", scratch=sp2)[0], "allow")
    check("29 scratchpad stays DENY, not downgraded to warn",
          tmp_decide(cfg, "sess-GGG", agent="ag-2", command=f"echo b > {dual}", scratch=sp2)[0], "deny")
    shutil.rmtree(sp2, ignore_errors=True)

    shutil.rmtree(tmp, ignore_errors=True)
    if FAILURES:
        print(f"\nFAILED: {len(FAILURES)} case(s): {', '.join(FAILURES)}")
        return 1
    print("\nAll cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
