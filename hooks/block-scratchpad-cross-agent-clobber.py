#!/usr/bin/env python3
"""PreToolUse guard: stop one agent overwriting ANOTHER agent's file in the
shared session scratchpad.

WHY (measured 2026-09-17, from the live PreToolUse payload + the CLI's own bundle)
  Claude Code hands every subagent the SAME `scratchpad_dir` as its parent.
  Measured: a subagent's `scratchpad_dir` is byte-identical to the parent's;
  `session_id` and `transcript_path` are identical too. Only `agent_id` differs.

  Path shape, recovered from the CLI's embedded JS bundle (symbols qmt -> Pae ->
  G1n -> ZBo; cache key `scratchpadDirBySessionId`):

      realpath($CLAUDE_CODE_TMPDIR | /tmp) / claude-<uid>
        / dashEncode(originalCwd) / <sessionId> / scratchpad

  There is NO agent component anywhere in that path. So N concurrent subagents
  share ONE directory, and two of them writing `verify-run.log` or
  `commit-msg.txt` silently clobber each other. The reader then gets a FOREIGN
  file that is byte-indistinguishable from its own: a sibling's green reads
  exactly like yours.

  Observed on this machine: one session with 114 subagents had `verify-run.log`
  written by 3 agents across 3 different worktrees and `fix-commit-msg.txt` by 2.
  A commit message was taken from the wrong PR; a verify log reported a
  TypeScript error from a file in a different checkout.

SCOPE -- the name is a claim about coverage, so state it exactly:
  SEEN:    Write / Edit / MultiEdit `file_path` (unambiguous), and Bash writes via
           the unambiguous operators `> path`, `>> path`, `tee [-a] path`.
           A shell variable assigned in the SAME command (`SP=/x; echo y > $SP/f`)
           IS expanded -- that form slipped past the first production run.
  NOT SEEN: a write smuggled through a script, python open(), cp/mv, an editor,
           or a path built from the environment / a previous Bash call. Deleting
           <scratchpad>/.owners.json also resets ownership. This guard NARROWS an
           ACCIDENTAL collision between cooperating agents; it is not anti-tamper
           and does not eliminate the hazard.

  Ownership is first-writer-wins, per session, recorded in
  <scratchpad>/.owners.json. Self-rewrites (same agent, same path) are ALWAYS
  allowed -- retry loops and commit-msg iterations must not be blocked, or the
  gate teaches bypass (see rules/over-strict-verification-teaches-bypass.md).

Contract: stdin JSON; stdout hookSpecificOutput.permissionDecision; exit 0 always.
Fails OPEN on every error -- a guard that breaks the session is worse than the bug.

Bypass: SCRATCHPAD_CLOBBER_BYPASS=1 (exported OR inline `VAR=1 <cmd>`).
Self-test: `python3 block-scratchpad-cross-agent-clobber.py --selftest`
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from _lib.cmd_env import inline_bypass
except Exception:                                    # pragma: no cover - fail open
    def inline_bypass(command, var, value="1"):
        return False
try:
    from _lib.guard_telemetry import log_fire
except Exception:                                    # pragma: no cover - fail open
    def log_fire(*a, **k):
        pass

BYPASS = "SCRATCHPAD_CLOBBER_BYPASS"
LEDGER = ".owners.json"
NAME = "block-scratchpad-cross-agent-clobber"

# `> p`, `>> p`, `1> p`, `tee p`, `tee -a p`. Quoted or bare.
_REDIR = re.compile(
    r"""(?:\d?>>?|\btee\b(?:\s+-a\b)?)\s*(?:"([^"]+)"|'([^']+)'|([^\s;|&<>()]+))"""
)

# `SP=/x/y` / `SP="/x/y"` assigned in the SAME command string. Shell state does not
# persist between Bash tool calls, so a same-command assignment is the realistic
# case -- and it was the FIRST thing to slip past this guard in production.
_ASSIGN = re.compile(
    r"""(?:^|[;&|\n]\s*)([A-Za-z_][A-Za-z0-9_]*)=(?:"([^"]*)"|'([^']*)'|([^\s;|&]*))"""
)


def _var_map(command: str) -> dict:
    out = {}
    for mo in _ASSIGN.finditer(command or ""):
        val = next((g for g in mo.groups()[1:] if g), None)
        if val:
            out[mo.group(1)] = val
    return out


