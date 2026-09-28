#!/usr/bin/env python3
"""Controls for heavy-command-admission.py.

Cases (task letters a-k; a2/c2 are closely-related extras, not separate
letters): a/a2 idle + warn-level-alone both allow silently; b critical
pressure denies with the reading in the message; c/c2 swap>=50%RAM (macOS)
and MemAvailable<10% (Linux) both deny; d the running-count cap denies at
cap, allows one below; e a non-heavy command never even calls a reader
(proven with a call counter, not just the exit code -- a reader that raised
would ALSO read as allow through the fail-open path, so only the counter
tells the two apart); f narrowed tsc/vitest forms are allowed even under a
reading that would otherwise deny (proves detection, not policy, is what
let them through); g detection survives env-var/nice/cd/pnpm-filter
prefixes; h the inline and session-env override both allow and write
exactly one override-log line; i a raising reader still allows and writes
exactly one error-log line; j drives real pgrep against a real planted
process carrying a fake credential in argv+env and asserts it never reaches
stdout/stderr/either log; k mutates a scratch, never-committed copy with
every threshold neutered and shows the same scenarios as b/c/d now
(wrongly) allow -- proving a/b/c/d actually depend on the real constants.

Drives the hook by importing it as a module (hyphenated filename, so via
importlib.util.spec_from_file_location) and monkeypatching read_signal /
_count_running -- never a production env-var or file seam, so an agent
cannot fake an idle machine. HOME is pointed at a tempdir for the whole run
so no case ever touches the real ~/.claude/heavy-admission-*.log.

Run: python3 hooks/test_heavy_command_admission.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOOK_PATH = HERE / "heavy-command-admission.py"
RAM = 16 * 2 ** 30
FAILURES: list[str] = []


def check(label, got, want):
    if got == want:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}: got {got!r}, want {want!r}")
        FAILURES.append(label)


def _load(path=HOOK_PATH, name="heavy_command_admission"):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _call(mod, command: str) -> tuple[int, str, str]:
    """Drive mod.main() with a Bash payload on stdin; return (exit, stdout, stderr)."""
    old_stdin = sys.stdin
    sys.stdin = io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}))
    out_buf, err_buf = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            code = mod.main()
    finally:
        sys.stdin = old_stdin
    return code, out_buf.getvalue(), err_buf.getvalue()


def _idle_signal():
    return {"platform": "darwin", "pressure_level": 1, "swap_used_bytes": 1.0 * 2 ** 20, "ram_bytes": RAM}


def _run_a_to_i(mod, home: Path):
    override_log = home / ".claude" / "heavy-admission-overrides.log"
    error_log = home / ".claude" / "heavy-admission-errors.log"

    # -- a: idle -> allow, no output. a2: warn-level (2) alone -> still allow.
    mod.read_signal, mod._count_running = _idle_signal, lambda cls: 0
    check("a heavy + idle -> allow, no output", _call(mod, "next build"), (0, "", ""))
    mod.read_signal = lambda: {**_idle_signal(), "pressure_level": 2}
    check("a2 warn-level alone must not deny", _call(mod, "next build"), (0, "", ""))

    # -- b: critical pressure -> deny; reading is in the message.
    mod.read_signal = lambda: {**_idle_signal(), "pressure_level": 4}
    code, _out, err = _call(mod, "next build")
    check("b critical pressure -> deny", code, 2)
    check("b reason contains the pressure reading", "pressure level 4" in err, True)

    # -- c: swap >= 50% RAM (macOS) -> deny. c2: MemAvailable < 10% (Linux) -> deny.
    mod.read_signal = lambda: {"platform": "darwin", "pressure_level": 1,
                                "swap_used_bytes": RAM * 0.6, "ram_bytes": RAM}
    code, _out, err = _call(mod, "cargo build")
    check("c swap>=50%RAM -> deny", code, 2)
    check("c reason contains the swap reading", "swap" in err and "RAM" in err, True)
    mod.read_signal = lambda: {"platform": "linux", "mem_total_kb": 16_000_000,
                                "mem_available_kb": 1_000_000, "swap_total_kb": 0, "swap_free_kb": 0}
    check("c2 linux MemAvailable<10% -> deny", _call(mod, "cargo test")[0], 2)

    # -- d: class cap. next_build cap=1, cargo cap=2.
    mod.read_signal, mod._count_running = _idle_signal, lambda cls: 1
    check("d next_build at cap(1) -> deny", _call(mod, "next build")[0], 2)
    mod._count_running = lambda cls: 0
    check("d next_build below cap -> allow", _call(mod, "next build"), (0, "", ""))
    mod._count_running = lambda cls: 2
    check("d cargo at cap(2) -> deny", _call(mod, "cargo build")[0], 2)
    mod._count_running = lambda cls: 1
    check("d cargo below cap(2) -> allow", _call(mod, "cargo build"), (0, "", ""))

    # -- e: non-heavy command never even calls a reader (counter, not just exit code --
    # a raising reader ALSO reads as allow through the fail-open path).
    calls = []

    def _unexpected_signal():
        calls.append("signal")
        raise AssertionError("read_signal must not be called for a non-heavy command")

    def _unexpected_count(cls):
        calls.append("count")
        raise AssertionError("_count_running must not be called for a non-heavy command")

    mod.read_signal, mod._count_running = _unexpected_signal, _unexpected_count
    check("e non-heavy -> allow", _call(mod, "ls -la"), (0, "", ""))
    check("e readers never called", calls, [])

    # -- f: narrowed forms allowed even under a reading that would otherwise deny.
    mod.read_signal = lambda: {**_idle_signal(), "pressure_level": 4}
    mod._count_running = lambda cls: 99
    for cmd in ("tsc -p apps/x/tsconfig.json --noEmit", "vitest run src/a.test.ts",
                "pnpm vitest run src/a.test.ts"):
        check(f"f narrowed allowed: {cmd}", _call(mod, cmd), (0, "", ""))

    # -- g: detection survives prefixes (pure function; also end-to-end under idle).
    mod.read_signal, mod._count_running = _idle_signal, lambda cls: 0
    for cmd, want_cls in (
        ("CARGO_BUILD_JOBS=4 nice -n 10 cargo test --lib x", "cargo"),
        ("cd apps/web && pnpm run build", "next_build"),
        ("pnpm --filter web build", "next_build"),
    ):
        check(f"g detect_class prefix form: {cmd}", mod.detect_class(cmd), want_cls)
        check(f"g end-to-end idle allow: {cmd}", _call(mod, cmd), (0, "", ""))

    # -- h: override (inline, then session-env) -> allow + exactly one override-log line.
    mod.read_signal = lambda: {**_idle_signal(), "pressure_level": 2, "swap_used_bytes": 3 * 2 ** 30}
    mod._count_running = lambda cls: 0
    before = override_log.read_text(encoding="utf-8") if override_log.exists() else ""
    check("h inline override -> allow", _call(mod, "HEAVY_ADMISSION_OVERRIDE=1 next build"), (0, "", ""))
    added = (override_log.read_text(encoding="utf-8") if override_log.exists() else "")[len(before):]
    check("h override log grew by exactly one line", len(added.strip().splitlines()), 1)
    check("h override log line names class+pressure+swap",
          all(s in added for s in ("class=next_build", "pressure_level=2", "swap_used_gb=3")), True)
    before = override_log.read_text(encoding="utf-8")
    os.environ["HEAVY_ADMISSION_OVERRIDE"] = "1"
    try:
        check("h session-env override -> allow", _call(mod, "next build"), (0, "", ""))
    finally:
        os.environ.pop("HEAVY_ADMISSION_OVERRIDE", None)
    added = override_log.read_text(encoding="utf-8")[len(before):]
    check("h session-env override also logs exactly one line", len(added.strip().splitlines()), 1)

    # -- i: a raising reader -> allow + exactly one error-log line.
    def _raise():
        raise RuntimeError("simulated sysctl failure")
    mod.read_signal = _raise
    before = error_log.read_text(encoding="utf-8") if error_log.exists() else ""
    check("i reader raises -> allow", _call(mod, "next build"), (0, "", ""))
    added = (error_log.read_text(encoding="utf-8") if error_log.exists() else "")[len(before):]
    check("i error log grew by exactly one line", len(added.strip().splitlines()), 1)
    check("i error log names exception type + message",
          "RuntimeError" in added and "simulated sysctl failure" in added, True)


def _case_j(home: Path):
    """Leak control: real pgrep against a real process carrying a fake
    credential in argv AND env. _count_running is left REAL (only
    read_signal is forced critical) so pgrep genuinely enumerates."""
    print("\ncase j: leak control against real processes")
    mod = _load(name="heavy_command_admission_j")
    token = "ghp_" + "A" * 36
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", "next build", token],
        env={**os.environ, "FAKE_SECRET": token},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.5)
        running = mod._count_running("next_build")
        check("j pgrep (real) enumerates the planted process", running >= 1, True)

        mod.read_signal = lambda: {"platform": "darwin", "pressure_level": 4,
                                    "swap_used_bytes": 10 * 2 ** 30, "ram_bytes": RAM}
        code, out, err = _call(mod, "next build")
        check("j denies under the forced-critical reading", code, 2)

        haystacks = [out, err]
        for name in ("heavy-admission-errors.log", "heavy-admission-overrides.log"):
            p = home / ".claude" / name
            if p.exists():
                haystacks.append(p.read_text(encoding="utf-8", errors="replace"))
        check("j fake credential never appears in stdout/stderr/logs",
              any(token in h for h in haystacks), False)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def _case_k():
    """Negative control: neuter every threshold in a SCRATCH copy (tempdir,
    never written into the repo, removed in `finally`) and show the b/c/d
    scenarios now (wrongly) allow -- proving a-d depend on the real values."""
    print("\ncase k: negative control (scratch copy, every threshold neutered)")
    src = HOOK_PATH.read_text(encoding="utf-8")
    subs = [
        ("PRESSURE_LEVEL_CRITICAL = 4", "PRESSURE_LEVEL_CRITICAL = 999"),
        ("SWAP_USED_OVER_RAM_CRITICAL = 0.50", "SWAP_USED_OVER_RAM_CRITICAL = 999.0"),
        ("MEM_AVAILABLE_OVER_TOTAL_CRITICAL = 0.10", "MEM_AVAILABLE_OVER_TOTAL_CRITICAL = -1.0"),
        ('"next_build": 1, "verify": 1, "tsc_full": 1,\n'
         '    "vitest_unscoped": 1, "playwright": 1, "cargo": 2,',
         '"next_build": 999, "verify": 999, "tsc_full": 999,\n'
         '    "vitest_unscoped": 999, "playwright": 999, "cargo": 999,'),
    ]
    broken = src
    for old, new in subs:
        assert old in broken, f"negative-control anchor text not found: {old!r}"
        broken = broken.replace(old, new, 1)
    assert broken != src

    tmpdir = Path(tempfile.mkdtemp(prefix="heavy-admission-negctl-"))
    try:
        scratch = tmpdir / "heavy-command-admission-BROKEN.py"
        scratch.write_text(broken, encoding="utf-8")
        bmod = _load(scratch, "heavy_command_admission_broken")

        bmod.read_signal = lambda: {**_idle_signal(), "pressure_level": 4}
        bmod._count_running = lambda cls: 0
        code_b, _o, _e = _call(bmod, "next build")

        bmod.read_signal = lambda: {"platform": "darwin", "pressure_level": 1,
                                     "swap_used_bytes": RAM * 0.6, "ram_bytes": RAM}
        bmod._count_running = lambda cls: 0
        code_c, _o, _e = _call(bmod, "cargo build")

        bmod.read_signal, bmod._count_running = _idle_signal, lambda cls: 1
        code_d, _o, _e = _call(bmod, "next build")

        print("  command: in-memory scratch copy of heavy-command-admission.py with"
              " PRESSURE_LEVEL_CRITICAL/SWAP_USED_OVER_RAM_CRITICAL/"
              "MEM_AVAILABLE_OVER_TOTAL_CRITICAL/CLASS_CAPS all neutered;"
              " re-run the b/c/d readings")
        print(f"  output:  b(critical pressure)={code_b}  c(swap 60%)={code_c}  "
              f"d(at cap)={code_d}  (0 == wrongly ALLOW on all three)")

        check("k broken copy wrongly allows the b-shape (critical pressure)", code_b, 0)
        check("k broken copy wrongly allows the c-shape (swap 60%)", code_c, 0)
        check("k broken copy wrongly allows the d-shape (at cap)", code_d, 0)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)  # broken copy never committed


def main() -> int:
    home = Path(tempfile.mkdtemp(prefix="heavy-admission-test-"))
    saved = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE", "HEAVY_ADMISSION_OVERRIDE")}
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)
    os.environ.pop("HEAVY_ADMISSION_OVERRIDE", None)
    try:
        mod = _load()
        _run_a_to_i(mod, home)
        _case_j(home)
        _case_k()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(home, ignore_errors=True)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} case(s): {', '.join(FAILURES)}")
        return 1
    print("All cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
