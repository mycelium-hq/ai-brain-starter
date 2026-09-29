"""_lib/heavy_admission.py -- admission check for a heavy build/test command,
folded into retry-budget.py's PreToolUse(Bash) hook (MYC-5053) instead of its
own slot: ADR-0004's Bash fan-out was already at budget.

Incident (2026-09-26): ~10 agent sessions on one 24 GB Mac -- two `next
build`s, full-project `tsc --noEmit`, vitest runs from several builders --
pushed swap to 19.4 GB and the machine rebooted. This is the refusal at the
tool boundary.

Detection resolves shell_parse tokens to a FIXPOINT (wrappers, env assigns,
package-manager scope flags, exec/dlx), never a raw substring, so a heavy
phrase in a commit message is not a heavy command. Counting reads ONE `ps -A`
snapshot and runs each process's whitespace-split argv through the same
_resolve_segment/_classify rules; argv is never printed or logged. Only ROOT
invocations count; shells and this hook's own ancestors never do. Memory is
read first: critical denies WITHOUT counting. An exception that propagates to
admit() admits VISIBLY (additionalContext + log_fire).

`git push` counts as `verify` when the repo's pre-push hook file, read from
disk, contains a heavy-verifier marker.

Bypass: HEAVY_ADMISSION_BYPASS=1, inline or session env -- logged only when
it actually suppressed a deny.
"""
from __future__ import annotations

import json
import os
import re
import stat
import sys

try:
    from shell_parse import (ENV_ASSIGN_RE, WRAPPER_PREFIXES, cwd_candidates,
        split_segments_with_seps, strip_heredoc_bodies, strip_noncode, tokens)
    from cmd_env import inline_bypass
    from guard_telemetry import log_fire
except ImportError:
    from _lib.shell_parse import (ENV_ASSIGN_RE, WRAPPER_PREFIXES, cwd_candidates,
        split_segments_with_seps, strip_heredoc_bodies, strip_noncode, tokens)
    from _lib.cmd_env import inline_bypass
    from _lib.guard_telemetry import log_fire

BYPASS_VAR = "HEAVY_ADMISSION_BYPASS"
HOOK_NAME = "heavy-admission"

# macOS kern.memorystatus_vm_pressure_level: 1 normal, 2 warn, 4 critical.
PRESSURE_LEVEL_CRITICAL = 4
# Swap-vs-RAM only backs up pressure once it is already at WARN -- never
# denies on swap alone at level 1. kern.memorystatus_level is percent free.
SWAP_OVER_RAM_CRITICAL = 0.50
MEMORYSTATUS_LEVEL_CRITICAL = 10
# Linux: the kernel's own reclaimable-aware "about to swap-thrash" estimate.
MEM_AVAILABLE_OVER_TOTAL_CRITICAL = 0.10

CLASS_CAPS = {"build": 1, "verify": 1, "test_suite": 1, "tsc_full": 1, "playwright": 1, "cargo": 2}
_HINTS = {  # only where a narrower command is actually admitted; every other
    "test_suite": "run one file: `vitest run <file>`",  # class just says "wait".
    "tsc_full": "narrow the project: `tsc -p <one tsconfig>`",
}

# ---- detection: real argv tokens resolved to a FIXPOINT, never a substring --
_BARE_SKIP = WRAPPER_PREFIXES | {"npx", "bunx"}
_TWO_WORD_SKIP = {("pnpm", "exec"), ("pnpm", "dlx"), ("yarn", "dlx"), ("npm", "exec")}
_KNOWN_BINS = {"next", "tsc", "vitest", "playwright", "turbo", "tauri"}
_PM_SCOPE_VALUE = {"-C", "--dir", "--filter", "-F", "--prefix", "--workspace"}
_PM_SCOPE_BOOL = {"-w", "--workspace-root", "-r", "--recursive"}
_ENV_FLAGS = {"-u": 2, "--unset": 2, "-i": 1, "--ignore-environment": 1}  # -> tokens consumed
_TIMEOUT_WORDS = {"timeout", "gtimeout"}
_SHELLS = {"bash", "sh", "zsh"}
_CARGO_VERBS = {"build", "test", "check", "clippy", "nextest", "b", "t", "c"}
_CARGO_SKIP_FLAGS = ("--locked", "--offline", "--frozen")
_VITEST_VALUE_FLAGS = {"--config", "-c", "--pool", "--maxWorkers", "--shard",
                       "--bail", "--reporter", "-t", "--project", "--dir",
                       "--root", "--environment"}