def _expand(path: str, vars_: dict) -> str:
    """Substitute $VAR / ${VAR}. Longest name first so $SP beats $S."""
    if not vars_ or "$" not in path:
        return path
    keys = sorted(vars_, key=len, reverse=True)
    prev = None
    for _ in range(5):                                # bounded: nested vars
        if path == prev:
            break
        prev = path
        for k in keys:
            path = path.replace("${%s}" % k, vars_[k]).replace("$" + k, vars_[k])
    return path


def _emit(decision: str, reason: str | None = None) -> None:
    out = {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": decision}}
    if reason:
        out["hookSpecificOutput"]["permissionDecisionReason"] = reason
    print(json.dumps(out))
    sys.exit(0)


def allow() -> None:
    _emit("allow")


def deny(reason: str) -> None:
    _emit("deny", reason)


def bash_write_targets(command: str) -> list[str]:
    """Paths a Bash command unambiguously WRITES. Read-only forms are not returned."""
    vars_ = _var_map(command)
    out = []
    for m in _REDIR.finditer(command or ""):
        p = m.group(1) or m.group(2) or m.group(3)
        if not p or p.startswith("&") or p == "/dev/null":
            continue
        p = _expand(p, vars_)
        if p != "/dev/null":
            out.append(p)
    return out


def tool_write_targets(tool_name: str, ti: dict) -> list[str]:
    if tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        fp = ti.get("file_path") or ti.get("filePath") or ti.get("notebook_path")
        return [fp] if fp else []
    if tool_name == "Bash":
        return bash_write_targets(ti.get("command") or "")
    return []


def _read_ledger(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _claim(ledger_path: Path, rel: str, me: str, agent_type: str) -> str | None:
    """Return the CURRENT owner of `rel`, claiming it for `me` when unowned.

    Locked so two concurrent agents cannot both see 'unowned'. On any lock
    failure we return None (fail open) rather than risk a false deny.
    """
    lock = ledger_path.with_suffix(".lock")
    fd = None
    for _ in range(25):                               # ~250ms ceiling, hot path
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            # Reap a stale lock from an agent that died mid-claim.
            try:
                if time.time() - lock.stat().st_mtime > 5:
                    lock.unlink()
                    continue
            except Exception:
                pass
            time.sleep(0.01)
        except Exception:
            return None
    if fd is None:
        return None
    try:
        data = _read_ledger(ledger_path)
        rec = data.get(rel)
        if rec:
            return rec.get("owner")
        data[rel] = {"owner": me, "agent_type": agent_type, "ts": int(time.time())}
        tmp = ledger_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=0), encoding="utf-8")
        os.replace(str(tmp), str(ledger_path))
        return None
    except Exception:
        return None
    finally:
        try:
            os.close(fd)
            lock.unlink()
        except Exception:
            pass


def suggest(rel: str, me: str) -> str:
    p = Path(rel)
    return str(p.with_name(f"{p.stem}.{me[:8]}{p.suffix}"))


def evaluate(payload: dict) -> tuple[str, str | None]:
    """Pure decision core. Returns (decision, reason). Used by --selftest."""
    scratch = payload.get("scratchpad_dir")
    if not scratch:
        return "allow", None

    tool_name = payload.get("tool_name") or payload.get("toolName") or ""
    ti = payload.get("tool_input") or payload.get("toolInput") or {}
    command = ti.get("command") or ""

    if os.environ.get(BYPASS) == "1" or inline_bypass(command, BYPASS):
        return "allow", None

    targets = tool_write_targets(tool_name, ti)
    if not targets:
        return "allow", None

    sdir = Path(scratch).resolve()
    me = payload.get("agent_id") or "main"
    agent_type = payload.get("agent_type") or "session"
    ledger_path = sdir / LEDGER

    for t in targets:
        try:
            tp = Path(t)
            if not tp.is_absolute():
                tp = Path(payload.get("cwd") or ".") / tp
            tp = tp.resolve()
            rel = str(tp.relative_to(sdir))
        except Exception:
            continue                                   # not in the scratchpad
        if rel == LEDGER or rel.startswith(".owners"):
            continue
        owner = _claim(ledger_path, rel, me, agent_type)
        if owner is None or owner == me:
            continue
        return "deny", (
            f"SCRATCHPAD CLOBBER: `{rel}` in this session's scratchpad was created by a "
            f"DIFFERENT agent (owner={owner}, you={me}).\n"
            f"Every subagent shares ONE scratchpad_dir -- there is no per-agent directory -- "
            f"so this write would silently destroy that agent's file, and whoever reads it "
            f"next gets your content believing it is theirs.\n"
            f"Write to a name of your own instead, e.g.:\n"
            f"    {sdir / suggest(rel, me)}\n"
            f"If you genuinely mean to overwrite another agent's file, re-run with "
            f"{BYPASS}=1 prefixed."
        )
    return "allow", None


