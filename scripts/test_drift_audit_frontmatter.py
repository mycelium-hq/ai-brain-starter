#!/usr/bin/env python3
"""
test_drift_audit_frontmatter.py — the generated Drift Audit must parse as YAML.

drift-detection.py writes `Meta/Drift Audit.md` with a frontmatter block. The
`purpose:` value carries both ": " and "'":

    purpose: Multi-edit drift audit. ... Include: '*.md'.

An unquoted YAML scalar containing ": " is read as a nested mapping, so
yaml.safe_load raised "mapping values are not allowed here" and the file was
invisible to every consumer that parses frontmatter — Dataview queries, the
metadata extractors, any vault-wide frontmatter audit. Nothing errored; the
file simply stopped counting. A generator that emits unparseable frontmatter
and a generator that works report the same green.

This suite runs the real script against a throwaway git vault and asserts the
frontmatter it produces round-trips through yaml.safe_load, including for an
--include value chosen to break naive quoting.

Every case is also parsed with yaml.CSafeLoader when PyYAML is built against
libyaml (yaml.__with_libyaml__), not only the pure yaml.SafeLoader that
yaml.safe_load always uses. The two disagree on an astral-plane character
(one outside the Basic Multilingual Plane, e.g. an emoji): json.dumps's
default ensure_ascii=True escapes it to a UTF-16 SURROGATE PAIR of two
separate \\uXXXX sequences. The pure SafeLoader quietly reassembles those into
a single lone-surrogate Python string (which then blows up the moment
anything tries to re-encode it as UTF-8); the libyaml-backed CSafeLoader --
what a production PyYAML install actually runs when libyaml is available --
raises ScannerError outright on the same input. A suite that only calls
yaml.safe_load never sees either failure. ensure_ascii=False (this fix) emits
the real UTF-8 character instead, which both loaders parse as one codepoint.

Run:
  python3 scripts/test_drift_audit_frontmatter.py
  python3 scripts/test_drift_audit_frontmatter.py --verbose

Exits 0 on all-pass, 1 on any failure. CI-runnable.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "drift-detection.py"

try:
    import yaml  # type: ignore
except ImportError:
    print("ERROR: PyYAML required. Install with: python3 -m pip install --user pyyaml")
    sys.exit(1)


def git(vault: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(vault),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def build_vault(vault: Path, filename: str = "Note.md", edits: int = 6) -> None:
    """A git vault with one file edited enough times to land in the audit.

    `filename` may include a subfolder (e.g. the astral-emoji case's
    "\U0001F4D3 Journals/Note.md") -- its parent is created too.
    """
    git(vault, "init", "-q")
    git(vault, "config", "user.email", "test@example.com")
    git(vault, "config", "user.name", "Test")
    (vault / "Meta").mkdir(parents=True, exist_ok=True)
    note = vault / filename
    note.parent.mkdir(parents=True, exist_ok=True)
    for i in range(edits):
        note.write_text(f"# Note\n\nrevision {i}\n", encoding="utf-8")
        git(vault, "add", filename)
        git(vault, "commit", "-q", "-m", f"edit {i}")


def run_script(vault: Path, include: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, VAULT_ROOT=str(vault))
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--include", include, "--min-edits", "2"],
        cwd=str(vault),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def read_frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise AssertionError("generated file has no frontmatter block")
    end = text.find("\n---", 3)
    if end == -1:
        raise AssertionError("frontmatter block is never closed")
    return text[3:end]


# (case name, filename to create, --include glob). The glob is also a git
# pathspec, so it has to actually match the file or the script exits before
# writing anything.
CASES = [
    ("default glob", "Note.md", "*.md"),
    # An apostrophe inside the value: the purpose line wraps --include in
    # single quotes, so this is the shape that a naive single-quoted scalar
    # cannot survive. json.dumps can.
    ("glob with an apostrophe", "Note's.md", "*'s.md"),
    # An astral-plane character (outside the Basic Multilingual Plane) --
    # a real vault folder name, not a synthetic edge case. json.dumps's
    # default ensure_ascii=True escapes this to a UTF-16 surrogate pair that
    # the pure SafeLoader silently mis-parses and libyaml's CSafeLoader
    # rejects outright (review F5). ensure_ascii=False fixes both.
    ("astral emoji glob", "\U0001F4D3 Journals/AstralNote.md", "\U0001F4D3 Journals/*.md"),
]


# yaml.safe_load() always uses the pure-Python SafeLoader, never the
# libyaml-backed CSafeLoader even when it's available. A production install
# with libyaml (the common case: `python3 -c "import yaml; print(yaml.
# __with_libyaml__)"`) parses frontmatter with CSafeLoader whenever calling
# code asks for it by name, and the two loaders disagree on a surrogate pair
# (see the module docstring) -- so both are exercised here, not just the one
# yaml.safe_load happens to pick.
_LOADERS = [("SafeLoader", yaml.SafeLoader)]
if getattr(yaml, "__with_libyaml__", False):
    _LOADERS.append(("CSafeLoader", yaml.CSafeLoader))


def run_case(name: str, filename: str, include: str, verbose: bool) -> bool:
    tmp = Path(tempfile.mkdtemp(prefix="drift-audit-test-"))
    try:
        build_vault(tmp, filename)
        proc = run_script(tmp, include)
        out = tmp / "Meta" / "Drift Audit.md"
        if not out.exists():
            print(f"  FAIL {name}: no Meta/Drift Audit.md written")
            if verbose:
                print("    stdout:", proc.stdout.strip()[:400])
                print("    stderr:", proc.stderr.strip()[:400])
            return False

        fm = read_frontmatter(out)
        parsed = {}
        for loader_name, loader in _LOADERS:
            try:
                # Both loaders in _LOADERS are the SAFE ones (SafeLoader is
                # what yaml.safe_load calls internally; CSafeLoader is its
                # libyaml-accelerated equivalent) -- never yaml.Loader or
                # unsafe_load. Explicit Loader= is required here because
                # safe_load() hardcodes SafeLoader and cannot select
                # CSafeLoader at all.
                parsed[loader_name] = yaml.load(fm, Loader=loader)
            except yaml.YAMLError as e:
                print(f"  FAIL {name}: frontmatter is not valid YAML under {loader_name}")
                print(f"    {str(e).splitlines()[0]}")
                if verbose:
                    print("    frontmatter was:")
                    for line in fm.strip().splitlines():
                        print("      " + line)
                return False

        for loader_name, data in parsed.items():
            if not isinstance(data, dict):
                print(f"  FAIL {name}: frontmatter parsed to {type(data).__name__} under {loader_name}, not a mapping")
                return False
            for key in ("creationDate", "type", "purpose", "generator"):
                if key not in data:
                    print(f"  FAIL {name}: frontmatter lost the '{key}' key under {loader_name}")
                    return False
            if include not in str(data["purpose"]):
                print(f"  FAIL {name}: purpose does not round-trip the --include value under {loader_name}")
                print(f"    got: {data['purpose']!r}")
                return False
            try:
                str(data["purpose"]).encode("utf-8")
            except UnicodeEncodeError as e:
                print(f"  FAIL {name}: purpose parsed under {loader_name} but won't re-encode as UTF-8: {e}")
                return False

        data = parsed["SafeLoader"]
        if verbose:
            print(f"    purpose -> {data['purpose']!r}  (checked: {', '.join(parsed)})")
        print(f"  ok   {name}")
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not SCRIPT.exists():
        print(f"ERROR: {SCRIPT} not found")
        return 1

    print(f"drift-detection.py frontmatter: {len(CASES)} case(s)")
    failures = 0
    for name, filename, include in CASES:
        if not run_case(name, filename, include, args.verbose):
            failures += 1

    print()
    if failures:
        print(f"{failures} of {len(CASES)} case(s) FAILED")
        return 1
    print(f"all {len(CASES)} case(s) passed")
    return 0


if __name__ == "__main__":
    # Windows cp1252-console safety (#313): force UTF-8 so a non-ASCII print can't crash.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
