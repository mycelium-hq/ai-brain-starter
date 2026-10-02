#!/usr/bin/env python3
"""Close gate 2 (the runner ran) must be satisfied by THIS session's run only.

session-close-runner.sh wrote ONE shared report, /tmp/abs-session-close-runner.report,
and verify-session-close-cascade.py's gate 2 read that one file. Any session's
run within 30 minutes therefore satisfied every other session's gate: on a
shared checkout session A could close without ever running the runner, because
session B had. Gates 1 and 3 were scoped by session id in ai-brain-starter#713;
gate 2 was left out because the runner did not know which session invoked it.

The fix: detect-closing-signal.py hands the session id to the runner in the
command it injects (`bash "<runner>" --session <id>`), the runner writes a
per-session report next to the shared one, and the gate checks THIS session's
report. The shared report is the fallback only when no session id is available,
or when the vault's installed runner predates per-session reports (blocking
there would block every close forever, until the vault's scripts re-sync).

Every scenario drives the REAL runner (copied into a hermetic vault, exactly
as sync-vault-scripts.sh installs it) and the REAL gate as subprocesses, with
HOME and USERPROFILE sandboxed and ABS_RUNNER_REPORT pointing into a tmpdir.

Assertions:
  1. Only B ran the runner -> B's gate passes, A's gate is BLOCKED on gate 2
     and the block tells A to run the runner with A's own id.
  2. NEGATIVE CONTROL: A ran it too -> A's gate passes (not an always-block).
  3. A's run is stale (>30 min) -> A is BLOCKED.
  4. A session with no id falls back to the shared report and passes.
  5. A session WITH an id is not satisfied by an unscoped run (one with no
     --session), since that run cannot be attributed to it.
  6. A vault whose installed runner predates per-session reports falls back
     to the shared report instead of blocking every close forever.
  7. An unsafe id (path characters) is never put into a path: the runner
     writes no per-session file for it, and the gate treats it as no id.
  8. End to end: the runner command detect-closing-signal.py injects carries
     this session's id, and EXECUTING that exact line satisfies this
     session's gate. With no usable id the command carries no --session.
  9. The gate's own fix-it line (`Run: ...` in the block), EXECUTED from the
     worktree the session runs in, clears the gate: also when that worktree
     carries an older committed copy of the runner (a vault-relative path
     would run that copy, which writes only the shared report, forever).
 10. `--session=<id>` is the same as `--session <id>`.
 11. ABS_RUNNER_REPORT set but EMPTY means the default on both sides (the
     runner's `${VAR:-default}` treats empty as unset; the gate must too).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Windows cp1252-console safety (ai-brain-starter#313). Module scope, not
# __main__: every scenario below runs and prints at import time, and the labels
# carry vault paths under the decorated meta folder.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # Python 3.7+
    except (AttributeError, ValueError):
        pass

HOOKS = Path(__file__).resolve().parent
REPO = HOOKS.parent
GATE = HOOKS / "verify-session-close-cascade.py"
DETECT = HOOKS / "detect-closing-signal.py"
RUNNER = REPO / "scripts" / "session-close-runner.sh"

META = "⚙️ Meta"
TODAY = datetime.now().strftime("%Y-%m-%d")
A, B = "sessA-1111-aaaa", "sessB-2222-bbbb"
WT = "wt-shared"
UTF8 = {"encoding": "utf-8", "errors": "replace"}

failures: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    if cond:
        print(f"PASS: {label}")
    else:
        failures.append(label)
        print(f"FAIL: {label}" + (f"\n      {detail}" if detail else ""))


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True, **UTF8,
    ).stdout


class Env:
    """One hermetic world: a git vault with the REAL runner installed + a HOME.

    Both sessions share one worktree slug, so gates 1 and 3 (scoped by slug on
    this base) pass for both and only gate 2 decides the outcome.
    """

    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="close-gate-runner-")).resolve()
        self.vault = self.root / "vault"
        self.home = self.root / "home"
        (self.home / ".claude").mkdir(parents=True)
        scripts = self.vault / META / "scripts"
        for d in ("Sessions", "Decisions", "scripts"):
            (self.vault / META / d).mkdir(parents=True)
        self.runner = scripts / "session-close-runner.sh"
        shutil.copy2(RUNNER, self.runner)
        self.wt = self.vault / ".claude" / "worktrees" / WT
        self.wt.mkdir(parents=True)
        (self.vault / ".gitignore").write_text(".claude/\n", encoding="utf-8")
        (self.vault / META / "Sessions" / f"{TODAY}T10-00-{WT}.md").write_text(
            f"---\ntype: session\nworktree: {WT}\n---\n# Session\n", encoding="utf-8")
        git(self.vault, "init", "-q")
        git(self.vault, "config", "user.email", "t@example.com")
        git(self.vault, "config", "user.name", "t")
        git(self.vault, "add", "-A")
        git(self.vault, "commit", "-qm", "init")
        # The base report path. The runner and the gate both derive every
        # report from it, so nothing here touches the machine's real /tmp one.
        self.report = self.root / "reports" / "abs-session-close-runner.report"
        self.report.parent.mkdir()
        self.transcript = self.root / "transcript.jsonl"
        self.transcript.write_text(json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text",
                                     "text": "Cascade complete. Closing the session."}]},
        }) + "\n", encoding="utf-8")

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def env(self) -> dict:
        env = {k: v for k, v in os.environ.items()
               if k not in ("VERIFY_CASCADE_BYPASS", "VERIFY_CASCADE_SOFT")}
        # USERPROFILE too: on Windows Path.home() reads it, not HOME, and the
        # hooks would otherwise read and write markers in the REAL ~/.claude.
        env.update(HOME=str(self.home), USERPROFILE=str(self.home),
                   VAULT_ROOT=str(self.vault), ABS_RUNNER_REPORT=str(self.report))
        env.pop("ANTHROPIC_API_KEY", None)
        return env

    def run_runner(self, session: str | None, *raw: str) -> subprocess.CompletedProcess:
        args = ["bash", str(self.runner)] + (["--session", session] if session else [])
        return subprocess.run(args + list(raw), capture_output=True, text=True,
                              env=self.env(), cwd=str(self.wt), timeout=120, **UTF8)

    def run_line(self, line: str) -> subprocess.CompletedProcess:
        """Execute a command line exactly as a model would, from the worktree."""
        return subprocess.run(["bash", "-c", line], capture_output=True, text=True,
                              env=self.env(), cwd=str(self.wt), timeout=120, **UTF8)

    def gate(self, session: str | None) -> tuple[int, str]:
        payload = {"transcript_path": str(self.transcript), "cwd": str(self.wt)}
        if session is not None:
            payload["session_id"] = session
        r = subprocess.run([sys.executable, str(GATE)], input=json.dumps(payload),
                           capture_output=True, text=True, env=self.env(),
                           cwd=str(self.wt), timeout=60, **UTF8)
        return r.returncode, r.stderr

    def reports(self) -> list[Path]:
        return sorted(self.report.parent.iterdir())


def scenario(fn):
    env = Env()
    try:
        fn(env)
    except Exception as e:  # a crash in one scenario must not hide the rest
        failures.append(f"{fn.__name__} crashed: {e!r}")
        print(f"FAIL: {fn.__name__} crashed: {e!r}")
    finally:
        env.cleanup()
    return fn


# ── 1: only B ran the runner ──────────────────────────────────────────────────
@scenario
def only_b_ran(e: Env) -> None:
    r = e.run_runner(B)
    check(r.returncode == 0, f"B's runner run exits 0 (rc={r.returncode})", r.stderr[-300:])
    rc, err = e.gate(B)
    check(rc == 0, f"B's gate passes on B's own run (rc={rc})", err[-500:])
    rc, err = e.gate(A)
    check(rc == 2, f"A's gate is BLOCKED although only B ran the runner (rc={rc})", err[-500:])
    check("session-close-runner.sh report" in err, "the block names gate 2", err[-500:])
    check(f"--session {A}" in err,
          "the block tells A to run the runner with A's own id", err[-500:])


# ── 2: negative control — A ran it too ────────────────────────────────────────
@scenario
def both_ran(e: Env) -> None:
    e.run_runner(B)
    e.run_runner(A)
    rc, err = e.gate(A)
    check(rc == 0, f"A's gate passes once A ran the runner itself (rc={rc})", err[-500:])


# ── 3: A's own run is stale ───────────────────────────────────────────────────
@scenario
def a_run_stale(e: Env) -> None:
    e.run_runner(A)
    own = [p for p in e.reports() if A in p.name]
    check(len(own) == 1, f"A's run wrote exactly one report naming A ({[p.name for p in e.reports()]})")
    if len(own) != 1:
        return
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = own[0].read_text(encoding="utf-8")
    own[0].write_text(re.sub(r"RUNNER COMPLETE @ \S+", f"RUNNER COMPLETE @ {old}", text),
                      encoding="utf-8")
    rc, err = e.gate(A)
    check(rc == 2, f"A's gate is BLOCKED when A's own run is 2h old (rc={rc})", err[-500:])


# ── 4: no session id -> the shared report ─────────────────────────────────────
@scenario
def no_id_uses_shared(e: Env) -> None:
    e.run_runner(None)
    check(e.report.is_file(), "an unscoped run writes the shared report")
    rc, err = e.gate(None)
    check(rc == 0, f"a session with no id passes on the shared report (rc={rc})", err[-500:])


# ── 5: a session with an id is not satisfied by an unscoped run ───────────────
@scenario
def id_not_satisfied_by_unscoped(e: Env) -> None:
    e.run_runner(None)
    rc, err = e.gate(A)
    check(rc == 2, f"A (has an id) is BLOCKED on an unscoped run nobody owns (rc={rc})",
          err[-500:])


# ── 6: an installed runner that predates per-session reports ──────────────────
@scenario
def legacy_runner_falls_back(e: Env) -> None:
    # What an un-synced vault copy does: one shared report, args ignored.
    e.runner.write_text(
        "#!/bin/bash\n"
        'REPORT="${ABS_RUNNER_REPORT:-/tmp/abs-session-close-runner.report}"\n'
        "printf 'RUNNER COMPLETE @ %s\\n' \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\" > \"$REPORT\"\n",
        encoding="utf-8")
    e.run_runner(A)
    rc, err = e.gate(A)
    check(rc == 0, f"a legacy runner's shared report still clears gate 2 (rc={rc})", err[-500:])


# ── 7: an unsafe id never becomes a path ──────────────────────────────────────
@scenario
def unsafe_id(e: Env) -> None:
    bad = "../escape"
    r = e.run_runner(bad)
    check(r.returncode == 0, f"the runner still completes on an unsafe id (rc={r.returncode})")
    names = [p.name for p in e.reports()]
    check(names == [e.report.name], f"only the shared report was written ({names})")
    check(not (e.root / "escape.report").exists() and not any(
        "escape" in p.name for p in e.root.rglob("*")), "nothing was written for the unsafe id")
    rc, err = e.gate(bad)
    check(rc == 0, f"the gate treats an unsafe id as no id (rc={rc})", err[-500:])
    # The runner (bash) and the gate (Python) must reject the SAME ids, or one
    # side writes a report the other never reads.
    for odd in ("a b", "caf\u00e9", "x\ny", "a]b", "a\\b", "\uff21"):
        for p in e.reports():
            p.unlink()
        e.run_runner(odd)
        names = [p.name for p in e.reports()]
        rc, err = e.gate(odd)
        check(names == [e.report.name] and rc == 0,
              f"runner and gate both treat {odd!r} as no id (reports={names}, rc={rc})",
              err[-300:])


# ── 8: end to end through the injected command ────────────────────────────────
def injected_runner_line(e: Env, session: str | None) -> str:
    lines = [json.dumps({"type": "user", "message": {"content": f"msg {i}"}}) for i in range(6)]
    transcript = e.root / "user-transcript.jsonl"
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = {"prompt": "ok bye", "cwd": str(e.wt), "transcript_path": str(transcript)}
    if session is not None:
        payload["session_id"] = session
    r = subprocess.run([sys.executable, str(DETECT)], input=json.dumps(payload),
                       capture_output=True, text=True, env=e.env(), cwd=str(e.wt),
                       timeout=60, **UTF8)
    try:
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    except Exception:
        ctx = r.stdout
    found = [ln.strip() for ln in ctx.splitlines()
             if ln.strip().startswith("bash ") and "session-close-runner.sh" in ln]
    check(len(found) == 1, f"the cascade injects exactly one runner command ({found})", ctx[:400])
    return found[0] if found else ""


@scenario
def injected_command_end_to_end(e: Env) -> None:
    line = injected_runner_line(e, A)
    check(line.endswith(f"--session {A}"), f"the injected command carries A's id ({line!r})")
    # The detector pre-built A's note; a real close commits it (Phase 2b), so
    # gate 3 is clear and only gate 2 decides this scenario.
    git(e.vault, "add", "-A")
    git(e.vault, "commit", "-qm", "close: A's note", "--allow-empty")
    e.run_runner(B)
    rc, err = e.gate(A)
    check(rc == 2, f"before A runs the injected line, B's run does not clear A (rc={rc})",
          err[-500:])
    r = subprocess.run(["bash", "-c", line], capture_output=True, text=True, env=e.env(),
                       cwd=str(e.wt), timeout=120, **UTF8)
    check(r.returncode == 0, f"the injected line runs (rc={r.returncode})", r.stderr[-300:])
    rc, err = e.gate(A)
    check(rc == 0, f"executing the injected line clears A's gate (rc={rc})", err[-500:])


@scenario
def injected_command_without_id(e: Env) -> None:
    for sid in (None, "unknown", "../escape"):
        line = injected_runner_line(e, sid)
        check(line != "" and "--session" not in line,
              f"no usable id ({sid!r}) -> the injected command carries no --session ({line!r})")


# ── 9: the gate's own fix-it line, executed from the worktree ────────────────
def run_block_line(e: Env) -> None:
    e.run_runner(B)
    rc, err = e.gate(A)
    lines = [ln.strip()[len("Run: "):] for ln in err.splitlines()
             if ln.strip().startswith("Run: ") and "session-close-runner.sh" in ln]
    check(rc == 2 and len(lines) == 1, f"A is blocked with one Run: line (rc={rc}, {lines})",
          err[-500:])
    if len(lines) != 1:
        return
    r = e.run_line(lines[0])
    check(r.returncode == 0, f"the Run: line executes from the worktree (rc={r.returncode})",
          r.stderr[-300:])
    rc, err = e.gate(A)
    check(rc == 0, f"executing the gate's own Run: line clears A's gate (rc={rc})", err[-500:])


@scenario
def block_line_clears_gate(e: Env) -> None:
    run_block_line(e)


@scenario
def block_line_ignores_worktree_copy(e: Env) -> None:
    # A vault that tracks its scripts in git: the worktree holds its own,
    # older committed copy of the runner, which writes only the shared report.
    stale = e.wt / META / "scripts" / "session-close-runner.sh"
    stale.parent.mkdir(parents=True)
    stale.write_text(
        "#!/bin/bash\n"
        'REPORT="${ABS_RUNNER_REPORT:-/tmp/abs-session-close-runner.report}"\n'
        "printf 'RUNNER COMPLETE @ %s\\n' \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\" > \"$REPORT\"\n",
        encoding="utf-8")
    run_block_line(e)


# ── 10: --session=<id> ────────────────────────────────────────────────────────
@scenario
def session_equals_form(e: Env) -> None:
    e.run_runner(None, f"--session={A}")
    names = [p.name for p in e.reports()]
    check(any(A in n for n in names) and e.report.name not in names,
          f"--session={A} writes A's own report, not the shared one ({names})")
    rc, err = e.gate(A)
    check(rc == 0, f"--session=<id> clears A's gate (rc={rc})", err[-500:])


# ── 11: an empty ABS_RUNNER_REPORT is the default, as the runner reads it ────
def empty_override_is_default() -> None:
    probe = (
        "import importlib.util, sys\n"
        "spec = importlib.util.spec_from_file_location('gate', sys.argv[1])\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "print(m.RUNNER_REPORT); print(m.session_runner_report('sessA'))\n"
    )
    env = {k: v for k, v in os.environ.items()}
    home = Path(tempfile.mkdtemp(prefix="close-gate-runner-home-"))
    try:
        env.update(HOME=str(home), USERPROFILE=str(home), ABS_RUNNER_REPORT="")
        r = subprocess.run([sys.executable, "-c", probe, str(GATE)], capture_output=True,
                           text=True, env=env, timeout=60, **UTF8)
    finally:
        shutil.rmtree(home, ignore_errors=True)
    got = r.stdout.splitlines()
    default = (str(Path(tempfile.gettempdir()) / "abs-session-close-runner.report")
               if os.name == "nt" else "/tmp/abs-session-close-runner.report")
    want = [default, default[: -len(".report")] + ".sessA.report"]
    check(got == want, f"empty ABS_RUNNER_REPORT -> the gate uses the default ({got})",
          r.stderr[-300:])


empty_override_is_default()


if __name__ == "__main__":
    if failures:
        print(f"\n{len(failures)} FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("\nAll close-gate runner-per-session checks passed.")
