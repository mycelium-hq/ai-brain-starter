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
                       capture_output=True, text=True, check=True,
                       encoding="utf-8", errors="replace")
    return r.stdout


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        cfg = d / "sub" / "config.toml"  # missing file and missing folder
        run(cfg)
        assert not cfg.exists(), "dry run must write nothing"
        run(cfg, "--apply")
        assert 'target-dir = "/x/t"' in cfg.read_text(encoding="utf-8")
        before = cfg.read_text(encoding="utf-8")
        assert "by hand" in run(cfg, "--apply")
        assert cfg.read_text(encoding="utf-8") == before, "second apply must change nothing"

        for name, body in {
            "plain-build": '[build]\njobs = 4\n',
            "comment-header": '[build] # hi\njobs = 1\n',
            "dotted": 'build.target-dir = "q"\n',
            "inline": 'build = { target-dir = "q" }\n',
            "quoted": '[build]\n"target-dir" = "q"\n',
        }.items():
            f = d / f"{name}.toml"
            f.write_text(body, encoding="utf-8")
            out = run(f, "--apply")
            assert f.read_text(encoding="utf-8") == body, f"{name}: must be left alone"
            assert "by hand" in out
        net = d / "net.toml"  # no build text: appended, existing table kept
        net.write_text('[net]\nretry = 3', encoding="utf-8")
        run(net, "--apply")
        assert net.read_text(encoding="utf-8") == '[net]\nretry = 3\n\n[build]\ntarget-dir = "/x/t"\n'
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
