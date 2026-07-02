"""Shared scanner for in-flight builds across ~/dev/* repos.

Used by:
- block-branch-switch-with-untracked-build.py (PreToolUse)
- nudge-checkpoint-after-pytest-pass.py (PostToolUse)
- warn-uncommitted-builds-on-stop.py (Stop)
- list-wip-stashes-on-session-start.py (SessionStart)

Heuristic for "in-flight build":
- A directory under <repo> contains 3+ untracked source files matching
  one of: .py .ts .tsx .js .jsx .go .rs .java .rb .php .c .cpp .h
- OR a new test file exists alongside a new module (tests/X/* + src/X/*)

Heuristic for "active repo": modified within the last 60 minutes.
Faster than scanning every ~/dev/* repo every session-start.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple, Optional


SOURCE_EXT_RE = re.compile(
    r"\.(py|ts|tsx|js|jsx|go|rs|java|rb|php|c|cpp|h|hpp|swift|kt|scala)$"
)
DEV_ROOT = Path.home() / "dev"
ACTIVE_WINDOW_SECONDS = 60 * 60  # 60 minutes
MIN_FILES_FOR_MODULE = 3


class ModuleInFlight(NamedTuple):
    repo: Path
    module_dir: str  # relative to repo, e.g. "src/voice"
    file_count: int
    files: list[str]  # relative to repo


class StashEntry(NamedTuple):
    repo: Path
    stash_ref: str  # e.g. "stash@{0}"
    branch: str
    message: str


def find_active_repos(now_ts: Optional[float] = None) -> list[Path]:
    """Return ~/dev/<repo> dirs whose .git or working tree was touched recently."""
    if not DEV_ROOT.exists():
        return []
    now_ts = now_ts or time.time()
    cutoff = now_ts - ACTIVE_WINDOW_SECONDS
    out: list[Path] = []
    try:
        for child in DEV_ROOT.iterdir():
            if not child.is_dir():
                continue
            git_dir = child / ".git"
            if not git_dir.exists():
                continue
            # Cheap activity check: stat the .git/HEAD or working tree mtime
            try:
                head_mtime = (git_dir / "HEAD").stat().st_mtime
                index_mtime = (git_dir / "index").stat().st_mtime if (
                    git_dir / "index"
                ).exists() else 0
                # Also check working-tree top-level for recent edits
                try:
                    wt_mtime = max(
                        (
                            p.stat().st_mtime
                            for p in child.iterdir()
                            if p.name not in {".git", "node_modules", ".venv", "__pycache__"}
                        ),
                        default=0,
                    )
                except OSError:
                    wt_mtime = 0
                last_touch = max(head_mtime, index_mtime, wt_mtime)
                if last_touch >= cutoff:
                    out.append(child)
            except OSError:
                continue
    except OSError:
        return []
    return out


def find_modules_in_flight(repo: Path) -> list[ModuleInFlight]:
    """Run git status -uall in <repo> and group untracked source files by directory.

    Returns one ModuleInFlight per directory with 3+ untracked source files.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain=v1", "-uall"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []
    if result.returncode != 0:
        return []

    # Untracked entries start with "?? " in porcelain v1
    untracked_sources: list[str] = []
    for line in result.stdout.splitlines():
        if not line.startswith("?? "):
            continue
        rel = line[3:].strip()
        # git can emit quoted paths for unicode; strip surrounding quotes
        if rel.startswith('"') and rel.endswith('"'):
            try:
                rel = rel[1:-1].encode("utf-8").decode("unicode_escape")
            except Exception:
                pass
        if SOURCE_EXT_RE.search(rel):
            untracked_sources.append(rel)

    # Group by 2-segment directory prefix (e.g. "src/voice/" or "tests/voice/")
    grouped: dict[str, list[str]] = {}
    for rel in untracked_sources:
        parts = rel.split("/")
        if len(parts) < 2:
            # Top-level untracked file; skip (not module-shaped)
            continue
        # 2-segment prefix; if file is deeper (e.g. src/voice/backends/x.py)
        # we still group at the 2-segment level (src/voice/) because that
        # captures the module identity. Subdirs roll up to the same module.
        prefix = "/".join(parts[:2]) + "/"
        grouped.setdefault(prefix, []).append(rel)

    out: list[ModuleInFlight] = []
    for prefix, files in grouped.items():
        if len(files) >= MIN_FILES_FOR_MODULE:
            out.append(
                ModuleInFlight(
                    repo=repo,
                    module_dir=prefix,
                    file_count=len(files),
                    files=files,
                )
            )
    return out


