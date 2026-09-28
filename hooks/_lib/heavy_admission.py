"""_lib/heavy_admission.py -- admission check for a heavy build/test command,
folded into retry-budget.py's PreToolUse(Bash) hook (MYC-5053) instead of its
own slot: ADR-0004's Bash fan-out was already at budget, and the prior
raise's own rationale said the next addition should fold in, not raise again.

Incident (2026-09-26): concurrent agent sessions on one Mac each ran nested
builders -- two `next build`s, full-project `tsc --noEmit`, several `vitest
run`s, cargo -- and pushed swap to 19.4 GB on a 24 GB machine; it rebooted,
killing every session's work. This is the refusal at the tool boundary.

Detection resolves real argv tokens (shell_parse), past env assigns,
wrappers and package-manager scoping flags -- never a raw substring, so a
heavy phrase in a commit message is not a heavy command. Counting matches
running processes with `pgrep -f` (PIDs only, argv never read), anchored on
a path/word boundary so "tsc" cannot match "tsconfig".

Memory is read first: critical denies WITHOUT counting, so a stalled pgrep
can never discard a genuinely critical reading; a failed count instead
raises, reaching the same visible fail-open as any other internal error.

Bypass: HEAVY_ADMISSION_BYPASS=1, inline (cmd_env.inline_bypass) or session
env -- logged only when it actually suppressed a deny.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

try:
    from shell_parse import ENV_ASSIGN_RE, split_segments_with_seps, strip_heredoc_bodies, strip_noncode, tokens
    from cmd_env import inline_bypass
    from guard_telemetry import log_fire
except ImportError:
    from _lib.shell_parse import ENV_ASSIGN_RE, split_segments_with_seps, strip_heredoc_bodies, strip_noncode, tokens
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
_HINTS = {
    "build": "wait for the running build, or scope it to one workspace",
    "verify": "wait for the running verify",
    "test_suite": "run one file: `vitest run <file>`",
    "tsc_full": "narrow the project: `tsc -p <one tsconfig>`",
    "playwright": "wait for the running run, or pass one spec file",
    "cargo": "wait for the running cargo job, or narrow with `-p <crate>`",
}

# ---- detection: real argv tokens, never a raw substring ---------------------
_BARE_SKIP = {"nohup", "time", "env", "command", "exec", "npx", "bunx"}
_TWO_WORD_SKIP = {("pnpm", "exec"), ("pnpm", "dlx"), ("yarn", "dlx")}
_PM_SCOPE_VALUE = {"-C", "--dir", "--filter", "-F", "--prefix", "-w", "--workspace"}
_SHELLS = {"bash", "sh", "zsh"}
_CARGO_VERBS = {"build", "test", "check", "clippy", "nextest", "b", "t", "c"}
_VITEST_VALUE_FLAGS = {"--reporter", "-t", "--project"}
_TSC_DEFAULT_PROJECTS = {".", "./", "tsconfig.json", "./tsconfig.json"}
_REDIR_RE = re.compile(r"^\d*(&?(?:>>|<<|>|<))(.*)$")

def _skip_n(t: list[str], want: int) -> list[str]:
    """Drop each token `want(tok, has_next)` says to consume (1 or 2)."""
    out, i, n = [], 0, len(t)
    while i < n:
        k = want(t[i], i + 1 < n)
        if k:
            i += k
        else:
            out.append(t[i]); i += 1
    return out

def _pm_scope(tok: str, has_next: bool) -> int:
    """pnpm/npm -C/--dir/--filter/-F/--prefix/-w/--workspace(=val), -r/
    --recursive, wherever they sit -- a trailing flag reads like a leading one."""
    if tok.split("=", 1)[0] in _PM_SCOPE_VALUE:
        return 1 if "=" in tok else (2 if has_next else 1)
    return 1 if tok in ("-r", "--recursive") else 0

def _redir(tok: str, has_next: bool) -> int:
    """`>`,`>>`,`<`,`2>`,`2>&1`,`&>`: shlex has no redirect notion, so `2>&1`
    survives as one token and a bare `>` is followed by a separate target."""
    if "<" not in tok and ">" not in tok:
        return 0
    m = _REDIR_RE.match(tok)
    if not m:
        return 0
    return 1 if (m.group(2) or not has_next) else 2

def _skip_wrappers(t: list[str]) -> list[str]:
    """nice [-n N] / nohup / time / env / timeout N / command / exec / npx /
    bunx / `pnpm exec|dlx` / `yarn dlx` -- past the real command word."""
    while t:
        w = t[0]
        if w in _BARE_SKIP:
            t = t[1:]
        elif w == "nice":
            t = t[3:] if t[1:2] == ["-n"] else t[1:]
        elif w == "timeout":
            j = 1
            while t[j:j + 1] and t[j].startswith("-"):
                j += 1
            t = t[j + 1:]
        elif tuple(t[:2]) in _TWO_WORD_SKIP:
            t = t[2:]
        else:
            break
    return t

def _dash_c_script(rest: list[str]):
    if rest and rest[0].startswith("-") and not rest[0].startswith("--") and "c" in rest[0][1:]:
        return rest[1] if len(rest) > 1 else None
    return None

def _after_run(r: list[str]) -> list[str]:
    return r[1:] if r[:1] == ["run"] else r

def _vitest_unscoped(tail: list[str]) -> bool:
    """A surviving positional (not a flag) means the run is scoped."""
    i, n = 0, len(tail)
    while i < n:
        if tail[i] in _VITEST_VALUE_FLAGS:
            i += 2
        elif tail[i].startswith("-"):
            i += 1
        else:
            return False
    return True

def _test_tail(head: str, rest: list[str]):
    if head == "vitest":
        return _after_run(rest)
    if head in ("npm", "pnpm", "yarn"):
        r = _after_run(rest)
        if r[:1] in (["test"], ["vitest"]):
            return _after_run(r[1:])
    return None

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
    """First matching class for one RESOLVED segment's tokens, or None."""
    if not t:
        return None
    head, rest = t[0], t[1:]
    r = _after_run(rest)
    if (head in ("next", "npm", "pnpm", "yarn", "turbo") and r[:1] == ["build"]) or (
            head == "pnpm" and rest[:1] == ["turbo"] and rest[1:2] == ["build"]):
        return "build"
    if head in ("npm", "pnpm") and r[:1] == ["verify"]:
        return "verify"
    if head in ("npm", "pnpm", "yarn") and r[:1] == ["typecheck"]:
        return "tsc_full"
    if head == "tsc" and _tsc_is_full(rest):
        return "tsc_full"
    tail = _test_tail(head, rest)
    if tail is not None and _vitest_unscoped(tail):
        return "test_suite"
    if head == "playwright" and rest[:1] == ["test"]:
        return "playwright"
    if head == "cargo" and rest[:1] and rest[0] in _CARGO_VERBS:
        return "cargo"
    return None

