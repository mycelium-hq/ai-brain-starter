#!/usr/bin/env python3
"""Controls for hooks/_lib/heavy_admission.py (MYC-5053), folded into
retry-budget.py's PreToolUse(Bash) hook. Stdlib only, plain script, exit 0 =
all pass, in the style of hooks/test_retry_budget.py.

D/C: must-admit / must-detect corpora, forced critical memory + at-cap.
A: memory-first ordering, visible fail-open, the advertised inline bypass.
M: counting logic on real and synthetic process rows -- an ancestor chain
already holding a match doesn't count again; shells never count.
G: `git push` classifies `verify` only when the repo's own pre-push hook is
heavy, against real (hand-built, no `git init` needed) `.git/hooks/`.
L: a real child process with a secret in its argv never reaches admit()'s
own output/log; a direct `ps -ww -o args=` read of that SAME pid proves the
secret was retrievable, so the check has teeth.
N: scratch, never-committed mutants (attribute patches on the loaded module,
never a rewritten source file) -- neutered thresholds, a raw-substring
widening, and a deleted shell filter must each wrongly flip a verdict.
H: drives the REAL retry-budget.py as a subprocess.

Run: python3 hooks/test_heavy_admission.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ["GUARD_FIRES_LOG"] = os.path.join(tempfile.mkdtemp(prefix="heavy-admission-telemetry-"), "fires.jsonl")
# ^ BEFORE the first module load, for every leg below: guard_telemetry.LOG_PATH
# binds this at ITS OWN first import, which a fresh heavy_admission load
# triggers transitively. Without this, every run appends fake `blocked`
# records to the operator's REAL ~/.claude/guard-fires.jsonl.

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

def _load(name: str = "heavy_admission_under_test"):
    spec = importlib.util.spec_from_file_location(name, MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _admit(mod, command: str, cwd=None):
    """admit() with stdout+stderr captured (merged) and log_fire recorded:
    (rc, output, statuses). log_fire is swapped for an in-memory recorder --
    use a DIRECT mod.admit() call instead when a leg needs the REAL telemetry
    file write exercised (e.g. the leak check)."""
    fires, out, err = [], io.StringIO(), io.StringIO()
    mod.log_fire = lambda name, status="fired", **ctx: fires.append(status)
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = mod.admit(command, cwd)
    return rc, out.getvalue() + err.getvalue(), fires

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
    # correctness-redesign miss-list (both reviews) -----------------------
    ('pnpm -C apps/web exec tsc --noEmit', 'tsc_full'),
    ('pnpm --filter web exec tsc --noEmit', 'tsc_full'),
    ('pnpm -r exec tsc --noEmit', 'tsc_full'),
    ('pnpm tsc --noEmit', 'tsc_full'),
    ('pnpm next build', 'build'),
    ('pnpm playwright test', 'playwright'),
    ('pnpm turbo run build', 'build'),
    ('env -u EQUIPO_DATABASE_URL npx vitest run', 'test_suite'),
    ('env NODE_OPTIONS=--max-old-space-size=4096 next build', 'build'),
    ('./node_modules/.bin/next build', 'build'),
    ('node_modules/.bin/tsc --noEmit', 'tsc_full'),
    ('~/.cargo/bin/cargo build', 'cargo'),
    ('npx -y tsc --noEmit', 'tsc_full'),
    ('vitest run --config vite.config.ts', 'test_suite'),
    ('vitest -c vitest.config.ts', 'test_suite'),
    ('vitest --pool forks', 'test_suite'),
    ('vitest run --maxWorkers 2', 'test_suite'),
    ('vitest --shard 1/4', 'test_suite'),
    ('vitest run --bail 1', 'test_suite'),
    ('pnpm -w build', 'build'),
    ('pnpm -w typecheck', 'tsc_full'),
    ('bash -e -c "pnpm run build"', 'build'),
    ('bash -o pipefail -c "pnpm run build"', 'build'),
    ('bash --login -c "pnpm run build"', 'build'),
    ('pnpm tauri build', 'build'),
    ('next build>/tmp/b.log', 'build'),
    ('pnpm build>out.log', 'build'),
    ('cargo --locked build', 'cargo'),
    ('time -p cargo build', 'cargo'),
    ('gtimeout 900 cargo build', 'cargo'),
]


# ---------------------------------------------------------- D / C: corpora ---
def leg_corpora() -> None:
    mod = _load()
    mod.read_signal = lambda: CRITICAL
    mod._count_running = lambda cls, snap: 999
    for cmd in MUST_ADMIT:
        check(f"D critical+at-cap admits: {cmd[:50]!r}", mod.admit(cmd) == 0)
    for cmd, want in MUST_DETECT:
        try:
            got = mod.detect_class(cmd)
        except Exception as exc:  # detection must never raise
            got = f"raised {exc!r}"
        check(f"C detects: {cmd[:50]!r} -> {want}", got == want, f"got {got!r}")


# --------------------------------------------------------------- A: decision --
def leg_decision() -> None:
    def _raise_sig():
        raise TimeoutError("reader stalled")

    mod = _load("heavy_admission_a_critical")
    mod.read_signal = lambda: CRITICAL
    mod._count_running = lambda cls, snap: (_ for _ in ()).throw(RuntimeError("must not count"))
    check("A critical memory denies WITHOUT counting", _admit(mod, "next build")[0] == 2)

    mod = _load("heavy_admission_a_error")
    mod.read_signal = _raise_sig
    rc, out, fires = _admit(mod, "next build")
    check("A an internal error admits VISIBLY (additionalContext + log_fire)",
          rc == 0 and "unmeasured (TimeoutError)" in out and fires == ["warned"], f"rc={rc} out={out!r} {fires}")

    mod = _load("heavy_admission_a_bypass")
    mod.read_signal = lambda: IDLE
    mod._count_running = lambda cls, snap: 1
    rc, _out, fires = _admit(mod, "HEAVY_ADMISSION_BYPASS=1 next build")
    check("A the advertised inline bypass admits at cap, logged", rc == 0 and fires == ["bypassed"], f"rc={rc} {fires}")

    mod = _load("heavy_admission_a_hint")
    mod.read_signal = lambda: CRITICAL
    rc, out, _fires = _admit(mod, "next build")
    check("A a critical-memory deny never says 'the running'", rc == 2 and "the running" not in out, out)


# ------------------------------------------------------- M: counting logic ---
def _sleeper() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def _snapshot_of(mod, plants: dict) -> dict:
    """{pid: (REAL ppid/ucomm, FAKE argv)} for exactly the given {proc: argv}
    pairs. Restricting to what we planted removes the whole-machine flake a
    prior pgrep-based version hit; the REAL ucomm/ppid still come from a REAL
    `_read_snapshot()` call, so a real shell's real ucomm is still real."""
    real = mod._read_snapshot()
    return {p.pid: (real[p.pid][0], real[p.pid][1], argv) for p, argv in plants.items()}