_TSC_DEFAULT_PROJECTS = {".", "./", "tsconfig.json", "./tsconfig.json"}
_REDIR_RE = re.compile(r"^\d*(&?(?:>>|<<|>|<))(.*)$")
_INLINE_REDIR_RE = re.compile(r"\d*&?(?:>>|<<|>|<)")

def _basename(p: str) -> str:
    return p.replace("\\", "/").rsplit("/", 1)[-1]

def _strip_rest(t: list[str], pm: str) -> tuple[list[str], bool]:
    """Drop, past t[0]: redirects -- bare `>` plus its target, self-contained
    `2>&1`, or GLUED (`build>/tmp/b.log` is one token) -- and, when PM ("pnpm"
    /"npm"/""), the scope flags (`-C`/`--filter`/... take a value; pnpm's
    `-w`/`-r` do not -- but npm's OWN `-w`/`--workspace` DOES take a value)."""
    out, i, n = [t[0]], 1, len(t)
    while i < n:
        tok, has_next = t[i], i + 1 < n
        m = _INLINE_REDIR_RE.search(tok)
        if m and m.start() > 0:
            out.append(tok[:m.start()]); i += 1; continue
        rm = _REDIR_RE.match(tok)
        if rm:
            i += 1 if (rm.group(2) or not has_next) else 2; continue
        key = tok.split("=", 1)[0]
        npm_w = pm == "npm" and key in ("-w", "--workspace")
        if pm and (key in _PM_SCOPE_VALUE or npm_w):
            i += 1 if "=" in tok else (2 if has_next else 1)
        elif pm and tok in _PM_SCOPE_BOOL and not npm_w:
            i += 1
        else:
            out.append(tok); i += 1
    return out, out != t

def _strip_once(t: list[str]) -> tuple[list[str], bool]:
    """One step; the caller repeats to a FIXPOINT so order never matters."""
    if not t:
        return t, False
    w = t[0]
    if ENV_ASSIGN_RE.match(w):
        return t[1:], True
    if w == "env":  # past env's own `-u NAME` / `-i` / `NAME=val`, any mix
        i = 1
        while i < len(t) and (t[i] in _ENV_FLAGS or ENV_ASSIGN_RE.match(t[i])):
            i += _ENV_FLAGS.get(t[i], 1)
        return t[i:], True
    if w in _BARE_SKIP:  # `time -p` and `npx -y` also drop their flag
        flag = (w == "time" and t[1:2] == ["-p"]) or (w == "npx" and t[1:2] in (["-y"], ["--yes"]))
        return t[2 if flag else 1:], True
    if w == "nice":
        return (t[3:] if t[1:2] == ["-n"] else t[1:]), True
    if w in _TIMEOUT_WORDS:
        j = 1
        while t[j:j + 1] and t[j].startswith("-"):
            j += 1
        return t[j + 1:], True
    if tuple(t[:2]) in _TWO_WORD_SKIP:
        return t[2:], True
    if w in ("pnpm", "yarn") and t[1:2] and t[1] in _KNOWN_BINS:
        return t[1:], True  # a local-bin invocation is exec's equivalent
    if t[:2] == ["yarn", "workspace"] and len(t) > 2:
        return ["yarn"] + t[3:], True
    return _strip_rest(t, pm=w if w in ("pnpm", "npm") else "")

def _resolve_segment(t: list[str]) -> list[str]:
    while True:
        t, changed = _strip_once(t)
        if not changed:
            return t

