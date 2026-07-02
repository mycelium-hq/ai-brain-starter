#!/usr/bin/env python3
"""Observe local footprint before it bloats — SessionStart signal.

The 102-worktree pileup was discovered only when the machine fell over. That
is the real failure: it was invisible until catastrophic. This hook makes the
footprint observable at every SessionStart so "12 worktrees and climbing" is
seen early, not "102, machine dead" later. Cheap: a couple of git/stat calls,
no per-worktree filesystem walk.

Surfaces (only when something warrants attention — silent when healthy):
  * worktree count over the soft threshold (WORKTREE_WARN, default 8)
  * on-disk worktree dirs git no longer tracks (orphans)
  * low free disk on the vault's volume
  * THE DANGEROUS COMBO: an AI-brain vault inside a consumer cloud-sync folder
    (iCloud / OneDrive / Dropbox / Google Drive / Box) — worktree/.git churn
    there is what melts the sync daemon. Detected for ANY such vault — the one
    cwd is in, $CLAUDE_PROJECT_DIR, OR any vault in Obsidian's registry, so a
    pre-existing iCloud vault is caught even outside guided onboarding — and the
    auto-capable relocate is OFFERED as ONE recommended safe action (keep the
    notes where they are, move only the churning machinery out) — never a
    two-option menu a non-technical user can't answer — self-silencing once
    relocated. (MYC-2360 + offer-simplification follow-up)

Bypass: WORKTREE_FOOTPRINT_BYPASS=1.

WIRING (SessionStart):
  "SessionStart": [
    {"hooks": [{
      "type": "command",
      "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/worktree-footprint-signal.py 2>/dev/null || echo '{\"continue\":true,\"suppressOutput\":true}'"
    }]}
  ]
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOK_DIR))

from _lib.worktree_safety import (  # noqa: E402
    WORKTREES_SEG,
    detect_cloud_sync,
    find_main_repo,
    is_scratch_worktree,
    list_worktrees,
    obsidian_vault_paths,
)

DEFAULT_WARN = 8
DEFAULT_FREE_GB = 5.0
# Scripts dir of the installed skill — where the auto-capable relocate helpers
# live. The offer prints ready-to-run commands against this canonical path.
SKILL_SCRIPTS = "~/.claude/skills/ai-brain-starter/scripts"


def _emit(ctx: str | None) -> int:
    if ctx:
        print(json.dumps({"continue": True, "additionalContext": ctx}))
    else:
        print(json.dumps({"continue": True, "suppressOutput": True}))
    return 0


# ── cloud-sync auto-detect + relocate OFFER (MYC-2360) ───────────────────────
# Fires UNCONDITIONALLY at SessionStart — independent of guided onboarding and
# of whether cwd is inside the vault. The freeze class (a git-backed brain inside
# iCloud/Drive/Dropbox/Box) is detected for ANY such vault and the auto-capable
# relocate scripts are OFFERED in plain language, rather than left as a passive
# "see docs" warning the user must act on. Self-silences once relocated:
# Shape A (relocate-vault.sh: move-local + symlink) resolves clean through
# detect_cloud_sync; Shape B (relocate-machinery-sidecar.sh: machinery out, notes
# stay) is suppressed by its sidecar manifest. Bounded by construction: a small
# JSON read + a few stats + a tiny manifest glob, never a corpus walk.


def _cwd_git_root() -> Path | None:
    """The git checkout cwd sits in — bounded upward `.git` search, so a vault
    that is git-backed but has no `.claude/worktrees/` yet (find_main_repo only
    resolves worktree-owners) is still discovered when you're cwd'd in it."""
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        return None
    for d in (cwd, *cwd.parents):
        try:
            if (d / ".git").exists():
                return d
        except OSError:
            continue
    return None


def _candidate_vaults(main_repo: Path | None) -> list[Path]:
    """Every vault to consider, INDEPENDENT of guided onboarding: the worktree-
    owning repo (find_main_repo, collapses an in-worktree cwd to its main vault)
    ∪ $CLAUDE_PROJECT_DIR ∪ the git checkout cwd is in ∪ the Obsidian registry
    ∪ $VAULT_ROOT. De-duped by resolved path, order preserved."""
    cands: list[Path] = []
    if main_repo is not None:
        cands.append(main_repo)
    pd = os.environ.get("CLAUDE_PROJECT_DIR")
    if pd:
        p = Path(pd)
        try:
            if p.is_dir():
                cands.append(p)
        except OSError:
            pass
    cwd_root = _cwd_git_root()
    if cwd_root is not None:
        cands.append(cwd_root)
    cands.extend(obsidian_vault_paths())
    vr = os.environ.get("VAULT_ROOT")
    if vr:
        cands.append(Path(vr).expanduser())
    out: list[Path] = []
    seen: set[str] = set()
    for c in cands:
        try:
            key = str(c.resolve())
        except OSError:
            key = str(c)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _is_brain_vault(vault: Path) -> bool:
    """Offer only for an actual AI brain — git-backed or carrying substrate
    machinery — never a pristine markdown folder (markdown alone is low-churn,
    not the freeze class). Mirrors surface-backup-status.py's _is_brain."""
    try:
        if (vault / ".git").exists() or (vault / "CLAUDE.md").is_file():
            return True
        for c in vault.iterdir():
            if c.is_dir() and (c.name.endswith("Meta")
                               or c.name in (".smart-env", ".codegraph")):
                return True
    except OSError:
        return False
    return False


