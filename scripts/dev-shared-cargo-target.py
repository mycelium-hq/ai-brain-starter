#!/usr/bin/env python3
"""dev-shared-cargo-target — one cargo target dir for every worktree (tickets#7084).

Every session worktree used to compile Rust from scratch (8m47s, 418 crates,
892 s of CPU measured on a 10-core Mac). With one shared target dir the second
worktree rebuilds only the app crate (4m08s, 242 s of CPU), and new worktrees
stop adding GBs of `target/`.

Writes `[build] target-dir` into the user-level cargo config only when that file
has no `build` or `target-dir` text at all; otherwise it prints the line to add
by hand. CARGO_TARGET_DIR (CI sets its own) wins over the config at cargo run time.

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

TOUCHY = re.compile(r"target-dir|\bbuild\b")


def plan(text: str, target: str) -> str | None:
    """New file text, or None when the file already mentions `build` or
    `target-dir` in any spelling (table, dotted key, inline table, comment).
    TOML has too many ways to write those to edit safely, so a human adds the
    line; a wrong edit would make cargo reject the whole config."""
    if TOUCHY.search(text):
        return None
    gap = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
    return f'{text}{gap}[build]\ntarget-dir = "{target}"\n'


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
        print(f"{cfg} already mentions build/target-dir, so it is left alone.")
        print(f'Add by hand under [build]:  target-dir = "{a.dir}"')
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
