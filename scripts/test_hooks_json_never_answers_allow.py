#!/usr/bin/env python3
"""The installed PreToolUse hooks never answer Claude Code's permission prompt.

Claude Code's contract: a PreToolUse hook that prints permissionDecision "allow"
skips the permission prompt; one that prints nothing leaves the normal flow
alone. Our hooks may deny or warn, never answer for the user. Before this test
18 hooks.json commands fell back to an allow, and 8 hook scripts printed one on
every ordinary pass, so a free install quietly stopped Claude Code asking.

What it runs: every command under hooks.PreToolUse in hooks.json, with
[PYTHON] rendered to this interpreter and ~ pointed at a temp HOME that holds the
repo's hooks, against one benign payload per tool (a Write to notes.txt, an Edit
of it, a Bash ls). Then the same commands again with the hook files ABSENT, which
is the fallback path. The respelling removed the `||` that used to swallow a
hook's exit code, so a hook that exits non-zero on a benign call now shows an
error on every call and one that exits 2 would block a benign write: both are
asserted as well.

Mutants and the check that kills each:
  M1  a pass path prints allow                        -> the "present" legs
  M2  a missing-script fallback prints allow          -> the "absent" legs
  M3  a hook exits non-zero or crashes on a benign    -> the exit-code leg
      call now that nothing masks it
  M4  this test can never fail                        -> a planted copy of
      hooks.json (an echoed allow, an allow reachable only when the file is
      absent, an exit 2) must be reported by the matching leg and only by it
  M5  the sandbox runs no real hook (a vacuous green) -> every script a command
      names exists in the "present" HOME and is missing from the "absent" one

POSIX only (the hook commands are shell one-liners). Plain script, no pytest.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS_JSON = REPO / "hooks.json"
FAILURES = []
DECISION = '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else "  -> " + str(detail)))
    if not cond:
        FAILURES.append(name)


def answers_allow(stdout):
    """True if stdout would make Claude Code skip its prompt: a permissionDecision
    of allow in any spelling (quotes and backslashes tolerated: a miss costs more
    than a false alarm), or the legacy top-level decision approve/allow."""
    if re.search(r"""permissionDecision[\\"']*\s*[:=]\s*[\\"']*allow""", stdout, re.I):
        return True
    decoder, i = json.JSONDecoder(), stdout.find("{")
    while 0 <= i < len(stdout):
        try:
            obj, end = decoder.raw_decode(stdout, i)
        except ValueError:
            i = stdout.find("{", i + 1)
            continue
        if isinstance(obj, dict) and str(obj.get("decision", "")).lower() in ("approve", "allow"):
            return True
        i = stdout.find("{", end)
    return False


class Sandbox:
    """Two throwaway HOMEs: one holding the repo's hooks, one holding none."""

    def __init__(self, root):
        root = Path(root)
        self.work = root / "work"
        self.work.mkdir()
        (self.work / "notes.txt").write_text("hello\n", encoding="utf-8")
        self.homes = {"present": root / "present", "absent": root / "absent"}
        present = self.homes["present"] / ".claude"
        (present / "skills").mkdir(parents=True)
        (present / "skills" / "ai-brain-starter").symlink_to(REPO)
        (present / "hooks").symlink_to(REPO / "hooks")
        (self.homes["absent"] / ".claude").mkdir(parents=True)
        # A working python3 first on PATH, so a machine whose python3 is a shim that
        # refuses script files cannot change what a hook that shells out to it does.
        (root / "bin").mkdir()
        (root / "bin" / "python3").symlink_to(sys.executable)
        self.path = str(root / "bin") + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin")
        self.cache = {}

    def payload(self, tool):
        notes = str(self.work / "notes.txt")
        tool_input = {"Write": {"file_path": notes, "content": "hello\n"},
                      "Edit": {"file_path": notes, "old_string": "hello", "new_string": "world"},
                      "Bash": {"command": "ls"}}[tool]
        return {"session_id": "t", "cwd": str(self.work), "hook_event_name": "PreToolUse",
                "tool_name": tool, "tool_input": tool_input, "tool_use_id": "toolu_t"}

    def run(self, command, tool, scenario):
        key = (command, tool, scenario)
        if key not in self.cache:
            home = self.homes[scenario]
            env = {"PATH": self.path, "HOME": str(home), "USERPROFILE": str(home),
                   "CLAUDE_CONFIG_DIR": str(home / ".claude"), "LANG": "C.UTF-8",
                   "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
            rendered = command.replace("[PYTHON]", shlex.quote(sys.executable))
            try:
                p = subprocess.run(["/bin/sh", "-c", rendered], input=json.dumps(self.payload(tool)),
                                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   env=env, cwd=str(self.work), timeout=60)
                self.cache[key] = (p.returncode, p.stdout, p.stderr)
            except subprocess.TimeoutExpired:
                self.cache[key] = (124, "", "timed out")
        return self.cache[key]

    def unfaithful(self, command, scenario):
        """Scripts the command names whose presence does not match the scenario."""
        named = [self.homes[scenario] / rel for rel in re.findall(r"~/(\S+?\.(?:py|sh))\b", command)]
        return [p for p in named if p.exists() != (scenario == "present")]


def scan(sb, hooks_json):
    """Run every PreToolUse command in hooks_json on every leg that applies.

    Returns a dict of lists of (scenario, tool, command, detail): `allow` (printed
    an allow), `nonzero` (exit != 0 or a traceback), `unfaithful` (sandbox wrong),
    plus `legs` (how many runs there were, per scenario)."""
    doc = json.loads(Path(hooks_json).read_text(encoding="utf-8"))
    found = {"allow": [], "nonzero": [], "unfaithful": [], "legs": {"present": 0, "absent": 0}}
    for group in doc["hooks"]["PreToolUse"]:
        matcher = group.get("matcher") or ".*"
        for hook in group["hooks"]:
            command = hook["command"]
            legs = [("present", t) for t in ("Write", "Edit", "Bash") if re.fullmatch(matcher, t)]
            legs.append(("absent", "Bash"))  # no script runs when it is absent: any payload will do
            for scenario, tool in legs:
                rc, out, err = sb.run(command, tool, scenario)
                found["legs"][scenario] += 1
                if answers_allow(out):
                    found["allow"].append((scenario, tool, command, out.strip()[:80]))
                if rc != 0 or "Traceback" in err:
                    found["nonzero"].append((scenario, tool, command, "rc=%d %s" % (rc, err.strip()[-100:])))
                if sb.unfaithful(command, scenario):
                    found["unfaithful"].append((scenario, tool, command, "script presence"))
    return found


def show(items):
    return "%d:\n    %s" % (len(items), "\n    ".join("%s/%s %s  [%s]" % (s, t, c[:100], d) for s, t, c, d in items))


def main():
    if os.name == "nt":
        print("skip: the hook commands are POSIX shell one-liners")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        sb = Sandbox(tmp)

        print("1. the shipped hooks.json")
        real = scan(sb, HOOKS_JSON)
        check("both legs ran: hooks present and hooks absent", all(real["legs"].values()), real["legs"])
        check("M5 the sandbox is faithful: scripts exist when present, are missing when absent",
              not real["unfaithful"], show(real["unfaithful"]))
        check("M1/M2 no command prints an allow, hook present or absent", not real["allow"], show(real["allow"]))
        check("M3 every command exits 0 on every benign payload, hook present or absent",
              not real["nonzero"], show(real["nonzero"]))

        print("2. a planted copy of hooks.json is caught, by the right leg")
        planted = {
            "echo": "echo '%s'" % DECISION,
            # An allow reachable only when the hook file is absent: the shape the 18 fallbacks had.
            "fallback": ("if [ -f ~/.claude/hooks/retry-budget.py ]; then [PYTHON] ~/.claude/hooks/retry-budget.py; "
                         "else echo '%s'; fi" % DECISION),
            "exit2": "[PYTHON] -c 'import sys; sys.exit(2)'",
        }
        doc = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
        next(g for g in doc["hooks"]["PreToolUse"] if g.get("matcher") == "Bash")["hooks"].extend(
            {"type": "command", "command": c} for c in planted.values())
        copy = Path(tmp) / "planted-hooks.json"
        copy.write_text(json.dumps(doc), encoding="utf-8")
        bad = scan(sb, copy)

        def by(kind, key):
            return sorted({s for s, _, c, _ in bad[kind] if c == planted[key]})

        check("M4 an echoed allow is reported on both legs", by("allow", "echo") == ["absent", "present"], by("allow", "echo"))
        check("M4 an allow reachable only when the file is absent is reported on the absent leg only",
              by("allow", "fallback") == ["absent"], by("allow", "fallback"))
        check("M4 an exit 2 on a benign payload is reported", bool(by("nonzero", "exit2")), by("nonzero", "exit2"))
        check("M4 nothing else is reported: the shipped entries stay clean in the planted copy",
              all(c in planted.values() for _, _, c, _ in bad["allow"] + bad["nonzero"]),
              show([x for x in bad["allow"] + bad["nonzero"] if x[2] not in planted.values()]))

    if FAILURES:
        print("\n%d check(s) failed" % len(FAILURES))
        return 1
    print("\nPASS: no PreToolUse command in hooks.json answers Claude Code's permission prompt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