def find_wip_stashes(repo: Path) -> list[StashEntry]:
    """Return stash entries whose message hints at parking/WIP/incomplete work."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "stash", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []
    if result.returncode != 0:
        return []

    pattern = re.compile(
        r"(?i)\b(wip|parking|parked|incomplete|in[- ]flight|do not lose|preserve|recover)\b"
    )
    out: list[StashEntry] = []
    for line in result.stdout.splitlines():
        # Format: stash@{0}: On <branch>: <message>
        m = re.match(r"^(stash@\{\d+\}):\s+(?:On|WIP on)\s+([^:]+):\s+(.*)$", line)
        if not m:
            continue
        stash_ref, branch, message = m.group(1), m.group(2).strip(), m.group(3)
        if pattern.search(message):
            out.append(
                StashEntry(
                    repo=repo,
                    stash_ref=stash_ref,
                    branch=branch,
                    message=message,
                )
            )
    return out


class UnpushedCommitEntry(NamedTuple):
    repo: Path
    branch: str  # local branch with the commits
    commits: list[tuple[str, str, float]]  # (sha7, subject, committer_ts)
    upstream: Optional[str]  # tracking ref, e.g. "origin/main", or None


def find_unpushed_local_commits(
    repo: Path,
    min_age_minutes: int = 24 * 60,
) -> list[UnpushedCommitEntry]:
    """Return local branches with commits not on any remote ref.

    Filters to commits older than `min_age_minutes` (default 24h) so a
    just-committed change in active work doesn't get flagged as drift.

    Bug class this surfaces: LOCAL-COMMITS-DRIFT-UNPUSHED. A chore commit
    (e.g. a CI pin from an automated hardening pass) sitting on local main
    unpushed for days blocks fast-forward pulls AND silently corrupts any
    deploy that ships whatever is at local HEAD — the operator's local ends
    up several commits behind origin while production serves the stale tree.
    """
    try:
        # --branches restricts to commits reachable from local branches.
        # --not --remotes excludes anything already on a remote ref.
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "log",
                "--branches",
                "--not",
                "--remotes",
                "--format=%H%x09%s%x09%ct%x09%D",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []

    cutoff_ts = time.time() - (min_age_minutes * 60)
    by_branch: dict[str, list[tuple[str, str, float]]] = {}

    for line in result.stdout.splitlines():
        parts = line.split("\t", 3)
        if len(parts) < 3:
            continue
        sha, subject, ct_str = parts[0], parts[1], parts[2]
        refs = parts[3] if len(parts) > 3 else ""
        try:
            ct = float(ct_str)
        except ValueError:
            continue
        if ct > cutoff_ts:
            # Too fresh to nudge — operator may be mid-build.
            continue
        # `refs` is like "HEAD -> main, tag: v1, feature/x". Pull out
        # local branch names; skip remote/tag/HEAD pointers.
        branch_names: list[str] = []
        for ref in refs.split(","):
            ref = ref.strip()
            if not ref or ref.startswith("tag:") or ref.startswith("HEAD"):
                continue
            if ref.startswith("HEAD -> "):
                ref = ref[len("HEAD -> "):]
            if ref.startswith("origin/") or ref.startswith("upstream/"):
                continue
            branch_names.append(ref)
        if not branch_names:
            branch_names = ["(detached)"]
        for b in branch_names:
            by_branch.setdefault(b, []).append((sha[:7], subject, ct))

    out: list[UnpushedCommitEntry] = []
    for branch, commits in by_branch.items():
        upstream = _resolve_upstream(repo, branch)
        out.append(
            UnpushedCommitEntry(
                repo=repo,
                branch=branch,
                commits=commits,
                upstream=upstream,
            )
        )
    return out


def _resolve_upstream(repo: Path, branch: str) -> Optional[str]:
    """Return the tracking ref for a local branch, or None if unset."""
    if branch == "(detached)":
        return None
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                f"{branch}@{{u}}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    upstream = result.stdout.strip()
    return upstream or None


# ---------------------------------------------------------------------------
# Branch lifecycle classifier (MYC-683) — the shared reap/surface primitive.
#
# The drift surfacer + the reaper both need to tell GENUINE-UNIQUE work (the
# only real drift, the only thing worth surfacing/pushing) apart from
# squash-merged-stale + relic branches (content is already on origin → safe to
# reap, NOT drift). `merge-base --is-ancestor` alone CANNOT — a squash-merged
# branch's commits are not ancestors of main (the squash is a new SHA) yet its
# content IS on main. That false-positive is the ~25x cry-wolf the surfacer
# showed (MYC-683 re-verification 2026-06-14). Five classes, evaluated in order:
# ---------------------------------------------------------------------------


class BranchClass:
    """String enum (kept as plain constants for json/log friendliness)."""

    RELIC = "relic"                          # no common ancestor with origin/main → obsolete
    TRUE_MERGED = "true_merged"              # tip is an ancestor of origin/main
    BACKED_UP = "backed_up"                  # pushed to its own origin/<branch>, not merged
    SQUASH_MERGED_STALE = "squash_merged_stale"  # content ⊆ origin/main (squash artifact)
    GENUINE_UNIQUE = "genuine_unique"        # real divergent work NOT on any remote → the only drift
    UNKNOWN = "unknown"                      # can't classify safely → always preserve


# Content is provably preserved on origin → the local branch ref is safe to delete.
REAPABLE_CLASSES = frozenset({BranchClass.TRUE_MERGED, BranchClass.SQUASH_MERGED_STALE})
# Real, un-backed-up state → surface for a human, NEVER auto-delete.
SURFACE_CLASSES = frozenset({BranchClass.RELIC, BranchClass.GENUINE_UNIQUE})


def _git(repo: Path, *args: str, timeout: int = 15):
    """Run git, never raise. Returns (returncode, stdout, stderr) trimmed."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return 99, "", "git-exec-failed"