def detect_class(command: str, _depth: int = 0):
    """First matching class in COMMAND, resolved per shell segment, or None.
    Recurses one level into `bash|sh|zsh -c "<string>"`."""
    cleaned = strip_noncode(strip_heredoc_bodies(command))
    for _sep, seg in split_segments_with_seps(cleaned):
        t = tokens(seg.strip())
        while t and ENV_ASSIGN_RE.match(t[0]):
            t = t[1:]
        t = _skip_wrappers(t)
        if t[:2] == ["yarn", "workspace"] and len(t) > 2:
            t = ["yarn"] + t[3:]
        elif t[:1] and t[0] in ("pnpm", "npm"):
            t = _skip_n(t, _pm_scope)
        t = _skip_n(t, _redir)
        if not t:
            continue
        cls = _classify(t)
        if cls:
            return cls
        if _depth < 1 and t[0] in _SHELLS:
            script = _dash_c_script(t[1:])
            if script:
                inner = detect_class(script, _depth + 1)
                if inner:
                    return inner
    return None


# ---- counting running work: PIDs only, never argv/env -----------------------
def _anchored(*phrases: str) -> str:
    return "|".join(rf"(^|/){p}( |$)" for p in phrases)

_BUILD_VERBS = ("next", "npm run", "pnpm run", "pnpm", "yarn", "yarn run", "turbo", "turbo run", "pnpm turbo")
_VERIFY_VERBS = ("npm run", "pnpm run", "pnpm")
_PGREP_PATTERN = {
    "build": _anchored(*(f"{v} build" for v in _BUILD_VERBS)),
    "verify": _anchored(*(f"{v} verify" for v in _VERIFY_VERBS)),
    "test_suite": _anchored("vitest run", "vitest"),
    "tsc_full": _anchored("tsc"),
    "playwright": _anchored("playwright test"),
    "cargo": _anchored(*(f"cargo {v}" for v in _CARGO_VERBS)),
}
_SHELL_COMM = {"sh", "bash", "zsh", "dash", "fish"}