def _dash_c_script(rest: list[str]):
    """`sh|bash|zsh [flags] -c '<script>'`'s script -- skips leading flags
    (`-e`, `-o pipefail`, `-lc`, `--login`) so `-c` need not be first."""
    i = 0
    while i < len(rest):
        tok = rest[i]
        if not tok.startswith("-"):
            return None
        if not tok.startswith("--") and "c" in tok[1:]:
            return rest[i + 1] if i + 1 < len(rest) else None
        i += 2 if tok == "-o" else 1
    return None

def _after_run(r: list[str]) -> list[str]:
    return r[1:] if r[:1] == ["run"] else r

def _vitest_unscoped(tail: list[str]) -> bool:
    """True unless a positional (a file or filter) survives the flags."""
    it = iter(tail)
    for tok in it:
        if tok in _VITEST_VALUE_FLAGS:
            next(it, None)
        elif not tok.startswith("-"):
            return False
    return True

def _tsc_is_full(rest: list[str]) -> bool:
    if not ({"--noEmit", "-b", "--build"} & set(rest)):
        return False
    for i, tok in enumerate(rest):
        if tok in ("-p", "--project"):
            return rest[i + 1] in _TSC_DEFAULT_PROJECTS if i + 1 < len(rest) else False
        if tok.startswith("--project="):
            return tok.split("=", 1)[1] in _TSC_DEFAULT_PROJECTS
    return True

def _classify(t: list[str]):
    """Class of one RESOLVED segment/argv, or None. `head` is the BASENAME
    of the command word, so `~/.cargo/bin/cargo` classifies like `cargo`."""
    if not t:
        return None
    head, rest = _basename(t[0]), t[1:]
    r = _after_run(rest)
    pm = head in ("npm", "pnpm", "yarn")
    if (pm or head in ("next", "turbo", "tauri")) and r[:1] == ["build"]:
        return "build"
    if head in ("npm", "pnpm") and r[:1] == ["verify"]:
        return "verify"
    if (pm and r[:1] == ["typecheck"]) or (head == "tsc" and _tsc_is_full(rest)):
        return "tsc_full"
    if (head == "vitest" and _vitest_unscoped(r)) or (
            pm and r[:1] in (["test"], ["vitest"]) and _vitest_unscoped(_after_run(r[1:]))):
        return "test_suite"
    if head == "playwright" and rest[:1] == ["test"]:
        return "playwright"
    if head == "cargo" and next((x for x in rest if x not in _CARGO_SKIP_FLAGS), None) in _CARGO_VERBS:
        return "cargo"
    return None

# ---- `git push` -> class `verify`, iff the repo's own pre-push hook is heavy
_HEAVY_HOOK_MARKERS = ("pnpm verify", "npm run verify", "pnpm test", "vitest",
                       "tsc", "eslint .", "turbo", "ci-test")
# Git global options that can sit BEFORE the subcommand. -c/-C/--git-dir/
# --work-tree/--namespace/--super-prefix take a value; the rest are boolean.
_GIT_GLOBAL_ARG = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--super-prefix"}
_GIT_GLOBAL_ARG_GLUED = ("--git-dir=", "--work-tree=", "--namespace=", "--super-prefix=")
_GIT_GLOBAL_BOOL = {"--no-pager", "-p", "--paginate", "--bare", "--literal-pathspecs",
                    "--no-optional-locks", "--no-replace-objects"}

def _parse_git_prefix(rest: list[str]) -> tuple[list[str], list[str]]:
    """REST is argv AFTER the `git` command word. Returns (prefix, subcmd):
    PREFIX is every global option, forwarded VERBATIM to a fresh `git` asking
    about the same repo/config -- so an inline `-c core.hooksPath=` or `-C`
    on the REAL push is honoured resolving ITS hook too, not just whatever
    this machine's ambient config says."""
    i, prefix = 0, []
    while i < len(rest):
        tok = rest[i]
        if tok in _GIT_GLOBAL_ARG:
            if i + 1 >= len(rest):
                return prefix, []  # dangling flag, no subcommand to find
            prefix += [tok, rest[i + 1]]; i += 2
        elif tok in _GIT_GLOBAL_BOOL or tok.startswith(_GIT_GLOBAL_ARG_GLUED):
            prefix.append(tok); i += 1
        else:
            break
    return prefix, rest[i:]

