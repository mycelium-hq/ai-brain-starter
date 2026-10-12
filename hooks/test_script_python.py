#!/usr/bin/env python3
"""test_script_python.py - a hook that runs a script it does not ship gets past
a session's python3 shim, and runs that script under the shell's python3, not
under its own interpreter (MYC-5434).

THE DEFECT. Two hooks ran vault scripts as ["python3", script]. Inside a Claude
Code session a Python-tooling plugin puts a shim first on PATH that refuses
exactly `python3 <script>`, so every in-session test saw the child refused and
the hook fail open (verify-discoverability-on-close: 2 of its 6 cases). The
obvious fix, sys.executable, breaks production instead: that hook is registered
under a 3.9 interpreter and its verifier needs 3.12, so the verifier died before
printing anything and the gate passed everything.

WHAT THIS PINS
  1. hooks/_lib/script_python.py: past a refusing shim; the first python3 when
     there is none (the old call's choice); sys.executable when nothing on PATH
     runs a script; relative PATH entries ignored; a wrapper that prints advice
     and exits 0 is skipped. Only a refusal skips: a probe that times out, one
     killed by a signal, and one that cannot fork right now (EAGAIN) all keep
     their candidate, while a candidate that cannot be executed at all is
     skipped; no temp dir keeps the first candidate. On Windows only
     python3.exe is a candidate (simulated by setting os.name).
  2. verify-discoverability-on-close.py, refusing shim first on PATH: the
     verifier still runs and the hook blocks on this session's gap. The same hook
     with ["python3", ...] put back does not block. That control is what makes
     the leg mean something.
  3. The verifier runs under PATH's python3, not the hook's own interpreter: a
     witness wrapper marks the environment and the stub reports the gap only
     when the mark is there. With sys.executable put back, no block.
  4. The measured incident: the hook under a pre-3.12 interpreter, a verifier
     that needs 3.12. Blocks; with sys.executable put back, does not. SKIPs
     where no pre-3.12 interpreter is installed.
  5. check-rule-conflicts-on-write.py, refusing shim first on PATH: the vault
     detector runs and its result is surfaced; the old form surfaces nothing.
  6. pre-write-settings-lint.py (its lint ships beside it, so
     `sys.executable or "python3"`, unchanged) still blocks a duplicate-key
     write with a refusing shim first on PATH. A regression check, not a
     control: its spawn did not change.

Fake interpreters are /bin/sh scripts, so this runs on POSIX only and prints a
SKIP line on Windows. Plain script, no pytest; registered in scripts/ci.sh
PY_DIRECT. Stdlib only; Python 3.9+.
"""
from __future__ import annotations

import errno
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS))
from _lib import script_python as sp  # noqa: E402

REAL = sys.executable
META = "⚙️ Meta"
CLOSING = "Closing the session now and writing the artifact."
OLD_SPAWN = '["python3", '
NEW_SPAWN = "[script_python(), "

_counts = {"pass": 0, "fail": 0}


def ok(label: str) -> None:
    _counts["pass"] += 1
    print("PASS  %s" % label)


def bad(label: str, why: str) -> None:
    _counts["fail"] += 1
    print("FAIL  %s :: %s" % (label, why))


def check(label: str, cond: bool, why: str) -> None:
    (ok(label) if cond else bad(label, why))


# --- fake interpreters ----------------------------------------------------------------

