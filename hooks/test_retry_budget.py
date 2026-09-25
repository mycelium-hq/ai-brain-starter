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
   at all under a POSIX shell: `||` rewrites exit 2 into 0, so an install
   carrying only that copy had a decorative guard. (Windows rewrites hooks.json
   commands through hook_runner.py, which keeps exit 2.)

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

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
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
        # A broken hook can leave any JSON here (a planted top-level list, for
        # one); report that as "no attempts", never crash the whole suite.
        try:
            s = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return s if isinstance(s, dict) else {}

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


def fingerprint(command: str) -> str:
    """The hook's key for a command. Mirrors the hook on purpose so a leg can
    plant state for a command; leg C5a proves the two still agree."""
    norm = " ".join(command.split())
    return hashlib.md5(norm.encode("utf-8", "surrogatepass")).hexdigest()[:12]


def plant_state(sb: Sandbox, state: dict) -> None:
    sb.state_path.write_text(json.dumps(state), encoding="utf-8")


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


def leg_fingerprint_sees_a_middle_difference() -> None:
    # Every pair above differs only at its END, which a head+tail "fix" (hash
    # the first N and last M characters) would also pass. Real commands often
    # share a long head (a scratch path) AND a long tail (a log redirect) and
    # differ only in a flag between them.
    sb = Sandbox()
    try:
        head = long_prefix(600) + " --mode "
        tail = " > /private/tmp/example-gate/" + "gate-output-" * 50 + ".log 2>&1"
        a, b = head + "alpha" + tail, head + "bravo" + tail
        assert len(tail) > 600 and " ".join(a.split()) == a and len(a) == len(b)
        run_hook(sb, a, "toolu_mid_a")
        run_hook(sb, b, "toolu_mid_b")
        h = sb.histories()
        check("A4 two long commands differing only in the middle get distinct fingerprints",
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


def leg_short_command_exemption_is_measured_after_normalizing() -> None:
    # "git status -sb" is 14 characters, under the 15-character exemption. The
    # same command with its spacing reflowed is the same command, so it must
    # stay exempt too.
    sb = Sandbox()
    try:
        codes = [run_hook(sb, "git  status   -sb ", f"toolu_short_{i}")[0] for i in range(1, 6)]
        check("A5 a short command padded with extra spaces is still exempt",
              codes == [0] * 5 and sb.attempts() == 0,
              f"exit codes {codes}, timestamps={sb.attempts()}")
    finally:
        sb.cleanup()


def leg_lone_surrogate_is_counted_not_a_crash() -> None:
    sb = Sandbox()
    try:
        code, err = run_hook(sb, "printf '%s' '\ud800' > example-output.txt", "toolu_surrogate")
        check("A6 a command carrying a lone surrogate is counted, not a crash",
              code == 0 and sb.attempts() == 1,
              f"exit {code}, timestamps={sb.attempts()}, stderr {err[-160:]!r}")
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
                                      env=sb.env, text=True, encoding="utf-8",
                                      errors="replace") for _ in range(2)]
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


def leg_concurrent_calls_share_one_file_safely() -> None:
    # Subagents share their parent's session_id, so different calls race on one
    # state file. Each command starts with 2 attempts, so its call is attempt 3:
    # if a racing write wiped the call's record, its second registration would
    # count attempt 4 and block, splitting the verdict. Three rounds.
    name = "B5 eight calls x two registrations racing: every call counted once, pairs agree"
    if not POSIX:
        skip(name, "the parallel leg is exercised on the POSIX runner")
        return
    problem = ""
    for rnd in range(3):
        sb = Sandbox()
        try:
            cmds = [f"cargo build --package example-crate-{i} --release" for i in range(8)]
            now = time.time()
            plant_state(sb, {fingerprint(c): [now - 20, now - 10] for c in cmds})
            jobs = []
            for i, cmd in enumerate(cmds):
                data = payload(cmd, f"toolu_mix_{rnd}_{i}")
                for _ in range(2):
                    p = subprocess.Popen([sys.executable, str(HOOK)], stdin=subprocess.PIPE,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         env=sb.env, text=True, encoding="utf-8",
                                         errors="replace")
                    jobs.append((i, data, p))
            # Barrier: let every interpreter finish starting and block on stdin,
            # then release them together, so their read-modify-writes overlap.
            time.sleep(1.5)
            for _, data, p in jobs:
                p.stdin.write(data)
                p.stdin.close()
            codes: dict = {}
            for i, _, p in jobs:
                codes.setdefault(i, []).append(p.wait(timeout=60))
            per_cmd = sorted(len(v) for v in sb.histories().values())
            if per_cmd != [3] * len(cmds) or any(c != [0, 0] for c in codes.values()):
                problem = f"round {rnd}: attempts per command {per_cmd}, exit codes {codes}"
                break
        finally:
            sb.cleanup()
    check(name, not problem, problem)


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


