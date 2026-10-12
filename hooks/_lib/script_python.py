"""script_python.py - the interpreter a hook runs a separate Python script with.

WHY THIS EXISTS. A hook that runs another Python script has to name an
interpreter, and the two obvious choices each fail somewhere:

  `subprocess.run(["python3", script, ...])` looks python3 up on PATH. Inside a
  Claude Code session a Python-tooling plugin puts a shim first on PATH that
  refuses exactly that shape, `python3 <script path>`: advice on stderr, exit 1,
  nothing run. The harness runs hooks with a PATH that has no shim, so the hook
  works in production, while every test that runs it from a session sees the
  child refused and the hook fail open.

  `sys.executable` is never the shim, but it is the HOOK's interpreter, and that
  can be older than the script the hook runs. Measured (MYC-5434): a Stop hook
  registered as `/usr/bin/python3` (3.9) ran a vault verifier that uses 3.12
  f-string syntax. Under 3.9 the verifier died with a SyntaxError before
  printing anything, the hook read the empty output as "no gaps", and the gate
  passed everything. The PATH python3 the harness resolves (a 3.14) ran it.

THE RULE.
  - A hook running a script it does NOT ship (a vault script, another repo's
    script) spawns `script_python()`: the first `python3` on PATH that actually
    runs a script file. In the harness that is the interpreter the old
    `["python3", ...]` already ran, so production behaviour does not change; in
    a session it steps past the shim.
  - A hook running a script it ships alongside itself (same install, same
    interpreter contract) uses `sys.executable` and does not need this module.

WHY A PROBE, NOT A NAME. The shim forwards `-c`, `-m` and `-` and refuses only
a script path, so a `-c` probe passes on exactly the machines this exists for
(tests/integration/lib/real_python.sh records the same trap). Each candidate
runs a tiny script FILE and must print that script's own output back, so any
wrapper that refuses, or prints advice and exits 0, is judged by what it does
rather than by where it lives.

ONLY A REFUSAL SKIPS A CANDIDATE. A candidate is skipped when it ran and did
not run the script (it exited without the probe's output), or when it cannot
be executed at all (missing, not executable, not a program). Anything that only
says the machine is struggling is no verdict on the candidate, and it is kept:
a probe that times out, one killed by a signal (an OOM killer), one that could
not start because fork hit a process limit. Skipping on those would hand a
script to an interpreter the hook never used, which on a loaded machine is the
3.9 interpreter of the incident above. When no candidate runs a script,
`sys.executable`: the hook is running, so it exists.

An empty or relative PATH entry is skipped. It resolves against the hook's cwd,
which is wherever the session is standing, and a cloned repo can put a
`bin/python3` there. On Windows only `python3.exe` is considered: the old call
went through CreateProcess, which appends `.exe` and nothing else, and a
`.bat` or `.cmd` candidate would hand the script's arguments to cmd.exe.

The probe writes into a file, not a pipe, so a grandchild that keeps a pipe
open cannot hold a timed-out probe (on Windows, subprocess.run waits on the
pipe after the kill with no timeout).

Never raises. Stdlib only; Python 3.9+; POSIX and Windows.
"""
from __future__ import annotations

import errno
import os
import shutil
import subprocess
import sys
import tempfile

# Printed by the probe script and required back. An exit status alone is too
# weak: a wrapper is free to print its advice and exit 0 without running anything.
_SENTINEL = "__script_python_runs_ok__"

# Seconds one probe may run before it counts as "no verdict" (kept, see above).
# It bounds each probe, not the whole resolution: with one shim on PATH (the
# usual case) a hook waits for one refusal, which takes milliseconds, and then
# for one probe of the interpreter it goes on to use.
PROBE_TIMEOUT_SEC = 5.0

# An exec that cannot happen: the candidate will never run this script.
_EXEC_IMPOSSIBLE = frozenset({errno.ENOENT, errno.ENOTDIR, errno.EACCES, errno.EPERM, errno.ENOEXEC})

_resolved = None  # per process: a hook resolves once, however many scripts it runs


def _candidates(name: str = "python3") -> list:
    """Absolute `name` executables on PATH, in PATH order, each listed once."""
    exts = [".exe"] if os.name == "nt" else [""]
    found = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry or not os.path.isabs(entry):
            continue
        for ext in exts:
            path = os.path.join(entry, name + ext)
            if path not in found and os.path.isfile(path) and os.access(path, os.X_OK):
                found.append(path)
    return found


def _probe(interpreter: str, script: str, out_path: str):
    """True: it ran the script. False: it refused, or can never run it. None: no verdict."""
    try:
        out = open(out_path, "wb")
    except OSError:
        return None  # our own temp file, not the candidate
    try:
        with out:
            proc = subprocess.run(
                [interpreter, script],
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.DEVNULL,
                timeout=PROBE_TIMEOUT_SEC,
            )
    except subprocess.TimeoutExpired:
        return None
    except OSError as exc:
        return False if exc.errno in _EXEC_IMPOSSIBLE else None
    except Exception:
        return False
    if proc.returncode < 0:
        return None  # killed by a signal: says nothing about the candidate
    try:
        with open(out_path, "rb") as fh:
            ran = _SENTINEL.encode("ascii") in fh.read(4096)
    except OSError:
        return None
    return proc.returncode == 0 and ran


def _resolve():
    """The first PATH candidate that is not shown to refuse a script, else None."""
    try:
        candidates = _candidates()
    except Exception:
        return None
    if not candidates:
        return None
    try:
        probe_dir = tempfile.mkdtemp(prefix="script-python-")
    except Exception:
        return candidates[0]  # cannot probe at all: keep what the old code ran
    try:
        probe = os.path.join(probe_dir, "probe.py")
        with open(probe, "w", encoding="ascii") as fh:
            fh.write("print(%r)\n" % _SENTINEL)
        for i, candidate in enumerate(candidates):
            out_path = os.path.join(probe_dir, "out-%d" % i)
            if _probe(candidate, probe, out_path) is not False:
                return candidate
        return None
    except Exception:
        return candidates[0]
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)


def script_python() -> str:
    """Interpreter for a script this hook does not ship. See the module docstring."""
    global _resolved
    if _resolved is None:
        _resolved = _resolve() or sys.executable
    return _resolved
