#!/usr/bin/env python3
"""dev-hub-refresh — keep the main <dev-root>/<repo> checkouts fresh (MYC-1893).

Bare hubs ROT: parked on stale feature branches, dirtied by edits, written into
by background jobs (STALE-BARE-CHECKOUT-READ, MYC-670 / MYC-1127). The read-time
guard warn-stale-dev-checkout.py DETECTS the rot; this is the PREVENTION half.

TWO auto-actions: fast-forward a hub that is clean, on its default branch, behind,
and carrying no local commits (a GUARANTEED ff, reversible via reflog); and return
a clean hub parked on a FINISHED branch (merged, or deleted on origin, with every
commit pushed) to its default branch, then ff it (tickets#1589). The finished
branch is kept. Everything else — dirty / detached / an open or unpushed branch /
diverged — is SURFACED, never auto-switched, auto-cleaned, or auto-recovered. Worktrees and any repo with a live
.session-lock are skipped. The reap/surface decision lives in _lib/dev_repo_scan.py
and is proven RED-then-green (incl. neg controls) by scripts/test_dev_hub_refresh.py.

The dev root comes from the shared resolver ($ABS_DEV_ROOT, else `dev_root` in
~/.claude/dev-hygiene.json, else ~/dev) like every sibling tool. Until 2026-11-06
this script alone hard-coded ~/dev, so on a machine whose code lives elsewhere it
scanned nothing, reported "0 hub(s)" as success, and every main folder rotted.
A dev root that does not exist is now an error, never an empty fleet.

FETCH-FIRST: a stale local ref misleads in BOTH directions (MYC-1893 correction),
so the scan `git fetch --quiet origin` each hub before judging. --no-fetch skips it.

DRY-RUN BY DEFAULT. --apply performs the fast-forwards and writes the state file
(~/.claude/.dev-hub-refresh-state.json) the SessionStart surfacer reads, plus a
per-run log to ~/.claude/logs/dev-hub-refresh/. A fast-forward only advances the
branch pointer, so every action is reversible from the reflog.

Usage:
  dev-hub-refresh.py                 # dry-run, fetch-first, whole ~/dev fleet
  dev-hub-refresh.py --apply         # ff clean mains, return finished branches, surface the rest
  dev-hub-refresh.py --repo ~/dev/x  # one hub
  dev-hub-refresh.py --no-fetch      # skip the pre-scan `git fetch origin`
  dev-hub-refresh.py --json          # machine-readable plan
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows cp1252-console safety (#313): force UTF-8 so a non-ASCII print can't crash.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # Python 3.7+
    except (AttributeError, ValueError):
        pass
# Test/one-off override only; the normal path is the shared resolver.
DEV_ROOT_OVERRIDE = os.environ.get("DEV_HUB_REFRESH_ROOT")
STATE_PATH = Path(
    os.environ.get("DEV_HUB_REFRESH_STATE")
    or (Path.home() / ".claude" / ".dev-hub-refresh-state.json")
)
LOG_DIR = Path(
    os.environ.get("DEV_HUB_REFRESH_LOG_DIR")
    or (Path.home() / ".claude" / "logs" / "dev-hub-refresh")
)
FETCH_TIMEOUT = 20


def _add_lib_to_path() -> bool:
    """Locate the deployed/in-repo _lib package and put it on sys.path."""
    for c in (
        os.environ.get("DEV_REPO_SCAN_DIR"),
        # This script's own sibling first: a ~/.claude/hooks copy can be an older
        # deploy, and a stale classifier here decides what gets switched.
        str(Path(__file__).resolve().parent.parent / "hooks"),  # in-repo (bin/../hooks)
        str(Path.home() / ".claude" / "hooks"),            # deployed
    ):
        if c and (Path(c) / "_lib" / "dev_repo_scan.py").exists():
            sys.path.insert(0, c)
            return True
    return False


if not _add_lib_to_path():
    print(
        "dev-hub-refresh: could not locate _lib/dev_repo_scan.py "
        "(set DEV_REPO_SCAN_DIR).",
        file=sys.stderr,
    )
    sys.exit(2)

from _lib.dev_repo_scan import (  # noqa: E402
    HUB_SURFACE_ACTIONS,
    classify_hub_action,
    discover_hubs,
    execute_hub_refresh,
    resolve_dev_root,
    summarize_hub_states,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch(repo: Path) -> None:
    """Read-only origin refresh, fail-open + bounded."""
    try:
        subprocess.run(
            ["git", "-C", str(repo), "fetch", "--quiet", "origin"],
            capture_output=True,
            timeout=FETCH_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


def refresh_fleet(repos, *, apply: bool, fetch: bool):
    """Fetch-first (optional), then classify + execute each hub.

    Returns (states, results). States are the POST-action classification so an
    ff'd hub reads as current in the state file (not perpetually "behind").
    """
    if fetch:
        for r in repos:
            _fetch(r)
    states, results = [], []
    for r in repos:
        st = classify_hub_action(r)
        res = execute_hub_refresh(st, apply=apply)
        if res.get("applied"):
            st = classify_hub_action(r)  # reflect the fast-forward
        states.append(st)
        results.append(res)
    return states, results


def _state_payload(states, results, applied: bool) -> dict:
    return {
        "generated_at": _utcnow(),
        "applied": applied,
        "hubs": [
            {
                "repo": s.repo.name,
                "path": str(s.repo),
                "action": s.action,
                "behind": s.behind,
                "ahead": s.ahead,
                "dirty": s.dirty,
                "current_branch": s.current_branch,
                "default_branch": s.default_branch,
                "reason": s.reason,
            }
            for s in states
        ],
        "summary": summarize_hub_states(states),
        "ff_applied": [Path(r["repo"]).name for r in results if r.get("applied")],
        "returned": [
            {"repo": Path(r["repo"]).name, "from": r["returned_from"]}
            for r in results if r.get("applied") and r.get("returned_from")
        ],
    }


def _write_json(path: Path, payload: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Keep main dev checkouts fresh: ff clean mains, return "
                    "finished branches, surface the rest."
    )
    ap.add_argument("--apply", action="store_true",
                    help="perform the fast-forwards (default: dry-run)")
    ap.add_argument("--repo", help="limit to one hub path (default: the whole dev root)")
    ap.add_argument("--no-fetch", action="store_true",
                    help="skip the pre-scan `git fetch origin` freshness pass")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.repo:
        repos = [Path(args.repo).expanduser()]
    else:
        dev_root = (Path(DEV_ROOT_OVERRIDE).expanduser() if DEV_ROOT_OVERRIDE
                    else resolve_dev_root())
        if not dev_root.is_dir() and dev_root == Path.home() / "dev":
            # Nothing configured and no ~/dev: most members keep no code repos
            # at all. That is not a failure, and a daily red here would be noise.
            if not args.quiet:
                print(f"dev-hub-refresh: no code folder on this machine ({dev_root} "
                      f"is absent and no dev_root is configured) — nothing to do.")
            return 0
        if not dev_root.is_dir():
            # A CONFIGURED dev root that is not there is not a clean fleet; it is
            # this tool not running. "Scanned 0 hubs" would read as success.
            print(f"dev-hub-refresh: dev root {dev_root} does not exist — nothing "
                  f"was checked. Set dev_root in ~/.claude/dev-hygiene.json "
                  f"(or ABS_DEV_ROOT) to where your code repos live.",
                  file=sys.stderr)
            return 1
        repos = discover_hubs(dev_root)
    states, results = refresh_fleet(repos, apply=args.apply, fetch=not args.no_fetch)
    payload = _state_payload(states, results, args.apply)

    # The state file feeds the cheap SessionStart surfacer; refresh it every run
    # (dry-run included) so the surface stays current between --apply cycles.
    _write_json(STATE_PATH, payload)

    ff_done = payload["ff_applied"]
    summary = payload["summary"]

    if args.json:
        print(json.dumps(
            {"applied": args.apply, "ff_applied": ff_done,
             "results": results, "summary": summary}, indent=2))
    elif not args.quiet:
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"dev-hub-refresh {mode} — {len(repos)} hub(s) scanned")
        print(f"  ff: {summary['ff']}  returned to default: {summary['returned']}  "
              f"surfaced (need human): {summary['surfaced']}  "
              f"max-behind: {summary['max_behind']}")
        if ff_done:
            print(f"  fast-forwarded: {', '.join(ff_done)}")
        for r in payload["returned"]:
            print(f"  RETURNED {r['repo']}  from finished branch {r['from']} (branch kept)")
        for s in states:
            if s.action in HUB_SURFACE_ACTIONS:
                br = s.current_branch or "DETACHED"
                why = f" — {s.reason}" if s.reason else ""
                print(f"  SURFACE  {s.repo.name}  [{s.action}]  on {br}, "
                      f"{s.behind} behind, {s.ahead} ahead{why}")
            elif s.action == "return" and not args.apply:
                print(f"  RETURN   {s.repo.name}  from {s.current_branch} "
                      f"({s.reason}), {s.behind} behind")
        if not args.apply and (summary["ff"] or summary["returned"]):
            print("\nRe-run with --apply to fast-forward the clean mains and return "
                  "the finished branches (SURFACE items are never auto-touched).")

    if args.apply:
        _write_json(
            LOG_DIR / f"refresh-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json",
            payload,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