def _pre_push_hook_file(prefix: list[str], cwd: str):
    # git's OWN answer -- core.hooksPath at any scope (local, global,
    # worktree), the worktree commondir, and any -c/-C/--git-dir/--work-tree
    # carried on the REAL push itself (PREFIX, forwarded verbatim). A husky
    # v9 `.husky/_/` shim defers to the real `.husky/<hook>` one level up.
    # CWD is a real, existing directory or None: a bogus/unresolvable payload
    # cwd must never turn into an OS-level chdir error ahead of an absolute
    # -C/--git-dir in PREFIX, which would resolve the repo just fine anyway.
    real_cwd = cwd if cwd and os.path.isdir(cwd) else None
    hook = _run(["git", *prefix, "rev-parse", "--path-format=absolute",
                 "--git-path", "hooks/pre-push"], cwd=real_cwd, timeout=4).strip()
    shim_dir = os.path.dirname(hook)
    return os.path.join(os.path.dirname(shim_dir), "pre-push") if shim_dir.endswith("/.husky/_") else hook

def _repo_push_is_heavy(prefix: list[str], cwd: str) -> bool:
    hook = _pre_push_hook_file(prefix, cwd)
    if not hook or not os.path.exists(hook):
        return False  # no pre-push hook at all: a DECIDED light (silent admit)
    if not stat.S_ISREG(os.stat(hook).st_mode):
        # A directory, FIFO, etc. at the hook path: never open() it (a FIFO
        # blocks). Raising here reaches admit()'s catch-all -- admits WITH
        # the note, never a silent "light".
        raise OSError(f"pre-push hook is not a regular file: {hook}")
    with open(hook, encoding="utf-8", errors="replace") as fh:  # unreadable -> raises, same note
        return any(marker in fh.read(65536) for marker in _HEAVY_HOOK_MARKERS)

def _shell_scope_segs(segs, idx):
    """The slice of SEGS, up to and including IDX, that shares idx's OWN
    subshell scope as ITS top level -- so a `cd` inside the SAME `( ... )` as
    idx (`(cd heavy && git push)`) is visible to cwd_candidates, which
    otherwise treats anything inside unclosed parens as invisible (that
    function's OWN contract: a subshell's cd is invisible to the PARENT,
    which idx is not, when idx is a sibling inside the same parens)."""
    start, depth = 0, 0
    for i in range(idx, -1, -1):
        sep = segs[i][0]
        if sep == ")":
            depth += 1
        elif sep == "(":
            if depth == 0:
                start = i
                break
            depth -= 1
    inner = segs[start:idx + 1]
    return [("", inner[0][1])] + inner[1:] if start > 0 else inner

def detect_class(command: str, cwd: str | None = None, _depth: int = 0):
    """First matching class in COMMAND, resolved per shell segment, or None.
    Recurses one level into `bash|sh|zsh -c "<script>"`."""
    cleaned = strip_noncode(strip_heredoc_bodies(command))
    segs = split_segments_with_seps(cleaned)
    for idx, (_sep, seg) in enumerate(segs):
        t = _resolve_segment(tokens(seg.strip()))
        if not t:
            continue
        if _basename(t[0]) == "git":
            prefix, sub = _parse_git_prefix(t[1:])
            if sub[:1] == ["push"]:
                if "--no-verify" not in sub[1:] and cwd is not None:
                    cwds, _vars = cwd_candidates(_shell_scope_segs(segs, idx), cwd)
                    if len(cwds) == 1 and _repo_push_is_heavy(prefix, next(iter(cwds))):
                        return "verify"
                continue
        cls = _classify(t)
        if not cls and _depth < 1 and t[0] in _SHELLS:
            script = _dash_c_script(t[1:])
            cls = script and detect_class(script, cwd, _depth + 1)
        if cls:
            return cls
    return None


