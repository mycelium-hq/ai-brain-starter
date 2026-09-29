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

import atexit
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

_TELEMETRY_DIR = tempfile.mkdtemp(prefix="heavy-admission-telemetry-")
atexit.register(shutil.rmtree, _TELEMETRY_DIR, ignore_errors=True)  # 324 of these leaked pre-fix
os.environ["GUARD_FIRES_LOG"] = os.path.join(_TELEMETRY_DIR, "fires.jsonl")
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
    # admit() imports log_fire lazily via _guard_deps(): wrap that, keeping the real inline_bypass.
    real_deps = mod._guard_deps
    mod._guard_deps = lambda: (real_deps()[0], lambda name, status="fired", **ctx: fires.append(status))
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
    # correctness-redesign miss-list (both reviews) -----------------------
    ('pnpm -C apps/web exec tsc --noEmit', 'tsc_full'),
    ('pnpm --filter web exec tsc --noEmit', 'tsc_full'),
    ('pnpm -r exec tsc --noEmit', 'tsc_full'),
    ('pnpm tsc --noEmit', 'tsc_full'),
    ('pnpm next build', 'build'),
    ('pnpm playwright test', 'playwright'),
    ('pnpm turbo run build', 'build'),
    ('env -u EQUIPO_DATABASE_URL npx vitest run', 'test_suite'),
    ('env -i cargo build', 'cargo'),
    ('env --ignore-environment cargo build', 'cargo'),
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
    # step 6: bare tsc; timeout's own value flags; shell reserved words ---
    ('tsc', 'tsc_full'),
    ('npx tsc', 'tsc_full'),
    ('npx -y tsc', 'tsc_full'),
    ('timeout -s KILL 60 next build', 'build'),
    ('timeout -k 5 60 next build', 'build'),
    ('timeout --signal=KILL 60 next build', 'build'),
    ('timeout --preserve-status 60 cargo build', 'cargo'),
    ('for x in a b c; do next build; done', 'build'),
    ('{ next build; }', 'build'),
    ('if true; then pnpm run build; fi', 'build'),
    # step 5: a watcher did a FULL pass first -- still DETECTED as heavy;
    # only COUNTING exempts an already-running one (leg_counting/leg_decision).
    ('tsc -b -w', 'tsc_full'),
    ('tsc --noEmit --watch', 'tsc_full'),
    ('vitest --watch', 'test_suite'),
    ('pnpm vitest --watch', 'test_suite'),
    ('vitest watch', 'test_suite'),
    ('vitest dev', 'test_suite'),
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
    # step 5: a watcher is still DETECTED -- critical memory denies a NEW one
    # too (never silently admitted just because it will "only" sit resident).
    check("A a watcher (tsc --noEmit --watch) is STILL DETECTED: critical memory denies it too",
          _admit(mod, "tsc --noEmit --watch")[0] == 2)

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

    mod = _load("heavy_admission_a_tsc_hint")  # in a one-tsconfig repo `tsc -p` is refused again
    mod.read_signal, mod._count_running = (lambda: IDLE), (lambda cls, snap: 1)
    rc, out, _fires = _admit(mod, "tsc -p tsconfig.json --noEmit")
    check("A the tsc_full hint never suggests narrowing the project", rc == 2 and "wait for the running" in out, out)

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
    ts = {101: (1, ["node", "/fake/tsserver.js", "--cancellationPipeName", "/tmp/tscancellation-abc.tmp"]),
          102: (1, ["tsx", "watch", "--tsconfig", "tsconfig.json", "src/server.ts"])}
    check("M tsserver and tsx-watch argv count 0 for tsc_full", count("tsc_full", ts) == 0)
    check("M a next-build-shaped argv counts 1", count("build", {103: (1, ["node", "/x/next/dist/bin/next", "build"])}) == 1)
    # Rows captured 2026-09-29: Next 16.3.2's process.title, corepack pnpm, npm's title.
    check("M a captured Next 16.3.2 title row ['next-build','(v16.3.2)'] counts as build",
          count("build", {109: (1, ["next-build", "(v16.3.2)"])}) == 1)
    check("M a captured corepack pnpm row ['node','.../bin/pnpm','verify'] counts as verify",
          count("verify", {110: (1, ["node", "/x/.pnpm/bin/pnpm", "verify"])}) == 1)
    check("M a captured npm row ['npm','run','verify'] counts as verify",
          count("verify", {111: (1, ["npm", "run", "verify"])}) == 1)
    check("M a bun-run next-shaped argv (bun script resolution) counts as build",
          count("build", {112: (1, ["bun", "/x/next/dist/bin/next", "build"])}) == 1)
    # ROOT invocations only: a pnpm process and the build it spawned -> one build.
    tree = {201: (1, ["pnpm", "run", "build"]), 202: (201, ["node", "/x/next/dist/bin/next", "build"])}
    check("M a build's own spawned child doesn't count again", count("build", tree) == 1)
    check("M this hook's own ancestor chain is excluded even if it matches",
          count("build", {os.getppid(): (1, ["pnpm", "run", "build"])}) == 0)

    # step 5: a watcher did a full pass first (same heavy class) but then
    # sits resident -- it stays DETECTED (MUST_DETECT above) but is EXEMPT
    # from counting, so an idle one never holds the class's slot forever.
    check("M a tsc -b -w row counts 0 for tsc_full (detected, but a watcher)",
          count("tsc_full", {113: (1, ["tsc", "-b", "-w"])}) == 0)
    check("M a vitest --watch row counts 0 for test_suite",
          count("test_suite", {114: (1, ["vitest", "--watch"])}) == 0)
    check("M a vitest watch (subcommand form) row counts 0 for test_suite",
          count("test_suite", {115: (1, ["vitest", "watch"])}) == 0)
    mod2 = _load("heavy_admission_m_watcher_admit")
    mod2.read_signal = lambda: IDLE
    mod2._read_snapshot = lambda: {116: (1, ["tsc", "-b", "-w"])}  # a planted watcher row
    check("M with a planted `tsc -b -w` row in the snapshot, `pnpm typecheck` still admits",
          mod2.admit("pnpm typecheck") == 0)

    # Real, unmodified plants: _read_snapshot()'s own ps parse, end to end, next
    # to a foreign process whose argv carries a raw non-UTF-8 byte (0xE9).
    idle, foreign = _sleeper(), _sleeper("argv_byte_\udce9")
    try:
        time.sleep(0.5)
        snap = mod._read_snapshot()
        row = snap.get(idle.pid)
        check("M a real unmodified plant appears in the real snapshot", row is not None, str(row))
        check("M a real unmodified plant's own argv never classifies as heavy",
              mod._classify(mod._resolve_segment(mod._resolve_runner(row[1] if row else []))) is None, str(row))
        check("R a foreign non-UTF-8 argv byte does not raise, and other rows still parse",
              foreign.pid in snap and idle.pid in snap, f"{len(snap)} rows")
    finally:
        for p in (idle, foreign):
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
                  row is not None and mod._classify(mod._resolve_segment(mod._resolve_runner(row[1]))) == "build",
                  str(row))
        finally:
            titled.kill(); titled.wait(timeout=5)


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

