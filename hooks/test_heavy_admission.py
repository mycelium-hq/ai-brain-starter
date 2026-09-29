#!/usr/bin/env python3
"""Controls for hooks/_lib/heavy_admission.py (MYC-5053), folded into
retry-budget.py's PreToolUse(Bash) hook. Stdlib-only plain script, exit 0 =
all pass. Legs: D/C corpora; A decision order, fail-open, bypass, memory arms;
M counting on synthetic rows plus real plants for the ps parse; G git push;
L a planted token through the REAL reader and a matched row, with a positive
control; N attribute-patch mutants that must flip a verdict; H the real
retry-budget.py with ps/sysctl stubbed so the machine's load can't decide it.

Run: python3 hooks/test_heavy_admission.py
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

os.environ["GUARD_FIRES_LOG"] = os.path.join(tempfile.mkdtemp(prefix="heavy-admission-telemetry-"), "fires.jsonl")
os.environ.pop("HEAVY_ADMISSION_BYPASS", None)  # an ambient bypass would pass A/N for the wrong reason
# ^ BEFORE the first module load: guard_telemetry binds LOG_PATH at its own
# first import, so without this every run appends to the REAL guard-fires.jsonl.
os.environ["GIT_CONFIG_GLOBAL"] = os.devnull  # G must not see this machine's real core.hooksPath

HERE = Path(__file__).resolve().parent
MODULE = HERE / "_lib" / "heavy_admission.py"
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
    (rc, output, statuses). Call mod.admit() directly to exercise the REAL
    telemetry write instead."""
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
    # step 3: real package managers -----------------------------------------
    ('npm exec next build', 'build'),
    ('npm -w apps/web run build', 'build'),
    ('npm --workspace apps/web run build', 'build'),
    ('npm run build -w apps/web', 'build'),
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
    check("A cargo's cap is 2: one running cargo still admits", _admit(mod, "cargo build")[0] == 0)
    os.environ["HEAVY_ADMISSION_BYPASS"] = "1"
    rc, _out, fires = _admit(mod, "next build")
    os.environ.pop("HEAVY_ADMISSION_BYPASS")
    check("A the session-env bypass admits at cap, logged", rc == 0 and fires == ["bypassed"], f"rc={rc} {fires}")

    mod = _load("heavy_admission_a_hint")
    mod.read_signal = lambda: CRITICAL
    rc, out, _fires = _admit(mod, "next build")
    check("A a critical-memory deny never says 'the running'", rc == 2 and "the running" not in out, out)

    crit = lambda **kw: mod._memory_critical({**IDLE, **kw})[0]  # noqa: E731
    check("A each macOS arm fires alone: memorystatus <=10, swap>=RAM/2 at WARN",
          crit(memorystatus_level=10) and crit(pressure_level=2, swap_used=8 * 2 ** 30))
    check("A swap alone never denies at pressure level 1", not crit(swap_used=12 * 2 ** 30))
    linux = lambda avail: mod._memory_critical({"platform": "linux", "MemTotal": 100, "MemAvailable": avail})[0]  # noqa: E731
    check("A the Linux arm: MemAvailable under 10% denies, 50% does not", linux(9) and not linux(50))
    sig = _load("heavy_admission_a_reader").read_signal()  # the REAL reader, on this host
    check("A the real memory reader parses this host", sig["platform"] != "darwin" or sig["ram"] > 0, str(sig))


