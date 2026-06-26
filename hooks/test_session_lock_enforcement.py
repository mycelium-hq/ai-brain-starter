#!/usr/bin/env python3
"""Unit regression suite for session-lock.py's PreToolUse enforcement resolver.

Run: python3 hooks/test_session_lock_enforcement.py   (exit 0 = pass)

Exercises ``_is_home_repo_git_mutation`` across the matrix the
SIBLING-SESSION-FALSE-BLOCK ticket family hardened:
  * read-only vs mutating git subcommands (commit/push/reset vs status/log/diff)
  * cross-repo attribution via ``-C`` and the git-dir (``--git-dir`` flag or
    ``GIT_DIR=`` env) — the git-dir is the collision surface (HEAD/index/refs),
    so a cross-repo git-dir must NOT false-block and a home git-dir MUST block.
    ``--work-tree`` is deliberately NOT a redirect: a ``--work-tree=/other``
    mutation still writes the home git-dir, so it must still block (false-ALLOW
    avoidance)
  * in-command ``cd`` tracking (``cd /other && git commit`` is attributed to
    /other; a ``cd`` back into home re-attributes)
  * unresolved ``$VAR`` redirects + the unbalanced-quote coarse fallback that a
    multi-line ``-m`` message triggers

Pure logic — no git, no filesystem, no live sibling needed. The end-to-end exit
codes (BLOCKED / HEADS-UP / bypass) are covered by the bash wrapper in
tests/integration/test_session_coordination_guards.sh.
"""
import importlib.util
import os
import shlex
import sys

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session-lock.py")
_spec = importlib.util.spec_from_file_location("session_lock_under_test", HOOK)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

HOME = "/home/proj"
OTHER = "/home/other"
ML = 'git commit -m "line one\nline two"'          # multi-line msg => coarse branch (home)
ML_C = 'git -C /home/other commit -m "l1\nl2"'      # multi-line + -C at other repo
ML_VAR_C = 'git -C "$d" commit -m "l1\nl2"'         # multi-line + $VAR -C (must let through)

fails = []


def check(name, got, want):
    ok = (got == want)
    print(("PASS" if ok else "FAIL"), name, "" if ok else f":: got {got!r} want {want!r}")
    if not ok:
        fails.append(name)


def mut(cmd, cwd=HOME, home=HOME):
    return mod._is_home_repo_git_mutation(cmd, cwd, home)