def _repo_hooks_path(base: Path, name: str, hooks_path: str, files: dict) -> str:
    """A repo whose .git/config sets core.hooksPath in git's own camelCase, plus FILES (relpath -> body)."""
    repo = base / name
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    with open(repo / ".git" / "config", "a", encoding="utf-8") as fh:
        fh.write(f"[core]\n\thooksPath = {hooks_path}\n")
    for rel, body in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(body, encoding="utf-8")
        (repo / rel).chmod(0o755)
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
        # finding 1 (HIGH, bcd7757 regression): git applies -C options LEFT TO
        # RIGHT, so a later absolute -C wins. The payload's own -C must come
        # FIRST, so the push's own forwarded -C (parsed from the command text)
        # is the one that wins -- matching what git itself resolves for that
        # push. The control just above uses a payload cwd that does not EXIST,
        # so real_cwd is None and nothing is appended either way -- the one
        # shape for which order never mattered, which is why it never caught
        # this: every case below uses an EXISTING payload cwd.
        check("G git -C <heavy> push, from an EXISTING light cwd, resolves the heavy repo's own hook",
              mod.admit(f"git -C {heavy} push", light) == 2)
        check("G git -C <light> push, from cwd heavy, resolves the light repo's own hook (not heavy's)",
              mod.admit(f"git -C {light} push", heavy) == 0)
        check("G a RELATIVE -C into a heavy repo, from its parent dir as payload cwd, denies",
              mod.admit(f"git -C {os.path.basename(heavy)} push", str(tmp)) == 2)
        nonrepo = tmp / "not-a-repo"
        nonrepo.mkdir()
        old_signal = mod.read_signal
        mod.read_signal = lambda: CRITICAL
        check("G CRITICAL memory: git -C <heavy> push && pnpm build, from an existing non-repo cwd, denies",
              mod.admit(f"git -C {heavy} push && pnpm build", str(nonrepo)) == 2)
        mod.read_signal = old_signal
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
        # F1: a generic rule (skip any `-...` token, plus one extra token
        # after 7 value-taking options) replaces the named-option list, so an
        # option this file has never heard of doesn't stop the scan.
        check("G git --no-advice push (an UNKNOWN global bool) still finds push",
              mod.admit("git --no-advice push", heavy) == 2)
        # git needs its config-env value to name a REAL env var (else it
        # exits 128 "missing environment variable"), so HOME, always set.
        check("G git --config-env=foo.bar=HOME push (glued value) still finds push",
              mod.admit("git --config-env=foo.bar=HOME push", heavy) == 2)
        check("G git --config-env foo.bar=HOME push (split value) still finds push",
              mod.admit("git --config-env foo.bar=HOME push", heavy) == 2)

        rel_hp = _repo_hooks_path(tmp, "hookspath-rel", "custom-hooks", {"custom-hooks/pre-push": "exec pnpm verify\n"})
        check("G a repo-local camelCase hooksPath (RELATIVE) resolves to its heavy hook",
              mod.admit("git push", rel_hp) == 2)

        light_hooks = tmp / "light-hooks-override"
        light_hooks.mkdir()
        check("G git -c core.hooksPath=<light dir> push into a heavy repo admits",
              mod.admit(f"git -c core.hooksPath={light_hooks} push", heavy) == 0)

        subdir = Path(heavy) / "src" / "nested"
        subdir.mkdir(parents=True)
        check("G a subdirectory cwd still resolves the repo's heavy hook",
              mod.admit("git push", str(subdir)) == 2)
        check("G (cd heavy && git push) from a light cwd denies",
              mod.admit(f"(cd {heavy} && git push)", light) == 2)

        wt = tmp / "heavy-worktree"  # `worktree add` needs a commit: a throwaway identity
        subprocess.run(["git", "-C", heavy, "-c", "user.email=t@t.example", "-c", "user.name=t",
                        "commit", "--allow-empty", "-q", "-m", "init"], check=True)
        subprocess.run(["git", "-C", heavy, "worktree", "add", "-q", "--detach", str(wt)], check=True)
        check("G a linked worktree (git worktree add) shares the main repo's heavy hook",
              mod.admit("git push", str(wt)) == 2)

        husky = _repo_hooks_path(tmp, "husky-v9", ".husky/_", {".husky/_/pre-push": '. "$(dirname "$0")/h"\n',
                                                               ".husky/pre-push": "exec pnpm verify\n"})
        check("G husky v9 (.husky/_/ shim) resolves to the REAL .husky/<hook>", mod.admit("git push", husky) == 2)

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