def _exe(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def real_python(d: Path) -> Path:
    """A python3 that runs scripts: hands everything to this test's interpreter."""
    return _exe(d / "python3", '#!/bin/sh\nexec "%s" "$@"\n' % REAL)


def refusing_shim(d: Path) -> Path:
    """The plugin shim's shape: forwards -c / -m / -, refuses a script path."""
    return _exe(d / "python3",
                "#!/bin/sh\n"
                'case "$1" in -c|-m|-) exec "%s" "$@" ;; esac\n'
                "echo 'ERROR: Use uv run python <script> instead of python3 <script>' >&2\n"
                "exit 1\n" % REAL)


def advice_wrapper(d: Path) -> Path:
    """Prints advice and exits 0 without running anything."""
    return _exe(d / "python3", "#!/bin/sh\necho 'use uv run python instead'\nexit 0\n")


def stalled_python(d: Path) -> Path:
    """Never answers within a short probe (a loaded machine, as far as a probe can tell).

    `sleep` by absolute path: the legs run with PATH holding only the fake
    interpreters, so a bare `sleep` would exit 127 at once and read as a refusal.
    """
    sleep = shutil.which("sleep") or "/bin/sleep"
    return _exe(d / "python3", '#!/bin/sh\nexec "%s" 30\n' % sleep)


def killed_once_python(d: Path) -> Path:
    """Killed by a signal the first time it runs (an OOM killer, as far as a probe can tell), healthy after."""
    marker = d / "killed-once"
    return _exe(d / "python3",
                '#!/bin/sh\nif [ ! -e "%s" ]; then : > "%s"; kill -9 $$; fi\nexec "%s" "$@"\n'
                % (marker, marker, REAL))


def unexecutable_python(d: Path) -> Path:
    """Marked executable, but its interpreter line names nothing: the exec itself fails."""
    return _exe(d / "python3", "#!/nonexistent/interpreter\n")


def witness_python(d: Path) -> Path:
    """A python3 that runs scripts and marks the environment it ran them in."""
    return _exe(d / "python3",
                '#!/bin/sh\nSCRIPT_PYTHON_WITNESS=1\nexport SCRIPT_PYTHON_WITNESS\nexec "%s" "$@"\n' % REAL)


# --- 1. the resolver ------------------------------------------------------------------

def resolve(path_entries, timeout=None, mkdtemp=None, cwd=None, run=None, os_name=None, env=None) -> str:
    saved = (os.environ.get("PATH"), sp.PROBE_TIMEOUT_SEC, sp.tempfile.mkdtemp, os.getcwd(),
             sp.subprocess.run, sp.os.name)
    saved_env = {k: os.environ.get(k) for k in (env or {})}
    try:
        for k, v in (env or {}).items():
            os.environ[k] = v
        os.environ["PATH"] = os.pathsep.join(str(p) for p in path_entries)
        sp._resolved = None
        if timeout is not None:
            sp.PROBE_TIMEOUT_SEC = timeout
        if mkdtemp is not None:
            sp.tempfile.mkdtemp = mkdtemp
        if cwd is not None:
            os.chdir(cwd)
        if run is not None:
            sp.subprocess.run = run
        if os_name is not None:
            sp.os.name = os_name
        return sp.script_python()
    finally:
        old_path, sp.PROBE_TIMEOUT_SEC, sp.tempfile.mkdtemp, old_cwd, sp.subprocess.run, sp.os.name = saved
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        os.chdir(old_cwd)
        if old_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = old_path
        sp._resolved = None


def resolver_legs(tmp: Path) -> None:
    print("=== 1. the resolver ===")
    shim = refusing_shim(tmp / "shim")
    real = real_python(tmp / "real")
    empty = tmp / "empty"
    empty.mkdir()

    got = resolve([shim.parent, real.parent])
    check("a refusing shim first on PATH is stepped past", got == str(real), "got %s" % got)

    got = resolve([real.parent])
    want = shutil.which("python3", path=str(real.parent))
    check("with no shim, the answer is the first python3, the one the old call ran",
          got == str(real) == want, "got %s, plain PATH lookup %s" % (got, want))

    got = resolve([shim.parent])
    check("only a refusing shim on PATH: the hook's own interpreter", got == REAL, "got %s" % got)

    got = resolve([empty])
    check("no python3 on PATH: the hook's own interpreter", got == REAL, "got %s" % got)

    rel_root = tmp / "relcwd"
    planted = real_python(rel_root / "bin")
    other = real_python(tmp / "real2")
    got = resolve(["bin", other.parent], cwd=rel_root)
    check("a relative PATH entry is never used (the cwd is not the hook's to choose)",
          got == str(other), "got %s (planted %s)" % (got, planted))

    advice = advice_wrapper(tmp / "advice")
    got = resolve([advice.parent, real.parent])
    check("a wrapper that prints advice and exits 0 is skipped (its script never ran)",
          got == str(real), "got %s" % got)

    stalled = stalled_python(tmp / "stalled")
    start = time.monotonic()
    got = resolve([stalled.parent, real.parent], timeout=0.5)
    took = time.monotonic() - start
    check("a probe that times out keeps its candidate (no verdict is not a refusal)",
          got == str(stalled), "got %s" % got)
    check("and the timeout bounds the wait", took < 10, "took %.1fs" % took)

    def no_tempdir(*_a, **_k):
        raise OSError("no writable temp dir")

    got = resolve([shim.parent, real.parent], mkdtemp=no_tempdir)
    check("no temp dir to probe with: the first candidate, as the old call would",
          got == str(shim), "got %s" % got)

    try:
        got = resolve([tmp / "missing", str(real) + "-not-a-dir", real.parent])
        check("missing and non-directory PATH entries are ignored", got == str(real), "got %s" % got)
    except Exception as exc:  # noqa: BLE001 - the contract is "never raises"
        bad("the resolver never raises", "%s: %s" % (type(exc).__name__, exc))

    # Only a refusal skips a candidate. Skipping on a struggling machine would hand
    # the script to an interpreter the hook never used (the 3.9 of the incident).
    killed = killed_once_python(tmp / "killed")
    got = resolve([killed.parent, real.parent])
    check("a probe killed by a signal keeps its candidate (no verdict, not a refusal)",
          got == str(killed), "got %s" % got)

    real_run = subprocess.run
    calls = {"n": 0}

    def eagain_first(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BlockingIOError(errno.EAGAIN, "Resource temporarily unavailable")
        return real_run(*args, **kwargs)

    got = resolve([real.parent, other.parent], run=eagain_first)
    check("a probe that cannot fork right now (EAGAIN) keeps its candidate",
          got == str(real), "got %s" % got)

    broken = unexecutable_python(tmp / "broken")
    got = resolve([broken.parent, real.parent])
    check("a candidate that cannot be executed at all is skipped",
          got == str(real), "got %s" % got)

    # Windows: the old call went through CreateProcess, which appends .exe only. A
    # WORKING python3.BAT sits earlier on PATH and PATHEXT names it, so a resolver
    # that walked PATHEXT (as the first version did) would pick it.
    win = tmp / "win"
    _exe(win / "python3.BAT", '#!/bin/sh\nexec "%s" "$@"\n' % REAL)
    exe = real_python(tmp / "winexe")
    exe_named = exe.parent / "python3.exe"
    exe.rename(exe_named)
    got = resolve([win, exe_named.parent], os_name="nt", env={"PATHEXT": ".BAT"})
    check("on Windows only python3.exe is a candidate, even past a working python3.BAT",
          got == str(exe_named), "got %s" % got)


# --- hooks under test -----------------------------------------------------------------

def hook_copy(tmp: Path, name: str, old: str, new: str, label: str):
    """A copy of hooks/<name> with one spawn replaced, beside a copy of _lib."""
    src = (HOOKS / name).read_text(encoding="utf-8")
    if src.count(old) != 1:
        bad("control for %s can be built" % label,
            "expected exactly one %r in %s, found %d" % (old, name, src.count(old)))
        return None
    d = tmp / ("ctl-" + label)
    if not (d / "_lib").exists():
        shutil.copytree(HOOKS / "_lib", d / "_lib")
    out = d / name
    out.write_text(src.replace(old, new), encoding="utf-8")
    return out


def hook_env(path_entries, **extra) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("DISCOVERABILITY_VERIFIER_BYPASS", "SCRIPT_PYTHON_WITNESS", "VAULT_ROOT")}
    env["PATH"] = os.pathsep.join(str(p) for p in path_entries)
    env.update({k: str(v) for k, v in extra.items()})
    return env


def run_hook(interpreter: str, hook: Path, payload: dict, env: dict, cwd: Path):
    return subprocess.run([interpreter, str(hook)], input=json.dumps(payload), env=env,
                          cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=180)


GAP = {"artifact": {"repo": "vault", "path": "skills/ours.md", "kind": "skill",
                    "commit": "abc", "name": "ours"},
       "suggestion": "wire it"}

STUB_VERIFIER = "import json\nprint(json.dumps({'gaps': [%r]}))\n" % (GAP,)

WITNESS_VERIFIER = ("import json, os\n"
                    "gaps = [%r] if os.environ.get('SCRIPT_PYTHON_WITNESS') == '1' else []\n"
                    "print(json.dumps({'gaps': gaps}))\n" % (GAP,))

# Needs Python 3.12 (PEP 701: the same quote and a backslash inside an f-string
# expression). Older interpreters reject the file before it prints anything.
PEP701_VERIFIER = (r'import json' "\n"
                   r'parts = ["a", "b"]' "\n"
                   r'joined = f"{"\n".join(parts)}"' "\n"
                   "print(json.dumps({'gaps': [%r]}))\n" % (GAP,))


def verify_case(tmp: Path, tag: str, verifier_src: str):
    """A vault, a transcript in which THIS session wrote skills/ours.md and closes,
    and a stub verifier. Returns (payload, extra env, cwd)."""
    vault = tmp / ("vault-" + tag)
    (vault / "skills").mkdir(parents=True, exist_ok=True)
    stub = tmp / ("verifier-%s.py" % tag)
    stub.write_text(verifier_src, encoding="utf-8")
    transcript = tmp / ("transcript-%s.jsonl" % tag)
    records = [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": CLOSING}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Write",
             "input": {"file_path": str(vault / "skills" / "ours.md")}}]}},
    ]
    transcript.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    payload = {"transcript_path": str(transcript), "cwd": str(vault)}
    extra = {"VAULT_ROOT": vault, "DISCOVERABILITY_VERIFIER_PATH": stub}
    return payload, extra, vault