# (label, command, cwd, home, expected)
CASES = [
    # --- bare mutations attributed to cwd / home ---
    ("bare commit in home -> block", "git commit -m x", HOME, HOME, True),
    ("bare push in home -> block", "git push", HOME, HOME, True),
    ("reset --hard in home -> block", "git reset --hard HEAD~1", HOME, HOME, True),
    ("bare commit in a non-home cwd -> allow", "git commit -m x", OTHER, HOME, False),
    # --- read-only git is never a mutation ---
    ("status -> allow", "git status", HOME, HOME, False),
    ("log -> allow", "git log --oneline", HOME, HOME, False),
    ("diff -> allow", "git diff", HOME, HOME, False),
    ("fetch -> allow", "git fetch origin", HOME, HOME, False),
    # --- -C redirect ---
    ("-C cross-repo -> allow", "git -C /home/other commit -m x", HOME, HOME, False),
    ("-C within home -> block", "git -C /home/proj/sub commit -m x", HOME, HOME, True),
    ("-C unresolved $VAR -> allow", 'git -C "$VAR" commit', HOME, HOME, False),
    # --- git-dir IS the collision surface; --work-tree is NOT a redirect ---
    ("--git-dir cross-repo -> allow", "git --git-dir=/home/other/.git commit -m x", HOME, HOME, False),
    ("--git-dir home -> block", "git --git-dir=/home/proj/.git commit -m x", HOME, HOME, True),
    ("--git-dir space-form cross-repo -> allow",
     "git --git-dir /home/other/.git commit -m x", HOME, HOME, False),
    ("GIT_DIR= env cross-repo -> allow", "GIT_DIR=/home/other/.git git commit -m x", HOME, HOME, False),
    ("GIT_DIR= env home -> block", "GIT_DIR=/home/proj/.git git commit -m x", HOME, HOME, True),
    ("--work-tree=/other but home git-dir -> BLOCK (false-ALLOW avoided)",
     "git --work-tree=/home/other commit", HOME, HOME, True),
    ("--work-tree home -> block", "git --work-tree=/home/proj commit", HOME, HOME, True),
    ("--git-dir cross + --work-tree home -> allow (git-dir wins)",
     "git --git-dir=/home/other/.git --work-tree=/home/proj commit", HOME, HOME, False),
    # --- cd tracking across compound commands ---
    ("cd other && commit -> allow", "cd /home/other && git commit -m x", HOME, HOME, False),
    ("cd other then back home && commit -> block",
     "cd /home/other && cd /home/proj && git commit -m x", HOME, HOME, True),
    ("cd unknown $VAR && bare commit -> allow", 'cd "$X" && git commit -m y', HOME, HOME, False),
    ("cd other && -C home commit -> block (-C wins)",
     "cd /home/other && git -C /home/proj commit", HOME, HOME, True),
    ("subshell ( cd other && commit ) -> allow",
     "( cd /home/other && git commit -m x )", HOME, HOME, False),
    # --- branch / stash / tag mutation classification ---
    ("branch -D -> block", "git branch -D feature", HOME, HOME, True),
    ("branch list -> allow", "git branch", HOME, HOME, False),
    ("branch --list -> allow", "git branch --list", HOME, HOME, False),
    ("stash (push) -> block", "git stash", HOME, HOME, True),
    ("stash list -> allow", "git stash list", HOME, HOME, False),
    ("tag create -> block", "git tag v1.0", HOME, HOME, True),
    ("tag -l -> allow", "git tag -l", HOME, HOME, False),
    # --- wrappers + config opt ---
    ("env wrapper commit in home -> block", "env FOO=1 git commit -m x", HOME, HOME, True),
    ("sudo wrapper + -C cross-repo -> allow", "sudo git -C /home/other commit", HOME, HOME, False),
    ("-c config (not a redirect) + home commit -> block",
     "git -c user.name=x commit -m y", HOME, HOME, True),
    # --- non-git noise ---
    ("ls -> allow", "ls -la", HOME, HOME, False),
    ("echo containing 'git commit' -> allow", "echo git commit", HOME, HOME, False),
    # --- unbalanced-quote coarse fallback (multi-line -m) ---
    ("multi-line -m commit in home -> block (coarse)", ML, HOME, HOME, True),
    ("multi-line -m + -C cross-repo -> allow (coarse -C escape)", ML_C, HOME, HOME, False),
    ("multi-line -m + $VAR -C -> allow (coarse $VAR escape)", ML_VAR_C, HOME, HOME, False),
    # --- GIT_DIR= env form in the coarse multi-line -m branch ---
    ("GIT_DIR= env + multi-line, cross-repo -> allow (coarse mge)",
     'GIT_DIR=/home/other/.git git commit -m "l1\nl2"', HOME, HOME, False),
    ("GIT_DIR= env + multi-line, home -> block (coarse)",
     'GIT_DIR=/home/proj/.git git commit -m "l1\nl2"', HOME, HOME, True),
    ("FOO=bar GIT_DIR= prefix + multi-line, cross-repo -> allow",
     'FOO=bar GIT_DIR=/home/other/.git git commit -m "l1\nl2"', HOME, HOME, False),
    ("GIT_DIR= only INSIDE the message -> still blocks home commit (no false-ALLOW)",
     'git commit -m "ref GIT_DIR=/home/other/.git here\nl2"', HOME, HOME, True),
]

for label, cmd, cwd, home, want in CASES:
    check(label, mut(cmd, cwd, home), want)

# --- _git_mutation_target (cdir, gdir) unit checks ---
check("gmt: -C captured as cdir, --work-tree ignored", mod._git_mutation_target(shlex.split(
    "git -C /x --work-tree /y commit")), (True, "/x", None))
check("gmt: --git-dir captured as gdir, --work-tree ignored", mod._git_mutation_target(shlex.split(
    "git --work-tree /y --git-dir /z/.git commit")), (True, None, "/z/.git"))
check("gmt: --git-dir= form -> gdir", mod._git_mutation_target(shlex.split(
    "git --git-dir=/z/.git commit")), (True, None, "/z/.git"))
check("gmt: GIT_DIR= env -> gdir", mod._git_mutation_target(shlex.split(
    "GIT_DIR=/z/.git git commit")), (True, None, "/z/.git"))
check("gmt: -C + --git-dir both captured", mod._git_mutation_target(shlex.split(
    "git -C /x --git-dir /z/.git commit")), (True, "/x", "/z/.git"))
check("gmt: no redirect -> (True,None,None)", mod._git_mutation_target(shlex.split(
    "git commit -m x")), (True, None, None))
check("gmt: read-only -> False", mod._git_mutation_target(shlex.split(
    "git status")), False)

print(f"\n=== {len(CASES) + 7} assertions, {len(fails)} failed ===")
sys.exit(1 if fails else 0)
