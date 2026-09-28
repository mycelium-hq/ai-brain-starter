#!/usr/bin/env python3
"""PreToolUse hook: refuse a heavy build/test command when the machine is
already under memory pressure.

Incident (2026-09-26): ~10 concurrent agent sessions on one Mac each ran a
heavy command -- two `next build`s, a full-project `tsc --noEmit`, several
unscoped `vitest run`s, cargo builds. Swap reached 19.4 GB on a 24 GB-RAM
machine (7% RAM free) and the Mac rebooted, killing every session's work.
Prose rules ("one next build machine-wide") did not stop it -- this is the
refusal at the tool boundary instead.

Detection is a small regex set matched with re.search (never an anchored
^-match), so any prefix -- env assignments, `nice`, a leading `cd DIR &&`,
earlier `;`/`&&`/`|`-joined commands, `npx`, `pnpm exec` -- is tolerated for
free; nothing strips or walks it. No match -> return immediately, no
measurement (the common case, so this stays fast). Not shell-aware: a
heavy-looking substring inside a quoted arg or commit message can trigger a
measurement pass, but detection alone never denies -- only a critical
reading or an at-cap count does, so a false match costs a few cheap reads,
never a wrong block.

Readings (only on a match): macOS via sysctl (pressure level, swap, RAM);
Linux via /proc/meminfo; anything else (incl. Windows, no pgrep there) is
unmeasured and reaches the same fail-open path as a genuine read failure.
Already-running work is COUNTED with `pgrep` in list form -- PIDs only,
never -l/-f's list-name/list-full combination (see block-env-dump.py's pgrep
analysis for why that leaks a titled process's argv) -- so a matched
process's command line is never read by this hook, only the line count.

Fail-open boundary: `_handle()` lets every read/parse/subprocess exception
propagate (no per-reader try/except); `main()` is the one place that
catches, logs type+message (never argv/env) to
~/.claude/heavy-admission-errors.log, and allows. A broken reading must
never become a broken shell.

Override: HEAVY_ADMISSION_OVERRIDE=1, inline (cmd_env.inline_bypass) or
session env. Logs one line (timestamp, class, pressure, swap GB -- never
argv/env) to ~/.claude/heavy-admission-overrides.log and allows.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "_lib"))
try:
    from cmd_env import inline_bypass
except Exception:
    def inline_bypass(command, var, value="1"):
        return False

OVERRIDE_VAR = "HEAVY_ADMISSION_OVERRIDE"

# macOS kern.memorystatus_vm_pressure_level: 1 normal, 2 warn, 4 critical.
# Measured on this machine today: level 1 at idle. Only >= 4 denies -- a WARN
# reading alone must not (task spec).
PRESSURE_LEVEL_CRITICAL = 4

# vm.swapusage's TOTAL grows dynamically on macOS (measured today: `total =
# 7168.00M used = 5996.06M free = 1171.94M`, so used/total is not a usable
# ratio -- 7168M is not this machine's physical RAM). Compare swap USED
# against fixed physical RAM (hw.memsize) instead.
SWAP_USED_OVER_RAM_CRITICAL = 0.50

# Linux MemAvailable is the kernel's own reclaimable-aware estimate (unlike
# MemFree, which undercounts page cache that is actually reclaimable) -- the
# same "about to swap-thrash" line the macOS swap-ratio check draws.
MEM_AVAILABLE_OVER_TOTAL_CRITICAL = 0.10

# Already-running cap per class. Reached -> deny regardless of memory.
CLASS_CAPS = {
    "next_build": 1, "verify": 1, "tsc_full": 1,
    "vitest_unscoped": 1, "playwright": 1, "cargo": 2,
}

# pgrep -f pattern per class (node-based classes match on full command line;
# cargo matches on process name via -x instead, see _count_running).
_PGREP_PATTERN = {
    "next_build": "next build|npm run build|pnpm run build|pnpm build|yarn build|yarn run build",
    "verify": "npm run verify|pnpm run verify|pnpm verify",
    "tsc_full": "tsc",
    "vitest_unscoped": "vitest run",
    "playwright": "playwright test",
}

_NEXT_BUILD_RE = re.compile(
    r"\bnext\s+build\b"
    r"|\b(?:npm|pnpm|yarn)\s+run\s+build\b"
    r"|\bpnpm\s+build\b|\byarn\s+build\b"
    r"|\bpnpm\s+--filter\s+\S+\s+(?:run\s+)?build\b"
)
_VERIFY_RE = re.compile(r"\b(?:npm|pnpm)\s+run\s+verify\b|\bpnpm\s+verify\b")
_TSC_WORD_RE = re.compile(r"\btsc\b")
_TSC_UNBOUNDED_RE = re.compile(r"--noEmit\b|(?:^|\s)-b\b|--build\b")
_TSC_PROJECT_RE = re.compile(r"(?:^|\s)-p\b|--project\b")
_VITEST_RUN_RE = re.compile(r"\bvitest\s+run\b(?P<tail>[^;&|]*)")
_PLAYWRIGHT_RE = re.compile(r"\bplaywright\s+test\b")
_CARGO_RE = re.compile(r"\bcargo\s+(?:build|test)\b")


def _vitest_is_unscoped(command: str) -> bool:
    m = _VITEST_RUN_RE.search(command)
    if not m:
        return False
    tail = m.group("tail").split()
    return not any(not tok.startswith("-") for tok in tail)


def detect_class(command: str) -> str | None:
    """First matching class name, or None. Order is arbitrary among
    mutually-exclusive real-world invocations."""
    if _NEXT_BUILD_RE.search(command):
        return "next_build"
    if _VERIFY_RE.search(command):
        return "verify"
    if (_TSC_WORD_RE.search(command) and _TSC_UNBOUNDED_RE.search(command)
            and not _TSC_PROJECT_RE.search(command)):
        return "tsc_full"
    if _vitest_is_unscoped(command):
        return "vitest_unscoped"
    if _PLAYWRIGHT_RE.search(command):
        return "playwright"
    if _CARGO_RE.search(command):
        return "cargo"
    return None


# ---- machine readings -------------------------------------------------------
_SWAP_USED_RE = re.compile(r"used\s*=\s*([\d.]+)([MG])")


def _parse_swap_used_bytes(text: str) -> float | None:
    m = _SWAP_USED_RE.search(text)
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2)
    return value * (2 ** 30 if unit == "G" else 2 ** 20)


def _macos_pressure_level() -> int | None:
    r = subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
                        capture_output=True, text=True, timeout=2)
    return int(r.stdout.strip())


def _macos_swap_used_bytes() -> float | None:
    r = subprocess.run(["sysctl", "-n", "vm.swapusage"],
                        capture_output=True, text=True, timeout=2)
    return _parse_swap_used_bytes(r.stdout)


def _macos_ram_bytes() -> float | None:
    r = subprocess.run(["sysctl", "-n", "hw.memsize"],
                        capture_output=True, text=True, timeout=2)
    return float(r.stdout.strip())


_MEMINFO_FIELDS = {"MemTotal": "mem_total_kb", "MemAvailable": "mem_available_kb",
                    "SwapTotal": "swap_total_kb", "SwapFree": "swap_free_kb"}
_MEMINFO_VALUE_RE = re.compile(r"\s*(\d+)")


def _parse_meminfo(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        out_key = _MEMINFO_FIELDS.get(key.strip())
        if not out_key:
            continue
        m = _MEMINFO_VALUE_RE.match(rest)
        if m:
            out[out_key] = int(m.group(1))
    return out


def _linux_meminfo() -> dict:
    return _parse_meminfo(Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace"))


def read_signal() -> dict:
    """Current memory reading, shaped by platform. {"platform": "other"} on
    anything un-measured (incl. Windows) -- _memory_pressure_critical then
    reports not-critical and only the process cap can still deny."""
    if sys.platform == "darwin":
        return {"platform": "darwin", "pressure_level": _macos_pressure_level(),
                 "swap_used_bytes": _macos_swap_used_bytes(), "ram_bytes": _macos_ram_bytes()}
    if sys.platform.startswith("linux"):
        return {"platform": "linux", **_linux_meminfo()}
    return {"platform": "other"}


def _count_running(cls: str) -> int:
    """COUNT only. pgrep's default output is bare PIDs (no -l/-a here), so
    even a matched process's command line is never read by this hook."""
    argv = ["pgrep", "-x", "cargo"] if cls == "cargo" else ["pgrep", "-f", _PGREP_PATTERN[cls]]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=2)
    return len([ln for ln in (r.stdout or "").splitlines() if ln.strip()])


