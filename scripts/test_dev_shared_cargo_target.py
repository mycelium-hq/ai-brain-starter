#!/usr/bin/env python3
"""Controls for dev-shared-cargo-target: runs the real script on temp configs.

Run: python3 scripts/test_dev_shared_cargo_target.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("dev-shared-cargo-target.py")


def run(cfg: Path, *extra: str) -> str:
    r = subprocess.run([sys.executable, str(SCRIPT), "--config", str(cfg), "--dir", "/x/t", *extra],
                       capture_output=True, text=True, check=True)
    return r.stdout


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        cfg = d / "sub" / "config.toml"  # missing file and missing folder
        run(cfg)
        assert not cfg.exists(), "dry run must write nothing"
        run(cfg, "--apply")
        assert 'target-dir = "/x/t"' in cfg.read_text()
        before = cfg.read_text()
        assert "already set" in run(cfg, "--apply")
        assert cfg.read_text() == before, "second apply must change nothing"

        other = d / "other.toml"  # existing [build] keeps its keys; a set target-dir wins
        other.write_text('[net]\nretry = 3\n\n[build]\njobs = 4\n')
        run(other, "--apply")
        t = other.read_text()
        assert 'jobs = 4' in t and 'retry = 3' in t and t.count("[build]") == 1 and 'target-dir = "/x/t"' in t
        mine = d / "mine.toml"
        mine.write_text('[build]\ntarget-dir = "/mine"\n')
        run(mine, "--apply")
        assert mine.read_text() == '[build]\ntarget-dir = "/mine"\n', "never replace the user's own target-dir"
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