# ------------------------------------------------------- M: counting logic ---
def _sleeper(*extra: str, env=None) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", *extra], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def leg_counting() -> None:
    mod = _load("heavy_admission_m")
    count = mod._count_running
    ts = {101: (1, "node", ["node", "/fake/tsserver.js", "--cancellationPipeName", "/tmp/tscancellation-abc.tmp"]),
          102: (1, "node", ["tsx", "watch", "--tsconfig", "tsconfig.json", "src/server.ts"])}
    check("M tsserver and tsx-watch argv count 0 for tsc_full", count("tsc_full", ts) == 0)
    check("M a next-build-shaped argv counts 1", count("build", {103: (1, "node", ["node", "/x/next/dist/bin/next", "build"])}) == 1)
    # Captured 2026-09-29 (Next 16.3.2, macOS): `process.title=` overwrites the
    # argv memory region, so a real `next build`'s OWN snapshot row is this
    # shape, never `node .../next/dist/bin/next build`.
    check("M a captured Next 16.3.2 title row ['next-build','(v16.3.2)'] counts as build",
          count("build", {109: (1, "next-build", ["next-build", "(v16.3.2)"])}) == 1)
    # Captured 2026-09-29: real pnpm here runs in-process via corepack's node
    # shim, so the OWN pid's argv is `node .../bin/pnpm verify`, never a
    # separate `pnpm` process. npm's own title IS `npm run verify` (no shim).
    check("M a captured corepack pnpm row ['node','.../bin/pnpm','verify'] counts as verify",
          count("verify", {110: (1, "node", ["node", "/x/.pnpm/bin/pnpm", "verify"])}) == 1)
    check("M a captured npm row ['npm','run','verify'] counts as verify",
          count("verify", {111: (1, "npm", ["npm", "run", "verify"])}) == 1)
    # ROOT invocations only: a pnpm process and the build it spawned -> one build.
    tree = {201: (1, "node", ["pnpm", "run", "build"]), 202: (201, "node", ["node", "/x/next/dist/bin/next", "build"])}
    check("M a build's own spawned child doesn't count again", count("build", tree) == 1)
    # A NON-shell ucomm, so only the ancestor exclusion (not the shell filter) can zero it.
    check("M this hook's own ancestor chain is excluded even if it matches",
          count("build", {os.getppid(): (1, "node", ["pnpm", "run", "build"])}) == 0)

    # Real, unmodified plants: _read_snapshot()'s own ps parse, end to end. A
    # lone simple command would tail-exec away the shell, hence `; true`.
    idle = _sleeper()
    sh = subprocess.Popen(["/bin/sh", "-c", "sleep 30; true"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.5)
        snap = mod._read_snapshot()
        row = snap.get(idle.pid)
        check("M a real unmodified plant appears in the real snapshot", row is not None, str(row))
        check("M a real unmodified plant's own argv never classifies as heavy",
              mod._classify(mod._resolve_segment(mod._resolve_runner(row[2] if row else []))) is None, str(row))
        check("M a real /bin/sh -c plant has a real shell ucomm",
              snap.get(sh.pid, (0, "", []))[1] in mod._SHELL_COMM, str(snap.get(sh.pid)))
    finally:
        for p in (idle, sh):
            p.kill(); p.wait(timeout=5)

    # LIVE plant of a process that rewrites its OWN title, reproducing the
    # incident's real mechanism (not a synthetic row). Node is the tool that
    # needs to be present; a loud SKIP, never a silent pass, when it is not.
    node = shutil.which("node")
    if node is None:
        print("  SKIP: no node on PATH -- cannot live-plant a real process.title rewrite")
    else:
        titled = subprocess.Popen(
            [node, "-e", "process.title = 'next-build (v16.3.2)'; setTimeout(() => {}, 30000);"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(0.5)
            row = mod._read_snapshot().get(titled.pid)
            check("M a LIVE node process.title rewrite ('next-build (vX)') counts as build",
                  row is not None and mod._classify(mod._resolve_segment(mod._resolve_runner(row[2]))) == "build",
                  str(row))
        finally:
            titled.kill(); titled.wait(timeout=5)

    # LIVE plant of a real corepack-shape process: a real file at a path
    # ENDING in "bin/pnpm" (a tiny bash script -- it just sleeps), invoked as
    # `bash <that file> verify` with argv[0] renamed to "node" via bash's own
    # `exec -a` (portable; no node dependency for this shape). A python
    # interpreter does NOT work here: macOS framework python3 builds (both
    # Homebrew's and CommandLineTools') re-exec themselves internally and
    # silently DISCARD an `exec -a`-renamed argv[0] (measured 2026-09-29);
    # bash runs the script in the same process and keeps it.
    pnpm_home = Path(tempfile.mkdtemp(prefix="heavy-admission-corepack-"))
    fake_pnpm = pnpm_home / "bin" / "pnpm"
    fake_pnpm.parent.mkdir()
    fake_pnpm.write_text("#!/bin/bash\nsleep 30\n", encoding="utf-8")
    fake_pnpm.chmod(0o755)
    corepack = subprocess.Popen(
        ["bash", "-c", f'exec -a node bash "{fake_pnpm}" verify'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.5)
        row = mod._read_snapshot().get(corepack.pid)
        check("M a LIVE corepack-shape plant (node .../bin/pnpm verify) counts as verify",
              row is not None and mod._classify(mod._resolve_segment(mod._resolve_runner(row[2]))) == "verify",
              str(row))
    finally:
        corepack.kill(); corepack.wait(timeout=5)
        shutil.rmtree(pnpm_home, ignore_errors=True)


# ------------------------------------------------------------- G: git push ---
def _repo_with_hook(base: Path, content: str | None) -> str:
    repo = base / f"repo-{content is not None}-{len(content or '')}"
    (repo / ".git" / "hooks").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)  # a real repo: rev-parse must resolve it
    if content is not None:
        hook = repo / ".git" / "hooks" / "pre-push"
        hook.write_text(content, encoding="utf-8")
        hook.chmod(0o755)
    return str(repo)

def _repo_with_hookspath(base: Path, tag: str, hp_value: str, content: str) -> str:
    """A repo whose LOCAL .git/config sets core.hooksPath -- written with the
    EXACT camelCase git itself uses, appended directly to the ini file so
    this never depends on `git config`'s own normalization."""
    repo = base / f"hookspath-{tag}"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    with open(repo / ".git" / "config", "a", encoding="utf-8") as fh:
        fh.write(f"[core]\n\thooksPath = {hp_value}\n")
    hooks_dir = repo / hp_value if not os.path.isabs(hp_value) else Path(hp_value)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "pre-push").write_text(content, encoding="utf-8")
    (hooks_dir / "pre-push").chmod(0o755)
    return str(repo)

def _repo_husky_v9(base: Path, content: str) -> str:
    repo = base / "husky-v9"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    shim_dir = repo / ".husky" / "_"
    shim_dir.mkdir(parents=True)
    (shim_dir / "pre-push").write_text('#!/bin/sh\n. "$(dirname "$0")/h"\n', encoding="utf-8")
    (shim_dir / "pre-push").chmod(0o755)
    (repo / ".husky" / "pre-push").write_text(content, encoding="utf-8")
    (repo / ".husky" / "pre-push").chmod(0o755)
    with open(repo / ".git" / "config", "a", encoding="utf-8") as fh:
        fh.write("[core]\n\thooksPath = .husky/_\n")
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
        check("G git -C <path> push resolves an explicit override",
              mod.admit(f"git -C {heavy} push", "/somewhere/else") == 2)
        check("G a light pre-push hook admits", mod.admit("git push", light) == 0)
        check("G no pre-push hook admits", mod.admit("git push", none_) == 0)
        check("G --no-verify admits regardless of the hook", mod.admit("git push --no-verify", heavy) == 0)
        check("G an unresolvable repo (no cwd) admits", mod.admit("git push", None) == 0)

        # step 4: git push, asked of git -----------------------------------
        check("G /usr/bin/git push (basename of the command word) denies",
              mod.admit("/usr/bin/git push", heavy) == 2)
        check("G git -c k=v push (an unrelated global option) still finds push",
              mod.admit("git -c foo.bar=baz push", heavy) == 2)
        check("G git --no-pager push still finds push",
              mod.admit("git --no-pager push", heavy) == 2)

        rel_hp = _repo_with_hookspath(tmp, "rel", "custom-hooks", "#!/bin/sh\nexec pnpm verify\n")
        check("G a repo-local camelCase hooksPath (RELATIVE) resolves to its heavy hook",
              mod.admit("git push", rel_hp) == 2)
        abs_hooks = tmp / "abs-custom-hooks"
        abs_hp = _repo_with_hookspath(tmp, "abs", str(abs_hooks), "#!/bin/sh\nexec pnpm verify\n")
        check("G a repo-local camelCase hooksPath (ABSOLUTE) resolves to its heavy hook",
              mod.admit("git push", abs_hp) == 2)

        light_hooks = tmp / "light-hooks-override"
        light_hooks.mkdir()
        check("G git -c core.hooksPath=<light dir> push into a heavy repo admits",
              mod.admit(f"git -c core.hooksPath={light_hooks} push", heavy) == 0)

        subdir = Path(heavy) / "src" / "nested"
        subdir.mkdir(parents=True)
        check("G a subdirectory cwd still resolves the repo's heavy hook",
              mod.admit("git push", str(subdir)) == 2)
        check("G git -C <subdir> also resolves the repo's heavy hook",
              mod.admit(f"git -C {subdir} push", "/somewhere/else") == 2)
        check("G (cd heavy && git push) from a light cwd denies",
              mod.admit(f"(cd {heavy} && git push)", light) == 2)

        wt = tmp / "heavy-worktree"
        # `worktree add` needs a real HEAD to check out; this repo has no
        # commits yet. A throwaway, fully-hermetic identity (no ambient
        # user.email/user.name needed).
        subprocess.run(["git", "-C", heavy, "-c", "user.email=t@t.example", "-c", "user.name=t",
                        "commit", "--allow-empty", "-q", "-m", "init"], check=True)
        subprocess.run(["git", "-C", heavy, "worktree", "add", "-q", "--detach", str(wt)], check=True)
        check("G a linked worktree (git worktree add) shares the main repo's heavy hook",
              mod.admit("git push", str(wt)) == 2)

        check("G husky v9 (.husky/_/ shim) resolves to the REAL .husky/<hook>",
              mod.admit("git push", _repo_husky_v9(tmp, "#!/bin/sh\nexec pnpm verify\n")) == 2)

        plain = none_  # a repo with no LOCAL hook at all -- only the GLOBAL config below applies
        global_hooks = tmp / "global-heavy-hooks"
        global_hooks.mkdir()
        (global_hooks / "pre-push").write_text("#!/bin/sh\nexec pnpm verify\n", encoding="utf-8")
        (global_hooks / "pre-push").chmod(0o755)
        global_cfg = tmp / "fake-global.gitconfig"
        global_cfg.write_text(f"[core]\n\thooksPath = {global_hooks}\n", encoding="utf-8")
        old_global = os.environ.get("GIT_CONFIG_GLOBAL")
        os.environ["GIT_CONFIG_GLOBAL"] = str(global_cfg)
        try:
            check("G a GLOBAL core.hooksPath pointing at a heavy hook denies at cap",
                  mod.admit("git push", plain) == 2)
        finally:
            os.environ["GIT_CONFIG_GLOBAL"] = old_global if old_global is not None else os.devnull
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------- L: leak + positive control ---
_LEAK_TOKEN = "ghp_" + "A" * 36

def leg_leak_control() -> None:
    # A real token-bearing process, first through the REAL _read_snapshot (every
    # process is read once a class is detected), then as a MATCHED row at cap.
    # Direct mod.admit() calls: the real telemetry write, into the temp log.
    log = Path(os.environ["GUARD_FIRES_LOG"])
    p = _sleeper(_LEAK_TOKEN, env={**os.environ, "FAKE_SECRET": _LEAK_TOKEN})
    try:
        time.sleep(0.5)
        mod = _load("heavy_admission_l")
        mod.read_signal = lambda: IDLE
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            mod.admit("next build")
            mod._read_snapshot = lambda: {p.pid: (1, "node", ["node", "/x/next/dist/bin/next", "build", _LEAK_TOKEN])}
            rc = mod.admit("next build")
        check("L real code denies the token-bearing row at cap (premise)", rc == 2, f"rc={rc}")
        seen = out.getvalue() + err.getvalue() + (log.read_text(encoding="utf-8", errors="replace") if log.exists() else "")
        check("L token absent from admit()'s own stdout/stderr/telemetry log", _LEAK_TOKEN not in seen, seen[:200])
        argv_dump = subprocess.run(["ps", "-ww", "-o", "args=", "-p", str(p.pid)],
                                   capture_output=True, text=True).stdout
        check("L positive control: ps on that SAME pid DOES show the token the real reader read",
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
    synth = {4242: (1, "zsh", ["next", "build"])}  # a shell ucomm on an argv that WOULD match
    check("N with the real shell filter, a shell-named row counts 0", mod._count_running("build", synth) == 0)
    mod._SHELL_COMM = set()
    check("N deleting the shell filter wrongly counts that same row (goes RED)",
          mod._count_running("build", synth) == 1)


# ---------------------------------------------------------------- H: hook-level ---
def leg_hook_level_via_retry_budget() -> None:
    home = Path(tempfile.mkdtemp(prefix="heavy-admission-hook-home-"))
    stub = home / "bin"  # an empty ps and an idle sysctl: the verdict can't depend on this machine
    stub.mkdir()
    for name, body in (("ps", ""), ("sysctl", "printf '1\\n57\\ntotal = 0.00M  used = 0.00M  free = 0.00M\\n17179869184\\n'")):
        (stub / name).write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        (stub / name).chmod(0o755)
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "TMPDIR": str(home),
           "PATH": f"{stub}{os.pathsep}{os.environ.get('PATH', '')}"}

    def hook(command: str, call_id: str) -> subprocess.CompletedProcess:
        payload = json.dumps({"session_id": "heavy-admission-test", "hook_event_name": "PreToolUse",
                              "tool_name": "Bash", "tool_input": {"command": command}, "tool_use_id": call_id})
        return subprocess.run([sys.executable, str(RETRY_BUDGET)], input=payload, capture_output=True,
                              text=True, env=env, timeout=30)
    try:
        check("H a clean command allows via the real retry-budget.py", hook("ls -la", "toolu_h_allow").returncode == 0)
        r = hook("next build", "toolu_h_idle")
        check("H an idle next build admits (rc=0) end to end", r.returncode == 0, r.stderr[:200])
    finally:
        shutil.rmtree(home, ignore_errors=True)


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