def blocked(proc) -> bool:
    return proc.returncode == 2 and "BLOCKED by verify-discoverability-on-close" in proc.stderr


def verify_legs(tmp: Path) -> None:
    hook = HOOKS / "verify-discoverability-on-close.py"
    shim = refusing_shim(tmp / "vshim")
    real = real_python(tmp / "vreal")

    print("=== 2. verify-discoverability-on-close: past the shim ===")
    payload, extra, cwd = verify_case(tmp, "shim", STUB_VERIFIER)
    env = hook_env([shim.parent, real.parent], **extra)
    proc = run_hook(REAL, hook, payload, env, cwd)
    check("refusing shim first on PATH: the verifier runs and this session's gap blocks",
          blocked(proc), "exit %d; stderr: %s" % (proc.returncode, proc.stderr[-400:]))
    old = hook_copy(tmp, hook.name, NEW_SPAWN, OLD_SPAWN, "verify-old")
    if old:
        proc = run_hook(REAL, old, payload, env, cwd)
        check("control: with [\"python3\", ...] put back, the shim refuses and nothing blocks",
              proc.returncode == 0, "exit %d (the leg above cannot tell the two apart)" % proc.returncode)

    print("=== 3. verify-discoverability-on-close: the shell's python3, not the hook's ===")
    witness = witness_python(tmp / "witness")
    payload, extra, cwd = verify_case(tmp, "witness", WITNESS_VERIFIER)
    env = hook_env([witness.parent], **extra)
    proc = run_hook(REAL, hook, payload, env, cwd)
    check("the verifier runs under PATH's python3 (the witness mark is set) and blocks",
          blocked(proc), "exit %d; stderr: %s" % (proc.returncode, proc.stderr[-400:]))
    old = hook_copy(tmp, hook.name, NEW_SPAWN, "[sys.executable, ", "verify-sysexe")
    if old:
        proc = run_hook(REAL, old, payload, env, cwd)
        check("control: with sys.executable put back, the verifier runs unmarked and nothing blocks",
              proc.returncode == 0, "exit %d" % proc.returncode)

    print("=== 4. verify-discoverability-on-close: the measured incident ===")
    old_py = None
    for cand in ("/usr/bin/python3", "/usr/local/bin/python3.9", "/usr/bin/python3.9"):
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            try:
                ver = subprocess.run([cand, "-c", "import sys; print(sys.version_info[:2] < (3, 12))"],
                                     capture_output=True, text=True, encoding="utf-8",
                                     errors="replace", timeout=30).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                continue
            if ver == "True":
                old_py = cand
                break
    if sys.version_info < (3, 12) or old_py is None:
        print("SKIP  needs an interpreter older than 3.12 to run the hook and a 3.12+ one to run "
              "this suite (found %s, running %d.%d)" % (old_py, sys.version_info[0], sys.version_info[1]))
        return
    payload, extra, cwd = verify_case(tmp, "pep701", PEP701_VERIFIER)
    env = hook_env([real.parent], **extra)
    proc = run_hook(old_py, hook, payload, env, cwd)
    check("hook under %s, verifier needing 3.12: it runs and blocks" % old_py,
          blocked(proc), "exit %d; stderr: %s" % (proc.returncode, proc.stderr[-400:]))
    old = hook_copy(tmp, hook.name, NEW_SPAWN, "[sys.executable, ", "verify-sysexe")
    if old:
        proc = run_hook(old_py, old, payload, env, cwd)
        check("control: with sys.executable put back, the verifier dies under the hook's "
              "interpreter and the gate passes everything",
              proc.returncode == 0, "exit %d" % proc.returncode)