def detect_default_branch(repo: Path) -> Optional[str]:
    """The remote default branch name (no `origin/` prefix), or None.

    Tries `origin/HEAD`, then verifies `origin/main` / `origin/master`.
    """
    rc, out, _ = _git(repo, "rev-parse", "--abbrev-ref", "origin/HEAD")
    if rc == 0 and out and "/" in out:
        cand = out.split("/", 1)[1]
        rc2, _, _ = _git(repo, "rev-parse", "--verify", "--quiet", f"origin/{cand}")
        if rc2 == 0:
            return cand
    for cand in ("main", "master"):
        rc2, _, _ = _git(repo, "rev-parse", "--verify", "--quiet", f"origin/{cand}")
        if rc2 == 0:
            return cand
    return None


def _branch_adds_nothing(repo: Path, base_ref: str, branch: str) -> Optional[bool]:
    """True if `branch` introduces no content `base_ref` lacks (tree ⊆ base).

    Uses `git diff --numstat base..branch`: each line is `added<TAB>deleted<TAB>path`.
    If the total ADDED lines across all files is 0 AND there is no binary change,
    the branch adds nothing beyond base → its content is already absorbed
    (the squash-merged-stale signal that survives main moving on with its own
    unrelated commits). Returns None on any git error (caller preserves).
    """
    rc, out, _ = _git(repo, "diff", "--numstat", f"{base_ref}..{branch}")
    if rc != 0:
        return None
    if not out:
        return True  # identical trees → adds nothing
    total_added = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        added = parts[0]
        if added == "-":
            return False  # binary delta → can't prove ⊆; treat as genuine (preserve)
        try:
            total_added += int(added)
        except ValueError:
            return False
    return total_added == 0


