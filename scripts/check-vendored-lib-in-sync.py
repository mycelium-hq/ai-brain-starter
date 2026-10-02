#!/usr/bin/env python3
"""check-vendored-lib-in-sync.py - a vendored _lib mirror rots the moment its
canonical source changes and nothing says so.

THE CLASS THIS EXISTS FOR (commit 7ce621fc)
    tests/integration/test_extractors_localized_vault.sh makes "a private copy
    of scripts/" - extractors/ wholesale, plus vault-metadata-extract.py and
    vault-insight-engine.py named individually - to prove the tree still works
    as a plain copy, not the repo checkout. vault-insight-engine.py reaches
    hooks/_lib via `../hooks` on sys.path, which does not exist in that copy,
    so the script died at import with `ModuleNotFoundError: No module named
    '_lib'` the moment the test actually ran it.

    7ce621fc fixed the immediate failure by vendoring hooks/_lib/__init__.py
    and hooks/_lib/safe_read.py into scripts/extractors/_lib/, byte-identical
    to the source at the time. Per that commit and the comment it left at
    scripts/vault-insight-engine.py (beside the real hooks/_lib sys.path
    entry): the real hooks/_lib always wins when it is present (its sys.path
    entry lands first); the extractors/_lib mirror is a FALLBACK that only
    activates when ../hooks is entirely absent - exactly the localized-copy
    shape that integration test exercises, and a real deploy could hand this
    script the same shape.

    That comment ends: "Keep the mirror byte-identical to hooks/_lib - diff
    the two if hooks/_lib/safe_read.py ever changes." That is a promise a
    human has to remember to keep, by hand, forever, with nothing checking it.
    hooks/_lib/safe_read.py is an AUDITED bounded-read safety primitive
    (cloud placeholder / stalled mount / FIFO handling - see its own
    docstring). The moment someone patches it - a new offline-placeholder
    case, a tighter timeout, a fixed race - the vendored copy silently falls
    behind. Nothing imports it in the normal checkout (hooks/_lib wins there),
    so no test in the normal run path would ever notice. Only the fallback
    shape - a bare copy of scripts/ with no sibling hooks/ - would actually
    execute the stale reader, with no error at all: the import succeeds, the
    function runs, it just enforces last year's safety rules.

    No existing guard catches this. scripts/check-clobbered-vault-scripts.py
    is the nearest neighbor by name, but it polices a different sync
    direction entirely: a live VAULT's <meta>/scripts/ copy drifting from
    what this REPO ships. It has no notion of a mirror living inside this
    repo's own tree, and does not look at scripts/extractors/_lib/ at all.

WHAT THIS CHECKS
    Every vendored `_lib` directory anywhere under the repo root, other than
    the canonical hooks/_lib itself, discovered from the tracked file list -
    not hardcoded, so a second mirror added later (for the same reason a
    first one was) is covered with no edit here. For every tracked file
    inside such a directory, its counterpart at the same relative path under
    hooks/_lib/ must exist and match byte for byte. Two distinct failure
    shapes, reported separately:

        DIVERGED            the mirrored file exists in both places but its
                             bytes differ from the hooks/_lib source.
        MISSING-CANONICAL   the mirrored file has no counterpart under
                             hooks/_lib/ at all - vendoring something that
                             was since deleted or renamed upstream.

    A file that fails to read at all (permission error, cloud placeholder,
    something mid-write) is its own UNREADABLE finding - never silently
    skipped. A gate that drops an unreadable file from its population would
    report success over exactly the file it could not look at.

WHY GIT LS-FILES, NOT A DIRECTORY WALK
    Discovery reads the tracked file list via `git ls-files` - one bounded
    subprocess call - rather than os.walk/Path.rglob over the filesystem.
    Two independent reasons: an untracked scratch file cannot change this
    guard's verdict, and scripts/check-cloud-safe-file-walkers.py polices
    every recursive walker that also reads file content in this repo's
    Python fleet. A hand-rolled directory walk here would be exactly the
    shape that guard exists to catch; git ls-files sidesteps the question
    completely; the content reads that follow route through the same
    audited hooks/_lib/safe_read.safe_read_bytes this checker is guarding,
    per the cloud-safe-walker convention (bounded size, bounded wall-clock,
    regular-file-only) rather than a bare Path.read_bytes().

    That safe_read primitive is always imported from THIS repo's own
    hooks/_lib/ (resolved from this script's own location), never from
    whatever tree `--root` points at - the tree being audited is exactly the
    one place a stale or tampered copy is not a trustworthy read primitive.

Exit: 0 clean, 1 findings, 2 could not run.

Usage:
    check-vendored-lib-in-sync.py                 # audit this repo
    check-vendored-lib-in-sync.py --root PATH     # audit a different tree
    check-vendored-lib-in-sync.py --self-test     # negative + positive controls
"""
# exit-contract: ENFORCING

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "hooks"))

