#!/usr/bin/env python3
"""Controls for hooks/_lib/heavy_admission.py (MYC-5053), folded into
retry-budget.py's PreToolUse(Bash) hook rather than given its own slot.
Style follows hooks/test_retry_budget.py: stdlib only, plain script, exit 0
= all pass. H* drives the REAL retry-budget.py as a subprocess (stdin JSON,
HOME a temp dir). D*/C*/M*/L*/N* import heavy_admission directly and
replace read_signal / _count_running by attribute assignment on the loaded
module -- never a production env-var or file seam.

D: the 16 must-admit strings stay admitted even forced to critical memory
and an at-cap count -- detection, not a lucky reading, saves them.
C: the 15 must-detect strings resolve to some heavy class.
M: real planted processes prove the pgrep anchor (tsserver argv, tsx watch,
a zsh -c wrapper all count 0; a real next-build-shaped argv counts 1).
L: a real child process, real pgrep, a planted `ghp_`+36 token in argv AND
env -- absent from the child's real stdout/stderr/log; a mutant that echoes
`pgrep -lf` into the deny message must turn it RED.
N: two scratch, never-committed mutants -- a threshold mutant wrongly
ALLOWS a real critical/at-cap deny; a detection-widening mutant (raw
substring) wrongly DENIES must-admit strings.

Run: python3 hooks/test_heavy_admission.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE / "_lib"
MODULE = LIB / "heavy_admission.py"
RETRY_BUDGET = HERE / "retry-budget.py"

FAILURES: list[str] = []

def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok    {label}")
    else:
        FAILURES.append(label)
        print(f"  FAIL  {label}" + (f"\n        {detail}" if detail else ""))

def _load(path=MODULE, name="heavy_admission_under_test"):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

IDLE = {"platform": "darwin", "pressure_level": 1, "memorystatus_level": 57,
        "swap_used": 1 * 2 ** 30, "ram": 16 * 2 ** 30}
CRITICAL = {**IDLE, "pressure_level": 4}

MUST_ADMIT = [
    'git commit -m "fix: cargo build flake"',
    'rg "next build" docs/',
    'echo "next build is slow"',
    '# just a comment about next build\nls',
    'gh pr create --title x --body "pnpm run build passes"',
    'cat <<EOF2\ncargo test\nEOF2',
    'git log --grep "tsc --noEmit"',
    'git checkout -b fix-tsc-errors',
    'grep -rn "playwright test" .github/',
    'cat README.md # see pnpm build',
    'pkill -f "next build"',
    'pgrep -f "pnpm run build" | wc -l',
    'ps -axo pid,comm | grep "next build"',
    'tsc -p apps/x/tsconfig.json --noEmit',
    'vitest run src/a.test.ts',
    'pnpm vitest run src/a.test.ts 2>&1 | tail -5',
]
MUST_DETECT = [
    ('pnpm vitest run 2>&1 | tail -40', 'test_suite'),
    ('nohup pnpm vitest run > /tmp/v.log 2>&1; echo EXIT=$? >> /tmp/v.log', 'test_suite'),
    ('pnpm test', 'test_suite'),
    ('pnpm typecheck', 'tsc_full'),
    ('pnpm -C apps/web build', 'build'),
    ('pnpm --filter=web build', 'build'),
    ('pnpm -F web build', 'build'),
    ('turbo run build', 'build'),
    ('tsc -p . --noEmit', 'tsc_full'),
    ('mkdir -p dist && npx tsc --noEmit', 'tsc_full'),
    ('cargo clippy', 'cargo'),
    ('CARGO_BUILD_JOBS=4 nice -n 10 cargo test --lib x', 'cargo'),
    ('cd apps/web && pnpm run build', 'build'),
    ('bash -c "pnpm run build"', 'build'),
    ('yarn workspace web build', 'build'),
]


# ------------------------------------------------------------- D / C: lists ---
def leg_must_admit_under_critical_and_at_cap() -> None:
    mod = _load()
    for cmd in MUST_ADMIT:
        mod.read_signal = lambda: CRITICAL
        mod._count_running = lambda cls: 999
        check(f"D critical+at-cap admits: {cmd[:50]!r}", mod.admit(cmd) == 0)

def leg_must_detect() -> None:
    for cmd, want in MUST_DETECT:
        got = None
        try:
            spec = importlib.util.spec_from_file_location("heavy_admission_c", MODULE)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            got = m.detect_class(cmd)
        except Exception as exc:  # pragma: no cover - detection must never raise
            check(f"C detects: {cmd[:50]!r}", False, f"raised {exc!r}")
            continue
        check(f"C detects: {cmd[:50]!r} -> {want}", got == want, f"got {got!r}")


# --------------------------------------------------------- M: planted procs ---
class _Planted:
    """Real child processes with a chosen argv; killed in a finally block."""

    def __init__(self):
        self.procs: list[subprocess.Popen] = []

    def spawn(self, *argv: str, env=None) -> None:
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", *argv],
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.procs.append(p)

    def settle(self) -> None:
        time.sleep(0.6)

    def cleanup(self) -> None:
        for p in self.procs:
            p.terminate()
        for p in self.procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=5)

def leg_counting_anchors_on_a_boundary() -> None:
    mod = _load()
    planted = _Planted()
    try:
        planted.spawn("node", "/fake/tsserver", "--cancellationPipeName", "/tmp/tscancellation-abc.tmp*")
        planted.spawn("tsx", "watch", "--tsconfig", "tsconfig.json", "src/server.ts")
        planted.spawn("zsh", "-c", "sleep 30; next build")
        planted.settle()
        check("M tsserver-shaped argv counts 0 for tsc_full", mod._count_running("tsc_full") == 0)
        check("M tsx-watch-shaped argv counts 0 for tsc_full (2nd pass)", mod._count_running("tsc_full") == 0)
        check("M a zsh -c wrapper counts 0 for build (process NAME is a shell)",
              mod._count_running("build") == 0)
        planted.spawn("node", "/fake/path/next/dist/bin/next", "build")
        planted.settle()
        check("M a real next-build-shaped argv counts 1", mod._count_running("build") == 1)
    finally:
        planted.cleanup()


# --------------------------------------------------- L: leak + positive control ---
_DRIVER = (
    "import sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "import heavy_admission as ha\n"
    "ha.read_signal = lambda: {'platform': 'darwin', 'pressure_level': 1, "
    "'memorystatus_level': 57, 'swap_used': 1 * 2**30, 'ram': 16 * 2**30}\n"
    "sys.exit(ha.admit(sys.argv[2]))\n"
)

_LEAK_TOKEN = "ghp_" + "A" * 36

# A mutant that switches `pgrep -f` to the leaking `-lf` listing form and
# stuffs it into the deny headline -- the shape block-env-dump.py documents
# as exposing a titled process's full command line.
_LEAK_MUTATION = [
    ('pids = [p for p in _run(["pgrep", "-f", _PGREP_PATTERN[cls]]).split() if int(p) not in ancestors]',
     '_leak = _run(["pgrep", "-lf", _PGREP_PATTERN[cls]]); globals()["_LEAK"] = _leak\n'
     '    pids = [ln.split()[0] for ln in _leak.splitlines() if ln.split() and int(ln.split()[0]) not in ancestors]'),
    ('headline = f"a {cls} is already running ({running} of cap {cap})"',
     'headline = f"a {cls} is already running ({running} of cap {cap}): " + globals().get("_LEAK", "")'),
]

def _mutated_copy(subs: list[tuple[str, str]], tag: str) -> Path:
    """A scratch copy of heavy_admission.py with `subs` applied, in its own
    tempdir (never written into the repo)."""
    src = MODULE.read_text(encoding="utf-8")
    for old, new in subs:
        assert old in src, f"negative-control anchor text not found ({tag}): {old!r}"
        src = src.replace(old, new, 1)
    scratch = Path(tempfile.mkdtemp(prefix=f"heavy-admission-{tag}-")) / "_libdir"
    scratch.mkdir()
    (scratch / "heavy_admission.py").write_text(src, encoding="utf-8")
    for sib in ("shell_parse.py", "cmd_env.py", "guard_telemetry.py"):
        shutil.copy2(LIB / sib, scratch / sib)
    return scratch

def _run_driver(libdir: Path, command: str, env: dict) -> subprocess.CompletedProcess:
    driver = Path(tempfile.mkdtemp(prefix="heavy-admission-driver-")) / "drive.py"
    driver.write_text(_DRIVER, encoding="utf-8")
    try:
        return subprocess.run([sys.executable, str(driver), str(libdir), command],
                               capture_output=True, text=True, env=env, timeout=30)
    finally:
        shutil.rmtree(driver.parent, ignore_errors=True)

def leg_leak_control() -> None:
    home = Path(tempfile.mkdtemp(prefix="heavy-admission-leak-home-"))
    guard_log = home / "guard-fires.jsonl"
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "GUARD_FIRES_LOG": str(guard_log)}
    planted = _Planted()
    try:
        # argv AND env both carry the token; the planted argv also matches
        # the "build" pgrep pattern so counting (not memory) drives the deny.
        planted.spawn("node", "/fake/path/next/dist/bin/next", "build", _LEAK_TOKEN,
                       env={**os.environ, "FAKE_SECRET": _LEAK_TOKEN})
        planted.settle()

        r = _run_driver(LIB, "next build", env)
        check("L real code denies at cap (premise for the leak check)", r.returncode == 2, f"rc={r.returncode}")
        haystacks = [r.stdout, r.stderr]
        if guard_log.exists():
            haystacks.append(guard_log.read_text(encoding="utf-8", errors="replace"))
        check("L token absent from the child's real stdout/stderr/telemetry log",
              not any(_LEAK_TOKEN in h for h in haystacks),
              f"stdout={r.stdout!r} stderr={r.stderr!r}")

        mutant_dir = _mutated_copy(_LEAK_MUTATION, "leak-positive-control")
        try:
            rm = _run_driver(mutant_dir, "next build", env)
            leaked = _LEAK_TOKEN in rm.stdout or _LEAK_TOKEN in rm.stderr
            check("L positive control: the pgrep -lf mutant DOES leak (proves the check has teeth)",
                  leaked, f"mutant stdout={rm.stdout!r} stderr={rm.stderr!r}")
        finally:
            shutil.rmtree(mutant_dir.parent, ignore_errors=True)
    finally:
        planted.cleanup()
        shutil.rmtree(home, ignore_errors=True)


# --------------------------------------------------------- N: negative controls ---
_THRESHOLD_MUTATION = [
    ("PRESSURE_LEVEL_CRITICAL = 4", "PRESSURE_LEVEL_CRITICAL = 999"),
    ("SWAP_OVER_RAM_CRITICAL = 0.50", "SWAP_OVER_RAM_CRITICAL = 999.0"),
    ("MEMORYSTATUS_LEVEL_CRITICAL = 10", "MEMORYSTATUS_LEVEL_CRITICAL = -1"),
    ("MEM_AVAILABLE_OVER_TOTAL_CRITICAL = 0.10", "MEM_AVAILABLE_OVER_TOTAL_CRITICAL = -1.0"),
    ('CLASS_CAPS = {"build": 1, "verify": 1, "test_suite": 1, "tsc_full": 1, "playwright": 1, "cargo": 2}',
     'CLASS_CAPS = {"build": 999, "verify": 999, "test_suite": 999, "tsc_full": 999, "playwright": 999, "cargo": 999}'),
]
# A raw-substring widening: three must-admit strings contain these phrases
# verbatim inside quotes/comments, so a mutant that stops resolving real
# argv tokens and instead re.searches the whole command must catch them too.
_DETECTION_WIDENING_MUTATION = [
    ('    cleaned = strip_noncode(strip_heredoc_bodies(command))\n'
     '    for _sep, seg in split_segments_with_seps(cleaned):',
     '    if "next build" in command or "tsc --noEmit" in command or "playwright test" in command:\n'
     '        return "build"\n'
     '    cleaned = strip_noncode(strip_heredoc_bodies(command))\n'
     '    for _sep, seg in split_segments_with_seps(cleaned):'),
]

def leg_negative_control_threshold_mutant() -> None:
    mutant_dir = _mutated_copy(_THRESHOLD_MUTATION, "threshold")
    try:
        mod = _load(mutant_dir / "heavy_admission.py", "heavy_admission_threshold_mutant")
        mod.read_signal = lambda: CRITICAL
        mod._count_running = lambda cls: 0
        check("N threshold mutant wrongly ALLOWS a critical-memory deny",
              mod.admit("next build") == 0)
        mod.read_signal = lambda: IDLE
        mod._count_running = lambda cls: 1
        check("N threshold mutant wrongly ALLOWS an at-cap deny",
              mod.admit("next build") == 0)
    finally:
        shutil.rmtree(mutant_dir.parent, ignore_errors=True)

def leg_negative_control_detection_widening_mutant() -> None:
    mutant_dir = _mutated_copy(_DETECTION_WIDENING_MUTATION, "widening")
    try:
        mod = _load(mutant_dir / "heavy_admission.py", "heavy_admission_widening_mutant")
        turned_red = []
        for cmd in ('rg "next build" docs/', 'git log --grep "tsc --noEmit"',
                    'grep -rn "playwright test" .github/'):
            mod.read_signal = lambda: CRITICAL
            mod._count_running = lambda cls: 0
            if mod.admit(cmd) != 0:
                turned_red.append(cmd)
        check("N detection-widening mutant wrongly DENIES must-admit strings",
              len(turned_red) == 3, f"only {turned_red} turned red")
    finally:
        shutil.rmtree(mutant_dir.parent, ignore_errors=True)


# ---------------------------------------------------------- H: hook-level ---
def _payload(command: str, call_id: str) -> str:
    return json.dumps({"session_id": "heavy-admission-test", "hook_event_name": "PreToolUse",
                        "tool_name": "Bash", "tool_input": {"command": command}, "tool_use_id": call_id})

def _run_retry_budget(env: dict, command: str, call_id: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(RETRY_BUDGET)], input=_payload(command, call_id),
                           capture_output=True, text=True, env=env, timeout=30)

def leg_hook_level_via_retry_budget() -> None:
    home = Path(tempfile.mkdtemp(prefix="heavy-admission-hook-home-"))
    tmp = Path(tempfile.mkdtemp(prefix="heavy-admission-hook-tmp-"))
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "TMPDIR": str(tmp)}
    env.pop("HEAVY_ADMISSION_BYPASS", None)
    planted = _Planted()
    try:
        r = _run_retry_budget(env, "ls -la", "toolu_h_allow")
        check("H a clean command allows via the real retry-budget.py", r.returncode == 0)

        planted.spawn("node", "/fake/path/next/dist/bin/next", "build")
        planted.settle()
        r = _run_retry_budget(env, "next build", "toolu_h_deny")
        check("H a heavy command at cap denies via the real retry-budget.py (rc=2)", r.returncode == 2)
        check("H the deny message names the class and the bypass var",
              "build" in r.stderr and "HEAVY_ADMISSION_BYPASS=1" in r.stderr, r.stderr[:200])

        env_bypass = {**env, "HEAVY_ADMISSION_BYPASS": "1"}
        r = _run_retry_budget(env_bypass, "next build", "toolu_h_bypass")
        check("H HEAVY_ADMISSION_BYPASS=1 admits the same at-cap command", r.returncode == 0)
    finally:
        planted.cleanup()
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    print("heavy_admission controls")
    leg_must_admit_under_critical_and_at_cap()
    leg_must_detect()
    leg_counting_anchors_on_a_boundary()
    leg_leak_control()
    leg_negative_control_threshold_mutant()
    leg_negative_control_detection_widening_mutant()
    leg_hook_level_via_retry_budget()
    if FAILURES:
        print(f"\n{len(FAILURES)} control(s) FAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nall heavy_admission controls passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