def classify_branch(
    repo: Path, branch: str, default_branch: Optional[str] = None
) -> str:
    """Classify a local branch into one of BranchClass. Fail-safe to UNKNOWN."""
    default_branch = default_branch or detect_default_branch(repo)
    if not default_branch:
        return BranchClass.UNKNOWN
    origin_main = f"origin/{default_branch}"
    rc, _, _ = _git(repo, "rev-parse", "--verify", "--quiet", origin_main)
    if rc != 0:
        return BranchClass.UNKNOWN
    rc, tip, _ = _git(repo, "rev-parse", "--verify", "--quiet", branch)
    if rc != 0 or not tip:
        return BranchClass.UNKNOWN

    # 1. RELIC — no shared history with origin/main.
    rc_mb, mb, _ = _git(repo, "merge-base", origin_main, branch)
    if rc_mb != 0 or not mb:
        return BranchClass.RELIC

    # 2. TRUE_MERGED — tip already reachable from origin/main.
    rc_anc, _, _ = _git(repo, "merge-base", "--is-ancestor", branch, origin_main)
    if rc_anc == 0:
        return BranchClass.TRUE_MERGED

    # 3. BACKED_UP — pushed to its own upstream (tip == origin/<branch> or behind).
    rc_ob, _, _ = _git(repo, "rev-parse", "--verify", "--quiet", f"origin/{branch}")
    if rc_ob == 0:
        rc_bup, _, _ = _git(
            repo, "merge-base", "--is-ancestor", branch, f"origin/{branch}"
        )
        if rc_bup == 0:
            return BranchClass.BACKED_UP

    # 4. SQUASH_MERGED_STALE — content already on origin/main (squash artifact).
    adds_nothing = _branch_adds_nothing(repo, origin_main, branch)
    if adds_nothing is True:
        return BranchClass.SQUASH_MERGED_STALE
    if adds_nothing is None:
        return BranchClass.UNKNOWN  # git error → preserve

    # 5. GENUINE_UNIQUE — real divergent, un-backed-up work. The only real drift.
    return BranchClass.GENUINE_UNIQUE


# --- Reap planning ---------------------------------------------------------


@dataclass
class ReapTarget:
    branch: str
    cls: str
    sha: str


@dataclass
class WorktreeTarget:
    path: Path
    branch: str
    sha: str


@dataclass
class StashTarget:
    ref: str
    message: str
    reason: str = ""


@dataclass
class ReapPlan:
    repo: Path
    reap_branches: list = field(default_factory=list)      # ReapTarget
    reap_worktrees: list = field(default_factory=list)     # WorktreeTarget
    reap_stashes: list = field(default_factory=list)       # StashTarget
    surface_branches: list = field(default_factory=list)   # ReapTarget (human decision)
    skipped: list = field(default_factory=list)            # (name, reason)


def _list_worktrees(repo: Path) -> list[tuple[Path, Optional[str]]]:
    """Return [(worktree_path, branch_or_None)] incl. the primary checkout."""
    rc, out, _ = _git(repo, "worktree", "list", "--porcelain")
    if rc != 0:
        return []
    res: list[tuple[Path, Optional[str]]] = []
    cur_path: Optional[Path] = None
    cur_branch: Optional[str] = None
    for line in out.splitlines() + [""]:
        if line.startswith("worktree "):
            if cur_path is not None:
                res.append((cur_path, cur_branch))
            cur_path = Path(line[len("worktree "):])
            cur_branch = None
        elif line.startswith("branch "):
            cur_branch = line[len("branch "):].replace("refs/heads/", "")
        elif line == "" and cur_path is not None:
            res.append((cur_path, cur_branch))
            cur_path = None
            cur_branch = None
    return res


def _is_dirty(path: Path) -> bool:
    rc, out, _ = _git(path, "status", "--porcelain")
    return rc != 0 or bool(out)  # treat git error as dirty (preserve)


# A destructive tool errs toward PRESERVE: widen the system's own 300s "live"
# window to 15 min so a session that paused briefly still shields its repo.
SESSION_LOCK_LIVE_WINDOW_SEC = 900


def _has_live_session_lock(repo: Path, now_ts: Optional[float] = None) -> bool:
    """True if a Claude session was active in this repo within the live window.

    Reads the REAL shared lock written by session-lock.py at
    `<main_root>/.claude/.session-lock.json` — a multi-session map whose liveness
    field is `last_activity_at` (NOT `.session-lock`, NOT `pid`). A STALE lock
    (all sessions idle past the window) does NOT count, or the reaper would never
    run on a repo that ever hosted a session. Worktrees share the main lock, so
    checking the primary checkout covers the whole worktree set.
    """
    now_ts = now_ts or time.time()
    lock = repo / ".claude" / ".session-lock.json"
    try:
        data = json.loads(lock.read_text())
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    for s in data.get("sessions", []):
        la = s.get("last_activity_at") if isinstance(s, dict) else None
        if isinstance(la, (int, float)) and (now_ts - la) < SESSION_LOCK_LIVE_WINDOW_SEC:
            return True
    return False


