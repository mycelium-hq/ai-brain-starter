#!/usr/bin/env python3
"""The close gate and the close commit must scope to THIS session, not its worktree.

Two parallel sessions on one plain checkout both have worktree `main`; two
sessions sharing a worktree both have its slug. Anything that attributes
session-close artifacts by worktree cannot tell them apart:

  - verify-session-close-cascade.py passed gate 1 if ANY file today carried the
    slug, so session A's gate went green on session B's note; and gate 3
    flagged ANY uncommitted Sessions/ file carrying the slug, so A was blocked
    on B's half-written note. On a plain checkout the gate did not run at all.
  - session-end-hook.sh staged every Decisions/ file dated today and touched
    in the last 10 minutes, so A's close commit swept up B's decisions, and
    its bare `git commit` also carried anything B already had in the index.

The fix: the closing-signal marker records this session's exact
`session_file`; the gate checks THAT file. A note or decision whose
frontmatter names its owner (`session_id:`) is attributed by owner. Only when
nothing identifies the session does the old worktree behavior apply.

The owner line on a session NOTE is written by detect-closing-signal.py's
pre-built shell once ai-brain-starter#712 lands; the scenarios that need it
write it by hand, in that writer's exact format (`session_id: "<id>"`).

Assertions (each runs the real hook as a subprocess, hermetic HOME + vault):
  1. A without a note, B with one (main) -> A is BLOCKED, naming A's file.
  2. Same, two sessions sharing one worktree slug -> A is BLOCKED.
  3. A committed, B's note uncommitted -> A PASSES (main and shared worktree).
  4. A committed, B's decision uncommitted (owned, or naming no owner) -> A
     PASSES.
  5. Marker already consumed (a retry, or a close spanning two turns): A's
     owned note committed, B's uncommitted -> A PASSES; A's owned note
     uncommitted -> A is BLOCKED. On main and on a shared worktree.
  6. The close commit stages A's decisions, never B's, and never commits what
     B already staged.
  7. The injected cascade tells the model to stamp decisions with the id.
  8. Owner lines with CRLF endings or a trailing comment still parse.
  9. The close commit's owner filter survives a cp1252 stdio (Windows).
 10. A trivial close (the cascade told it to skip itself) is not gated.
 11. A vault in a repo subdirectory gets block paths relative to the vault.
 12. A VAULT_ROOT spelled in the wrong case still matches A's note (only on a
     case-insensitive filesystem).
  NEGATIVE CONTROLS - the gate still has teeth:
 13. A's own note uncommitted -> BLOCKED, naming A's file and not B's.
 14. A's own decision uncommitted -> BLOCKED, naming it.
 15. A's note committed and nothing else -> PASSES (not an always-block).
 16. The close commit still stages A's own decision AND an untagged one.
  FALLBACK (no marker, no owner) - unchanged behavior:
 17. Plain checkout, no marker, no owned note -> the gate skips, as before.
 18. Worktree, no marker, no note for the slug -> BLOCKED, as before.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
REPO = HOOKS.parent
GATE = HOOKS / "verify-session-close-cascade.py"
DETECT = HOOKS / "detect-closing-signal.py"
END_HOOK = REPO / "scripts" / "session-end-hook.sh"

META = "⚙️ Meta"
TODAY = datetime.now().strftime("%Y-%m-%d")
A, B = "sessA-1111-aaaa", "sessB-2222-bbbb"
WT = "wt-shared"
UTF8 = {"encoding": "utf-8", "errors": "replace"}

failures: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    if cond:
        print(f"PASS: {label}")
    else:
        failures.append(label)
        print(f"FAIL: {label}" + (f"\n      {detail}" if detail else ""))


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True, **UTF8,
    ).stdout


class Env:
    """One hermetic world: a git vault with the cascade installed + a HOME.

    `vault_dir` places the vault inside the repo (a subdirectory vault);
    `vault_dir_on_disk` lets the directory's real name differ in case from
    the spelling the hooks are given.
    """

    def __init__(self, vault_dir: str = "", vault_dir_on_disk: str | None = None) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="close-gate-")).resolve()
        self.repo = self.root / "repo"
        on_disk = vault_dir_on_disk if vault_dir_on_disk is not None else vault_dir
        real_vault = self.repo / on_disk if on_disk else self.repo
        self.vault = self.repo / vault_dir if vault_dir else self.repo  # as the hooks see it
        self.home = self.root / "home"
        (self.home / ".claude").mkdir(parents=True)
        for d in ("Sessions", "Decisions", "scripts"):
            (real_vault / META / d).mkdir(parents=True)
        self.sessions = self.vault / META / "Sessions"
        self.decisions = self.vault / META / "Decisions"
        # Runner installed => the gate ENFORCES (hard-block), not advisory.
        (real_vault / META / "scripts" / "session-close-runner.sh").write_text(
            "#!/bin/bash\n", encoding="utf-8")
        (self.repo / "README.md").write_text("# vault\n", encoding="utf-8")
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "init")
        self.report = self.root / "runner.report"
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.report.write_text(f"...\nRUNNER COMPLETE @ {stamp}\n", encoding="utf-8")
        self.transcript = self.root / "transcript.jsonl"
        self.transcript.write_text(json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text",
                                     "text": "Cascade complete. Closing the session."}]},
        }) + "\n", encoding="utf-8")

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def cwd(self, mode: str) -> Path:
        if mode == "main":
            return self.vault
        wt = self.vault / ".claude" / "worktrees" / WT
        wt.mkdir(parents=True, exist_ok=True)
        return wt

    def note(self, slug: str, sid: str, owned: bool = False, commit: bool = False) -> Path:
        """A session note named the way detect-closing-signal names it."""
        path = self.sessions / f"{TODAY}T15-25-{slug}-{sid[:8].replace('-', '')}.md"
        owner = f'session_id: "{sid}"\n' if owned else ""
        path.write_text(
            f"---\ntype: session\nworktree: {slug}\n{owner}session_date: {TODAY}\n---\n"
            f"# Session\n\nbody for {sid}\n", encoding="utf-8",
        )
        if commit:
            self.commit(path)
        return path

    def decision(self, slug: str, sid: str | None, name: str, commit: bool = False,
                 owner_line: str | None = None, newline: str = "\n") -> Path:
        path = self.decisions / f"{TODAY}-{name}.md"
        if owner_line is None:
            owner_line = f'session_id: "{sid}"' if sid else ""
        lines = ["---", "type: decision", f"worktree: {slug}"]
        lines += [owner_line] if owner_line else []
        lines += [f"decision_date: {TODAY}", "---", f"# Decision {name}", ""]
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(newline.join(lines))
        if commit:
            self.commit(path)
        return path

    def commit(self, path: Path) -> None:
        git(self.repo, "add", "--", str(path))
        git(self.repo, "commit", "-qm", f"add {path.name}")

    def marker(self, sid: str, session_file: Path, trivial: bool = False) -> Path:
        m = self.home / ".claude" / f".closing-signal-{sid}.json"
        m.write_text(json.dumps({"session_file": str(session_file), "is_trivial": trivial}),
                     encoding="utf-8")
        return m

    def _env(self) -> dict:
        env = {k: v for k, v in os.environ.items()
               if k not in ("VERIFY_CASCADE_BYPASS", "VERIFY_CASCADE_SOFT")}
        # USERPROFILE too: on Windows Path.home() reads it, not HOME, and the
        # hooks would otherwise read and write markers in the REAL ~/.claude.
        env.update(HOME=str(self.home), USERPROFILE=str(self.home),
                   VAULT_ROOT=str(self.vault), ABS_RUNNER_REPORT=str(self.report))
        return env

    def gate(self, sid: str, mode: str) -> tuple[int, str]:
        payload = {"session_id": sid, "transcript_path": str(self.transcript),
                   "cwd": str(self.cwd(mode))}
        r = subprocess.run([sys.executable, str(GATE)], input=json.dumps(payload),
                           capture_output=True, text=True, env=self._env(),
                           cwd=str(self.cwd(mode)), timeout=60, **UTF8)
        return r.returncode, r.stderr

    def end_hook(self, sid: str, **extra_env: str) -> None:
        env = self._env()
        env.update(CLOSE_MAX_LOAD_PER_CORE="99999", CLOSE_MUTEX=str(self.root / "close.lock"))
        env.update(extra_env)
        # transcript_path "" keeps the Haiku fallback out of a hermetic test.
        subprocess.run(["bash", str(END_HOOK)],
                       input=json.dumps({"session_id": sid, "transcript_path": ""}),
                       capture_output=True, text=True, env=env, cwd=str(self.vault),
                       timeout=120, **UTF8)

    def committed(self, path: Path) -> bool:
        """In HEAD -- not merely staged in the index."""
        rel = path.relative_to(self.repo).as_posix()
        return bool(git(self.repo, "ls-tree", "-r", "--name-only", "HEAD", "--", rel).strip())


def scenario(fn, **env_kw):
    env = Env(**env_kw)
    try:
        fn(env)
    except Exception as e:  # a crash in one scenario must not hide the rest
        failures.append(f"{fn.__name__} crashed: {e!r}")
        print(f"FAIL: {fn.__name__} crashed: {e!r}")
    finally:
        env.cleanup()


MODES = (("main", "main"), ("worktree", WT))


# ── 1 + 2: the false green (A has no note, B does) ────────────────────────────
for _mode, _slug in MODES:
    def _false_green(e: Env, mode=_mode, slug=_slug) -> None:
        own = e.sessions / f"{TODAY}T15-25-{slug}-sessA1111.md"  # never written
        e.note(slug, B, owned=True, commit=True)
        e.marker(A, own)
        rc, err = e.gate(A, mode)
        check(rc == 2, f"[{mode}] A with no note is BLOCKED although B has one (rc={rc})", err[-400:])
        check(own.name in err, f"[{mode}] the block names A's own file", err[-400:])
    _false_green.__name__ = f"false_green_{_mode}"
    scenario(_false_green)


# ── 3: the false block (B's note uncommitted) ─────────────────────────────────
for _mode, _slug in MODES:
    def _false_block(e: Env, mode=_mode, slug=_slug) -> None:
        own = e.note(slug, A, owned=True, commit=True)
        e.note(slug, B, owned=True, commit=False)
        e.marker(A, own)
        rc, err = e.gate(A, mode)
        check(rc == 0, f"[{mode}] A PASSES while B's note is uncommitted (rc={rc})", err[-400:])
    _false_block.__name__ = f"false_block_{_mode}"
    scenario(_false_block)


# ── 4: B's decision uncommitted does not block A ──────────────────────────────
for _owned in (True, False):
    def _decision_false_block(e: Env, owned=_owned) -> None:
        own = e.note(WT, A, owned=True, commit=True)
        e.decision(WT, B if owned else None, "b-decision", commit=False)
        e.marker(A, own)
        rc, err = e.gate(A, "worktree")
        kind = "owned" if owned else "unowned (worktree: only)"
        check(rc == 0, f"A PASSES while B's {kind} decision is uncommitted (rc={rc})", err[-400:])
    _decision_false_block.__name__ = f"decision_false_block_{'owned' if _owned else 'unowned'}"
    scenario(_decision_false_block)


# ── 5: marker consumed -> identity from the note's own frontmatter ────────────
for _mode, _slug in MODES:
    def _retry_passes(e: Env, mode=_mode, slug=_slug) -> None:
        e.note(slug, A, owned=True, commit=True)
        e.note(slug, B, owned=True, commit=False)
        rc, err = e.gate(A, mode)
        check(rc == 0, f"[{mode}] marker gone: A PASSES on its own committed note (rc={rc})", err[-400:])

    def _retry_blocks(e: Env, mode=_mode, slug=_slug) -> None:
        own = e.note(slug, A, owned=True, commit=False)
        rc, err = e.gate(A, mode)
        check(rc == 2, f"[{mode}] marker gone: A's own uncommitted note still BLOCKS (rc={rc})", err[-400:])
        check(own.name in err, f"[{mode}] marker gone: the block names A's note", err[-400:])
    _retry_passes.__name__ = f"retry_passes_{_mode}"
    _retry_blocks.__name__ = f"retry_blocks_{_mode}"
    scenario(_retry_passes)
    scenario(_retry_blocks)


# ── 6 + 16: the close commit stages this session's decisions only ────────────
def end_hook_scopes_decisions(e: Env) -> None:
    own = e.note("main", A, owned=True)
    mine = e.decision("main", A, "a-decision")
    theirs = e.decision("main", B, "b-decision")
    untagged = e.decision("main", None, "hand-written")
    e.marker(A, own)
    e.end_hook(A)
    check(e.committed(own), "close commit includes A's session note")
    check(not e.committed(theirs), "close commit does NOT stage B's decision")
    check(e.committed(mine), "NEGATIVE CONTROL: close commit still stages A's own decision")
    check(e.committed(untagged), "FALLBACK: an untagged decision is staged as before")
scenario(end_hook_scopes_decisions)


def end_hook_leaves_others_index(e: Env) -> None:
    # B ran `git add` on its decision (its own commit then failed or raced).
    # A's close commit must not carry it.
    own = e.note("main", A, owned=True)
    theirs = e.decision("main", B, "b-staged")
    git(e.repo, "add", "--", str(theirs))
    e.marker(A, own)
    e.end_hook(A)
    check(e.committed(own), "close commit includes A's note while B has a file staged")
    check(not e.committed(theirs), "close commit does NOT carry a decision B already staged")
    staged = git(e.repo, "diff", "--cached", "--name-only")
    check(theirs.name in staged, "B's staged decision is left staged for B", staged)
scenario(end_hook_leaves_others_index)


# ── 7: the cascade tells the model to stamp decisions with this session ──────
def cascade_asks_for_owner(e: Env) -> None:
    lines = [json.dumps({"type": "user", "message": {"content": f"msg {i}"}}) for i in range(6)]
    e.transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = {"prompt": "ok bye", "session_id": A, "cwd": str(e.vault),
               "transcript_path": str(e.transcript)}
    env = e._env()
    env.pop("ANTHROPIC_API_KEY", None)
    r = subprocess.run([sys.executable, str(DETECT)], input=json.dumps(payload),
                       capture_output=True, text=True, env=env, cwd=str(e.vault),
                       timeout=60, **UTF8)
    try:
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    except Exception:
        ctx = r.stdout
    check("Decisions dir" in ctx, "detect-closing-signal emitted the full cascade", ctx[:300])
    check(f'session_id: "{A}"' in ctx,
          "the cascade asks for session_id in each decision's frontmatter", ctx[:600])
scenario(cascade_asks_for_owner)


# ── 8: owner lines with CRLF or a trailing comment ────────────────────────────
def gate_parses_crlf_and_comment(e: Env) -> None:
    own = e.note("main", A, owned=True, commit=True)
    crlf = e.decision("main", A, "a-crlf", newline="\r\n")
    commented = e.decision("main", A, "a-comment", owner_line=f'session_id: "{A}"  # me')
    e.marker(A, own)
    rc, err = e.gate(A, "main")
    check(rc == 2 and crlf.name in err,
          f"gate: A's own CRLF decision, uncommitted, BLOCKS (rc={rc})", err[-400:])
    check(commented.name in err,
          "gate: A's own decision with a trailing comment is flagged as A's", err[-600:])
scenario(gate_parses_crlf_and_comment)


def end_hook_parses_crlf_and_comment(e: Env) -> None:
    own = e.note("main", A, owned=True)
    crlf = e.decision("main", A, "a-crlf", newline="\r\n")
    commented = e.decision("main", A, "a-comment", owner_line=f'session_id: "{A}"  # me')
    bare = e.decision("main", A, "a-bare", owner_line=f"session_id: {A}")
    theirs = e.decision("main", B, "b-comment", owner_line=f"session_id: '{B}' # them")
    e.marker(A, own)
    e.end_hook(A)
    check(e.committed(crlf), "close commit stages A's CRLF decision")
    check(e.committed(commented), "close commit stages A's decision with a trailing comment")
    check(e.committed(bare), "close commit stages A's decision with an unquoted id")
    check(not e.committed(theirs), "close commit skips B's commented decision")
scenario(end_hook_parses_crlf_and_comment)


# ── 9: cp1252 stdio (a stock Windows console) ─────────────────────────────────
def end_hook_survives_cp1252(e: Env) -> None:
    own = e.note("main", A, owned=True)
    mine = e.decision("main", A, "a-decision")
    theirs = e.decision("main", B, "b-decision")
    e.marker(A, own)
    e.end_hook(A, PYTHONIOENCODING="cp1252")
    check(e.committed(mine), "cp1252 stdio: close commit still stages A's decision")
    check(not e.committed(theirs), "cp1252 stdio: close commit still skips B's decision")
scenario(end_hook_survives_cp1252)


# ── 10: trivial close ─────────────────────────────────────────────────────────
def trivial_close_not_blocked(e: Env) -> None:
    # A trivial session (<5 user messages) is told to SKIP the cascade, so its
    # marker names a note that is never built. Gating it would block a goodbye
    # the cascade itself said to give.
    own = e.sessions / f"{TODAY}T15-25-main-sessA1111.md"
    e.marker(A, own, trivial=True)
    rc, err = e.gate(A, "main")
    check(rc == 0, f"a trivial close (cascade skipped by design) is not blocked (rc={rc})", err[-400:])
scenario(trivial_close_not_blocked)


# ── 11: vault in a repo subdirectory ──────────────────────────────────────────
def subdir_vault_paths(e: Env) -> None:
    own = e.note("main", A, owned=True, commit=False)
    e.marker(A, own)
    rc, err = e.gate(A, "main")
    check(rc == 2, f"subdirectory vault: A's own uncommitted note BLOCKS (rc={rc})", err[-400:])
    check(f"{META}/Sessions/{own.name}" in err and "sub vault/" not in err,
          "subdirectory vault: block paths are relative to the vault", err[-400:])
scenario(subdir_vault_paths, vault_dir="sub vault")


# ── 12: VAULT_ROOT spelled in the wrong case ──────────────────────────────────
def _case_insensitive_fs() -> bool:
    probe = Path(tempfile.mkdtemp(prefix="CaseProbe-"))
    try:
        return Path(str(probe).replace("CaseProbe-", "caseprobe-")).exists()
    finally:
        shutil.rmtree(probe, ignore_errors=True)


def case_mismatch(e: Env) -> None:
    own = e.note("main", A, owned=True, commit=False)
    e.marker(A, own)
    rc, err = e.gate(A, "main")
    check(rc == 2, f"VAULT_ROOT in the wrong case: A's own uncommitted note BLOCKS (rc={rc})", err[-400:])


if _case_insensitive_fs():
    scenario(case_mismatch, vault_dir="casevault", vault_dir_on_disk="CaseVault")
else:
    print("SKIP: VAULT_ROOT case mismatch (case-sensitive filesystem)")


# ── 13 + 14 + 15: negative controls ───────────────────────────────────────────
def own_note_uncommitted(e: Env) -> None:
    own = e.note("main", A, owned=True, commit=False)
    other = e.note("main", B, owned=True, commit=False)
    e.marker(A, own)
    rc, err = e.gate(A, "main")
    check(rc == 2, f"NEGATIVE CONTROL: A's own uncommitted note BLOCKS (rc={rc})", err[-400:])
    check(own.name in err and other.name not in err,
          "NEGATIVE CONTROL: the block names A's note and not B's", err[-600:])
scenario(own_note_uncommitted)


def own_decision_uncommitted(e: Env) -> None:
    own = e.note("main", A, owned=True, commit=True)
    mine = e.decision("main", A, "a-decision", commit=False)
    e.marker(A, own)
    rc, err = e.gate(A, "main")
    check(rc == 2, f"NEGATIVE CONTROL: A's own uncommitted decision BLOCKS (rc={rc})", err[-400:])
    check(mine.name in err, "NEGATIVE CONTROL: the block names A's decision", err[-600:])
scenario(own_decision_uncommitted)


def clean_close_passes(e: Env) -> None:
    own = e.note("main", A, owned=True, commit=True)
    e.marker(A, own)
    rc, err = e.gate(A, "main")
    check(rc == 0, f"NEGATIVE CONTROL: a fully committed close PASSES (rc={rc})", err[-400:])
scenario(clean_close_passes)


# ── 17 + 18: nothing identifies the session -> unchanged behavior ────────────
def fallback_plain_skips(e: Env) -> None:
    e.note("main", B, owned=True, commit=False)  # another session's, not ours
    rc, err = e.gate(A, "main")
    check(rc == 0, f"FALLBACK: plain checkout, no marker, no owned note skips, as before (rc={rc})", err[-400:])
scenario(fallback_plain_skips)


def fallback_worktree_has_teeth(e: Env) -> None:
    rc, err = e.gate(A, "worktree")
    check(rc == 2, f"FALLBACK: worktree with no marker and no note BLOCKS, as before (rc={rc})", err[-400:])
scenario(fallback_worktree_has_teeth)


if failures:
    print(f"\n{len(failures)} assertion(s) failed")
    sys.exit(1)
print("\nAll close-gate session-scoping assertions passed")
