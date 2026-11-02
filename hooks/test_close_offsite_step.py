#!/usr/bin/env python3
"""The close's Phase 2b matches how the vault keeps its history (tickets#5734).

detect-closing-signal.py told every close "You MUST run vault-safe-commit.sh",
whatever the vault. A vault kept as a plain folder (no .git; its off-machine
copy made some other way, e.g. a nightly mirror) has nothing to commit, so the
step could not run, and the session's notes stayed on the machine until the
next scheduled backup.

Assertions, each on the REAL cascade text build_injected_context() returns:
  1. A vault inside a git work tree keeps the vault-safe-commit step, word for
     word (NEGATIVE CONTROL: git vaults are unchanged).
  2. A plain-folder vault that ships <Meta>/scripts/session-close-offsite.sh is
     told to run that script after the writes, and is NOT told to commit.
  3. A plain-folder vault without that script is told there is no commit step,
     and is NOT told to commit or to run a script it does not have.
  4. A vault reached through a symlink into a git repo counts as a git vault,
     the way `git -C` (and so the close gate) sees it.
"""
import importlib.util
import shlex
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "detect_closing_signal", HOOKS / "detect-closing-signal.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

COMMIT = "You MUST run vault-safe-commit.sh"
failures = []


def cascade(vault: Path) -> str:
    meta = vault / "Meta"
    return mod.build_injected_context(
        confidence="high", matched="bye", timestamp_human="2026-11-02 08:00 PM",
        timestamp_file="2026-11-02T20-00", worktree="main", vault_root=vault,
        meta_dir=meta, session_file=meta / "Sessions" / "s.md",
        decisions_dir=meta / "Decisions", captures_file=meta / "Session Captures.md",
        pending_outcomes=[], is_trivial=False, is_ambiguous=False,
    )


def make_vault(root: Path, git: bool, offsite: bool) -> Path:
    vault = root / "vault"
    (vault / "Meta" / "scripts").mkdir(parents=True)
    if git:
        (vault / ".git").mkdir()
    if offsite:
        (vault / "Meta" / "scripts" / "session-close-offsite.sh").write_text("#!/bin/sh\n")
    return vault


with tempfile.TemporaryDirectory() as tmp:
    if any((d / ".git").exists() for d in Path(tmp).resolve().parents):
        sys.exit("SKIPPED: the temp folder sits inside a git repo, so a plain-folder vault can't be built here")

    # 1. Git vault: unchanged.
    with tempfile.TemporaryDirectory(dir=tmp) as t:
        text = cascade(make_vault(Path(t), git=True, offsite=True))
        if COMMIT not in text:
            failures.append("a git vault lost its vault-safe-commit step")
        if "OFF-MACHINE COPY" in text:
            failures.append("a git vault was sent to the off-machine script instead of committing")

    # 2. Plain folder with an off-machine step.
    with tempfile.TemporaryDirectory(dir=tmp) as t:
        vault = make_vault(Path(t), git=False, offsite=True)
        text = cascade(vault)
        script = vault / "Meta" / "scripts" / "session-close-offsite.sh"
        if COMMIT in text:
            failures.append("a plain-folder vault was told to run vault-safe-commit.sh")
        if f"bash {shlex.quote(str(script))}" not in text:
            failures.append("a plain-folder vault with session-close-offsite.sh was not told to run it")

    # 3. Plain folder without one.
    with tempfile.TemporaryDirectory(dir=tmp) as t:
        text = cascade(make_vault(Path(t), git=False, offsite=False))
        if COMMIT in text:
            failures.append("a plain-folder vault without an off-machine step was told to commit")
        if "session-close-offsite.sh" in text:
            failures.append("a vault without session-close-offsite.sh was told to run it")
        if "NO COMMIT STEP" not in text:
            failures.append("a plain-folder vault was not told there is no commit step")

    # 4. A vault reached through a symlink into a git repo is a git vault, as `git -C` sees it.
    with tempfile.TemporaryDirectory(dir=tmp) as t:
        repo = Path(t) / "repo"
        (repo / ".git").mkdir(parents=True)
        real = repo / "sub" / "vault"
        (real / "Meta" / "scripts").mkdir(parents=True)
        link = Path(t) / "link"
        link.symlink_to(real)
        if COMMIT not in cascade(link):
            failures.append("a vault reached through a symlink into a git repo was not told to commit")

if failures:
    print("FAILED — the close's Phase 2b does not match the vault:")
    for f in failures:
        print(f"  ✗ {f}")
    sys.exit(1)
print("OK - git vaults commit, plain-folder vaults run their off-machine step or skip")