def _plan_stash_reap(
    repo: Path, keep_k: int, ttl_days: float, now_ts: Optional[float] = None
) -> list[StashTarget]:
    """Reap claude-checkpoint stashes beyond keep-K OR older than TTL.

    NEVER touches named (non-checkpoint) stashes — those are hand-parked work.
    `git stash list` is newest-first, so we keep the first keep_k checkpoint
    entries and reap the rest, plus any checkpoint older than TTL.
    """
    now_ts = now_ts or time.time()
    rc, out, _ = _git(repo, "stash", "list", "--format=%gd%x09%ct%x09%gs")
    if rc != 0 or not out:
        return []
    targets: list[StashTarget] = []
    seen_checkpoints = 0
    for line in out.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        ref, ts_str, msg = parts[0], parts[1], parts[2]
        if PREFIX not in msg:  # PREFIX = "claude-checkpoint"
            continue  # named/parked stash → never reap
        try:
            ts = float(ts_str)
        except ValueError:
            ts = now_ts  # unknown age → don't reap on age grounds
        beyond_k = seen_checkpoints >= keep_k
        too_old = (now_ts - ts) > ttl_days * 86400
        seen_checkpoints += 1
        if beyond_k or too_old:
            reason = "beyond keep-K" if beyond_k else f"older than {ttl_days}d"
            targets.append(StashTarget(ref=ref, message=msg, reason=reason))
    return targets


PREFIX = "claude-checkpoint"  # checkpoint stash message prefix (see create-dev-repo-checkpoint.py)


def plan_repo_reap(
    repo: Path,
    keep_k: int = 10,
    ttl_days: float = 14,
    default_branch: Optional[str] = None,
    now_ts: Optional[float] = None,
) -> ReapPlan:
    """Compute (do NOT execute) what is safe to reap in one repo.

    Conservative by construction: reap only TRUE_MERGED + SQUASH_MERGED_STALE
    branches that are not checked out, only CLEAN worktrees on reapable
    branches, only surplus/old checkpoint stashes. Everything else is either
    surfaced for a human (RELIC, GENUINE_UNIQUE) or left untouched (BACKED_UP).
    A live .session-lock skips the whole repo.
    """
    repo = Path(repo)
    plan = ReapPlan(repo=repo)

    if _has_live_session_lock(repo, now_ts):
        plan.skipped.append((repo.name, "live session-lock — repo skipped wholesale"))
        return plan

    default_branch = default_branch or detect_default_branch(repo)
    if not default_branch:
        plan.skipped.append((repo.name, "no origin default branch — repo skipped"))
        return plan

    worktrees = _list_worktrees(repo)
    rc, primary, _ = _git(repo, "rev-parse", "--show-toplevel")
    primary_path = Path(primary) if rc == 0 and primary else repo
    checked_out = {b: p for (p, b) in worktrees if b}

    rc, out, _ = _git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/")
    for branch in out.splitlines():
        branch = branch.strip()
        if not branch or branch == default_branch:
            continue  # never touch the default branch
        cls = classify_branch(repo, branch, default_branch)
        rc_s, sha, _ = _git(repo, "rev-parse", "--short", branch)
        tgt = ReapTarget(branch=branch, cls=cls, sha=sha)
        if cls in REAPABLE_CLASSES:
            if branch in checked_out:
                plan.skipped.append(
                    (branch, f"{cls} but checked out at {checked_out[branch]} — branch kept")
                )
            else:
                plan.reap_branches.append(tgt)
        elif cls in SURFACE_CLASSES:
            plan.surface_branches.append(tgt)
        # BACKED_UP / UNKNOWN → no-op

    for wt_path, wt_branch in worktrees:
        if wt_branch is None:
            continue  # detached HEAD worktree → leave for human
        if wt_path.resolve() == primary_path.resolve():
            continue  # never reap the primary checkout
        if wt_branch == default_branch:
            continue
        cls = classify_branch(repo, wt_branch, default_branch)
        if cls not in REAPABLE_CLASSES:
            continue
        if _is_dirty(wt_path):
            plan.skipped.append(
                (str(wt_path), f"worktree on {cls} branch but DIRTY — never --force")
            )
            continue
        rc_s, sha, _ = _git(repo, "rev-parse", "--short", wt_branch)
        plan.reap_worktrees.append(WorktreeTarget(path=wt_path, branch=wt_branch, sha=sha))

    plan.reap_stashes = _plan_stash_reap(repo, keep_k, ttl_days, now_ts)
    return plan


