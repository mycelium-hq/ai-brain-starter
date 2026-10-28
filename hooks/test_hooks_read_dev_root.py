#!/usr/bin/env python3
"""Hooks that need the dev root read the install's config, not a hardcoded ~/dev.

An install that keeps its repo copies elsewhere says so with `dev_root` in
~/.claude/dev-hygiene.json. Hooks that hardcoded ~/dev skipped every repo there
without a word. Each now asks _lib/dev_root.resolve_dev_root(), the stdlib-only
resolver that dev_repo_scan.resolve_dev_root() delegates to.

Run: python3 hooks/test_hooks_read_dev_root.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
# hook -> the module-level name that holds its dev root
ROOT_NAMES = {
    "auto-capture-public-ships.py": "DEV",
    "create-dev-repo-checkpoint.py": "DEV_ROOT",
    "verify-discoverability-on-close.py": "DEV_ROOT",
    "warn-stale-dev-checkout.py": "DEV",
}


def load(name: str):
    spec = importlib.util.spec_from_file_location(name[:-3].replace("-", "_"), HOOKS / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    failed = []
    with tempfile.TemporaryDirectory() as td:
        home, code = Path(td), Path(td) / "code"
        (home / ".claude").mkdir()
        (home / ".claude" / "dev-hygiene.json").write_text(
            json.dumps({"dev_root": str(code)}), encoding="utf-8")
        os.environ.update(HOME=td, USERPROFILE=td, DEV_WORKTREE_WARN="1")
        for var in ("ABS_DEV_ROOT", "STALE_CHECKOUT_DEV_ROOT"):
            os.environ.pop(var, None)

        for name, attr in ROOT_NAMES.items():
            got = getattr(load(name), attr, None)
            if got != code:
                failed.append(f"{name}: {attr} is {got}, not the configured {code}")

        # $ABS_DEV_ROOT outranks the config; the stale-checkout guard's own override outranks both.
        os.environ.update(ABS_DEV_ROOT=str(home / "env"), STALE_CHECKOUT_DEV_ROOT=str(home / "stale"))
        if load("create-dev-repo-checkpoint.py").DEV_ROOT != home / "env":
            failed.append("$ABS_DEV_ROOT no longer wins over the config's dev_root")
        if load("warn-stale-dev-checkout.py").DEV != home / "stale":
            failed.append("STALE_CHECKOUT_DEV_ROOT no longer overrides the dev root")
        for var in ("ABS_DEV_ROOT", "STALE_CHECKOUT_DEV_ROOT"):
            os.environ.pop(var)

        # Two linked worktrees (a `.git` FILE each) over a warn threshold of 1.
        for i in range(2):
            (code / f"repo-{i}").mkdir(parents=True)
            (code / f"repo-{i}" / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
        signal = load("worktree-footprint-signal.py").sibling_worktree_signal()
        if str(code) not in signal:
            failed.append(f"worktree-footprint-signal ignored the configured root: {signal!r}")

    for f in failed:
        print(f"FAIL  {f}")
    print("FAILED" if failed else "OK - hooks read the configured dev root")
    return 1 if failed else 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Windows cp1252 console safety (#313)
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