# Emits the key the hook reads. The real detector does not emit it, so the real
# hook surfaces nothing either way; that is MYC-4723's to fix, not this suite's.
DETECTOR_STUB = ("import json, sys\n"
                 "print(json.dumps({'keyword_conflict_count': 1, 'keyword_conflicts': [{"
                 "'new': {'file': sys.argv[1], 'line_no': 1, 'line_text': 'Always do X.'}, "
                 "'existing': {'file': 'rules/a.md', 'line_no': 2, 'line_text': 'Never do X.'}, "
                 "'confidence': 0.9}]}))\n")


def rule_conflict_legs(tmp: Path) -> None:
    print("=== 5. check-rule-conflicts-on-write: past the shim ===")
    hook = HOOKS / "check-rule-conflicts-on-write.py"
    if ('"%s"' % META) not in hook.read_text(encoding="utf-8"):
        bad("the vault layout this leg builds matches the hook", "no %r in %s" % (META, hook.name))
        return
    vault = tmp / "rvault"
    (vault / META / "scripts").mkdir(parents=True)
    (vault / "CLAUDE.md").write_text("# rules\n", encoding="utf-8")
    (vault / META / "scripts" / "check-rule-conflicts.py").write_text(DETECTOR_STUB, encoding="utf-8")
    shim = refusing_shim(tmp / "rshim")
    real = real_python(tmp / "rreal")
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(vault / "CLAUDE.md")}}
    env = hook_env([shim.parent, real.parent])
    proc = run_hook(REAL, hook, payload, env, vault)
    check("refusing shim first on PATH: the detector runs and its conflict is surfaced",
          proc.returncode == 0 and "rule-conflict detector" in proc.stdout,
          "exit %d; stdout: %s" % (proc.returncode, proc.stdout[-300:]))
    old = hook_copy(tmp, hook.name, NEW_SPAWN, OLD_SPAWN, "rule-old")
    if old:
        proc = run_hook(REAL, old, payload, env, vault)
        check("control: with [\"python3\", ...] put back, the shim refuses and nothing is surfaced",
              proc.returncode == 0 and "rule-conflict detector" not in proc.stdout,
              "exit %d; stdout: %s" % (proc.returncode, proc.stdout[-300:]))