# ---- counting: ONE process snapshot, classified like detection, never pgrep -
_SHELL_COMM = {"sh", "bash", "zsh", "dash", "fish"}
_NODE_RUNNERS = {"node", "bun"}
_SCRIPT_TOOL_SUFFIX = (
    ("next/dist/bin/next", "next"), ("vitest/vitest.mjs", "vitest"),
    ("typescript/bin/tsc", "tsc"), ("@playwright/test/cli.js", "playwright"),
)

def _resolve_runner(t: list[str]) -> list[str]:
    """`node|bun <script> ...` -> the LOGICAL command it is really running,
    so a real process goes through the same rules detection uses."""
    if t[:1] and t[0].startswith("next-build"):
        # Next 16's own `nextBuild()` sets process.title = "next-build (vX)"
        # as its first statement; on macOS that overwrites the argv memory
        # region, so a real `next build`'s snapshot row IS this shape, not
        # `node .../next/dist/bin/next build` (captured 2026-09-29, v16.3.2).
        return ["next", "build"]
    if len(t) < 2 or _basename(t[0]) not in _NODE_RUNNERS:
        return t
    script = t[1].replace("\\", "/")
    for suffix, tool in _SCRIPT_TOOL_SUFFIX:
        if script.endswith(suffix):
            return [tool] + t[2:]
    name = _basename(script).split(".", 1)[0]  # pnpm.cjs, corepack bin/pnpm + pnpm.js, .bin/<tool>
    if name == "pnpm" or "node_modules/.bin/" in script:
        return [name] + t[2:]
    return t

def _read_snapshot() -> dict[int, tuple[int, str, list[str]]]:
    # One `ps -A` call: {pid: (ppid, ucomm, argv_tokens)}. The tokens live only
    # in this dict, for one admit() call -- never printed, logged or stored.
    rows = {}
    for line in _run(["ps", "-A", "-o", "pid=,ppid=,ucomm=,args="], timeout=4).splitlines():
        parts = line.split(None, 3)
        if len(parts) < 3 or not (parts[0].isdigit() and parts[1].isdigit()):
            continue
        rows[int(parts[0])] = (int(parts[1]), parts[2], parts[3].split() if len(parts) > 3 else [])
    return rows

def _ancestors(pid: int, snapshot: dict) -> set[int]:
    """PID and every ancestor of it present in SNAPSHOT (cycle-safe)."""
    seen = set()
    while pid in snapshot and pid not in seen:
        seen.add(pid)
        pid = snapshot[pid][0]
    return seen

def _count_running(cls: str, snapshot: dict) -> int:
    # ROOT invocations of CLS only: a match with a same-class match among its
    # ancestors doesn't count (one `pnpm run build` counts 1, not once per
    # spawned child). Shells and this hook's own ancestors never count.
    hook_anc = _ancestors(os.getppid(), snapshot)
    matched = {pid for pid, (_ppid, ucomm, argv) in snapshot.items()
               if pid not in hook_anc and ucomm not in _SHELL_COMM
               and argv and _classify(_resolve_segment(_resolve_runner(argv))) == cls}
    return sum(1 for pid in matched if not (_ancestors(snapshot[pid][0], snapshot) & matched))


# ---- memory: critical denies WITHOUT counting --------------------------------
_SWAP_USED_RE = re.compile(r"used\s*=\s*([\d.]+)([MG])")
_MEMINFO_RE = re.compile(r"^(MemTotal|MemAvailable):\s*(\d+)", re.MULTILINE)

def _run(argv: list[str], timeout: float = 2, cwd: str | None = None) -> str:
    import subprocess  # lazy: paid only once a class is actually detected
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=True, cwd=cwd).stdout

def _parse_swap_used(text: str) -> float:
    m = _SWAP_USED_RE.search(text)
    if not m:
        raise ValueError("unrecognized vm.swapusage output")
    return float(m.group(1)) * (2 ** 30 if m.group(2) == "G" else 2 ** 20)

