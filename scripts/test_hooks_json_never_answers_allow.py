#!/usr/bin/env python3
"""The installed PreToolUse hooks never answer Claude Code's permission prompt.

Claude Code's contract: a PreToolUse hook that prints permissionDecision "allow"
skips the permission prompt; one that makes no decision leaves the normal flow
alone. Our hooks may deny or warn, never answer for the user. Before this test
18 hooks.json commands fell back to an allow, and 8 hook scripts printed one on
every ordinary pass, so a free install quietly stopped Claude Code asking.

What it proves, and what it does not. It runs every command under
hooks.PreToolUse in hooks.json, with [PYTHON] rendered to this interpreter and ~
pointed at a temp HOME that holds the repo's hooks, and fails if one of those runs
prints an allow. The runs are: a benign payload per tool (a Write to notes.txt, an
Edit of it, a Bash ls); the same commands with the hook files ABSENT (the fallback
path); the same commands with each hook file present but UNREADABLE (mode 000);
and, for each hook that used to answer allow on its own pass path, one valid
payload from that hook's scope (section 4). An allow printed on some other payload,
or built outside a hook's own file, is not covered. The respelling removed the `||`
that used to swallow a hook's exit code, so a hook that exits non-zero on a benign
call now shows an error on every call and one that exits 2 would block a benign
write: both are asserted as well.

Mutants and the check that kills each:
  M1  a pass path prints allow                        -> the "present" legs
  M2  a missing-script fallback prints allow          -> the "absent" legs
  M3  a hook exits non-zero or crashes on a benign    -> the exit-code leg
      call now that nothing masks it
  M4  this test can never fail                        -> a planted copy of
      hooks.json (an echoed allow, an allow reachable only when the file is
      absent, an exit 2, a `[ -f X ]` with no `[ -r X ]`) must be reported by the
      matching leg and only by it
  M5  the sandbox runs no real hook (a vacuous green) -> every script a command
      names exists in the "present" HOME, is missing from the "absent" one and
      cannot be read in the "unreadable" one
  M12 an entry drops `[ -r X ]`, so a hook file that exists but cannot be read
      makes Python exit 2, which blocks the call -> the unreadable leg must give
      rc 0 and no decision on every command

Section 3 runs the shipped skill-validator command on every shipped
skills/**/SKILL.md (a Write of its own content) and on planted files:
  M6  a shipped SKILL.md is refused (schema too strict) -> all of them must print
      nothing and exit 0
  M7  extract_frontmatter is LF-only again, so a Windows file is refused on
      every edit -> a CRLF copy of a shipped file must pass
  M8  a PyYAML parse error is a deny again, though Claude Code reads such
      frontmatter -> a planted description with an unquoted ": " must pass
  M9  a deny exits non-zero, which the docs treat as a non-blocking error ->
      the planted denies must exit 0 with the deny on stdout
  M10 the schema branch never runs (PyYAML or jsonschema missing, so every file
      passes vacuously) -> this section FAILS, it never skips, when the hook's
      Python lacks either, and a planted tool_access string must be denied
  M11 the validator stops refusing a broken file -> a planted frontmatter with
      no closing --- must still be denied
It needs PyYAML and jsonschema in this interpreter; scripts/ci.sh and
.github/workflows/lint.yml install them on GitHub Actions.

Section 4 gives each other hook that used to answer allow one valid payload from
its own scope, where the right answer is "no decision", and a control from the
same scope that must still be denied:
  M13 a hook prints allow only on its in-scope pass path (invisible to the benign
      payloads above, which no hook of this kind acts on) -> the pass payload
  M14 a warning carries a permissionDecision again (it used to be an allow whose
      reason was the warning text) -> the warn payload must carry additionalContext
      and no permissionDecision
  M15 the hook's scope drifts, so the pass payload never reaches the hook's logic
      and "no decision" proves nothing -> the control must still be denied

POSIX only (the hook commands are shell one-liners). Plain script, no pytest.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import site
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS_JSON = REPO / "hooks.json"
FAILURES = []
DECISION = '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
CONTINUE = '{"continue":true,"suppressOutput":true}'

# PreToolUse wirings that were already `if [ -f X ]; then ...; else echo ...; fi` and still test `-f` alone,
# so a script that exists but cannot be read makes them exit non-zero. They are not among the 18 commands
# that were respelled, and they are left as they were. They are found by the shape of the command, not by
# hook name, and counted: respelling one means lowering this number, a third one means raising it in
# review, and each must still fail the unreadable leg.
UNREADABLE_GAP_COUNT = 2
OLD_IF_ELSE = re.compile(r"if \[ -f \S+ \]; then .+; else echo ")


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else "  -> " + str(detail)))
    if not cond:
        FAILURES.append(name)


def objects(stdout):
    """Every JSON object printed on stdout, in order."""
    found, decoder, i = [], json.JSONDecoder(), stdout.find("{")
    while 0 <= i < len(stdout):
        try:
            obj, end = decoder.raw_decode(stdout, i)
        except ValueError:
            i = stdout.find("{", i + 1)
            continue
        if isinstance(obj, dict):
            found.append(obj)
        i = stdout.find("{", end)
    return found


def decisions(stdout):
    """Every permission decision stdout carries: hookSpecificOutput.permissionDecision, or the legacy
    top-level decision. An empty list means the hook made no decision."""
    out = []
    for obj in objects(stdout):
        hs = obj.get("hookSpecificOutput")
        if isinstance(hs, dict) and "permissionDecision" in hs:
            out.append(str(hs["permissionDecision"]).lower())
        if "decision" in obj:
            out.append(str(obj["decision"]).lower())
    return out


def context(stdout):
    """The additionalContext text stdout carries, if any."""
    return " ".join(str(o["hookSpecificOutput"]["additionalContext"]) for o in objects(stdout)
                    if isinstance(o.get("hookSpecificOutput"), dict) and "additionalContext" in o["hookSpecificOutput"])


def answers_allow(stdout):
    """True if stdout would make Claude Code skip its prompt: a permissionDecision
    of allow in any spelling (quotes and backslashes tolerated: a miss costs more
    than a false alarm), or the legacy top-level decision approve/allow."""
    if re.search(r"""permissionDecision[\\"']*\s*[:=]\s*[\\"']*allow""", stdout, re.I):
        return True
    return any(d in ("approve", "allow") for d in decisions(stdout))


def in_gap(command):
    """True for a wiring in the known unreadable-file gap: the old if/else shape with no `[ -r X ]`."""
    return bool(OLD_IF_ELSE.match(command)) and "[ -r " not in command


class Sandbox:
    """Three throwaway HOMEs: one holding the repo's hooks, one holding none, one whose hook files cannot be read."""

    def __init__(self, root):
        root = Path(root)
        self.work = root / "work"
        self.work.mkdir()
        (self.work / "notes.txt").write_text("hello\n", encoding="utf-8")
        self.homes = {"present": root / "present", "absent": root / "absent", "unreadable": root / "unreadable"}
        present = self.homes["present"] / ".claude"
        (present / "skills").mkdir(parents=True)
        (present / "skills" / "ai-brain-starter").symlink_to(REPO)
        (present / "hooks").symlink_to(REPO / "hooks")
        (self.homes["absent"] / ".claude").mkdir(parents=True)
        (self.homes["unreadable"] / ".claude").mkdir(parents=True)
        # root, or an account with CAP_DAC_OVERRIDE, reads a mode 000 file, so nothing can be made unreadable to it.
        probe = self.homes["unreadable"] / ".claude" / "probe"
        probe.write_text("x", encoding="utf-8")
        probe.chmod(0)
        self.can_hide = not os.access(str(probe), os.R_OK)
        probe.unlink()
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

    def env(self, scenario):
        home = self.homes[scenario]
        # PYTHONUSERBASE: `pip install --user` packages (PyYAML, jsonschema on a runner) live under
        # the REAL home, and the hook runs under a sandbox HOME.
        return {"PATH": self.path, "HOME": str(home), "USERPROFILE": str(home),
                "CLAUDE_CONFIG_DIR": str(home / ".claude"), "LANG": "C.UTF-8",
                "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUSERBASE": site.getuserbase()}

    def run_payload(self, command, payload, scenario="present"):
        rendered = command.replace("[PYTHON]", shlex.quote(sys.executable))
        try:
            p = subprocess.run(["/bin/sh", "-c", rendered], input=json.dumps(payload),
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               env=self.env(scenario), cwd=str(self.work), timeout=60)
            return (p.returncode, p.stdout, p.stderr)
        except subprocess.TimeoutExpired:
            return (124, "", "timed out")

    def run(self, command, tool, scenario):
        key = (command, tool, scenario)
        if key not in self.cache:
            self.cache[key] = self.run_payload(command, self.payload(tool), scenario)
        return self.cache[key]

    def hide_scripts(self, command):
        """Put a mode 000 stand-in for each script the command names into the unreadable HOME. Returns
        whether the command names any script at all."""
        rels = re.findall(r"~/(\S+?\.(?:py|sh))\b", command)
        for rel in rels:
            stand_in = self.homes["unreadable"] / rel
            if not stand_in.exists():
                stand_in.parent.mkdir(parents=True, exist_ok=True)
                stand_in.write_text("# stand-in: an unreadable hook must never run\n", encoding="utf-8")
                stand_in.chmod(0)
        return bool(rels)

    def unfaithful(self, command, scenario):
        """Scripts the command names whose state does not match the scenario: present, absent or unreadable."""
        named = [self.homes[scenario] / rel for rel in re.findall(r"~/(\S+?\.(?:py|sh))\b", command)]
        if scenario == "unreadable":
            return [p for p in named if not p.exists() or os.access(str(p), os.R_OK)]
        return [p for p in named if p.exists() != (scenario == "present")]


def scan(sb, hooks_json):
    """Run every PreToolUse command in hooks_json on every leg that applies.

    Returns a dict of lists of (scenario, tool, command, detail): `allow` (printed
    an allow), `nonzero` (exit != 0 or a traceback, hook present or absent),
    `unreadable` (the hook file cannot be read and the command did anything but exit
    0 with no output or the pass-through), `unfaithful` (sandbox wrong), plus `legs`
    (how many runs there were, per scenario)."""
    doc = json.loads(Path(hooks_json).read_text(encoding="utf-8"))
    found = {"allow": [], "nonzero": [], "unreadable": [], "unfaithful": [], "legs": {"present": 0, "absent": 0}}
    if sb.can_hide:
        found["legs"]["unreadable"] = 0
    for group in doc["hooks"]["PreToolUse"]:
        matcher = group.get("matcher") or ".*"
        for hook in group["hooks"]:
            command = hook["command"]
            legs = [("present", t) for t in ("Write", "Edit", "Bash") if re.fullmatch(matcher, t)]
            legs.append(("absent", "Bash"))  # no script runs when it is absent: any payload will do
            if sb.can_hide and sb.hide_scripts(command):
                legs.append(("unreadable", "Bash"))  # nor when it cannot be read
            for scenario, tool in legs:
                rc, out, err = sb.run(command, tool, scenario)
                found["legs"][scenario] += 1
                if answers_allow(out):
                    found["allow"].append((scenario, tool, command, out.strip()[:80]))
                if scenario == "unreadable":
                    # All an unreadable hook may leave behind is nothing, or the pass-through some wirings print.
                    if rc != 0 or out.strip() not in ("", CONTINUE):
                        found["unreadable"].append((scenario, tool, command, "rc=%d out=%s %s" % (
                            rc, out.strip()[:40], err.strip()[-80:])))
                elif rc != 0 or "Traceback" in err:
                    found["nonzero"].append((scenario, tool, command, "rc=%d %s" % (rc, err.strip()[-100:])))
                if sb.unfaithful(command, scenario):
                    found["unfaithful"].append((scenario, tool, command, "script presence"))
    return found


def show(items):
    return "%d:\n    %s" % (len(items), "\n    ".join("%s/%s %s  [%s]" % (s, t, c[:100], d) for s, t, c, d in items))


def skill_validator_leg(sb):
    """Section 3: the shipped skill-validator command, on every shipped SKILL.md and on planted files."""
    doc = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    commands = [h["command"] for g in doc["hooks"]["PreToolUse"] for h in g["hooks"]
                if "validate-skill-frontmatter.py" in h["command"]]
    check("hooks.json runs the skill validator once", len(commands) == 1, commands)
    deps = subprocess.run([sys.executable, "-c", "import yaml, jsonschema"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=sb.env("present"))
    check("M10 the hook's Python has PyYAML and jsonschema, so the schema branch runs (this fails, it never skips)",
          deps.returncode == 0, "install them: python3 -m pip install pyyaml jsonschema (" + ([""] + deps.stderr.strip().splitlines())[-1] + ")")
    if len(commands) != 1 or deps.returncode != 0:
        return
    import yaml  # the probe above proved this interpreter has it
    command, planted_dir = commands[0], sb.work / "skills" / "planted"

    def ask(path, text):
        rc, out, _ = sb.run_payload(command, {"session_id": "t", "cwd": str(sb.work), "hook_event_name": "PreToolUse",
                                              "tool_name": "Write", "tool_use_id": "toolu_t",
                                              "tool_input": {"file_path": str(path), "content": text}})
        reason = ""
        if out.strip():
            try:
                hs = json.loads(out)["hookSpecificOutput"]
                reason = hs["permissionDecision"] + ": " + hs.get("permissionDecisionReason", "")
            except (ValueError, KeyError, TypeError):
                reason = "unreadable: " + out.strip()[:100]
        return rc, reason

    # Tracked files, listed by git rather than walked: shipped means committed, and a recursive walk that
    # reads file content is what scripts/check-cloud-safe-file-walkers.py (a gate) refuses.
    listed = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "--", "skills"], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    skills = sorted(REPO / n for n in listed.stdout.split("\0") if n.endswith("/SKILL.md"))
    texts = {p: p.read_text(encoding="utf-8") for p in skills}
    refused = [(p.relative_to(REPO).as_posix(), rc, reason[:150]) for p in skills
               for rc, reason in [ask(p, texts[p])] if rc != 0 or reason]
    check("M6 all %d shipped SKILL.md pass the shipped command: no decision, exit 0" % len(skills),
          bool(skills) and not refused, refused)

    def parses(text):
        m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        try:
            return bool(m) and isinstance(yaml.safe_load(m.group(1)), dict)
        except yaml.YAMLError:
            return False

    sample = next((p for p in skills if parses(texts[p])), None)
    rc, reason = ask(sample, texts[sample].replace("\n", "\r\n")) if sample else (1, "no parseable shipped SKILL.md")
    check("M7 a CRLF copy of a shipped SKILL.md passes: no decision, exit 0", rc == 0 and not reason, (sample, reason[:150]))

    unparseable = "---\nname: planted\ndescription: Use when X: do Y\n---\n\nbody\n"
    try:
        yaml.safe_load("name: planted\ndescription: Use when X: do Y")
        precondition = False
    except yaml.YAMLError:
        precondition = True
    rc, reason = ask(planted_dir / "SKILL.md", unparseable)
    check("M8 a planted description PyYAML cannot parse is not refused", precondition and rc == 0 and not reason,
          (precondition, rc, reason[:150]))

    rc, reason = ask(planted_dir / "SKILL.md", "---\nname: planted\ntool_access: Read\n---\n\nbody\n")
    check("M9/M10 a planted tool_access string is denied by the schema, with exit 0",
          rc == 0 and reason.startswith("deny:") and "tool_access" in reason, (rc, reason[:150]))

    rc, reason = ask(planted_dir / "SKILL.md", "---\nname: planted\n\nbody with no closing delimiter\n")
    check("M11 a planted frontmatter with no closing --- is still denied, with exit 0",
          rc == 0 and reason.startswith("deny:") and "not properly closed" in reason, (rc, reason[:150]))


def in_scope_leg(sb):
    """Section 4: each hook that used to answer allow on its own pass path gets one valid payload from its
    own scope, where the right answer is no decision, and a control from the same scope that must be denied."""
    doc = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    wired = [(g.get("matcher") or ".*", h["command"]) for g in doc["hooks"]["PreToolUse"] for h in g["hooks"]]
    probe = subprocess.run([sys.executable, "-c", "import yaml"], capture_output=True, env=sb.env("present"))
    check("M13 PyYAML is importable, so lint-vault-frontmatter lints instead of skipping (this fails, it never skips)",
          probe.returncode == 0, "install it: python3 -m pip install pyyaml")
    w, scratch = sb.work, sb.work / "scratchpad"
    scratch.mkdir(exist_ok=True)
    (w / "Meta").mkdir(exist_ok=True)  # a vault marker: the handoff guard only denies inside a vault
    aws_key = "AKIA" + "IOSFODNN7EXAMPLE"  # AWS's documented example key, split so no scanner flags this file
    session = "---\ntype: session\nworktree: main\nsession_date: %s\nsession_label: wrap\n---\n\nbody\n"
    agent_a = {"scratchpad_dir": str(scratch), "agent_id": "agent-a"}
    agent_b = {"scratchpad_dir": str(scratch), "agent_id": "agent-b"}

    def write(path, content):
        return {"file_path": str(path), "content": content}

    cases = [
        {"hook": "validate-mcp-json.py", "tool": "Write",
         "pass": write(w / ".mcp.json", '{"mcpServers": {}}\n'),
         "control": write(w / ".mcp.json", '{"mcpServers": ')},
        {"hook": "lint-vault-frontmatter.py", "tool": "Write",
         "pass": write(w / "Sessions" / "2026-04-30-wrap.md", session % "2026-04-30"),
         "control": write(w / "Sessions" / "2026-04-30-wrap.md", session % "April 30 2026")},
        {"hook": "validate-handoff-frontmatter.py", "tool": "Write",
         "pass": write(w / "Handoffs" / "2026-10-15-Handoff.md",
                       "---\ntype: handoff\nconsumes_when: the follow-up ships\n---\n\nbody\n"),
         "control": write(w / "Handoffs" / "2026-10-15-Handoff.md", "---\ntype: handoff\n---\n\nbody\n")},
        {"hook": "block-populated-public-skill.py", "tool": "Write",
         "pass": write(w / "ai-brain-starter" / "skills" / "demo" / "README.md", "---\nfloor: <floor-name>\n---\n\nbody\n"),
         "control": write(w / "ai-brain-starter" / "skills" / "demo" / "README.md", "---\nfloor: Courage\n---\n\nbody\n")},
        {"hook": "block-secret-in-note.py", "tool": "Write",
         "pass": write(w / "note.md", "# Note\n\nNothing secret here.\n"),
         "control": write(w / "note.md", "# Note\n\naws: %s\n" % aws_key)},
        {"hook": "block-scratchpad-cross-agent-clobber.py", "tool": "Write",
         "pass": write(scratch / "report.txt", "x\n"), "extra": agent_a,
         "control": write(scratch / "report.txt", "y\n"), "control_extra": agent_b},
        {"hook": "block-scratchpad-cross-agent-clobber.py", "tool": "Bash",
         "pass": {"command": "echo x > %s" % (scratch / "run.log")}, "extra": agent_a,
         "control": {"command": "echo y > %s" % (scratch / "run.log")}, "control_extra": agent_b},
        {"hook": "warn-chained-state-command-truncated.py", "tool": "Bash",
         "warn": {"command": "git add -A && git push origin main | tail -3"}},
    ]

    def ask(command, case, tool_input, extra):
        payload = {"session_id": "t", "cwd": str(w), "hook_event_name": "PreToolUse", "tool_name": case["tool"],
                   "tool_input": tool_input, "tool_use_id": "toolu_t"}
        payload.update(extra)
        return sb.run_payload(command, payload)

    for case in cases:
        who = "%s on %s" % (case["hook"], case["tool"])
        commands = [c for m, c in wired if case["hook"] in c and re.fullmatch(m, case["tool"])]
        check("%s is wired once" % who, len(commands) == 1, commands)
        for command in commands:
            if "warn" in case:
                rc, out, _ = ask(command, case, case["warn"], {})
                check("M14 %s: a push chained after && through tail warns on additionalContext, with no "
                      "permissionDecision and exit 0" % who,
                      rc == 0 and not decisions(out) and not answers_allow(out) and "git push" in context(out),
                      (rc, out.strip()[:160]))
                continue
            rc, out, _ = ask(command, case, case["pass"], case.get("extra", {}))
            check("M13 %s: a valid in-scope payload makes no decision, exit 0" % who,
                  rc == 0 and not decisions(out) and not answers_allow(out), (rc, out.strip()[:160]))
            rc, out, _ = ask(command, case, case["control"], case.get("control_extra", {}))
            check("M15 %s: the control from the same scope is still denied, exit 0" % who,
                  rc == 0 and decisions(out) == ["deny"], (rc, out.strip()[:160]))


def main():
    if os.name == "nt":
        print("skip: the hook commands are POSIX shell one-liners")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        sb = Sandbox(tmp)

        print("1. the shipped hooks.json")
        real = scan(sb, HOOKS_JSON)
        check("every leg ran: hooks present, absent and unreadable", all(real["legs"].values()), real["legs"])
        check("M5 the sandbox is faithful: scripts exist when present, are missing when absent, cannot be read when unreadable",
              not real["unfaithful"], show(real["unfaithful"]))
        check("M1/M2 no command prints an allow, hook present, absent or unreadable", not real["allow"], show(real["allow"]))
        check("M3 every command exits 0 on every benign payload, hook present or absent",
              not real["nonzero"], show(real["nonzero"]))
        if sb.can_hide:
            gap = [x for x in real["unreadable"] if in_gap(x[2])]
            rest = [x for x in real["unreadable"] if not in_gap(x[2])]
            check("M12 a hook file that exists but cannot be read (mode 000) gives rc 0 and no decision, on every command",
                  not rest, show(rest))
            wired = [h["command"] for g in json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
                     for h in g["hooks"]]
            check("M12 the wirings left out of that rule are the %d known if/else ones, and each still fails it"
                  % UNREADABLE_GAP_COUNT,
                  sorted(c for c in wired if in_gap(c)) == sorted({x[2] for x in gap}) and len({x[2] for x in gap}) == UNREADABLE_GAP_COUNT,
                  (UNREADABLE_GAP_COUNT, sorted({x[2][:70] for x in gap}), sum(in_gap(c) for c in wired)))
        else:
            print("  skip M12: this account can read a mode 000 file (root?), so no file can be made unreadable to it")

        print("2. a planted copy of hooks.json is caught, by the right leg")
        planted = {
            "echo": "echo '%s'" % DECISION,
            # An allow reachable only when the hook file is absent: the shape the 18 fallbacks had.
            "fallback": ("if [ -f ~/.claude/hooks/retry-budget.py ]; then [PYTHON] ~/.claude/hooks/retry-budget.py; "
                         "else echo '%s'; fi" % DECISION),
            "exit2": "[PYTHON] -c 'import sys; sys.exit(2)'",
            # The shape the 18 commands had before `[ -r X ]` was added: a script that exists but cannot be
            # read makes Python exit 2.
            "unreadable": "if [ -f ~/.claude/hooks/retry-budget.py ]; then [PYTHON] ~/.claude/hooks/retry-budget.py; fi",
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
        if sb.can_hide:
            check("M4/M12 a `[ -f X ]` with no `[ -r X ]` is reported on the unreadable leg and nowhere else",
                  by("unreadable", "unreadable") == ["unreadable"] and not by("allow", "unreadable")
                  and not by("nonzero", "unreadable"),
                  (by("unreadable", "unreadable"), by("allow", "unreadable"), by("nonzero", "unreadable")))
        stray = [x for x in bad["allow"] + bad["nonzero"] + bad["unreadable"]
                 if x[2] not in planted.values() and not in_gap(x[2])]
        check("M4 nothing else is reported: the shipped entries stay clean in the planted copy", not stray, show(stray))

        print("3. the skill validator, as wired, on every shipped SKILL.md and on planted files")
        skill_validator_leg(sb)

        print("4. one in-scope payload for each other hook that used to answer allow, with a control that must deny")
        in_scope_leg(sb)

    if FAILURES:
        print("\n%d check(s) failed" % len(FAILURES))
        return 1
    print("\nPASS: no PreToolUse command in hooks.json answers Claude Code's permission prompt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