def _swap_used_gb(signal: dict) -> float | None:
    b = signal.get("swap_used_bytes")
    if isinstance(b, (int, float)):
        return round(b / 2 ** 30, 2)
    total, free = signal.get("swap_total_kb"), signal.get("swap_free_kb")
    if isinstance(total, (int, float)) and isinstance(free, (int, float)):
        return round((total - free) / 2 ** 20, 2)
    return None


def _memory_pressure_critical(signal: dict) -> tuple[bool, str]:
    """(is_critical, human-readable reading) for the deny/override log."""
    platform = signal.get("platform")
    if platform == "darwin":
        level = signal.get("pressure_level")
        swap_gb = _swap_used_gb(signal)
        ram = signal.get("ram_bytes")
        ratio = swap_gb * 2 ** 30 / ram if (swap_gb is not None and isinstance(ram, (int, float)) and ram > 0) else None
        parts = []
        if isinstance(level, int):
            parts.append(f"pressure level {level}")
        if ratio is not None:
            parts.append(f"swap {swap_gb:.2f} GB / RAM {ram / 2 ** 30:.1f} GB ({ratio:.0%})")
        critical = (isinstance(level, int) and level >= PRESSURE_LEVEL_CRITICAL) or (
            ratio is not None and ratio >= SWAP_USED_OVER_RAM_CRITICAL)
        return critical, ("; ".join(parts) if parts else "reading unavailable")
    if platform == "linux":
        total, avail = signal.get("mem_total_kb"), signal.get("mem_available_kb")
        if isinstance(total, (int, float)) and total > 0 and isinstance(avail, (int, float)):
            ratio = avail / total
            desc = f"MemAvailable {avail / 2 ** 20:.1f} GB / MemTotal {total / 2 ** 20:.1f} GB ({ratio:.0%} available)"
            return ratio < MEM_AVAILABLE_OVER_TOTAL_CRITICAL, desc
        return False, "reading unavailable"
    return False, "unmeasured platform"