def leg_counting() -> None:
    mod = _load("heavy_admission_m")
    time.sleep(0.3)
    tsserver = _sleeper()
    tsx = _sleeper()
    real_next = _sleeper()
    try:
        snap = _snapshot_of(mod, {
            tsserver: ["node", "/fake/tsserver.js", "--cancellationPipeName", "/tmp/tscancellation-abc.tmp"],
            tsx: ["tsx", "watch", "--tsconfig", "tsconfig.json", "src/server.ts"],
        })
        check("M tsserver argv counts 0 for tsc_full", mod._count_running("tsc_full", snap) == 0)
        check("M tsx-watch argv counts 0 for tsc_full", mod._count_running("tsc_full", snap) == 0)

        snap = _snapshot_of(mod, {real_next: ["node", "/x/next/dist/bin/next", "build"]})
        check("M a real next-build-shaped argv counts 1", mod._count_running("build", snap) == 1)

        # ROOT invocations only: a pnpm process and a build process it spawned
        # (child ppid = parent pid) -> one build, not two.
        parent_pid, child_pid = real_next.pid, real_next.pid + 1
        synth = {parent_pid: (1, "python3", ["pnpm", "run", "build"]),
                 child_pid: (parent_pid, "python3", ["node", "/x/next/dist/bin/next", "build"])}
        check("M a build's own spawned child doesn't count again", mod._count_running("build", synth) == 1)

        # This hook's own ancestor chain never counts, even when it matches.
        my_ppid = os.getppid()
        synth = {**mod._read_snapshot(), my_ppid: (1, "zsh", ["pnpm", "run", "build"])}
        check("M this hook's own ancestor chain is excluded even if it matches",
              mod._count_running("build", synth) == 0)
    finally:
        for p in (tsserver, tsx, real_next):
            p.kill(); p.wait(timeout=5)

    # A real, LIVE, wholly UNMODIFIED plant: proves _read_snapshot()'s own ps
    # parsing end to end (real pid/ppid/ucomm), and that it never classifies
    # a bare sleeper as heavy.
    idle = _sleeper()
    try:
        time.sleep(0.5)
        real_snap = mod._read_snapshot()
        row = real_snap.get(idle.pid)
        check("M a real unmodified plant appears in the real snapshot", row is not None, str(row))
        argv = row[2] if row else []
        check("M a real unmodified plant's own argv never classifies as heavy",
              mod._classify(mod._resolve_segment(mod._resolve_runner(argv))) is None, str(argv))
    finally:
        idle.kill(); idle.wait(timeout=5)

    # A real shell -- proves a genuinely real `sh -c` row parses with a real
    # shell ucomm (never a heavy class, since a shell name is never itself a
    # recognized head). A single simple command tail-exec-optimizes away the
    # shell (ucomm becomes "sleep"), so the script needs a second statement.
    sh = subprocess.Popen(["/bin/sh", "-c", "sleep 30; true"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.5)
        snap = mod._read_snapshot()
        check("M a real /bin/sh -c plant has a real shell ucomm",
              snap.get(sh.pid, (0, "", []))[1] in mod._SHELL_COMM, str(snap.get(sh.pid)))
    finally:
        sh.kill(); sh.wait(timeout=5)


# ------------------------------------------------------------- G: git push ---
def _repo_with_hook(base: Path, content: str | None) -> str:
    repo = base / f"repo-{content is not None}-{len(content or '')}"
    (repo / ".git" / "hooks").mkdir(parents=True)
    if content is not None:
        hook = repo / ".git" / "hooks" / "pre-push"
        hook.write_text(content, encoding="utf-8")
        hook.chmod(0o755)
    return str(repo)

def leg_git_push() -> None:
    mod = _load("heavy_admission_g")
    mod.read_signal = lambda: IDLE
    tmp = Path(tempfile.mkdtemp(prefix="heavy-admission-gitpush-"))
    try:
        heavy = _repo_with_hook(tmp, "#!/bin/sh\nexec pnpm verify\n")
        light = _repo_with_hook(tmp, "#!/bin/sh\necho ok\n")
        none_ = _repo_with_hook(tmp, None)

        mod._count_running = lambda cls, snap: 1  # "a verify" already at cap
        check("G a heavy pre-push hook, at cap, denies", mod.admit("git push", heavy) == 2)

        mod._count_running = lambda cls, snap: 0
        check("G a light pre-push hook admits", mod.admit("git push", light) == 0)
        check("G no pre-push hook admits", mod.admit("git push", none_) == 0)
        check("G --no-verify admits regardless of the hook",
              mod.admit("git push --no-verify", heavy) == 0)
        check("G an unresolvable repo (no cwd) admits", mod.admit("git push", None) == 0)

        mod._count_running = lambda cls, snap: 1  # back to "already at cap"
        check("G git -C <path> push resolves an explicit override",
              mod.admit(f"git -C {heavy} push", "/somewhere/else") == 2)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------- L: leak + positive control ---
_LEAK_TOKEN = "ghp_" + "A" * 36

def leg_leak_control() -> None:
    # The REAL, shared telemetry log this whole run is bound to (set at the
    # top of this file, before the first module load) -- a DIRECT mod.admit()
    # call below (not the _admit() helper, which fakes log_fire out) exercises
    # the real write path against it.
    log = Path(os.environ["GUARD_FIRES_LOG"])
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)", _LEAK_TOKEN],
                         env={**os.environ, "FAKE_SECRET": _LEAK_TOKEN},
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.5)
        mod = _load("heavy_admission_l")
        mod.read_signal = lambda: IDLE
        snap = _snapshot_of(mod, {p: ["node", "/x/next/dist/bin/next", "build", _LEAK_TOKEN]})
        mod._read_snapshot = lambda: snap
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = mod.admit("next build")
        check("L real code denies at cap (premise for the leak check)", rc == 2, f"rc={rc}")
        seen = out.getvalue() + err.getvalue() + (log.read_text(encoding="utf-8", errors="replace") if log.exists() else "")
        check("L token absent from admit()'s own stdout/stderr/telemetry log", _LEAK_TOKEN not in seen, seen[:200])

        argv_dump = subprocess.run(["ps", "-ww", "-o", "args=", "-p", str(p.pid)],
                                   capture_output=True, text=True).stdout
        check("L positive control: ps -ww -o args= on that SAME pid DOES retrieve the token "
              "(proves the check has teeth, not that nothing can ever leak it)",
              _LEAK_TOKEN in argv_dump, argv_dump)
    finally:
        p.kill(); p.wait(timeout=5)