def _sidecar_roots() -> list[Path]:
    roots: list[Path] = []
    for env in ("BRAIN_SIDECAR", "MYCELIUM_SIDECAR"):
        v = os.environ.get(env)
        if v:
            roots.append(Path(v).expanduser())
    roots.append(Path.home() / ".brain-sidecar")
    return roots


def _machinery_relocated(vault: Path) -> bool:
    """True if a machinery-sidecar manifest names this vault (Shape B already
    applied: the vault may still sit in the cloud folder, but its churn is out,
    so the offer must go quiet — an existing user must not be nagged forever)."""
    try:
        vkey = str(vault.resolve())
    except OSError:
        vkey = str(vault)
    for root in _sidecar_roots():
        try:
            manifests = list((root / "manifests").glob("*.json"))
        except OSError:
            continue
        for man in manifests:
            try:
                doc = json.loads(man.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            mv = doc.get("vault") if isinstance(doc, dict) else None
            if not isinstance(mv, str):
                continue
            try:
                if str(Path(mv).resolve()) == vkey:
                    return True
            except OSError:
                if mv == vkey:
                    return True
    return False


def _suggest_local_dest(vault: Path) -> Path:
    """A safe local destination to pre-fill the move-local command with."""
    name = vault.name or "brain"
    home = Path.home()
    cand = home / name
    try:
        if cand.exists():
            return home / "vaults" / name
    except OSError:
        pass
    return cand


def _offer_os() -> str:
    """Command flavor to print: 'windows' (PowerShell .ps1) or 'posix' (bash .sh).

    Keys on the running OS so a Windows/OneDrive user gets commands they can
    actually run (MYC-2383: the bash scripts are not natively runnable on
    Windows). WORKTREE_FOOTPRINT_OS={nt|posix} forces the branch so both can be
    covered on a single-OS CI runner; it changes ONLY which command strings
    render, never whether the offer fires.
    """
    forced = os.environ.get("WORKTREE_FOOTPRINT_OS", "").strip().lower()
    if forced in ("nt", "win", "windows"):
        return "windows"
    if forced in ("posix", "unix", "mac", "linux"):
        return "posix"
    return "windows" if os.name == "nt" else "posix"


def _offer_block(vault: Path, service: str, dest: Path) -> str:
    if _offer_os() == "windows":
        # Windows PowerShell 5.1 is always present; -ExecutionPolicy Bypass lets
        # an unsigned local script run. The .ps1 leaves a junction (no admin /
        # Developer Mode needed), which OneDrive does not sync through.
        move_cmd = (
            f'powershell -ExecutionPolicy Bypass -File '
            f'"{SKILL_SCRIPTS}/relocate-vault.ps1" "{vault}" "{dest}"'
        )
        sidecar_cmd = (
            f'powershell -ExecutionPolicy Bypass -File '
            f'"{SKILL_SCRIPTS}/relocate-machinery-sidecar.ps1" "{vault}"'
        )
        rb = "-Rollback"
        # The .ps1 does not yet stand up a backup itself (MYC-2383 tracks Windows
        # parity for --ensure-backup), so keep asking the assistant to stand one up
        # first for Windows/OneDrive users.
        move_note = (
            "move the whole vault to a local disk (leaves a link so nothing "
            "breaks). Stand up a verified off-machine backup FIRST"
        )
    else:
        # --ensure-backup makes THIS the one approved step: it stands up + verifies
        # an off-machine backup before moving, and refuses if that can't be verified
        # — so a non-technical user never has to know --force or run a backup by hand
        # (MYC-2404 — fulfills this offer's "stand up a backup first" promise in the
        # mechanism instead of relying on the assistant to remember).
        move_cmd = f'bash {SKILL_SCRIPTS}/relocate-vault.sh --ensure-backup "{vault}" "{dest}"'
        sidecar_cmd = f'bash {SKILL_SCRIPTS}/relocate-machinery-sidecar.sh "{vault}"'
        rb = "--rollback"
        move_note = (
            "move the whole vault to a local disk. This ONE command stands up + "
            "verifies an off-machine backup FIRST, then moves (leaves a link so "
            "nothing breaks), and refuses to move if the backup can't be verified"
        )
    return (
        f"🟡 [cloud-sync] The user's brain `{vault}` is inside **{service}** — the "
        f"#1 cause of the \"whole machine froze\" failure (the sync daemon chokes on "
        f"constant `.git`/index churn and pegs the CPU). FIX IT FOR THEM. Do NOT make "
        f"them choose between options or understand the internals — a non-technical "
        f"user will be overwhelmed and won't know what to answer. Recommend ONE thing, "
        f"explain it in a single plain sentence, ask a simple yes, then run it (stand "
        f"up a backup first).\n"
        f"  DEFAULT FIX — run THIS one. It leaves their notes exactly where they are "
        f"(still synced, still on their phone) and just moves the noisy hidden "
        f"machinery (`.git`, worktrees, caches) out of the sync folder so the computer "
        f"stops choking. Reversible (`{rb}`), deletes nothing:\n"
        f"      {sidecar_cmd}\n"
        f"  Fallback — ONLY if they explicitly say they don't want {service} at all: "
        f"{move_note}:\n"
        f"      {move_cmd}\n"
        f"Say it to them roughly like: \"Your notes are in {service}, and that combo "
        f"can freeze your computer. I can fix it safely in the background — your notes "
        f"don't move and nothing gets deleted. Want me to?\" Don't list both commands "
        f"to them; don't explain machinery-vs-notes. Repeats each session until fixed."
    )


def cloud_sync_offer(main_repo: Path | None) -> list[str]:
    """One plain-language offer block per cloud-resident, not-yet-relocated brain."""
    lines: list[str] = []
    for vault in _candidate_vaults(main_repo):
        try:
            if not _is_brain_vault(vault):
                continue
            service = detect_cloud_sync(vault)
            if not service:
                continue  # local disk, or Shape A symlink->local resolved clean
            if _machinery_relocated(vault):
                continue  # Shape B already applied
        except OSError:
            continue
        lines.append(_offer_block(vault, service, _suggest_local_dest(vault)))
    return lines


def main() -> int:
    if os.environ.get("WORKTREE_FOOTPRINT_BYPASS") == "1":
        return _emit(None)

    main_repo = find_main_repo()

    lines: list[str] = []

    # Cloud-sync relocate OFFER — runs even when cwd is NOT inside a vault, so a
    # pre-existing iCloud Obsidian vault (Obsidian's common default) or a skipped
    # onboarding is still caught and the fix is OFFERED, not just documented.
    # (MYC-2360) Replaces the old passive "move it out, see docs" warning.
    lines.extend(cloud_sync_offer(main_repo))

    # Footprint observability needs a repo to measure — gated on main_repo.
    if main_repo is not None:
        try:
            warn_at = max(1, int(os.environ.get("WORKTREE_WARN", DEFAULT_WARN)))
        except ValueError:
            warn_at = DEFAULT_WARN
        try:
            free_floor = float(os.environ.get("WORKTREE_FREE_GB", DEFAULT_FREE_GB))
        except ValueError:
            free_floor = DEFAULT_FREE_GB

        # Count only scratch worktrees for the cap warning; deliberate sibling
        # worktrees (~/dev/<repo>-<slug>) are not part of the pileup problem.
        registered = sum(1 for w in list_worktrees(main_repo) if is_scratch_worktree(w))

        wt_dir = main_repo / WORKTREES_SEG
        on_disk = 0
        if wt_dir.is_dir():
            try:
                on_disk = sum(1 for c in wt_dir.iterdir() if c.is_dir())
            except OSError:
                on_disk = 0
        orphans = max(0, on_disk - registered)

        if registered > warn_at or orphans > 0:
            bits = [f"{registered} registered worktree(s) (soft cap {warn_at})"]
            if orphans:
                bits.append(f"{orphans} orphan dir(s) git no longer tracks")
            lines.append(
                f"[footprint] {'; '.join(bits)}. Each worktree is ~a full checkout. "
                f"They auto-trim at SessionEnd + via the cap; force now with "
                f"`python3 scripts/worktree-prune.sh` or the reclaim tool."
            )

        free_gb = None
        try:
            free_gb = shutil.disk_usage(main_repo).free / 1024 ** 3
        except OSError:
            pass
        if free_gb is not None and free_gb < free_floor:
            lines.append(f"⚠️  [footprint] Low free disk: {free_gb:.1f} GB on the vault volume.")

    return _emit("\n".join(lines) if lines else None)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(json.dumps({"continue": True, "suppressOutput": True}))
        sys.exit(0)