def _deny_reason(cls: str, signal: dict, running: int) -> str | None:
    critical, mem_desc = _memory_pressure_critical(signal)
    if critical:
        return f"memory is critical ({mem_desc})"
    cap = CLASS_CAPS.get(cls)
    if cap is not None and running >= cap:
        return f"{cls} is already at its cap ({running}/{cap} running)"
    return None


def _deny_message(cls: str, reason: str, signal: dict, running: int) -> str:
    _, mem_desc = _memory_pressure_critical(signal)
    cap = CLASS_CAPS.get(cls, "?")
    return (
        f"[heavy-command-admission] DECLINED: the machine is under memory "
        f"pressure, not because of your {cls} command.\n"
        f"Reading: {mem_desc}; {running} {cls} process(es) already running (cap {cap}).\n"
        f"Reason: {reason}.\n"
        "Wait for the running one to finish, or narrow it: "
        "`tsc -p <one tsconfig>`, `vitest run <one file>`.\n"
        f"Human override: {OVERRIDE_VAR}=1 <command>"
    )


# ---- logging (never argv, never env) ----------------------------------------
def _claude_home() -> Path:
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or str(Path.home())
    return Path(home) / ".claude"


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_log(name: str, line: str) -> None:
    try:
        path = _claude_home() / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass  # logging must never crash or deny


def _log_override(cls: str, signal: dict) -> None:
    level = signal.get("pressure_level")
    swap_gb = _swap_used_gb(signal)
    _append_log(
        "heavy-admission-overrides.log",
        f"{_utcnow()} class={cls} pressure_level="
        f"{level if level is not None else 'n/a'} swap_used_gb="
        f"{swap_gb if swap_gb is not None else 'n/a'}\n",
    )


def _log_error(exc: Exception) -> None:
    _append_log("heavy-admission-errors.log", f"{_utcnow()} {type(exc).__name__}: {exc}\n")


# ---- dispatch -----------------------------------------------------------------
def _handle(payload: dict) -> int:
    """0 = allow, 2 = deny. Every read/parse/subprocess exception below
    propagates to main(), the single fail-open boundary."""
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input")
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not isinstance(command, str) or not command:
        return 0

    cls = detect_class(command)
    if cls is None:
        return 0

    overridden = os.environ.get(OVERRIDE_VAR) == "1" or inline_bypass(command, OVERRIDE_VAR)
    signal = read_signal()
    if overridden:
        _log_override(cls, signal)
        return 0

    running = _count_running(cls)
    reason = _deny_reason(cls, signal, running)
    if reason is None:
        return 0
    print(_deny_message(cls, reason, signal, running), file=sys.stderr)
    return 2


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # fail open: malformed stdin is not this hook's call to make
    try:
        return _handle(payload)
    except Exception as exc:
        _log_error(exc)
        return 0  # fail open: a broken reading must never become a broken shell


if __name__ == "__main__":
    sys.exit(main())
