#!/usr/bin/env python3
"""Controls for retry-budget.py: the budget counts ATTEMPTS, an attempt is one
Bash call, and a call is keyed on its WHOLE command.

The hook exists to stop an agent looping on a failing command: the 4th identical
Bash command inside 30 minutes is blocked (exit 2, reason on stderr). Two
defects made it block work that was not a loop, both measured on live sessions:

1. FINGERPRINT TRUNCATION. Commands were keyed as md5(normalized[:400]). An md5
   digest is fixed-size whatever it hashes, so the cap bought nothing and merged
   distinct commands whose first difference fell past character 400. Agent
   commands routinely open with a ~230-character absolute scratch path, so three
   DIFFERENT steps of one builder shared a budget and its fourth distinct step
   was refused as a loop (first difference measured at character 466).

2. DOUBLE COUNTING. A machine running a second hook installer had this script
   registered TWICE under PreToolUse/Bash: this repo's `[ -f X ] && X || true`
   form, and the other installer's exit-preserving if/else form. Every
   registration appended a timestamp, so each Bash call counted twice and the
   3rd call was blocked instead of the 4th. The `|| true` copy could never block
   at all: `||` rewrites exit 2 into 0, so on an install carrying only that copy
   the guard was decorative.

The fixes under test: hash the whole normalized command; count each call once,
keyed on its tool_use_id (every registration of one call sees the same id, and
a later one reuses the first one's verdict); wire hooks.json in the
exit-preserving if/else form.

Drives the hook as a PROCESS over stdin, the way the harness does, and drives
the REGISTERED hooks.json command through `sh -c`, because the wrapper is where
defect 2's block went missing. Every leg runs in a private HOME and TMPDIR, so
no leg can read or write a real session's budget. Stdlib only, no pytest.
Exit 0 = all pass.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
HOOK = HERE / "retry-budget.py"
HOOKS_JSON = REPO / "hooks.json"
INSTALLER = REPO / "scripts" / "install-hooks-user-level.py"

SESSION = "retry-budget-test-session"
POSIX = os.name == "posix"
BLOCK_TEXT = "BLOCKED by retry-budget hook"

# The registration a second installer writes for this same script: the
# exit-preserving if/else form, allowing on an absent script. Only the
# interpreter is swapped for this process's own, so the leg is hermetic.
SECOND_INSTALLER_FORM = (
    "if [ -f ~/.claude/hooks/retry-budget.py ]; then {py} ~/.claude/hooks/retry-budget.py; "
    "else echo '{{\"hookSpecificOutput\":{{\"hookEventName\":\"PreToolUse\","
    "\"permissionDecision\":\"allow\"}}}}'; fi"
)
# The form hooks.json shipped before the fix; every existing install still has it.
OLD_TEMPLATE_FORM = (
    "[ -f ~/.claude/hooks/retry-budget.py ] && {py} ~/.claude/hooks/retry-budget.py || true"
)

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok    {name}")
    else:
        FAILURES.append(name)
        print(f"  FAIL  {name}" + (f"\n        {detail}" if detail else ""))


def skip(name: str, why: str) -> None:
    print(f"  skip  {name} ({why})")


class Sandbox:
    """A private HOME + TMPDIR. The hook keeps its state under
    tempfile.gettempdir(), which honors TMPDIR, so every leg is isolated."""

    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="retry-budget-test-"))
        self.home = self.root / "home"
        self.tmp = self.root / "tmp"
        self.home.mkdir()
        self.tmp.mkdir()
        env = {k: v for k, v in os.environ.items()
               if k not in ("RETRY_BUDGET_BYPASS", "CLAUDE_SESSION_ID", "VAULT_ROOT")}
        env.update(HOME=str(self.home), USERPROFILE=str(self.home),
                   TMPDIR=str(self.tmp), TEMP=str(self.tmp), TMP=str(self.tmp),
                   ABS_POSIX_PYTHON=sys.executable)
        self.env = env
        self.state_path = self.tmp / f"claude-retry-budget-{SESSION}.json"

    def state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def histories(self) -> dict:
        """fingerprint -> attempt timestamps. Anything else in the file is bookkeeping."""
        return {k: v for k, v in self.state().items() if isinstance(v, list)}

    def attempts(self) -> int:
        return sum(len(v) for v in self.histories().values())

    def deploy_hook(self) -> None:
        """Put the hook where the registered commands look for it."""
        dst = self.home / ".claude" / "hooks"
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HOOK, dst / HOOK.name)

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def payload(command: str, call_id: str | None) -> str:
    p = {"session_id": SESSION, "hook_event_name": "PreToolUse",
         "tool_name": "Bash", "tool_input": {"command": command}}
    if call_id is not None:
        p["tool_use_id"] = call_id
    return json.dumps(p)


def run_hook(sb: Sandbox, command: str, call_id: str | None) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(HOOK)], input=payload(command, call_id),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=sb.env, timeout=60)
    return r.returncode, r.stderr


def run_registered(sb: Sandbox, registration: str, command: str,
                   call_id: str) -> tuple[int, str, str]:
    """Run one settings.json registration the way the harness does: via a shell."""
    r = subprocess.run(["sh", "-c", registration], input=payload(command, call_id),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=sb.env, timeout=60)
    return r.returncode, r.stdout, r.stderr


def bash_registrations(settings: dict) -> list[str]:
    """Every PreToolUse registration of retry-budget.py that fires for Bash."""
    out = []
    for group in (settings.get("hooks") or {}).get("PreToolUse", []) or []:
        matcher = group.get("matcher") or ""
        if matcher not in ("Bash", "*", ""):
            try:
                if not re.fullmatch(matcher, "Bash"):
                    continue
            except re.error:
                continue
        for h in group.get("hooks", []) or []:
            cmd = h.get("command", "")
            if "retry-budget.py" in cmd:
                out.append(cmd)
    return out


def rendered_template() -> dict:
    """hooks.json with [PYTHON] bound to this interpreter, as the installer binds it."""
    return json.loads(HOOKS_JSON.read_text(encoding="utf-8").replace("[PYTHON]", sys.executable))


def run_installer(sb: Sandbox, settings: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(INSTALLER), "--settings", str(settings),
         "--hooks-source", str(HOOKS_JSON), "--quiet"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=sb.env, timeout=600)


def long_prefix(length: int) -> str:
    """A command head shaped like the ones that tripped the cap: a long absolute
    scratch path. No repeated whitespace, so normalizing it is a no-op and
    `length` is exactly where the first differing character lands."""
    head = ("bash /private/tmp/claude-501/-Users-example-projects-example-vault/"
            "00000000-0000-4000-8000-000000000000/scratchpad/")
    s = (head + "step-runner-" * 250)[:length]
    assert len(s) == length and " ".join(s.split()) == s and not s.endswith(" ")
    return s


# ---------------------------------------------------------------- defect 1 ---

def leg_fingerprint_covers_whole_command() -> None:
    # 400: the first character past the old cap. 466: the measured incident.
    # 2000: a difference deep in a long command.
    for at in (400, 466, 2000):
        sb = Sandbox()
        try:
            prefix = long_prefix(at)
            a, b = prefix + "alpha", prefix + "bravo"
            assert a[:at] == b[:at] and a[at] != b[at]
            run_hook(sb, a, f"toolu_a_{at}")
            run_hook(sb, b, f"toolu_b_{at}")
            h = sb.histories()
            check(f"A1 two commands first differing at char {at} get distinct fingerprints",
                  len(h) == 2 and sorted(len(v) for v in h.values()) == [1, 1],
                  f"attempts per fingerprint: {sorted(len(v) for v in h.values())}")
        finally:
            sb.cleanup()


def leg_poll_loop_with_changing_tail_is_not_a_loop() -> None:
    sb = Sandbox()
    try:
        prefix = long_prefix(466)
        codes = [run_hook(sb, f"{prefix}/poll.sh --attempt {i}", f"toolu_poll_{i}")[0]
                 for i in range(1, 6)]
        check("A2 five polls sharing a 466-char head, each with its own tail, are never blocked",
              codes == [0, 0, 0, 0, 0], f"exit codes {codes}")
    finally:
        sb.cleanup()


def leg_whitespace_variants_still_share_a_budget() -> None:
    # Normalization is kept on purpose: re-running the same command with its
    # spacing reflowed is still the same attempt.
    sb = Sandbox()
    try:
        variants = ["git push origin main --dry-run", "git  push origin main --dry-run",
                    "git push  origin   main --dry-run", "\tgit push origin main --dry-run\n"]
        codes = [run_hook(sb, v, f"toolu_ws_{i}")[0] for i, v in enumerate(variants)]
        check("A3 whitespace-only variants of one command share one budget (4th blocks)",
              codes == [0, 0, 0, 2], f"exit codes {codes}")
    finally:
        sb.cleanup()


# ---------------------------------------------------------------- defect 2 ---

def leg_one_call_is_one_attempt_sequential() -> None:
    sb = Sandbox()
    try:
        c1 = run_hook(sb, "pytest -x tests/test_example.py", "toolu_dup")[0]
        c2 = run_hook(sb, "pytest -x tests/test_example.py", "toolu_dup")[0]
        check("B1 two registrations of ONE call (same tool_use_id) add exactly one timestamp",
              sb.attempts() == 1 and (c1, c2) == (0, 0),
              f"timestamps={sb.attempts()} exit codes={(c1, c2)}")
    finally:
        sb.cleanup()


def leg_one_call_is_one_attempt_concurrent() -> None:
    name = "B2 registrations of one call racing in parallel still add exactly one timestamp"
    if not POSIX:
        skip(name, "the parallel leg is exercised on the POSIX runner")
        return
    sb = Sandbox()
    rounds = 8
    try:
        for rnd in range(rounds):
            data = payload(f"make -C build target-{rnd}", f"toolu_par_{rnd}")
            procs = [subprocess.Popen([sys.executable, str(HOOK)], stdin=subprocess.PIPE,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      env=sb.env, text=True) for _ in range(2)]
            for p in procs:
                p.stdin.write(data)
                p.stdin.close()
            for p in procs:
                p.wait(timeout=60)
        check(name, sb.attempts() == rounds,
              f"{rounds} calls, {sb.attempts()} timestamps")
    finally:
        sb.cleanup()


def leg_duplicate_registration_reuses_the_verdict() -> None:
    # A copy that runs second must return the SAME verdict as the copy that
    # counted, or a neutered copy running first could swallow the block.
    sb = Sandbox()
    try:
        per_call = []
        for i in range(1, 5):
            cid = f"toolu_pair_{i}"
            per_call.append((run_hook(sb, "npm run build --workspace api", cid)[0],
                             run_hook(sb, "npm run build --workspace api", cid)[0]))
        check("B3 each call answered identically by both registrations; only the 4th blocks",
              per_call == [(0, 0), (0, 0), (0, 0), (2, 2)] and sb.attempts() == 4,
              f"exit codes per call {per_call}, timestamps={sb.attempts()}")
    finally:
        sb.cleanup()


def leg_no_call_id_counts_every_invocation() -> None:
    # Negative control for B1: the dedupe keys on the id, it does not merely
    # drop every second invocation. A harness that sends no id keeps the old
    # count-each-invocation behaviour.
    sb = Sandbox()
    try:
        run_hook(sb, "pytest -x tests/test_example.py", None)
        run_hook(sb, "pytest -x tests/test_example.py", None)
        check("B4 without a tool_use_id every invocation still counts",
              sb.attempts() == 2, f"timestamps={sb.attempts()}")
    finally:
        sb.cleanup()


# ------------------------------------------------------ the block still fires ---

def leg_identical_command_blocks_on_fourth_call() -> None:
    sb = Sandbox()
    try:
        results = [run_hook(sb, "git push origin main --dry-run", f"toolu_same_{i}")
                   for i in range(1, 5)]
        codes = [c for c, _ in results]
        check("C1 a truly identical command still blocks on its 4th call",
              codes == [0, 0, 0, 2] and BLOCK_TEXT in results[-1][1]
              and "4 times" in results[-1][1],
              f"exit codes {codes}; last stderr {results[-1][1][:160]!r}")
    finally:
        sb.cleanup()


def leg_template_registration_preserves_the_block() -> None:
    name = "C2 the hooks.json registration carries the 4th-call block through its wrapper"
    if not POSIX:
        skip(name, "hooks.json commands are POSIX shell; Windows rewrites them")
        return
    regs = bash_registrations(rendered_template())
    check("C2 hooks.json registers retry-budget.py exactly once for Bash",
          len(regs) == 1, f"found {len(regs)}: {regs}")
    if len(regs) != 1:
        return
    check("C2 the registration has no `||` to rewrite exit 2 into an allow",
          "||" not in regs[0], regs[0])
    sb = Sandbox()
    try:
        sb.deploy_hook()
        codes = [run_registered(sb, regs[0], "git push origin main --dry-run",
                                f"toolu_tpl_{i}")[0] for i in range(1, 5)]
        check(name, codes == [0, 0, 0, 2], f"exit codes {codes}")
    finally:
        sb.cleanup()


def leg_template_registration_absent_script_is_neutral() -> None:
    name = "C3 with the script absent the registration exits 0 and makes no permission decision"
    if not POSIX:
        skip(name, "hooks.json commands are POSIX shell; Windows rewrites them")
        return
    regs = bash_registrations(rendered_template())
    if len(regs) != 1:
        check(name, False, f"expected one registration, found {len(regs)}")
        return
    sb = Sandbox()
    try:
        code, out, _ = run_registered(sb, regs[0], "git push origin main --dry-run", "toolu_absent")
        check(name, code == 0 and "permissionDecision" not in out,
              f"exit {code}, stdout {out[:160]!r}")
    finally:
        sb.cleanup()


def leg_state_write_does_not_follow_a_planted_link() -> None:
    name = "C4 the state write replaces a pre-planted link instead of writing through it"
    if not POSIX:
        skip(name, "creating a symlink needs privileges on Windows")
        return
    sb = Sandbox()
    try:
        sentinel = sb.root / "sentinel.txt"
        sentinel.write_text("do not overwrite\n", encoding="utf-8")
        os.symlink(sentinel, sb.state_path)
        run_hook(sb, "echo planted-link-probe-command", "toolu_link")
        check(name, sentinel.read_text(encoding="utf-8") == "do not overwrite\n"
              and not sb.state_path.is_symlink(),
              f"sentinel now {sentinel.read_text(encoding='utf-8')[:80]!r}, "
              f"state path is_symlink={sb.state_path.is_symlink()}")
    finally:
        sb.cleanup()


# ------------------------------------------- both installers on one machine ---

def leg_both_installers_one_attempt_per_call() -> None:
    name = "D1 with both installers' registrations live, one call adds one timestamp"
    if not POSIX:
        skip(name, "hooks.json commands are POSIX shell; Windows rewrites them")
        return
    sb = Sandbox()
    try:
        settings = sb.home / ".claude" / "settings.json"
        r = run_installer(sb, settings)
        check("D1 installer succeeds in a sandbox HOME", r.returncode == 0,
              f"exit {r.returncode}: {(r.stderr or r.stdout)[-400:]}")
        if r.returncode != 0:
            return
        data = json.loads(settings.read_text(encoding="utf-8"))
        # The second installer re-adds its own registration on every compile.
        group = next(g for g in data["hooks"]["PreToolUse"] if g.get("matcher") == "Bash")
        group["hooks"].append({"type": "command",
                               "command": SECOND_INSTALLER_FORM.format(py=sys.executable)})
        regs = bash_registrations(data)
        check("D1 premise: two registrations of the script are live", len(regs) == 2,
              f"found {len(regs)}")
        cmd = "git push origin main --dry-run"
        per_call = []
        for i in range(1, 5):
            per_call.append([run_registered(sb, reg, cmd, f"toolu_both_{i}")[0] for reg in regs])
            if i == 1:
                check(name, sb.attempts() == 1, f"timestamps after one call={sb.attempts()}")
        check("D1 calls 1-3 pass and every registration blocks the 4th",
              per_call == [[0, 0], [0, 0], [0, 0], [2, 2]] and sb.attempts() == 4,
              f"exit codes per call {per_call}, timestamps={sb.attempts()}")
    finally:
        sb.cleanup()


def leg_existing_install_upgrades_to_one_blocking_registration() -> None:
    name = "D2 an install carrying the old `|| true` form upgrades to one blocking registration"
    if not POSIX:
        skip(name, "hooks.json commands are POSIX shell; Windows rewrites them")
        return
    sb = Sandbox()
    try:
        settings = sb.home / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({"hooks": {"PreToolUse": [{
            "matcher": "Bash",
            "hooks": [{"type": "command",
                       "command": OLD_TEMPLATE_FORM.format(py=sys.executable)}]}]}}),
            encoding="utf-8")
        r = run_installer(sb, settings)
        if r.returncode != 0:
            check(name, False, f"installer exit {r.returncode}: {(r.stderr or r.stdout)[-400:]}")
            return
        regs = bash_registrations(json.loads(settings.read_text(encoding="utf-8")))
        check("D2 exactly one registration remains after the upgrade", len(regs) == 1,
              f"found {len(regs)}: {regs}")
        if len(regs) != 1:
            return
        codes = [run_registered(sb, regs[0], "git push origin main --dry-run",
                                f"toolu_up_{i}")[0] for i in range(1, 5)]
        check(name, "|| true" not in regs[0] and codes == [0, 0, 0, 2],
              f"registration {regs[0]!r}; exit codes {codes}")
    finally:
        sb.cleanup()


def main() -> int:
    for line in (sys.stdout, sys.stderr):
        try:
            line.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass
    print("retry-budget controls")
    leg_fingerprint_covers_whole_command()
    leg_poll_loop_with_changing_tail_is_not_a_loop()
    leg_whitespace_variants_still_share_a_budget()
    leg_one_call_is_one_attempt_sequential()
    leg_one_call_is_one_attempt_concurrent()
    leg_duplicate_registration_reuses_the_verdict()
    leg_no_call_id_counts_every_invocation()
    leg_identical_command_blocks_on_fourth_call()
    leg_template_registration_preserves_the_block()
    leg_template_registration_absent_script_is_neutral()
    leg_state_write_does_not_follow_a_planted_link()
    leg_both_installers_one_attempt_per_call()
    leg_existing_install_upgrades_to_one_blocking_registration()
    if FAILURES:
        print(f"\n{len(FAILURES)} control(s) FAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nall retry-budget controls passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