# --------------------------------------------- P: pre-approval PATH pathprobe ---
def leg_pathprobe() -> None:
    """SECURITY (step 3): git, ps and sysctl were spawned by BARE NAME, and git
    additionally got cwd= set to a directory the COMMAND TEXT can choose (a
    `cd`). A relative or empty PATH entry, reached from that directory, let a
    planted binary there run BEFORE the user approves the command. Drives the
    REAL retry-budget.py end to end; proves interception via a marker file
    (never by output shape -- git delegates to the real binary after
    logging, ps/sysctl return the same fixed idle shape leg H's stub uses)."""
    real_git = shutil.which("git")
    if real_git is None:
        print("  SKIP: no git on PATH -- cannot build the pathprobe's delegating wrapper")
        return
    tmp = Path(tempfile.mkdtemp(prefix="heavy-admission-pathprobe-"))
    try:
        evil = tmp / "evil-repo"
        subprocess.run(["git", "init", "-q", str(evil)], check=True)
        hook = evil / ".git" / "hooks" / "pre-push"
        hook.write_text("#!/bin/sh\nexec pnpm verify\n", encoding="utf-8")
        hook.chmod(0o755)
        nested = evil / "node_modules" / ".bin"
        nested.mkdir(parents=True)
        home = tmp / "home"
        home.mkdir()

        def plant(d: Path, marker: Path) -> None:
            (d / "git").write_text(
                f'#!/bin/sh\necho hit >> "{marker}"\nexec "{real_git}" "$@"\n', encoding="utf-8")
            (d / "ps").write_text(f'#!/bin/sh\necho hit >> "{marker}"\n', encoding="utf-8")
            (d / "sysctl").write_text(
                f'#!/bin/sh\necho hit >> "{marker}"\n'
                'printf "1\\n57\\ntotal = 0.00M  used = 0.00M  free = 0.00M\\n17179869184\\n"\n',
                encoding="utf-8")
            for name in ("git", "ps", "sysctl"):
                (d / name).chmod(0o755)

        for tag, path_prefix, plant_dir in (
            ("relative (node_modules/.bin)", "node_modules/.bin" + os.pathsep, nested),
            ("empty", os.pathsep, evil),
        ):
            marker = tmp / f"marker-{tag.split()[0]}"
            marker.unlink(missing_ok=True)
            plant(plant_dir, marker)
            env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "TMPDIR": str(home),
                   "PATH": path_prefix + os.environ.get("PATH", "")}
            payload = json.dumps({"session_id": "heavy-admission-pathprobe", "hook_event_name": "PreToolUse",
                                  "tool_name": "Bash", "tool_input": {"command": f"cd {evil} && git push"},
                                  "cwd": str(tmp), "tool_use_id": "toolu_pathprobe"})
            subprocess.run([sys.executable, str(RETRY_BUDGET)], input=payload, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=env, timeout=30)
            check(f"P git planted via a {tag} PATH entry, reached through the command's own "
                  "`cd` (git alone: ps/sysctl are never chdir'd there, so this shape never "
                  "reaches them -- see the hook-process-cwd case below), never ran",
                  not marker.exists(), "marker file appeared: a planted binary executed pre-approval")

        # finding 2 (LOW): the cases above are all reached via a `cd`/-C the
        # COMMAND TEXT chose. A planted git/ps/sysctl in the HOOK PROCESS's
        # OWN starting cwd -- set by whatever launches the hook, never by the
        # command text -- is a distinct surface (r6a's "same class" MEDIUM):
        # closed in code by _tool()'s absolute-only PATH filter, which is
        # cwd-independent by construction, but nothing exercised it before
        # this case (a mutant reverting _tool() to a bare name passed the
        # whole suite). No `cd`/-C anywhere in either command below; only the
        # subprocess's own `cwd=` reaches `evil`.
        cwd_marker = tmp / "marker-cwd"
        for command, payload_cwd in (("next build", str(tmp)), ("git push", str(evil))):
            cwd_marker.unlink(missing_ok=True)
            plant(evil, cwd_marker)
            env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "TMPDIR": str(home),
                   "PATH": "." + os.pathsep + os.environ.get("PATH", "")}
            payload = json.dumps({"session_id": "heavy-admission-pathprobe-cwd", "hook_event_name": "PreToolUse",
                                  "tool_name": "Bash", "tool_input": {"command": command},
                                  "cwd": payload_cwd, "tool_use_id": f"toolu_pathprobe_cwd_{len(command)}"})
            subprocess.run([sys.executable, str(RETRY_BUDGET)], input=payload, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=env,
                           cwd=str(evil), timeout=30)
            check(f"P git/ps/sysctl planted in the HOOK PROCESS's own cwd (never chosen by "
                  f"the command text), reached via a '.' PATH entry, never ran ({command!r})",
                  not cwd_marker.exists(), "marker file appeared: a planted binary executed pre-approval")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------- F: forwarded-prefix argv leak ---