def _stash_index(ref: str) -> int:
    m = re.search(r"\{(\d+)\}", ref)
    return int(m.group(1)) if m else 0


def execute_reap(plan: ReapPlan, apply: bool = False) -> dict:
    """Build a recovery manifest and, only when apply=True, perform the reaps.

    Order: worktrees first (frees their branch), then branches, then stashes
    (highest index first so lower indices stay valid mid-drop). Branch delete is
    `-D` — safe because the class proves the content is on origin. Worktree
    remove is WITHOUT `--force` (git refuses if it somehow turned dirty between
    plan and apply — fail safe). The manifest is ALWAYS returned (even dry-run)
    so a caller can persist it before destruction.
    """
    manifest: dict = {
        "repo": str(plan.repo),
        "applied": apply,
        "branches": [],
        "worktrees": [],
        "stashes": [],
    }
    for wt in plan.reap_worktrees:
        manifest["worktrees"].append(
            {"path": str(wt.path), "branch": wt.branch, "sha": wt.sha}
        )
        if apply:
            _git(plan.repo, "worktree", "remove", str(wt.path))  # no --force
    for t in plan.reap_branches:
        manifest["branches"].append({"branch": t.branch, "cls": t.cls, "sha": t.sha})
        if apply:
            _git(plan.repo, "branch", "-D", t.branch)
    for s in sorted(plan.reap_stashes, key=lambda x: _stash_index(x.ref), reverse=True):
        manifest["stashes"].append(
            {"ref": s.ref, "message": s.message, "reason": s.reason}
        )
        if apply:
            _git(plan.repo, "stash", "drop", s.ref)
    return manifest


