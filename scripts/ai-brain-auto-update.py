#!/usr/bin/env python3
"""ai-brain-auto-update.py — UserPromptSubmit auto-update for the deployed
ai-brain-starter checkout. Prints ONE Claude-Code hook JSON object on stdout
and ALWAYS exits 0 (a UserPromptSubmit hook must never block the turn).

This is the cross-platform (macOS / Linux / Windows) successor to
ai-brain-auto-update.sh, which is now a thin delegator to this file. The bash
version could not run on native Windows (no bash, no `timeout`, no `nice`,
no `find -mtime`), which left every Windows install permanently stale — the
exact silent-drift class the auto-update exists to prevent.

THE REACH GUARANTEE (MYC-720): when the pull moves HEAD, this DEPLOYS the new
hooks itself (runs scripts/install-hooks-user-level.py, bounded) instead of
only asking the model to.

Safety, preserved from the shell version:
  - Pinnable:      ~/.claude/.ai-brain-starter-pinned present => no-op.
  - Rate-limited:  runs at most once per ABS_UPDATE_INTERVAL_DAYS (default 6).
  - Single-flight: atomic mkdir lock so concurrent sessions never double-run.
  - ff-ONLY:       fetch + `merge --ff-only`. A dirty tree or divergent fork is
                   REFUSED and surfaced for manual merge — never given a
                   surprise merge commit.
  - Bounded:       every subprocess runs under a wall-clock timeout
                   (subprocess timeout= — portable, unlike GNU `timeout`), so a
                   hung git or installer can never wedge the user's prompt.
  - Fail-open:     any unexpected error emits a valid silent JSON object.

Hermetically testable via env overrides (tests/integration/
test_ai_brain_auto_update.sh runs through the .sh delegator): ABS_SKILL_DIR,
ABS_UPDATE_STATE_DIR, ABS_UPDATE_INTERVAL_DAYS, ABS_UPDATE_DEPLOY_TIMEOUT.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

GIT_TIMEOUT = 60  # seconds per git call; network hangs must not wedge the prompt


def _state_dir() -> Path:
    return Path(os.environ.get("ABS_UPDATE_STATE_DIR") or (Path.home() / ".claude"))


def _skill_dir() -> Path:
    return Path(os.environ.get("ABS_SKILL_DIR")
                or (Path.home() / ".claude" / "skills" / "ai-brain-starter"))


def silent() -> None:
    """The no-op form — a UserPromptSubmit hook must always print valid JSON."""
    print('{"continue":true,"suppressOutput":true}')
    raise SystemExit(0)


def emit_ctx(message: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": message,
    }}))
    raise SystemExit(0)


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True,
        timeout=GIT_TIMEOUT,
    )


def _reclaim_stale_lock(lock: Path) -> None:
    """A SIGKILL mid-run strands the lock and would silently disable updates
    forever — reclaim one older than any run could take (60 min >> timeouts)."""
    try:
        if lock.is_dir() and (time.time() - lock.stat().st_mtime) > 3600:
            lock.rmdir()
    except OSError:
        pass


def _install_fix_cmd() -> str:
    """The manual re-install command, phrased for the user's actual platform."""
    py = "python" if os.name == "nt" else "python3"
    return (f"{py} \"{_skill_dir() / 'scripts' / 'install-hooks-user-level.py'}\" "
            "--quiet --fail-on-missing")