def leg_forwarded_prefix_leak() -> None:
    """SECURITY (step 4, LOW): only -C/--git-dir/--work-tree/-c core.hooksPath=
    are forwarded to the REAL rev-parse spawn. Any OTHER -c (e.g. -c
    http.extraHeader=<secret>) must never reach that subprocess's argv --
    visible to any local `ps` reader before the user approves anything. Spy
    on subprocess.run's actual argv, in-process (never a `ps` read)."""
    mod = _load("heavy_admission_forward")
    mod.read_signal = lambda: IDLE
    mod._count_running = lambda cls, snap: 1  # "a verify" already at cap -> denied, the richest path
    tmp = Path(tempfile.mkdtemp(prefix="heavy-admission-forward-"))
    secret = "ghp_" + "B" * 36
    try:
        heavy = _repo_with_hook(tmp, "#!/bin/sh\nexec pnpm verify\n")
        seen_argv: list[list[str]] = []
        real_run = subprocess.run
        def spy(argv, *a, **kw):
            seen_argv.append(list(argv))
            return real_run(argv, *a, **kw)
        subprocess.run = spy
        try:
            rc = mod.admit(f"git -c http.extraHeader={secret} push", heavy)
        finally:
            subprocess.run = real_run
        check("F the push still resolves and denies (premise: dropping the -c didn't break resolution)",
              rc == 2, f"rc={rc}")
        flat = [tok for argv in seen_argv for tok in argv]
        check("F -c http.extraHeader=<secret> never reaches ANY spawned subprocess argv",
              not any(secret in tok for tok in flat), str(flat))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------- I: irregular hook file ---