def has_recent_session_commits(repo: Path, minutes: int = 30) -> bool:
    """True if at least one commit landed in the last <minutes>. Used to suppress
    nudges right after the user has actually committed.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "log",
                f"--since={minutes}.minutes.ago",
                "--oneline",
                "-1",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def discover_hubs(dev_root: Optional[Path] = None) -> list[Path]:
    """Enumerate the BARE hubs under ~/dev — one primary checkout per repo.

    A bare hub's `.git` is a real DIRECTORY (it can rot). A linked worktree's
    `.git` is a gitdir-pointer FILE (fresh off origin by construction) → excluded.
    A bare ORIGIN mirror (`<name>.git`, no `.git` subdir) is excluded too. This is
    deliberately simpler than the reaper's worktree-grouping discovery: hub-refresh
    only ever ff's / surfaces bare hubs, never worktrees.
    """
    dev_root = Path(dev_root) if dev_root is not None else (Path.home() / "dev")
    if not dev_root.exists():
        return []
    try:
        children = sorted(p for p in dev_root.iterdir() if p.is_dir())
    except OSError:
        return []
    return [c for c in children if (c / ".git").is_dir()]


# ---------------------------------------------------------------------------
# Hub-refresh classifier (MYC-1893) — keep bare ~/dev/<repo> hubs fresh.
#
# Bare hubs ROT: parked on stale feature branches, dirtied by edits, written
# into by background jobs (STALE-BARE-CHECKOUT-READ, MYC-670 / MYC-1127). The
# read-time guard warn-stale-dev-checkout.py DETECTS the rot; this is the
# PREVENTION half. It has exactly ONE auto-action — fast-forward a hub that is
# clean, on its default branch, behind, and carries no local commits (a
# GUARANTEED ff, fully reversible via reflog). Everything else is SURFACED for a
# human, NEVER auto-switched / auto-cleaned / auto-recovered (the over-engineered
# version was cut). Fetch-first is the CALLER's job (a stale local ref misleads
# in BOTH directions — MYC-1893 correction); this classifier reads refs only.
# ---------------------------------------------------------------------------


class HubAction:
    """String enum (plain constants for json/log friendliness)."""

    FF = "ff"                                  # clean + on default + behind>0 + ahead==0 → ff (only auto action)
    SURFACE_DIRTY = "surface:dirty"            # uncommitted changes → never touch
    SURFACE_OFF_DEFAULT = "surface:off-default"  # detached or on a feature branch → never switch
    SURFACE_DIVERGED = "surface:diverged"      # on default but carries unpushed local commits
    SKIP_CURRENT = "skip:current"              # already up to date with origin default
    SKIP_NO_ORIGIN = "skip:no-origin"          # no origin default branch (local-only repo)
    SKIP_SESSION_LOCK = "skip:session-lock"    # a live sibling session → don't fight it
    SKIP_WORKTREE = "skip:worktree"            # a linked worktree, not a primary bare hub


# A hub is only ever AUTO-advanced (ff); every other non-skip action is surfaced.
HUB_AUTO_ACTIONS = frozenset({HubAction.FF})
HUB_SURFACE_ACTIONS = frozenset({
    HubAction.SURFACE_DIRTY,
    HubAction.SURFACE_OFF_DEFAULT,
    HubAction.SURFACE_DIVERGED,
})


@dataclass
class HubState:
    repo: Path
    action: str
    default_branch: Optional[str] = None
    current_branch: Optional[str] = None  # None if HEAD is detached
    behind: int = 0
    ahead: int = 0
    dirty: bool = False
    head: str = ""


def _current_branch(repo: Path) -> Optional[str]:
    """The checked-out branch name, or None if HEAD is detached."""
    rc, out, _ = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
    return out if rc == 0 and out else None


def _ahead_behind(repo: Path, upstream: str) -> tuple[int, int]:
    """(ahead, behind) of HEAD vs `upstream` (e.g. 'origin/main'); (0, 0) on error.

    `git rev-list --left-right --count upstream...HEAD` prints '<behind>\\t<ahead>'
    (left = commits in upstream not in HEAD; right = commits in HEAD not in upstream).
    """
    rc, out, _ = _git(repo, "rev-list", "--left-right", "--count", f"{upstream}...HEAD")
    if rc != 0 or not out:
        return 0, 0
    parts = out.split()
    if len(parts) != 2:
        return 0, 0
    try:
        behind, ahead = int(parts[0]), int(parts[1])
    except ValueError:
        return 0, 0
    return ahead, behind


def classify_hub_action(
    repo: Path,
    *,
    default_branch: Optional[str] = None,
    now_ts: Optional[float] = None,
) -> HubState:
    """Classify a bare hub into exactly one HubAction. Fail-safe: anything the
    classifier cannot prove safe is SURFACEd or SKIPped, never auto-advanced.

    Decision order (first match wins):
      1. live .session-lock        → SKIP_SESSION_LOCK (don't fight a session)
      2. no origin default branch  → SKIP_NO_ORIGIN
      3. off the default branch    → SURFACE_OFF_DEFAULT (detached / feature branch)
      4. dirty working tree        → SURFACE_DIRTY
      5. unpushed local commits    → SURFACE_DIVERGED (ahead > 0)
      6. clean, on default, behind → FF   (the only auto action; a guaranteed ff)
         clean, on default, even   → SKIP_CURRENT
    """
    repo = Path(repo)
    st = HubState(repo=repo, action=HubAction.SKIP_CURRENT)
    rc, head, _ = _git(repo, "rev-parse", "--verify", "--quiet", "HEAD")
    st.head = head if rc == 0 else ""

    if _has_live_session_lock(repo, now_ts):
        st.action = HubAction.SKIP_SESSION_LOCK
        return st

    default_branch = default_branch or detect_default_branch(repo)
    st.default_branch = default_branch
    if not default_branch:
        st.action = HubAction.SKIP_NO_ORIGIN
        return st
    upstream = f"origin/{default_branch}"

    st.current_branch = _current_branch(repo)
    st.dirty = _is_dirty(repo)
    st.ahead, st.behind = _ahead_behind(repo, upstream)

    # Off the default branch (detached or a feature branch) → SURFACE, never
    # auto-switch. ff-only is only meaningful while sitting on the default.
    if st.current_branch != default_branch:
        st.action = HubAction.SURFACE_OFF_DEFAULT
        return st

    # On the default branch from here down.
    if st.dirty:
        st.action = HubAction.SURFACE_DIRTY
        return st

    # Un-backed-up local commits (ahead of origin) → SURFACE; an ff-only into a
    # branch carrying its own commits is either a no-op or impossible.
    if st.ahead > 0:
        st.action = HubAction.SURFACE_DIVERGED
        return st

    st.action = HubAction.FF if st.behind > 0 else HubAction.SKIP_CURRENT
    return st


def execute_hub_refresh(
    state: HubState,
    apply: bool = False,
    now_ts: Optional[float] = None,
) -> dict:
    """Advance exactly the FF hubs by a fast-forward; everything else is a no-op.

    apply=False is a dry-run that mutates nothing. apply=True re-classifies the
    hub immediately before mutating (a read-then-act atomicity gate: a hub that
    turned dirty / switched branch / diverged between plan and apply drops out of
    the FF set), then runs `git merge --ff-only` — which itself fails closed if
    the move is somehow no longer a fast-forward. A fast-forward only advances the
    branch pointer, so it is fully reversible from the reflog.
    """
    res: dict = {
        "repo": str(state.repo),
        "action": state.action,
        "applied": False,
        "ff_to": None,
        "ok": None,
    }
    if state.action != HubAction.FF:
        return res
    if not apply:
        res["ff_to"] = f"origin/{state.default_branch}"
        return res

    fresh = classify_hub_action(state.repo, now_ts=now_ts)
    if fresh.action != HubAction.FF:
        res["action"] = fresh.action
        res["skipped"] = "state-changed-since-plan"
        return res

    upstream = f"origin/{fresh.default_branch}"
    rc, _out, err = _git(state.repo, "merge", "--ff-only", upstream)
    res["ok"] = rc == 0
    res["applied"] = rc == 0
    if rc == 0:
        rc2, head, _ = _git(state.repo, "rev-parse", "HEAD")
        res["ff_to"] = head if rc2 == 0 else upstream
    else:
        res["error"] = err[:200]
    return res


def summarize_hub_states(states) -> dict:
    """Roll a fleet of HubState into counts + worst offenders, for the cheap
    SessionStart surfacer. 'offenders' = surfaced hubs + any hub still behind,
    sorted by commits-behind descending."""
    states = list(states)
    ff = sum(1 for s in states if s.action == HubAction.FF)
    surfaced = sum(1 for s in states if s.action in HUB_SURFACE_ACTIONS)
    skipped = sum(1 for s in states if s.action.startswith("skip:"))
    max_behind = max((s.behind for s in states), default=0)
    offenders = sorted(
        (
            (s.repo.name, s.action, s.behind)
            for s in states
            if s.action in HUB_SURFACE_ACTIONS or s.behind > 0
        ),
        key=lambda t: t[2],
        reverse=True,
    )
    return {
        "ff": ff,
        "surfaced": surfaced,
        "skipped": skipped,
        "max_behind": max_behind,
        "offenders": offenders,
    }


_HUB_ACTION_LABEL = {
    HubAction.SURFACE_DIRTY: "dirty working tree",
    HubAction.SURFACE_OFF_DEFAULT: "off the default branch",
    HubAction.SURFACE_DIVERGED: "unpushed local commits",
    HubAction.FF: "behind (auto-ff pending)",
}


def format_hub_surface_line(
    summary: dict, threshold: int = 50, limit: int = 6
) -> Optional[str]:
    """A one-line SessionStart nudge, or None when nothing is worth saying.

    Speaks up when ANY hub needs a human (surfaced: dirty / off-default /
    diverged) OR a hub is >= `threshold` commits behind origin (a sign the
    launchd auto-refresh has stalled). A clean main only a little behind is
    auto-fixable and stays silent."""
    surfaced = summary.get("surfaced", 0)
    max_behind = summary.get("max_behind", 0)
    if surfaced == 0 and max_behind < threshold:
        return None
    offenders = summary.get("offenders", [])
    parts = [
        "[dev-hub-refresh]",
        "",
        (
            f"{surfaced} bare ~/dev hub(s) need a human; worst is {max_behind} "
            f"commit(s) behind origin. Auto-ff handles clean mains — these need you:"
        ),
    ]
    for name, action, behind in offenders[:limit]:
        label = _HUB_ACTION_LABEL.get(action, action)
        parts.append(f"- `{name}` — {label} ({behind} behind)")
    if len(offenders) > limit:
        parts.append(f"- … and {len(offenders) - limit} more")
    parts += [
        "",
        (
            "Resolve each in its repo (commit or stash local work, then "
            "`git pull --ff-only`), or run `dev-hub-refresh.py` (dry-run) "
            "then `--apply` to handle the clean ones in bulk."
        ),
    ]
    return "\n".join(parts)