def _run(argv: list[str], timeout: float = 2) -> str:
    import subprocess  # lazy: paid only once a class is actually detected
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout).stdout

def _ancestor_pids() -> set[int]:
    pids, pid, seen = set(), os.getppid(), set()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        pids.add(pid)
        nxt = _run(["ps", "-o", "ppid=", "-p", str(pid)]).strip()
        pid = int(nxt) if nxt.isdigit() else 0
    return pids

def _count_running(cls: str) -> int:
    """COUNT only (bare PIDs; a matched process's argv is never read). Drops
    the hook's own ancestors and any PID whose process NAME is a shell."""
    ancestors = _ancestor_pids()
    pids = [p for p in _run(["pgrep", "-f", _PGREP_PATTERN[cls]]).split() if int(p) not in ancestors]
    return sum(1 for p in pids
               if _run(["ps", "-o", "comm=", "-p", p]).strip().rsplit("/", 1)[-1] not in _SHELL_COMM)


# ---- memory: critical denies WITHOUT counting --------------------------------
_SWAP_USED_RE = re.compile(r"used\s*=\s*([\d.]+)([MG])")
_MEMINFO_RE = re.compile(r"^(MemTotal|MemAvailable):\s*(\d+)", re.MULTILINE)

def _parse_swap_used(text: str) -> float:
    m = _SWAP_USED_RE.search(text)
    if not m:
        raise ValueError(f"unrecognized vm.swapusage output: {text!r}")
    return float(m.group(1)) * (2 ** 30 if m.group(2) == "G" else 2 ** 20)

def _parse_meminfo(text: str) -> dict:
    return {k: int(v) for k, v in _MEMINFO_RE.findall(text)}

def read_signal() -> dict:
    if sys.platform == "darwin":
        return {
            "platform": "darwin",
            "pressure_level": int(_run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"])),
            "memorystatus_level": int(_run(["sysctl", "-n", "kern.memorystatus_level"])),
            "swap_used": _parse_swap_used(_run(["sysctl", "-n", "vm.swapusage"])),
            "ram": float(_run(["sysctl", "-n", "hw.memsize"])),
        }
    if sys.platform.startswith("linux"):
        return {"platform": "linux",
                **_parse_meminfo(Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace"))}
    return {"platform": "other"}  # incl. Windows: no pgrep there either

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
def _note_unmeasured(kind: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
        "additionalContext": f"[heavy-admission] unmeasured ({kind}) -- admitted"}}))
    log_fire(HOOK_NAME, status="error", detail=kind)

def admit(command: str) -> int:
    """0 = allow, 2 = deny. retry-budget.py's own try/except around the call
    is a second, outer safety net -- every error here already fails open."""
    try:
        cls = detect_class(command)
        if cls is None:
            return 0
        sig = read_signal()
        if sig["platform"] not in ("darwin", "linux"):
            return 0  # Windows and unmeasured platforms: allow silently, not an error
        critical, reading = _memory_critical(sig)
        running = None
        if critical:
            headline = "machine memory is critical"
        else:
            running = _count_running(cls)
            cap = CLASS_CAPS[cls]
            if running < cap:
                return 0
            headline = f"a {cls} is already running ({running} of cap {cap})"
        if os.environ.get(BYPASS_VAR) == "1" or inline_bypass(command, BYPASS_VAR):
            log_fire(HOOK_NAME, status="bypassed", cls=cls, reason=headline)
            return 0
        print(
            "BLOCKED by heavy-command-admission (folded into retry-budget):\n"
            f"  {headline}.\n"
            f"  Reading: {reading}.\n"
            f"  {_HINTS.get(cls, 'wait for the running one to finish')}.\n"
            f"  Bypass: prefix with {BYPASS_VAR}=1.",
            file=sys.stderr,
        )
        log_fire(HOOK_NAME, status="blocked", cls=cls, reason=headline)
        return 2
    except Exception as exc:
        _note_unmeasured(type(exc).__name__)
        return 0
