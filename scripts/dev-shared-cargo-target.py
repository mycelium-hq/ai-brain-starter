#!/usr/bin/env python3
"""dev-shared-cargo-target — one cargo target dir for every worktree (tickets#7084).

Every session worktree used to compile Rust from scratch (8m47s, 418 crates,
892 s of CPU measured on a 10-core Mac). With one shared target dir the second
worktree rebuilds only the app crate (4m08s, 242 s of CPU), and new worktrees
stop adding GBs of `target/`.

Writes `[build] target-dir` into the user-level cargo config. It never replaces
an existing `target-dir` or a CARGO_TARGET_DIR env var (CI sets its own and wins).

  dev-shared-cargo-target.py            # show what is set
  dev-shared-cargo-target.py --apply    # add the line if missing
  --dir PATH   target dir (default ~/code/.cargo-target-shared)
  --config P   cargo config to edit (default ~/.cargo/config.toml)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HAS_TARGET_DIR = re.compile(r"^\s*target-dir\s*=", re.M)
HAS_BUILD = re.compile(r"^\s*\[build\]\s*$", re.M)


def plan(text: str, target: str) -> str | None:
    """New file text, or None when a target-dir is already set."""
    if HAS_TARGET_DIR.search(text):
        return None
    line = f'target-dir = "{target}"\n'
    m = HAS_BUILD.search(text)
    if m:
        return text[: m.end()] + "\n" + line + text[m.end():]
    sep = "" if not text or text.endswith("\n") else "\n"
    gap = "\n" if text else ""
    return f"{text}{sep}{gap}[build]\n{line}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dir", default=str(Path.home() / "code" / ".cargo-target-shared"))
    ap.add_argument("--config", default=str(Path.home() / ".cargo" / "config.toml"))
    a = ap.parse_args()
    cfg = Path(a.config)
    text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
    new = plan(text, a.dir)
    if new is None:
        print(f"already set in {cfg}: nothing to do")
        return 0
    if not a.apply:
        print(f"would add target-dir = {a.dir} to {cfg} (re-run with --apply)")
        return 0
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(new, encoding="utf-8")
    print(f"added target-dir = {a.dir} to {cfg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
