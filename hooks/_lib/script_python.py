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

NO VERDICT IS NOT A REFUSAL. A candidate whose probe times out (a loaded
machine) is kept: a refusing shim answers at once, and keeping it repeats the
old behaviour instead of jumping to an interpreter the hook never used. When no
candidate runs a script, `sys.executable`: the hook is running, so it exists.

An empty or relative PATH entry is skipped. It resolves against the hook's cwd,
which is wherever the session is standing, and a cloned repo can put a
`bin/python3` there.

Never raises. Stdlib only; Python 3.9+; POSIX and Windows.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

# Printed by the probe script and required back. An exit status alone is too
# weak: a wrapper is free to print its advice and exit 0 without running anything.
_SENTINEL = "__script_python_runs_ok__"

# Seconds one probe may run before it counts as "no verdict" (kept, see above).
# A refusing shim answers in milliseconds, so this only bounds what a loaded
# machine can add to the hook; the verdict on timeout is the old behaviour anyway.
PROBE_TIMEOUT_SEC = 5.0

_resolved = None  # per process: a hook resolves once, however many scripts it runs


def _candidates(name: str = "python3") -> list:
    """Absolute `name` executables on PATH, in PATH order, each listed once."""
    if os.name == "nt":
        exts = [e for e in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(os.pathsep) if e]
    else:
        exts = [""]
    found = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry or not os.path.isabs(entry):
            continue
        for ext in exts:
            path = os.path.join(entry, name + ext)
            if path not in found and os.path.isfile(path) and os.access(path, os.X_OK):
                found.append(path)
    return found


def _probe(interpreter: str, script: str):
    """True: it ran the script. False: it refused or could not start. None: no verdict."""
    try:
        proc = subprocess.run(
            [interpreter, script],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=PROBE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return False
    # Bytes, not text: decoding a refusing wrapper's output must not be able to raise.
    return proc.returncode == 0 and _SENTINEL.encode("ascii") in proc.stdout


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
        for candidate in candidates:
            if _probe(candidate, probe) is not False:
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