from _lib.safe_read import safe_read_bytes  # noqa: E402

CANONICAL_DIR = "hooks/_lib"


class VendorSyncError(RuntimeError):
    """The tracked-file population could not be enumerated at all."""


@dataclass(frozen=True)
class Finding:
    kind: str  # "DIVERGED" | "MISSING-CANONICAL" | "UNREADABLE"
    mirror_rel: str
    canonical_rel: str
    detail: str


def _tracked_files(root: Path) -> list[str]:
    """Every path git tracks under `root`, as repo-relative POSIX strings.

    Raises VendorSyncError on anything that means the population itself is
    untrustworthy: git failing to run, a non-zero exit, or a suspicious empty
    result. An empty population is not a clean tree - it means the check
    looked at nothing, which check-exit-contract.py's own precedent (this
    repo's population-enumeration gate) treats as UNEVALUATED, not OK.
    """
    try:
        res = subprocess.run(
            ["git", "ls-files"],
            cwd=str(root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VendorSyncError(
            f"git ls-files failed to run under {root}: {exc}") from exc
    if res.returncode != 0:
        raise VendorSyncError(
            f"git ls-files exited {res.returncode} under {root}: "
            f"{(res.stderr or '').strip()}")
    files = [line for line in res.stdout.split("\n") if line]
    if not files:
        raise VendorSyncError(
            f"git ls-files returned zero tracked files under {root} - either "
            "this is not a git checkout, or the population enumeration is "
            "broken. An empty population is not a clean tree.")
    return files


def discover_vendor_mirrors(tracked: list[str]) -> dict[str, list[str]]:
    """Map each vendored `_lib` directory (repo-relative, e.g.
    "scripts/extractors/_lib") to the tracked file paths under it, for every
    `_lib` directory in the tree except the canonical hooks/_lib.

    Directories are discovered from the tracked file list alone - by path
    segment, not by a hardcoded name - so a new vendored mirror added later
    for the same ModuleNotFoundError-under-a-bare-copy reason is picked up
    automatically, with no edit to this function.
    """
    mirrors: dict[str, list[str]] = {}
    for rel in tracked:
        parts = rel.split("/")
        if "_lib" not in parts:
            continue
        idx = parts.index("_lib")
        lib_dir = "/".join(parts[: idx + 1])
        if lib_dir == CANONICAL_DIR:
            continue
        mirrors.setdefault(lib_dir, []).append(rel)
    return mirrors


def check_mirrors(root: Path, mirrors: dict[str, list[str]]) -> list[Finding]:
    """Compare every discovered mirror file against its hooks/_lib counterpart.

    Reads go through safe_read_bytes (bounded size, bounded wall-clock,
    regular-file-only) on both sides, never a bare Path.read_bytes() -
    exactly the primitive this checker exists to keep in sync, used here to
    read the very files it is comparing.
    """
    findings: list[Finding] = []
    for lib_dir, files in sorted(mirrors.items()):
        prefix = lib_dir + "/"
        for mirror_rel in sorted(files):
            suffix = mirror_rel[len(prefix):]
            canonical_rel = f"{CANONICAL_DIR}/{suffix}"

            mirror_read = safe_read_bytes(root / mirror_rel)
            if not mirror_read.ok:
                findings.append(Finding(
                    "UNREADABLE", mirror_rel, canonical_rel,
                    f"{mirror_read.status}: {mirror_read.detail}"))
                continue

            canon_read = safe_read_bytes(root / canonical_rel)
            if canon_read.status == "missing":
                findings.append(Finding(
                    "MISSING-CANONICAL", mirror_rel, canonical_rel,
                    "no counterpart file under hooks/_lib/"))
                continue
            if not canon_read.ok:
                findings.append(Finding(
                    "UNREADABLE", canonical_rel, canonical_rel,
                    f"{canon_read.status}: {canon_read.detail}"))
                continue

            if mirror_read.data != canon_read.data:
                findings.append(Finding(
                    "DIVERGED", mirror_rel, canonical_rel,
                    f"{len(mirror_read.data or b'')} byte(s) vs "
                    f"{len(canon_read.data or b'')} byte(s) in the canonical "
                    "copy"))
    return findings


def format_finding(f: Finding) -> str:
    if f.kind == "DIVERGED":
        return (
            f"DIVERGED  {f.mirror_rel}\n"
            f"    differs from its canonical source {f.canonical_rel} "
            f"({f.detail}).\n"
            f"    Remedy: re-copy {f.canonical_rel} over {f.mirror_rel}."
        )
    if f.kind == "MISSING-CANONICAL":
        return (
            f"MISSING-CANONICAL  {f.mirror_rel}\n"
            f"    is vendored here but hooks/_lib/ has no file at "
            f"{f.canonical_rel} ({f.detail}).\n"
            f"    Remedy: restore {f.canonical_rel} under hooks/_lib/, or "
            f"delete {f.mirror_rel} if it should no longer be vendored."
        )
    return (
        f"UNREADABLE  {f.mirror_rel}\n"
        f"    could not be read while comparing against {f.canonical_rel} "
        f"({f.detail}).\n"
        f"    Remedy: investigate the file (permissions, size, cloud "
        f"placeholder) and re-run."
    )


def run_check(root: Path) -> int:
    tracked = _tracked_files(root)
    mirrors = discover_vendor_mirrors(tracked)

    if not mirrors:
        print("[vendored-lib-sync] 0 vendored _lib mirror(s) found outside "
              f"{CANONICAL_DIR}/ under {root} - nothing to check.")
        return 0

    findings = check_mirrors(root, mirrors)
    file_count = sum(len(v) for v in mirrors.values())

    if not findings:
        print(f"[vendored-lib-sync] clean - {file_count} file(s) across "
              f"{len(mirrors)} mirror dir(s) "
              f"({', '.join(sorted(mirrors))}) match {CANONICAL_DIR}/ byte "
              "for byte.")
        return 0

    print(f"[vendored-lib-sync] FINDINGS ({len(findings)}):\n")
    for finding in findings:
        for line in format_finding(finding).splitlines():
            print(f"  {line}")
        print()
    print("Why this is a gate: a vendored copy of an audited safety "
          "primitive rots silently the instant its canonical source changes "
          "and nothing re-syncs the mirror - the normal checkout never "
          "notices because hooks/_lib always wins there. Only a localized "
          "copy with no sibling hooks/ (a real, tested shape - see "
          "tests/integration/test_extractors_localized_vault.sh) actually "
          "runs the stale mirror, silently.")
    return 1


# --- self-test: the negative controls ---------------------------------------
# Each case builds the defect this checker exists to catch and asserts it
# goes RED, then asserts the clean form stays quiet. A self-test that only
# exercises the clean path proves the guard ran, never that it bites.

def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(root), check=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=30)


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _build_fixture(tmp: Path) -> None:
    """A tiny fixture repo with TWO independently-discoverable vendor
    mirrors (proving auto-discovery needs no hardcoded path) and a nested
    subpath in one of them (proving the comparison is not flat-directory
    only). Every file starts byte-identical to its canonical counterpart.
    """
    _git(tmp, "init", "-q")

    _write(tmp / "hooks/_lib/__init__.py", b'"""fixture lib."""\n')
    _write(tmp / "hooks/_lib/safe_read.py", b"CANONICAL = 1\n" * 5)
    _write(tmp / "hooks/_lib/sub/deep.py", b"DEEP = 1\n")

    # Mirror A: flat, mirrors the real scripts/extractors/_lib/ shape.
    _write(tmp / "scripts/extractors/_lib/__init__.py", b'"""fixture lib."""\n')
    _write(tmp / "scripts/extractors/_lib/safe_read.py", b"CANONICAL = 1\n" * 5)

    # Mirror B: a second, differently-located mirror with a nested file,
    # never named anywhere in this script - only discovered structurally.
    _write(tmp / "tools/vendored/_lib/sub/deep.py", b"DEEP = 1\n")

    _git(tmp, "add", "-A")


def self_test() -> int:
    import shutil
    import tempfile

    failures: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="check-vendored-lib-in-sync-selftest-"))
    try:
        _build_fixture(tmp)

        # --- positive control on discovery itself -------------------------
        # If discovery silently stopped matching, every case below would
        # "pass" for the wrong reason: zero mirrors found reads identically
        # to zero findings.
        tracked = _tracked_files(tmp)
        mirrors = discover_vendor_mirrors(tracked)
        expected_dirs = {"scripts/extractors/_lib", "tools/vendored/_lib"}
        if set(mirrors) != expected_dirs:
            failures.append(
                f"discovery: expected mirror dirs {expected_dirs}, got "
                f"{set(mirrors)}")
        expected_file_count = 3  # __init__.py + safe_read.py + sub/deep.py
        got_file_count = sum(len(v) for v in mirrors.values())
        if got_file_count != expected_file_count:
            failures.append(
                f"discovery: expected {expected_file_count} mirrored "
                f"file(s), got {got_file_count} ({mirrors})")

        # --- clean fixture: everything byte-identical -> zero findings ----
        findings = check_mirrors(tmp, mirrors)
        if findings:
            failures.append(
                f"clean fixture: expected 0 findings, got "
                f"{[(f.kind, f.mirror_rel) for f in findings]}")
        rc_clean = run_check(tmp)
        if rc_clean != 0:
            failures.append(
                f"run_check: expected exit 0 on a clean fixture, got "
                f"{rc_clean}")

        # --- NEGATIVE CONTROL: a byte-divergent mirror file must bite, and
        # must name the EXACT file, not just "something is wrong". ---------
        target = tmp / "scripts/extractors/_lib/safe_read.py"
        original = target.read_bytes()
        target.write_bytes(original + b"# tampered\n")
        findings2 = check_mirrors(tmp, discover_vendor_mirrors(
            _tracked_files(tmp)))
        diverged = [f for f in findings2 if f.kind == "DIVERGED"]
        if not diverged:
            failures.append(
                "negative control: a byte-divergent mirror file did not "
                "bite")
        elif diverged[0].mirror_rel != "scripts/extractors/_lib/safe_read.py":
            failures.append(
                "negative control bit the WRONG file: "
                f"{diverged[0].mirror_rel}")
        rc_dirty = run_check(tmp)
        if rc_dirty != 1:
            failures.append(
                f"run_check: expected exit 1 on a divergent mirror, got "
                f"{rc_dirty}")
        target.write_bytes(original)  # restore before the next sub-case

        # --- MISSING-CANONICAL: vendored file with no hooks/_lib sibling,
        # reported as a DISTINCT kind from DIVERGED. ------------------------
        orphan = tmp / "scripts/extractors/_lib/orphan.py"
        _write(orphan, b"# no counterpart under hooks/_lib\n")
        _git(tmp, "add", "-A")
        findings3 = check_mirrors(tmp, discover_vendor_mirrors(
            _tracked_files(tmp)))
        missing = [f for f in findings3 if f.kind == "MISSING-CANONICAL"]
        if not missing:
            failures.append(
                "missing-canonical control: an orphaned mirror file did not "
                "bite")
        elif missing[0].mirror_rel != "scripts/extractors/_lib/orphan.py":
            failures.append(
                f"missing-canonical control bit the WRONG file: "
                f"{missing[0].mirror_rel}")
        if any(f.kind == "DIVERGED" for f in missing):
            failures.append(
                "missing-canonical control: an absent counterpart was "
                "reported as DIVERGED, not as its own distinct kind")
        orphan.unlink()
        _git(tmp, "add", "-A")

        # --- clean again after both mutations are reverted -----------------
        findings4 = check_mirrors(tmp, discover_vendor_mirrors(
            _tracked_files(tmp)))
        if findings4:
            failures.append(
                "fixture did not return to clean after reverting both "
                f"mutations: {[(f.kind, f.mirror_rel) for f in findings4]}")

        # --- population-enumeration floor: a git-less root must not read as
        # a silent clean pass. --------------------------------------------
        empty_dir = tmp.parent / (tmp.name + "-not-a-repo")
        empty_dir.mkdir()
        try:
            try:
                _tracked_files(empty_dir)
                failures.append(
                    "a directory with no git repo did not raise "
                    "VendorSyncError")
            except VendorSyncError:
                pass
        finally:
            shutil.rmtree(empty_dir, ignore_errors=True)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print("SELF-TEST FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("OK - self-test: discovery finds exactly the planted mirrors (a "
          "positive control on the search itself), a clean fixture passes, "
          "a byte-divergent mirror file bites BY NAME as DIVERGED, an "
          "orphaned mirror file with no hooks/_lib counterpart bites BY "
          "NAME as the distinct MISSING-CANONICAL kind, a second "
          "independently-located mirror with a nested subpath is picked up "
          "with no code change, run_check()'s exit code follows every case, "
          "and a non-git root fails loud instead of reading as clean.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=REPO_ROOT,
        help="repo root to audit (default: this script's own repo)")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    try:
        return run_check(args.root.resolve())
    except VendorSyncError as exc:
        print(f"UNEVALUATED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    # Windows cp1252-console safety (#313): force UTF-8 so a non-ASCII print
    # can't crash a caller that redirects this checker's output to a file.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