# --------------------------------------------------------- N: negative controls ---
def leg_negative_controls() -> None:
    mod = _load("heavy_admission_n_threshold")
    mod.PRESSURE_LEVEL_CRITICAL, mod.SWAP_OVER_RAM_CRITICAL = 999, 999.0
    mod.MEMORYSTATUS_LEVEL_CRITICAL, mod.MEM_AVAILABLE_OVER_TOTAL_CRITICAL = -1, -1.0
    mod.CLASS_CAPS = dict.fromkeys(mod.CLASS_CAPS, 999)
    mod.read_signal, mod._count_running = (lambda: CRITICAL), (lambda cls, snap: 0)
    check("N threshold mutant wrongly ALLOWS a critical-memory deny", mod.admit("next build") == 0)
    mod.read_signal, mod._count_running = (lambda: IDLE), (lambda cls, snap: 1)
    check("N threshold mutant wrongly ALLOWS an at-cap deny", mod.admit("next build") == 0)

    mod = _load("heavy_admission_n_widening")
    real_detect = mod.detect_class
    mod.detect_class = lambda c, cwd=None, _d=0: (
        "build" if any(p in c for p in ("next build", "tsc --noEmit", "playwright test")) else real_detect(c, cwd, _d))
    mod.read_signal, mod._count_running = (lambda: CRITICAL), (lambda cls, snap: 0)
    with contextlib.redirect_stderr(io.StringIO()):
        red = [c for c in ('rg "next build" docs/', 'git log --grep "tsc --noEmit"',
                           'grep -rn "playwright test" .github/') if mod.admit(c) != 0]
    check("N detection-widening mutant wrongly DENIES must-admit strings", len(red) == 3, f"only {red} turned red")

    mod = _load("heavy_admission_n_shell_filter")
    synth = {4242: (1, "zsh", ["next", "build"])}  # synthetic: a shell's ucomm on a
    check("N with the real shell filter, a shell-named row counts 0",     # row whose argv
          mod._count_running("build", synth) == 0)                       # WOULD otherwise match
    mod._SHELL_COMM = set()
    check("N deleting the shell filter wrongly counts that same row (goes RED)",
          mod._count_running("build", synth) == 1)