def _mkrepo(base: Path, name: str) -> Path:
    repo = base / name
    (repo / ".git" / "hooks").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo

def leg_fifo_hook() -> None:
    """A FIFO or a directory at the pre-push hook path must admit WITH the
    visible note (never a silent light, never a crash) and must never hang.
    Driven through the REAL retry-budget.py as an EXTERNAL subprocess, so a
    genuine hang is caught by subprocess.run's own timeout from OUTSIDE the
    hung process -- an in-process signal-based bound doesn't work here: it
    was tried first, and the raised TimeoutError was silently absorbed by
    admit()'s own broad `except Exception` into just another 'unmeasured
    (TimeoutError) -- admitted', indistinguishable from the fixed code
    (measured against a scratch revert of the S_ISREG guard)."""
    home = Path(tempfile.mkdtemp(prefix="heavy-admission-fifo-home-"))
    stub = home / "bin"
    stub.mkdir()
    for name, body in (("ps", ""), ("sysctl", "printf '1\\n57\\ntotal = 0.00M  used = 0.00M  free = 0.00M\\n17179869184\\n'")):
        (stub / name).write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        (stub / name).chmod(0o755)
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "TMPDIR": str(home),
           "GIT_CONFIG_GLOBAL": os.devnull, "PATH": f"{stub}{os.pathsep}{os.environ.get('PATH', '')}"}

    def hook_admit(command: str, cwd: str, call_id: str):
        payload = json.dumps({"session_id": "heavy-admission-fifo", "hook_event_name": "PreToolUse",
                              "tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd,
                              "tool_use_id": call_id})
        return subprocess.run([sys.executable, str(RETRY_BUDGET)], input=payload, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=env, timeout=15)

    tmp = Path(tempfile.mkdtemp(prefix="heavy-admission-fifo-"))
    try:
        fifo_repo = _mkrepo(tmp, "fifo-repo")
        fifo_hook = fifo_repo / ".git" / "hooks" / "pre-push"
        os.mkfifo(fifo_hook)  # never opened by the code under test, or by this test
        try:
            r = hook_admit("git push", str(fifo_repo), "toolu_fifo_hook")
        except subprocess.TimeoutExpired:
            check("I a FIFO pre-push hook never hangs", False, "subprocess TIMED OUT")
        else:
            check("I a FIFO pre-push hook admits WITH the visible note, and never hangs",
                  r.returncode == 0 and "[heavy-admission] unmeasured" in r.stdout,
                  f"rc={r.returncode} out={r.stdout[:200]!r}")

        dir_repo = _mkrepo(tmp, "dir-repo")
        dir_hook = dir_repo / ".git" / "hooks" / "pre-push"
        dir_hook.mkdir()
        r = hook_admit("git push", str(dir_repo), "toolu_dir_hook")
        check("I a DIRECTORY at the pre-push hook path admits WITH the visible note",
              r.returncode == 0 and "[heavy-admission] unmeasured" in r.stdout,
              f"rc={r.returncode} out={r.stdout[:200]!r}")
    finally:
        # rmtree unlinks the FIFO dirent without opening it -- nothing was
        # ever opened, so there is nothing to explicitly close first.
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


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
            mod._read_snapshot = lambda: {p.pid: (1, ["node", "/x/next/dist/bin/next", "build", _LEAK_TOKEN])}
            rc = mod.admit("next build")
        check("L real code denies the token-bearing row at cap (premise)", rc == 2, f"rc={rc}")
        seen = out.getvalue() + err.getvalue() + (log.read_text(encoding="utf-8", errors="replace") if log.exists() else "")
        check("L token absent from admit()'s own stdout/stderr/telemetry log", _LEAK_TOKEN not in seen, seen[:200])
        argv_dump = subprocess.run(["ps", "-ww", "-o", "args=", "-p", str(p.pid)],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
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

    # No shell filter: _classify alone must reject a shell-headed argv.
    mod = _load("heavy_admission_n_shell_head")
    synth = {4242: (1, ["zsh", "next", "build"])}
    check("N a shell-headed argv ([zsh, next, build]) counts 0 via _classify alone",
          mod._count_running("build", synth) == 0)
    real_classify = mod._classify
    mod._classify = lambda t: "build" if t and t[0] in ("zsh", "bash", "sh") else real_classify(t)
    check("N a mutant that widens _classify to accept a shell head wrongly counts that row (goes RED)",
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
                              text=True, encoding="utf-8", errors="replace", env=env, timeout=30)
    try:
        check("H a clean command allows via the real retry-budget.py", hook("ls -la", "toolu_h_allow").returncode == 0)
        r = hook("next build", "toolu_h_idle")
        check("H an idle next build admits (rc=0) end to end", r.returncode == 0, r.stderr[:200])
    finally:
        shutil.rmtree(home, ignore_errors=True)


def main() -> int:
    print("heavy_admission controls")
    for leg in (leg_corpora, leg_decision, leg_counting, leg_git_push, leg_pathprobe,
                leg_forwarded_prefix_leak, leg_fifo_hook, leg_leak_control,
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
