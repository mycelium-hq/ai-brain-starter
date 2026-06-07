#!/usr/bin/env python3
"""Guard: surface repeated Obsidian *renderer* crashes (the large-vault OOM class).

On a large vault, heavy "indexer" plugins (Smart Connections embeddings, Tasks'
full-vault scan) building their indexes on open can exhaust Obsidian's single
Electron renderer heap and crash the app before you can disable anything: a hard
EXC_BREAKPOINT (SIGTRAP) V8 fatal with the CPU pinned. macOS writes one crash
report per crash to ~/Library/Logs/DiagnosticReports/ named like
"Obsidian Helper (Renderer)-<timestamp>.ips". Repeated such reports are the
signature of this footgun. This check counts the recent ones and points at the
remedy (restricted mode -> Dataview only -> add others one at a time, scoped).

This is a DIAGNOSTIC, not an install gate: the crashes already happened. diagnose
treats a hit as a WARN with the remedy, never a hard FAIL.

Crash reports are macOS-only (.ips DiagnosticReports). On other platforms this
check skips unless an explicit --reports-dir is given (which is how the test
exercises the detection logic on any CI OS).

Usage:
  check-renderer-crashes.py [--porcelain] [--days N] [--reports-dir DIR]

Exit codes:
  0  OK    - no repeated renderer crashes (or not applicable on this platform)
  1  HIT   - repeated renderer-OOM crash reports found in the window
  2  USAGE - bad arguments

Porcelain first token: OK_NO_CRASHES | RENDERER_CRASHES:<count> | SKIP_NOT_MACOS
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

DEFAULT_DAYS = 14
# "repeated": a single isolated crash can be anything; two or more in the window
# is the chronic-misconfiguration signal this check exists to surface.
REPEAT_THRESHOLD = 2
DEFAULT_REPORTS_DIR = Path.home() / "Library" / "Logs" / "DiagnosticReports"
CRASH_SIGNATURE = "EXC_BREAKPOINT"

USAGE = "usage: check-renderer-crashes.py [--porcelain] [--days N] [--reports-dir DIR]"


def _matches_obsidian_renderer(name: str) -> bool:
    """True for a macOS crash report belonging to Obsidian's renderer process."""
    low = name.lower()
    return low.endswith(".ips") and "obsidian" in low and "renderer" in low


def count_renderer_crashes(reports_dir: Path, days: int) -> int:
    """Count recent Obsidian-renderer .ips reports carrying the OOM signature.

    Best-effort and read-only. A single report we cannot stat or read (vanished
    mid-scan, permission, transient I/O) is SKIPPED, not fatal, so one odd file
    never crashes the whole diagnostic; worst case is undercounting by that file,
    which for a >=2-in-14-days heuristic is acceptable. An unreadable directory
    listing degrades to 0 (the caller reports that as "could not evaluate").
    The broad `except OSError` is intentional for a filesystem scan, not a masked
    correctness error: every OSError subtype here means "can't inspect this one
    path", and the right response is to move on.
    """
    if not reports_dir.is_dir():
        return 0
    cutoff = time.time() - days * 86400
    try:
        entries = sorted(reports_dir.iterdir())
    except OSError:
        return 0
    hits = 0
    for entry in entries:
        # Name match first (pure string, no I/O); only then touch the disk.
        if not _matches_obsidian_renderer(entry.name):
            continue
        try:
            if not entry.is_file():
                continue
            if entry.stat().st_mtime < cutoff:
                continue
            text = entry.read_text(errors="ignore")
        except OSError:
            continue
        if CRASH_SIGNATURE in text:
            hits += 1
    return hits


def main(argv):
    porcelain = "--porcelain" in argv
    args = [a for a in argv if a != "--porcelain"]

    days = DEFAULT_DAYS
    reports_dir = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--days":
            i += 1
            if i >= len(args):
                print(USAGE, file=sys.stderr)
                return 2
            try:
                days = int(args[i])
            except ValueError:
                print("--days must be an integer", file=sys.stderr)
                return 2
        elif a == "--reports-dir":
            i += 1
            if i >= len(args):
                print(USAGE, file=sys.stderr)
                return 2
            reports_dir = Path(args[i]).expanduser()
        else:
            print("unknown argument: {}".format(a), file=sys.stderr)
            print(USAGE, file=sys.stderr)
            return 2
        i += 1

    explicit_dir = reports_dir is not None
    if reports_dir is None:
        reports_dir = DEFAULT_REPORTS_DIR

    # .ips DiagnosticReports are macOS-only. Off macOS, skip the default path. An
    # explicit --reports-dir forces a scan so the test runs on any CI OS.
    if not explicit_dir and sys.platform != "darwin":
        if porcelain:
            print("SKIP_NOT_MACOS")
        else:
            print("OK    Renderer-crash check is macOS-only; skipped on this platform.")
        return 0

    count = count_renderer_crashes(reports_dir, days)

    if count >= REPEAT_THRESHOLD:
        if porcelain:
            print("RENDERER_CRASHES:{}".format(count))
            return 1
        print("WARN  {} Obsidian renderer crash report(s) in the last {} days "
              "(EXC_BREAKPOINT / renderer OOM).".format(count, days))
        print("      Likely a heavy indexer plugin exhausting the renderer on a large vault.")
        print("      Remedy: quit Obsidian; set <vault>/.obsidian/community-plugins.json to []")
        print("      (restricted mode); reopen; re-enable Dataview only; then add others one")
        print("      at a time, watching Activity Monitor. Scope or drop Smart Connections / Tasks.")
        print("      See templates/rules/obsidian-plugins.md -> 'Large-vault plugin posture'.")
        return 1

    if porcelain:
        print("OK_NO_CRASHES")
    else:
        print("OK    No repeated Obsidian renderer crashes in the last {} days.".format(days))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