def read_signal() -> dict:
    if sys.platform == "darwin":
        level, ms, swap_txt, ram = _run(["sysctl", "-n",
            "kern.memorystatus_vm_pressure_level", "kern.memorystatus_level",
            "vm.swapusage", "hw.memsize"]).splitlines()
        return {"platform": "darwin", "pressure_level": int(level),
                "memorystatus_level": int(ms), "swap_used": _parse_swap_used(swap_txt),
                "ram": float(ram)}
    if sys.platform.startswith("linux"):
        with open("/proc/meminfo", encoding="utf-8", errors="replace") as fh:
            return {"platform": "linux", **{k: int(v) for k, v in _MEMINFO_RE.findall(fh.read())}}
    return {"platform": "other"}  # incl. Windows: no snapshot counting there either

def _memory_critical(sig: dict) -> tuple[bool, str]:
    if sig["platform"] == "darwin":
        level, ms = sig["pressure_level"], sig["memorystatus_level"]
        swap, ram = sig["swap_used"], sig["ram"]
        ratio = swap / ram if ram else 0.0
        reading = (f"pressure level {level}; swap {swap / 2 ** 30:.2f} GB / "
                   f"RAM {ram / 2 ** 30:.1f} GB ({ratio:.0%}); {ms}% free")
        critical = (level >= PRESSURE_LEVEL_CRITICAL or ms <= MEMORYSTATUS_LEVEL_CRITICAL
                    or (level >= 2 and ratio >= SWAP_OVER_RAM_CRITICAL))
        return critical, reading
    total, avail = sig.get("MemTotal"), sig.get("MemAvailable")
    if not total:
        raise ValueError("unrecognized /proc/meminfo output")
    ratio = avail / total
    return (ratio < MEM_AVAILABLE_OVER_TOTAL_CRITICAL,
            f"MemAvailable {avail / 2 ** 20:.1f} GB / MemTotal {total / 2 ** 20:.1f} GB ({ratio:.0%})")


# ---- dispatch -----------------------------------------------------------------
def admit(command: str, cwd: str | None = None) -> int:
    """0 = allow, 2 = deny; an exception that propagates here admits, visibly.
    `cwd` is the payload's cwd, used only to resolve a `git push`'s repo."""
    try:
        cls = detect_class(command, cwd)
        if cls is None:
            return 0
        sig = read_signal()
        if sig["platform"] not in ("darwin", "linux"):
            return 0  # Windows and unmeasured platforms: allow silently, not an error
        critical, reading = _memory_critical(sig)
        if critical:
            # Counting was SKIPPED, so there is no "the running" job to name.
            headline, hint = "machine memory is critical", "wait for machine memory to recover"
        else:
            running = _count_running(cls, _read_snapshot())
            cap = CLASS_CAPS[cls]
            if running < cap:
                return 0
            headline = f"a {cls} is already running ({running} of cap {cap})"
            hint = _HINTS.get(cls, "wait for the running one to finish")
        if os.environ.get(BYPASS_VAR) == "1" or inline_bypass(command, BYPASS_VAR):
            log_fire(HOOK_NAME, status="bypassed", cls=cls, reason=headline)
            return 0
        print(
            "BLOCKED by heavy-command-admission (folded into retry-budget):\n"
            f"  {headline}.\n"
            f"  Reading: {reading}.\n"
            f"  {hint}.\n"
            f"  Bypass: prefix with {BYPASS_VAR}=1.",
            file=sys.stderr,
        )
        log_fire(HOOK_NAME, status="blocked", cls=cls, reason=headline)
        return 2
    except Exception as exc:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
            "additionalContext": f"[heavy-admission] unmeasured ({type(exc).__name__}) -- admitted"}}))
        # "warned", not "blocked"/"bypassed"/"fired": guard_telemetry's own
        # taxonomy (see its module docstring) has no "error" status.
        log_fire(HOOK_NAME, status="warned", detail=type(exc).__name__)
        return 0