def _selftest() -> int:
    """Negative + positive controls. A guard earns trust by FAILING on the thing
    it catches, so prove both directions before shipping."""
    import shutil, tempfile
    tmp = Path(tempfile.mkdtemp(prefix="sp-guard-selftest-"))
    sdir = tmp / "scratchpad"
    sdir.mkdir()
    ok = True

    def payload(agent, cmd=None, fp=None, tool="Bash"):
        p = {"scratchpad_dir": str(sdir), "tool_name": tool, "cwd": str(tmp),
             "tool_input": {"command": cmd} if cmd else {"file_path": fp}}
        if agent:
            p["agent_id"] = agent
        return p

    def check(label, got, want):
        nonlocal ok
        hit = got == want
        ok = ok and hit
        print(f"  [{'PASS' if hit else 'FAIL'}] {label}: got {got}, want {want}")

    log = f"{sdir}/verify-run.log"
    # 1. first writer claims -> allowed
    check("agent A first write", evaluate(payload("AAA", f"npm run verify > {log}"))[0], "allow")
    # 2. NEGATIVE CONTROL: a different agent must be DENIED
    check("agent B clobber (must deny)", evaluate(payload("BBB", f"npm run verify > {log}"))[0], "deny")
    # 3. POSITIVE CONTROL: same agent re-writing its own file must be ALLOWED
    check("agent A self-rewrite", evaluate(payload("AAA", f"npm run verify > {log}"))[0], "allow")
    # 4. append by a foreign agent is corruption too
    check("agent B append (must deny)", evaluate(payload("BBB", f"echo x >> {log}"))[0], "deny")
    # 5. reads are never blocked
    check("agent B read", evaluate(payload("BBB", f"cat {log}"))[0], "allow")
    # 6. Write tool is attributed the same way
    wf = f"{sdir}/commit-msg.txt"
    check("Write tool, agent C claims", evaluate(payload("CCC", fp=wf, tool="Write"))[0], "allow")
    check("Write tool, agent D clobber (must deny)", evaluate(payload("DDD", fp=wf, tool="Write"))[0], "deny")
    # 7. paths outside the scratchpad are none of our business
    check("outside scratchpad", evaluate(payload("BBB", f"echo x > {tmp}/elsewhere.log"))[0], "allow")
    # 8. inline bypass must actually reach the command string
    check("inline bypass", evaluate(payload("BBB", f"{BYPASS}=1 npm run verify > {log}"))[0], "allow")
    # 9. /dev/null is never a claimable target
    check("/dev/null never claimed", evaluate(payload("BBB", "echo x > /dev/null"))[0], "allow")
    # 10. the PARENT session (no agent_id) owns files exactly like any subagent
    mf = f"{sdir}/parent-notes.md"
    check("main session claims", evaluate(payload(None, f"echo x > {mf}"))[0], "allow")
    check("subagent clobbers main (must deny)", evaluate(payload("EEE", f"echo y > {mf}"))[0], "deny")

    # 11. REGRESSION: the shell-variable form that slipped past the live run
    vlog = "vars-run.log"
    pre = f"SP={sdir}"
    check("var form claims", evaluate(payload("FFF", f"{pre}; echo a > $SP/{vlog}"))[0], "allow")
    check("var form clobber (must deny)",
          evaluate(payload("GGG", f"{pre}; echo b > $SP/{vlog}"))[0], "deny")
    check("braced var form clobber (must deny)",
          evaluate(payload("GGG", f'{pre}; echo b > "${{SP}}/{vlog}"'))[0], "deny")
    check("var form self-rewrite", evaluate(payload("FFF", f"{pre}; echo c > $SP/{vlog}"))[0], "allow")

    shutil.rmtree(tmp, ignore_errors=True)
    print("SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> None:
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()
        return
    try:
        decision, reason = evaluate(payload)
    except Exception:
        allow()                                        # fail OPEN, always
        return
    if decision == "deny":
        try:
            log_fire(NAME, status="blocked", agent=payload.get("agent_id") or "main")
        except Exception:
            pass
        deny(reason or "scratchpad clobber")
    allow()


if __name__ == "__main__":
    main()