def leg_planted_link_is_neither_read_nor_written_through() -> None:
    # The state path is predictable. A link planted there must not steer the
    # count (its target claims 3 fresh attempts, so reading through it blocks
    # the first call) and must not be written through.
    name = "C4 a link planted at the state path neither steers the count nor is written through"
    if not POSIX:
        skip(name, "creating a symlink needs privileges on Windows")
        return
    sb = Sandbox()
    try:
        probe = "echo planted-link-probe-command"
        now = time.time()
        steer = json.dumps({fingerprint(probe): [now - 3, now - 2, now - 1]})
        target = sb.root / "planted-target.json"
        target.write_text(steer, encoding="utf-8")
        os.symlink(target, sb.state_path)
        code, _ = run_hook(sb, probe, "toolu_link")
        check(name, code == 0 and target.read_text(encoding="utf-8", errors="replace") == steer
              and not sb.state_path.is_symlink(),
              f"exit {code} (2 = the planted attempts were read), target unchanged="
              f"{target.read_text(encoding='utf-8', errors='replace') == steer}, "
              f"state path is_symlink={sb.state_path.is_symlink()}")
    finally:
        sb.cleanup()


def leg_malformed_state_fails_open_and_repairs() -> None:
    # The hook runs before every Bash call: a bad value anywhere in its file
    # must not turn into a crash on every call, and the next write repairs it.
    probe = "pytest -x tests/test_example.py"
    key = fingerprint(probe)
    sb = Sandbox()
    try:
        run_hook(sb, probe, "toolu_premise")
        check("C5a premise: the test's fingerprint() matches the hook's key",
              key in sb.histories(), f"hook keys {list(sb.histories())}, test key {key}")
    finally:
        sb.cleanup()
    cases = {
        "a number as this command's history": {key: 5},
        "null as this command's history": {key: None},
        "a 402-digit integer in another command's history": {"0123456789ab": [10 ** 401]},
        "a 402-digit integer inside a counted call": {"_calls": {"toolu_old": [10 ** 401, 1]}},
        "_calls that is not a dict": {"_calls": [1, 2, 3]},
        "a top-level list": [1, 2, 3],
    }
    for label, state in cases.items():
        sb = Sandbox()
        try:
            sb.state_path.write_text(json.dumps(state), encoding="utf-8")
            c1, err = run_hook(sb, probe, "toolu_mal_1")
            c2, _ = run_hook(sb, probe, "toolu_mal_2")
            got = len(sb.histories().get(key, []))
            check(f"C5 {label}: exit 0, and the next call counts from a repaired file",
                  (c1, c2) == (0, 0) and got == 2,
                  f"exit codes {(c1, c2)}, attempts for the command {got}, stderr {err[-200:]!r}")
        finally:
            sb.cleanup()