# ---------------------------------------------------------------- H: hook-level ---
def leg_hook_level_via_retry_budget() -> None:
    home = Path(tempfile.mkdtemp(prefix="heavy-admission-hook-home-"))
    tmp = Path(tempfile.mkdtemp(prefix="heavy-admission-hook-tmp-"))
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "TMPDIR": str(tmp)}
    env.pop("HEAVY_ADMISSION_BYPASS", None)

    def hook(command: str, call_id: str, **extra: str) -> subprocess.CompletedProcess:
        payload = json.dumps({"session_id": "heavy-admission-test", "hook_event_name": "PreToolUse",
                              "tool_name": "Bash", "tool_input": {"command": command}, "tool_use_id": call_id})
        return subprocess.run([sys.executable, str(RETRY_BUDGET)], input=payload, capture_output=True,
                              text=True, env={**env, **extra}, timeout=30)
    try:
        r = hook("ls -la", "toolu_h_allow")
        check("H a clean command allows via the real retry-budget.py", r.returncode == 0)
        # A genuinely idle machine: the real end-to-end path (no monkeypatch,
        # real ps snapshot, real memory read) must not deny a heavy command
        # that nothing is actually running.
        r = hook("next build", "toolu_h_idle")
        check("H a real idle next build admits (rc=0) end to end", r.returncode == 0, r.stderr[:200])
    finally:
        import shutil
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    print("heavy_admission controls")
    for leg in (leg_corpora, leg_decision, leg_counting, leg_git_push, leg_leak_control,
                leg_negative_controls, leg_hook_level_via_retry_budget):
        leg()
    if FAILURES:
        print(f"\n{len(FAILURES)} control(s) FAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nall heavy_admission controls passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
