#!/usr/bin/env python3
"""
test_vault_root_seam.py — drift-detection.py and compress-vault-doc.py must
resolve VAULT_ROOT to the SAME path, for the same cwd/VAULT_ROOT/
VAULT_ROOT_FORCE, in every case except the one they are documented to
differ on.

Both scripts call the SAME function, hooks/_lib/vault_root.py's
resolve_cli_vault_root() (#683 review follow-up), instead of each carrying
its own copy of this precedence. That is what makes "these two agree" true
by construction rather than an assertion two independently-edited copies
could silently stop satisfying -- which is exactly what happened once
already: compress-vault-doc.py read VAULT_ROOT naively while
drift-detection.py's own copy had already been hardened, so a cwd/
VAULT_ROOT combination the producer resolved one way left the consumer
looking for "Meta/Drift Audit.md" somewhere else.

This suite runs each script as a subprocess with runpy.run_path() (run_name
deliberately NOT "__main__", so each script's own `if __name__ ==
"__main__": ...sys.exit(main())` guard never fires -- no audit runs, no
file gets written, no argparse happens; only the module-level
VAULT_ROOT = resolve_cli_vault_root(...) line executes) and compares the
resolved VAULT_ROOT each one prints.

Cases mirror test_drift_detection_vault_root.py's fixtures (mismatch, force,
non-git-cwd-with-valid-VAULT_ROOT, unset-uses-cwd, code-repo-is-not-a-vault,
vault-worktree, vault-subfolder) and assert EQUALITY between the two
scripts for every one of them.

One case is deliberately EXCLUDED from the equality assertion: neither cwd
nor VAULT_ROOT resolves to an established vault at all. resolve_cli_
vault_root()'s own docstring names this the one parameter callers are
allowed to differ on (`fallback=`) -- there is no vault here for the two
scripts to agree ABOUT. drift-detection.py's documented default is cwd
itself; compress-vault-doc.py's is its own script's parent directory. This
suite still runs that case, but asserts the two DIFFER (documenting why the
exclusion is real, not just assumed) rather than silently skipping it.

Run:
  python3 scripts/test_vault_root_seam.py
  python3 scripts/test_vault_root_seam.py --verbose

Exits 0 on all-pass, 1 on any failure. CI-runnable. No third-party deps.
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
DRIFT_SCRIPT = REPO / "scripts" / "drift-detection.py"
COMPRESS_SCRIPT = REPO / "scripts" / "compress-vault-doc.py"

# Executes the target script's module-level code ONLY (never its __main__
# block, since run_name is not "__main__") and prints the resolved
# VAULT_ROOT. Passed via `-c` so each probe gets a fresh interpreter with the
# cwd/env the case under test needs.
_PROBE_SRC = (
    "import runpy, sys\n"
    "ns = runpy.run_path(sys.argv[1], run_name='vault_root_seam_probe')\n"
    "print(str(ns['VAULT_ROOT']))\n"
)


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def build_vault(vault: Path, filename: str = "Note.md") -> None:
    """A git repo WITH a Meta folder -- an established vault."""
    vault.mkdir(parents=True, exist_ok=True)
    git(vault, "init", "-q")
    git(vault, "config", "user.email", "test@example.com")
    git(vault, "config", "user.name", "Test")
    (vault / "Meta").mkdir(parents=True, exist_ok=True)
    note = vault / filename
    note.write_text("# Note\n", encoding="utf-8")
    git(vault, "add", filename)
    git(vault, "commit", "-q", "-m", "init")


def build_code_repo(repo: Path, filename: str = "README.md") -> None:
    """A git repo with NO Meta folder -- a plain code checkout, not a vault."""
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    (repo / filename).write_text("code\n", encoding="utf-8")
    git(repo, "add", filename)
    git(repo, "commit", "-q", "-m", "init")


def probe(script: Path, cwd: Path, extra_env: dict) -> tuple[str | None, str]:
    """(resolved VAULT_ROOT string or None on error, diagnostic detail)."""
    env = dict(os.environ)
    env.pop("VAULT_ROOT", None)
    env.pop("VAULT_ROOT_FORCE", None)
    env.update(extra_env)
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE_SRC, str(script)],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        return None, f"{script.name} probe exited {proc.returncode}; stderr={proc.stderr.strip()[:300]!r}"
    return proc.stdout.strip(), ""


def check(name: str, condition: bool, detail: str, verbose: bool) -> bool:
    if condition:
        print(f"  ok   {name}")
        return True
    print(f"  FAIL {name}: {detail}")
    return False


def case_agree(name: str, cwd: Path, extra_env: dict, verbose: bool) -> bool:
    """Both scripts must resolve to the identical VAULT_ROOT."""
    drift_root, drift_err = probe(DRIFT_SCRIPT, cwd, extra_env)
    compress_root, compress_err = probe(COMPRESS_SCRIPT, cwd, extra_env)
    if drift_root is None or compress_root is None:
        return check(name, False, drift_err or compress_err, verbose)
    ok = check(
        name,
        drift_root == compress_root,
        f"drift-detection -> {drift_root!r}, compress-vault-doc -> {compress_root!r}",
        verbose,
    )
    if verbose:
        print(f"    both -> {drift_root!r}")
    return ok


def case_mismatch(verbose: bool) -> bool:
    tmp = Path(tempfile.mkdtemp(prefix="vault-root-seam-test-"))
    try:
        cwd_vault = tmp / "cwd-vault"
        env_vault = tmp / "env-vault"
        build_vault(cwd_vault, "CwdNote.md")
        build_vault(env_vault, "EnvNote.md")
        return case_agree(
            "mismatch (unforced): both prefer cwd's own vault",
            cwd_vault,
            {"VAULT_ROOT": str(env_vault)},
            verbose,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_force(verbose: bool) -> bool:
    tmp = Path(tempfile.mkdtemp(prefix="vault-root-seam-test-"))
    try:
        cwd_vault = tmp / "cwd-vault"
        env_vault = tmp / "env-vault"
        build_vault(cwd_vault, "CwdNote.md")
        build_vault(env_vault, "EnvNote.md")
        return case_agree(
            "VAULT_ROOT_FORCE=1: both prefer VAULT_ROOT",
            cwd_vault,
            {"VAULT_ROOT": str(env_vault), "VAULT_ROOT_FORCE": "1"},
            verbose,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_non_git_cwd(verbose: bool) -> bool:
    tmp = Path(tempfile.mkdtemp(prefix="vault-root-seam-test-"))
    try:
        non_git_cwd = tmp / "not-a-repo"
        non_git_cwd.mkdir(parents=True)
        env_vault = tmp / "env-vault"
        build_vault(env_vault, "EnvNote.md")
        return case_agree(
            "non-git cwd, valid VAULT_ROOT: both fall back to it",
            non_git_cwd,
            {"VAULT_ROOT": str(env_vault)},
            verbose,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_unset(verbose: bool) -> bool:
    tmp = Path(tempfile.mkdtemp(prefix="vault-root-seam-test-"))
    try:
        cwd_vault = tmp / "cwd-vault"
        build_vault(cwd_vault, "CwdNote.md")
        return case_agree("VAULT_ROOT unset, cwd is a vault: both use cwd", cwd_vault, {}, verbose)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_code_repo(verbose: bool) -> bool:
    tmp = Path(tempfile.mkdtemp(prefix="vault-root-seam-test-"))
    try:
        code_repo = tmp / "code-repo"
        env_vault = tmp / "env-vault"
        build_code_repo(code_repo)
        build_vault(env_vault, "EnvNote.md")
        return case_agree(
            "code-repo cwd (not a vault): both prefer VAULT_ROOT",
            code_repo,
            {"VAULT_ROOT": str(env_vault)},
            verbose,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_worktree(verbose: bool) -> bool:
    tmp = Path(tempfile.mkdtemp(prefix="vault-root-seam-test-"))
    try:
        vault = tmp / "vault"
        build_vault(vault, "MainNote.md")
        worktree = vault / ".claude" / "worktrees" / "wt1"
        git(vault, "worktree", "add", "-q", str(worktree), "-b", "wt1")
        return case_agree(
            "vault worktree cwd: both collapse to the main vault",
            worktree,
            {},
            verbose,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_subfolder(verbose: bool) -> bool:
    tmp = Path(tempfile.mkdtemp(prefix="vault-root-seam-test-"))
    try:
        vault = tmp / "vault"
        build_vault(vault, "SubNote.md")
        sub = vault / "sub"
        sub.mkdir(parents=True)
        return case_agree("vault subfolder cwd: both walk up to the vault", sub, {}, verbose)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_no_vault_anywhere_excluded(verbose: bool) -> bool:
    """The ONE documented exclusion: neither cwd nor VAULT_ROOT resolves to
    an established vault at all. resolve_cli_vault_root()'s `fallback=` is
    the one parameter callers are allowed to differ on for exactly this
    case -- drift-detection.py's is cwd itself, compress-vault-doc.py's is
    its own script's parent directory. Asserts they DIFFER, so this
    exclusion is measured, not just assumed.
    """
    tmp = Path(tempfile.mkdtemp(prefix="vault-root-seam-test-"))
    try:
        plain = tmp / "plain"
        plain.mkdir(parents=True)
        drift_root, drift_err = probe(DRIFT_SCRIPT, plain, {})
        compress_root, compress_err = probe(COMPRESS_SCRIPT, plain, {})
        if drift_root is None or compress_root is None:
            return check(
                "no-vault-anywhere (excluded): probes ran",
                False,
                drift_err or compress_err,
                verbose,
            )
        # os.getcwd() (what resolve_cli_vault_root's default cwd resolves
        # through) returns the symlink-resolved real path, which can differ
        # from the literal tempdir string on a host where /var -> /private/var
        # (macOS) -- resolve both sides before comparing, or this assertion
        # is flaky on exactly the platform the test suite runs on most.
        want_drift = str(plain.resolve())
        want_compress = str(COMPRESS_SCRIPT.parent.parent.resolve())
        ok = check(
            "no-vault-anywhere (excluded): fallbacks differ as documented",
            drift_root != compress_root and drift_root == want_drift and compress_root == want_compress,
            f"drift-detection -> {drift_root!r} (want cwd {want_drift!r}), "
            f"compress-vault-doc -> {compress_root!r} (want its script parent {want_compress!r})",
            verbose,
        )
        return ok
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


CASES = [
    ("mismatch prefers cwd's vault (both)", case_mismatch),
    ("VAULT_ROOT_FORCE=1 prefers VAULT_ROOT (both)", case_force),
    ("non-git cwd falls back to VAULT_ROOT (both)", case_non_git_cwd),
    ("VAULT_ROOT unset uses cwd (both)", case_unset),
    ("code-repo cwd is not a vault (both)", case_code_repo),
    ("vault worktree cwd resolves to main vault (both)", case_worktree),
    ("vault subfolder cwd resolves to vault (both)", case_subfolder),
    ("no-vault-anywhere fallback (excluded from agreement)", case_no_vault_anywhere_excluded),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    for script in (DRIFT_SCRIPT, COMPRESS_SCRIPT):
        if not script.exists():
            print(f"ERROR: {script} not found")
            return 1

    print(f"drift-detection.py / compress-vault-doc.py VAULT_ROOT seam: {len(CASES)} case(s)")
    failures = 0
    for name, fn in CASES:
        if not fn(args.verbose):
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
