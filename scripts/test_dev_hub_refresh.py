#!/usr/bin/env python3
"""Controls for dev-hub-refresh (MYC-1893, tickets#1589).

The refresh moves main checkouts, so its controls are about what it refuses to
move at least as much as what it moves. Built on real throwaway repos: a bare
"origin", a hub clone under a scratch dev root, and a second clone that plays the
merge on GitHub.

  * dev root from the shared resolver; a configured one that is missing
    -> exit 1, never "0 hubs"; none configured and no ~/dev -> quiet 0
  * on main, clean, behind                         -> FF
  * clean, branch squash-merged + deleted on origin -> RETURN, then on main at
                                                       origin/main, branch KEPT
  * clean, branch merged into main (still on origin) -> RETURN
  * branch still open on origin, not merged       -> SURFACE (stays put)
  * finished branch but an untracked file         -> SURFACE (stays put)
  * finished branch but a commit on no remote     -> SURFACE (stays put)
  * finished branch but local main has own commits -> SURFACE (stays put)
  * finished branch, but an IGNORED local file sits where main tracks a file
    (git switch would overwrite it silently)       -> SURFACE (stays put)
  * branch tracking a fork remote, pushed under another name without -u, a
    fresh branch tracking main, or no upstream      -> SURFACE (stays put)
  * squash-merged but its tracking ref was pruned  -> SURFACE (cannot prove pushed)
  * a switch that fails                            -> listed as FAILED, exit 1
  * a configured dev root that is ~/dev and missing -> exit 1, not "unconfigured"
  * dry-run                                       -> moves nothing at all

Run: python3 scripts/test_dev_hub_refresh.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
REFRESH = SCRIPTS / "dev-hub-refresh.py"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
}


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                       text=True, env=dict(os.environ, **GIT_ENV))
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {repo}: {r.stderr}")
    return r.stdout.strip()


def commit(repo, name, text="x"):
    (Path(repo) / name).write_text(text)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", f"add {name}")


def make_hub(tmp: Path, dev: Path, name: str):
    """origin (bare) + a hub clone in the dev root + a 'github' clone."""
    origin = tmp / f"{name}.git"
    git(tmp, "init", "-q", "--bare", "-b", "main", str(origin))
    gh = tmp / f"{name}-gh"
    git(tmp, "clone", "-q", str(origin), str(gh))
    git(gh, "switch", "-q", "-c", "main")
    commit(gh, "README")
    git(gh, "push", "-q", "-u", "origin", "main")
    hub = dev / name
    git(tmp, "clone", "-q", str(origin), str(hub))
    return origin, gh, hub


def feature(hub: Path, branch: str):
    """The hub parks on a pushed feature branch (the incident's shape)."""
    git(hub, "switch", "-q", "-c", branch)
    commit(hub, f"{branch.replace('/', '-')}.txt")
    git(hub, "push", "-q", "-u", "origin", branch)


def squash_merge_and_delete(gh: Path, branch: str):
    git(gh, "fetch", "-q", "origin")
    git(gh, "switch", "-q", "main")
    git(gh, "merge", "-q", "--squash", f"origin/{branch}")
    git(gh, "commit", "-q", "-m", f"squash {branch}")
    commit(gh, "later.txt")  # main moves on past the merge
    git(gh, "push", "-q", "origin", "main")
    git(gh, "push", "-q", "origin", "--delete", branch)


def run(dev: Path, tmp: Path, *extra, root=None, via_resolver=False):
    env = {k: v for k, v in os.environ.items() if k != "DEV_HUB_REFRESH_ROOT"}
    env.update(GIT_ENV,
               DEV_REPO_SCAN_DIR=str(SCRIPTS.parent / "hooks"),
               DEV_HUB_REFRESH_STATE=str(tmp / "state.json"),
               DEV_HUB_REFRESH_LOG_DIR=str(tmp / "logs"))
    if via_resolver:
        # The path a real install takes: no override, the shared resolver.
        env["ABS_DEV_ROOT"] = str(dev)
    else:
        env["DEV_HUB_REFRESH_ROOT"] = str(root or dev)
    return subprocess.run([sys.executable, str(REFRESH), "--json", *extra],
                          capture_output=True, text=True, env=env)


def main() -> int:
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td).resolve()
        dev = tmp / "code"
        dev.mkdir()

        # FF: on main, behind.
        _, gh, ff = make_hub(tmp, dev, "ffhub")
        commit(gh, "new.txt"); git(gh, "push", "-q", "origin", "main")

        # RETURN: squash-merged, deleted on origin (the 2026-11-06 incident).
        _, gh, sq = make_hub(tmp, dev, "squashed")
        feature(sq, "claude/done")
        squash_merge_and_delete(gh, "claude/done")

        # RETURN: merged by ancestry, remote branch left in place.
        _, gh, anc = make_hub(tmp, dev, "merged")
        feature(anc, "claude/merged")
        git(gh, "fetch", "-q", "origin"); git(gh, "merge", "-q", "--ff-only", "origin/claude/merged")
        commit(gh, "later.txt"); git(gh, "push", "-q", "origin", "main")

        # SURFACE: open branch.
        _, gh, opn = make_hub(tmp, dev, "open")
        feature(opn, "claude/wip")
        commit(gh, "later.txt"); git(gh, "push", "-q", "origin", "main")

        # SURFACE: finished but untracked file.
        _, gh, dirty = make_hub(tmp, dev, "dirty")
        feature(dirty, "claude/done")
        squash_merge_and_delete(gh, "claude/done")
        (dirty / "scratch.txt").write_text("unsaved")

        # SURFACE: finished but a commit on no remote.
        _, gh, unp = make_hub(tmp, dev, "unpushed")
        feature(unp, "claude/done")
        squash_merge_and_delete(gh, "claude/done")
        commit(unp, "local-only.txt")

        # SURFACE: finished but local main carries its own commit.
        _, gh, div = make_hub(tmp, dev, "diverged")
        commit(div, "local-main.txt")
        feature(div, "claude/done")
        # feature() pushed claude/done, which carries local-main's commit too,
        # so only main itself holds something origin/main lacks.
        squash_merge_and_delete(gh, "claude/done")

        # SURFACE: a branch that moved a config file out of git; the local copy
        # is now ignored, and main still tracks it.
        _, gh, ign = make_hub(tmp, dev, "ignored")
        commit(gh, "settings.json", '{"default":1}'); git(gh, "push", "-q", "origin", "main")
        git(ign, "pull", "-q", "--ff-only")
        git(ign, "switch", "-q", "-c", "claude/untrack")
        git(ign, "rm", "-q", "--cached", "settings.json")
        (ign / ".gitignore").write_text("settings.json\n"); git(ign, "add", ".gitignore")
        git(ign, "commit", "-q", "-m", "untrack settings")
        git(ign, "push", "-q", "-u", "origin", "claude/untrack")
        (ign / "settings.json").write_text('{"MY_LOCAL":"precious"}')
        # The PR is closed and its branch deleted; main still tracks the file.
        git(gh, "push", "-q", "origin", "--delete", "claude/untrack")

        # SURFACE: tracking a fork remote; origin never had the branch.
        fork_origin, gh, frk = make_hub(tmp, dev, "forked")
        fork = tmp / "fork.git"; git(tmp, "init", "-q", "--bare", "-b", "main", str(fork))
        git(frk, "remote", "add", "fork", str(fork))
        git(frk, "switch", "-q", "-c", "feat"); commit(frk, "f.txt")
        git(frk, "push", "-q", "-u", "fork", "feat")

        # SURFACE: pushed to origin under another name, no tracking.
        _, gh, ren = make_hub(tmp, dev, "renamed")
        git(ren, "switch", "-q", "-c", "local-name"); commit(ren, "r.txt")
        git(ren, "push", "-q", "origin", "local-name:pr-branch")

        # SURFACE: fresh branch tracking origin/main (no commits of its own).
        _, gh, fresh = make_hub(tmp, dev, "fresh")
        git(fresh, "switch", "-q", "-c", "feat", "--track", "origin/main")

        # SURFACE: squash-merged and deleted, but the tracking ref was pruned,
        # so nothing here proves the branch's tip was ever pushed.
        _, gh, prn = make_hub(tmp, dev, "pruned")
        feature(prn, "claude/done")
        squash_merge_and_delete(gh, "claude/done")
        git(prn, "fetch", "-q", "--prune", "origin")

        # FAILED: finished, but a live index.lock makes the switch itself fail.
        _, gh, lck = make_hub(tmp, dev, "locked")
        feature(lck, "claude/done")
        squash_merge_and_delete(gh, "claude/done")

        def branch(repo):
            return git(repo, "rev-parse", "--abbrev-ref", "HEAD")

        stays = (opn, dirty, unp, div, ign, frk, ren, fresh, prn)
        everyone = (ff, sq, anc, lck) + stays
        before = {p.name: (branch(p), git(p, "rev-parse", "HEAD")) for p in everyone}

        # --- missing dev root is an error, not an empty fleet ---------------
        r = run(dev, tmp, root=tmp / "nope")
        check(r.returncode == 1 and "does not exist" in r.stderr,
              f"missing dev root must exit 1 with a reason, got rc={r.returncode} "
              f"stderr={r.stderr[-300:]}")

        # --- a CONFIGURED ~/dev that is missing is an error ------------------
        r = subprocess.run(
            [sys.executable, str(REFRESH)], capture_output=True, text=True,
            env=dict({k: v for k, v in os.environ.items()
                      if k != "DEV_HUB_REFRESH_ROOT"},
                     HOME=str(tmp / "emptyhome"),
                     ABS_DEV_ROOT=str(tmp / "emptyhome" / "dev"),
                     DEV_REPO_SCAN_DIR=str(SCRIPTS.parent / "hooks"),
                     DEV_HUB_REFRESH_STATE=str(tmp / "state-cfg.json"),
                     DEV_HUB_REFRESH_LOG_DIR=str(tmp / "logs-cfg")))
        check(r.returncode == 1 and "does not exist" in r.stderr,
              f"a configured ~/dev that is missing must exit 1, got rc={r.returncode} "
              f"out={r.stdout[-200:]}")

        # --- no code folder at all (most members): quiet success -----------
        r = subprocess.run(
            [sys.executable, str(REFRESH)], capture_output=True, text=True,
            env=dict({k: v for k, v in os.environ.items()
                      if k not in ("DEV_HUB_REFRESH_ROOT", "ABS_DEV_ROOT")},
                     HOME=str(tmp / "emptyhome"),
                     DEV_REPO_SCAN_DIR=str(SCRIPTS.parent / "hooks"),
                     DEV_HUB_REFRESH_STATE=str(tmp / "state-empty.json"),
                     DEV_HUB_REFRESH_LOG_DIR=str(tmp / "logs-empty")))
        check(r.returncode == 0 and "no code folder" in r.stdout,
              f"no dev root configured and no ~/dev must be a quiet success, got "
              f"rc={r.returncode} out={r.stdout[-200:]} err={r.stderr[-200:]}")

        # --- dry run: classifies, moves nothing ------------------------------
        r = run(dev, tmp, via_resolver=True)
        check(r.returncode == 0, f"dry-run failed: {r.stderr[-500:]}")
        state = json.loads((tmp / "state.json").read_text())
        check(len(state["hubs"]) == len(everyone),
              f"the shared dev-root resolver must find all {len(everyone)} hubs, found "
              f"{len(state['hubs'])} (the ~/dev hard-code scanned none)")
        actions = {h["repo"]: h["action"] for h in state["hubs"]}
        reasons = {h["repo"]: h.get("reason", "") for h in state["hubs"]}
        expect = {"ffhub": "ff", "squashed": "return", "merged": "return",
                  "locked": "return"}
        # Each stay-put hub must stay for ITS reason, not because a probe errored.
        why = {"open": "still open", "dirty": "uncommitted", "unpushed": "not pushed",
               "diverged": "local main has commits", "ignored": "ignored local file",
               "forked": "tracks fork", "renamed": "no upstream",
               "fresh": "tracks main itself", "pruned": "pruned"}
        for name in why:
            expect[name] = "surface:off-default"
        for name, want in expect.items():
            check(actions.get(name) == want,
                  f"{name}: expected {want}, got {actions.get(name)} ({reasons.get(name)})")
        for name, frag in why.items():
            check(frag in reasons.get(name, ""),
                  f"{name}: surfaced for the wrong reason: {reasons.get(name)!r}")
        after_dry = {p.name: (branch(p), git(p, "rev-parse", "HEAD")) for p in everyone}
        check(after_dry == before, f"dry-run moved something: {before} -> {after_dry}")

        # --- apply ----------------------------------------------------------
        (lck / ".git" / "index.lock").write_text("")  # a git running right now
        r = run(dev, tmp, "--apply")
        (lck / ".git" / "index.lock").unlink()
        check(r.returncode == 1, f"a failed switch must fail the run, got rc={r.returncode}")
        try:
            doc = json.loads(r.stdout)
        except ValueError:
            doc = {}
        check([f["repo"] for f in doc.get("failed", [])] == ["locked"],
              f"the failed switch must be listed, got {doc.get('failed')}")
        check(doc.get("summary", {}).get("returned") == 2,
              f"returned count must be what actually returned (2), got "
              f"{doc.get('summary', {}).get('returned')}")
        check(branch(lck) == "claude/done", "locked: must still be on its branch")
        for hub in (sq, anc):
            check(branch(hub) == "main", f"{hub.name}: not returned to main ({branch(hub)})")
            check(git(hub, "rev-parse", "HEAD") == git(hub, "rev-parse", "origin/main"),
                  f"{hub.name}: returned but not fast-forwarded to origin/main")
        check(git(sq, "branch", "--list", "claude/done") != "",
              "squashed: the finished branch must be kept, not deleted")
        check(git(ff, "rev-parse", "HEAD") == git(ff, "rev-parse", "origin/main"),
              "ffhub: not fast-forwarded")
        for hub in stays:
            check((branch(hub), git(hub, "rev-parse", "HEAD")) == before[hub.name],
                  f"{hub.name}: must stay put, moved to {branch(hub)}")
        check((dirty / "scratch.txt").read_text() == "unsaved",
              "dirty: the untracked file must be untouched")
        check((ign / "settings.json").read_text() == '{"MY_LOCAL":"precious"}',
              "ignored: the ignored local file must not be overwritten")
        check(any((tmp / "logs").glob("refresh-*.json")),
              "apply must write its log to the overridden log dir")

    if failures:
        print("FAILED — dev-hub-refresh (MYC-1893, tickets#1589):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("OK - dev-hub-refresh: reads the configured dev root, fails on a missing one, "
          "ff's clean mains, returns clean finished branches (kept), and leaves open, "
          "dirty, unpushed and diverged hubs exactly where they were")
    return 0


if __name__ == "__main__":
    sys.exit(main())