def settings_lint_legs(tmp: Path) -> None:
    print("=== 6. pre-write-settings-lint: sys.executable first, unaffected by the shim (regression check) ===")
    hook = HOOKS / "pre-write-settings-lint.py"
    shim = refusing_shim(tmp / "lshim")
    target = tmp / "proj" / ".claude" / "settings.json"
    env = hook_env([shim.parent])
    bad_write = {"tool_name": "Write",
                 "tool_input": {"file_path": str(target), "content": '{"a": 1, "a": 2}'}}
    proc = run_hook(REAL, hook, bad_write, env, tmp)
    check("refusing shim first on PATH: a duplicate-key write is still blocked",
          proc.returncode == 2 and "BLOCKED by pre-write-settings-lint" in proc.stderr,
          "exit %d; stderr: %s" % (proc.returncode, proc.stderr[-300:]))
    good_write = {"tool_name": "Write",
                  "tool_input": {"file_path": str(target), "content": '{"a": 1}'}}
    proc = run_hook(REAL, hook, good_write, env, tmp)
    check("and a valid write passes", proc.returncode == 0, "exit %d" % proc.returncode)


def main() -> int:
    if os.name == "nt":
        print("SKIP  test_script_python.py: the fake interpreters are /bin/sh scripts (POSIX only)")
        return 0
    tmp = Path(tempfile.mkdtemp(prefix="test-script-python-"))
    try:
        resolver_legs(tmp)
        verify_legs(tmp)
        rule_conflict_legs(tmp)
        settings_lint_legs(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    print("=== summary: %d passed, %d failed ===" % (_counts["pass"], _counts["fail"]))
    return 0 if _counts["fail"] == 0 else 1


if __name__ == "__main__":
    # Windows cp1252-console safety: failure messages can quote vault paths.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