def leg_fifo_at_state_path_does_not_hang() -> None:
    name = "C6 a FIFO planted at the state path does not hang the hook"
    if not POSIX or not hasattr(os, "mkfifo"):
        skip(name, "needs mkfifo")
        return
    sb = Sandbox()
    try:
        os.mkfifo(sb.state_path)
        try:
            r = subprocess.run([sys.executable, str(HOOK)],
                               input=payload("make -C build all-targets", "toolu_fifo"),
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", env=sb.env, timeout=20)
            check(name, r.returncode == 0, f"exit {r.returncode}: {r.stderr[-160:]!r}")
        except subprocess.TimeoutExpired:
            check(name, False, "still blocked on the FIFO after 20 s")
    finally:
        sb.cleanup()


def leg_infinite_and_future_attempts_expire() -> None:
    # A planted Infinity, or a clock stepped backwards, must not pin a
    # command's budget. json writes float("inf") as Infinity and reads it back.
    sb = Sandbox()
    try:
        probe = "terraform plan -out example.plan"
        now = time.time()
        plant_state(sb, {fingerprint(probe): [float("inf"), now + 7200, now + 7200]})
        code, _ = run_hook(sb, probe, "toolu_future")
        got = len(sb.histories().get(fingerprint(probe), []))
        check("C7 planted Infinity and far-future attempts do not count",
              code == 0 and got == 1, f"exit {code}, attempts for the command {got}")
    finally:
        sb.cleanup()


def leg_unreadable_script_is_a_no_op_not_a_block() -> None:
    # `python3 <file it cannot read>` exits 2, which the harness treats as a
    # BLOCK: a mode-000 script behind a bare `[ -f ]` guard would refuse every
    # Bash call. The old `|| true` hid this; the if/else form must not expose it.
    name = "C8 an unreadable script makes the registration a no-op, not a block"
    if not POSIX:
        skip(name, "hooks.json commands are POSIX shell; Windows rewrites them")
        return
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        skip(name, "root can read a mode-000 file")
        return
    regs = bash_registrations(rendered_template())
    if len(regs) != 1:
        check(name, False, f"expected one registration, found {len(regs)}")
        return
    sb = Sandbox()
    try:
        sb.deploy_hook()
        deployed = sb.home / ".claude" / "hooks" / HOOK.name
        os.chmod(deployed, 0)
        try:
            code, out, err = run_registered(sb, regs[0], "git push origin main --dry-run",
                                            "toolu_unreadable")
        finally:
            os.chmod(deployed, 0o644)
        check(name, code == 0 and "permissionDecision" not in out,
              f"exit {code}, stderr {err[-160:]!r}")
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
        data = json.loads(settings.read_text(encoding="utf-8", errors="replace"))
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
        regs = bash_registrations(json.loads(settings.read_text(encoding="utf-8", errors="replace")))
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


def leg_installer_collapses_existing_copies_in_one_run() -> None:
    # A machine where two installers already wired the script holds BOTH forms.
    # One install must leave exactly one registration, in the template's own
    # form. The live shape that exposed this: the second installer's copy
    # first, the old `|| true` copy last in the same group; the merge rewrote
    # the first and the owned-hook dedupe then kept the LAST, i.e. the one
    # that can never block.
    if not POSIX:
        skip("D3 installer layouts", "hooks.json commands are POSIX shell; Windows rewrites them")
        return
    py = sys.executable
    second, old = SECOND_INSTALLER_FORM.format(py=py), OLD_TEMPLATE_FORM.format(py=py)
    user_a = "echo '{}' # the user's own hook A"
    user_b = "echo '{}' # the user's own hook B"
    template_regs = bash_registrations(rendered_template())

    def hook(c):
        return {"type": "command", "command": c}

    layouts = {
        "second installer's copy first, old copy last, one group": [
            {"matcher": "Bash", "hooks": [hook(user_a), hook(second), hook(user_b), hook(old)]}],
        "old copy first, one group": [
            {"matcher": "Bash", "hooks": [hook(old), hook(second)]}],
        "the two copies in separate groups": [
            {"matcher": "Bash", "hooks": [hook(second)]},
            {"matcher": "Bash", "hooks": [hook(old), hook(user_a)]}],
    }
    for label, groups in layouts.items():
        sb = Sandbox()
        try:
            settings = sb.home / ".claude" / "settings.json"
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text(json.dumps({"hooks": {"PreToolUse": groups}}), encoding="utf-8")
            r = run_installer(sb, settings)
            if r.returncode != 0:
                check(f"D3 {label}", False, f"installer exit {r.returncode}: {(r.stderr or r.stdout)[-300:]}")
                continue
            data = json.loads(settings.read_text(encoding="utf-8", errors="replace"))
            regs = bash_registrations(data)
            cmds = [h.get("command", "") for g in data["hooks"].get("PreToolUse", [])
                    for h in g.get("hooks", [])]
            users_kept = all(u in cmds for u in (user_a, user_b) if any(
                h["command"] == u for g in groups for h in g["hooks"]))
            codes = [run_registered(sb, reg, "git push origin main --dry-run", f"toolu_lay_{i}")[0]
                     for i in range(1, 5) for reg in regs[:1]] if len(regs) == 1 else []
            check(f"D3 {label}: one run leaves exactly the template's registration, and it blocks",
                  regs == template_regs and users_kept and codes == [0, 0, 0, 2],
                  f"registrations {regs}; user hooks kept={users_kept}; exit codes {codes}")
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
    leg_fingerprint_sees_a_middle_difference()
    leg_poll_loop_with_changing_tail_is_not_a_loop()
    leg_whitespace_variants_still_share_a_budget()
    leg_short_command_exemption_is_measured_after_normalizing()
    leg_lone_surrogate_is_counted_not_a_crash()
    leg_one_call_is_one_attempt_sequential()
    leg_one_call_is_one_attempt_concurrent()
    leg_duplicate_registration_reuses_the_verdict()
    leg_no_call_id_counts_every_invocation()
    leg_concurrent_calls_share_one_file_safely()
    leg_identical_command_blocks_on_fourth_call()
    leg_template_registration_preserves_the_block()
    leg_template_registration_absent_script_is_neutral()
    leg_planted_link_is_neither_read_nor_written_through()
    leg_malformed_state_fails_open_and_repairs()
    leg_fifo_at_state_path_does_not_hang()
    leg_infinite_and_future_attempts_expire()
    leg_unreadable_script_is_a_no_op_not_a_block()
    leg_both_installers_one_attempt_per_call()
    leg_existing_install_upgrades_to_one_blocking_registration()
    leg_installer_collapses_existing_copies_in_one_run()
    if FAILURES:
        print(f"\n{len(FAILURES)} control(s) FAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nall retry-budget controls passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