def run() -> None:
    state = _state_dir()
    skill = _skill_dir()
    pin = state / ".ai-brain-starter-pinned"
    last = state / ".ai-brain-starter-last-update"
    lock = state / ".ai-brain-starter-update.lock"
    interval_days = float(os.environ.get("ABS_UPDATE_INTERVAL_DAYS", "6"))
    deploy_timeout = float(os.environ.get("ABS_UPDATE_DEPLOY_TIMEOUT", "120"))

    # 0. Pinned -> no-op (the escape hatch; must win before any fetch).
    if pin.exists():
        silent()

    # 1. Rate-limit: only once per interval. Absent LAST means "never ran".
    try:
        if last.is_file() and (time.time() - last.stat().st_mtime) < interval_days * 86400:
            silent()
    except OSError:
        silent()

    # 2. Single-flight: atomic mkdir lock, with stale-lock reclaim.
    _reclaim_stale_lock(lock)
    try:
        lock.mkdir()
    except OSError:
        silent()  # a held-and-fresh lock is a real concurrent session
    try:
        try:
            last.touch()  # claim this interval up-front (matches prior behavior)
        except OSError:
            pass

        if not (skill / ".git").exists():
            silent()

        # 3. Fetch. Network down -> gentle note, never crash the turn.
        try:
            fetch = _git(["fetch", "origin", "main", "--quiet"], skill)
        except (subprocess.TimeoutExpired, OSError):
            fetch = None
        if fetch is None or fetch.returncode != 0:
            emit_ctx(
                "AI Brain Starter checked for updates but couldn't reach the "
                "internet (or the repository). Nothing is wrong — it will try "
                "again in a few days. No action needed.")

        try:
            head = _git(["rev-parse", "HEAD"], skill).stdout.strip()
            origin = _git(["rev-parse", "origin/main"], skill).stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            silent()
        if not head or head == origin:
            silent()  # already current

        # 4. ff-ONLY. Tracked-file edits or a divergent fork refuse the pull.
        try:
            status = _git(["status", "--porcelain", "--untracked-files=no"], skill)
            if status.stdout.strip():
                emit_ctx(
                    "AI Brain Starter auto-update is BLOCKED (safely): your copy at "
                    f"{skill} has local edits to tracked files, so it will not "
                    "auto-pull — your edits are preserved. To update when you're "
                    f"ready: cd \"{skill}\" && git stash && git pull --ff-only "
                    "origin main && git stash pop (or discard the local changes "
                    "first). Everything else keeps working in the meantime.")
            merge = _git(["merge", "--ff-only", "origin/main", "--quiet"], skill)
            if merge.returncode != 0:
                emit_ctx(
                    "AI Brain Starter auto-update is BLOCKED (safely): your copy at "
                    f"{skill} has diverged from the official version (a local "
                    "fork), so it cannot fast-forward. Your fork is preserved. To "
                    f"merge manually: cd \"{skill}\" && git pull --rebase origin "
                    "main (or your preferred strategy).")
        except (subprocess.TimeoutExpired, OSError):
            silent()

        try:
            log = _git(["log", "--oneline", f"{head}..HEAD"], skill)
            changes = ";".join(log.stdout.splitlines()[:20])
        except (subprocess.TimeoutExpired, OSError):
            changes = "(unavailable)"

        # 5. Propagate skill content (backs up customizations before overwrite).
        #    sync-skills.py is canonical; the .sh stub survives for old fixtures.
        sync_py = skill / "scripts" / "sync-skills.py"
        sync_sh = skill / "scripts" / "sync-skills.sh"
        sync_env = {**os.environ, "ABS_SYNC_STARTER_DIR": str(skill)}
        sync_output = ""
        try:
            if sync_py.is_file():
                sync = subprocess.run([sys.executable, str(sync_py)],
                                      capture_output=True, text=True,
                                      timeout=deploy_timeout, env=sync_env)
                sync_output = "\n".join((sync.stdout + sync.stderr).splitlines()[-20:])
            elif os.name != "nt" and sync_sh.is_file():
                sync = subprocess.run(["bash", str(sync_sh)],
                                      capture_output=True, text=True,
                                      timeout=deploy_timeout)
                sync_output = "\n".join((sync.stdout + sync.stderr).splitlines()[-20:])
        except (subprocess.TimeoutExpired, OSError):
            sync_output = "(skill sync did not finish; it will retry next update)"

        # 6. THE REACH GUARANTEE: deploy the freshly-pulled hooks NOW, bounded.
        installer = skill / "scripts" / "install-hooks-user-level.py"
        deploy_note = "Hooks were rewired automatically."
        try:
            deploy = subprocess.run(
                [sys.executable, str(installer), "--quiet", "--fail-on-missing"],
                capture_output=True, text=True, timeout=deploy_timeout)
            rc = deploy.returncode
        except subprocess.TimeoutExpired:
            rc = 124
        except OSError:
            rc = 1
        if rc == 124:
            deploy_note = (
                "One follow-up needed: the hook re-install step ran out of time, "
                "so the newest hooks may not be active yet. To finish it, run: "
                f"{_install_fix_cmd()}")
        elif rc != 0:
            deploy_note = (
                "One follow-up needed: the hook re-install step didn't finish "
                "cleanly, so the newest hooks may not be active yet. To finish "
                f"it, run: {_install_fix_cmd()}")

        emit_ctx(
            f"AI Brain Starter was auto-updated and hooks were redeployed. "
            f"Commits: {changes} Skill sync: {sync_output} {deploy_note} "
            "Any changed file was backed up to <file>.bak-YYYY-MM-DD-HHMM first, "
            "so local customizations are recoverable. Now, briefly and casually "
            "(not a changelog dump, no jargon, nothing alarming): 1) Read "
            "docs/CHANGELOG.md in the ai-brain-starter skill folder (top entry "
            "only) and tell the user in 1-2 plain sentences what changed and "
            "why it helps them. 2) If the update added rules to the Obsidian "
            "Rules or Session Protocol sections of SKILL.md, read the user's "
            "vault CLAUDE.md and, for each new or changed rule not already "
            "there, offer to merge it: show a short diff, explain the benefit "
            "in plain words, ask one yes/no question, and on yes back up "
            "CLAUDE.md to CLAUDE.md.bak-YYYY-MM-DD-HHMM before editing. 3) If "
            "the skill sync backed up any files, mention it so the user knows "
            "their customizations are recoverable.")
    finally:
        try:
            lock.rmdir()
        except OSError:
            pass


def main() -> None:
    try:
        run()
    except SystemExit:
        raise
    except Exception:
        # Fail-open backstop: never break the user's prompt.
        print('{"continue":true,"suppressOutput":true}')
        raise SystemExit(0)


if __name__ == "__main__":
    main()
