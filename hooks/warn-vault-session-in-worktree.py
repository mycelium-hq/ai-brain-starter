#!/usr/bin/env python3
"""LOUD tripwire: this session is running inside an Obsidian-vault git worktree.

The Claude Desktop app's per-session "worktree" checkbox creates a
`.claude/worktrees/<slug>/` checkout. On a CODE repo that is cheap and correct.
On an OBSIDIAN VAULT (repo-root == vault-root, thousands of files) that checkout
lands INSIDE Obsidian's watched file tree -> runaway CPU / RAM / crash, AND the
worktree can be silently archived/deleted mid-session, taking any worktree-only
files with it. A vault must run PLAIN (no worktree); code isolation belongs in a
sibling worktree on a CODE repo, never inside the vault.

There is no documented config switch to stop the Desktop app creating the
worktree, and a hook cannot un-create the worktree the session already started
in. But it CAN make the bad state LOUD on the first turn so you abort and
relaunch plain BEFORE the melt compounds and BEFORE anything is silently lost.
A plain (non-worktree) vault session never trips this.

Detection reads THREE independent channels; first hit wins. The `.obsidian/`
gate distinguishes a vault from a code repo in ALL THREE, so a code-repo worktree
(Desktop `.claude/worktrees/` on a code repo, or a sibling-dir `<repo>-<slug>/`
worktree) never fires.
  - Channel A (payload cwd): cwd is under a `.claude/worktrees/` segment. This is
    the terminal/CLI shape and the tool-time payloads (where the worktree cwd is
    reliably present).
  - Channel B (transcript marker): cwd is the main root; the worktree id is in
    transcript_path as `--claude-worktrees-<slug>` (Desktop SessionStart, when the
    marker is present).
  - Channel C (git ground truth, payload-INDEPENDENT): ask git -- from the hook's
    OWN process cwd AND the payload cwd -- for the working-tree root
    (`rev-parse --show-toplevel`). A linked worktree's toplevel carries the
    `/.claude/worktrees/` segment regardless of what the harness reported in the
    payload. This is the channel that catches the Desktop-SessionStart case where
    the harness delivers cwd=main AND a transcript_path with no marker, so A and B
    both go silent while git knows the truth.

Wiring (scripts/install-hooks-user-level.py + hooks.json): SessionStart (early)
PLUS UserPromptSubmit + PreToolUse(Bash) -- the tool-time events where the
worktree cwd is reliably present, so Channel A/C catch the Desktop-SessionStart
miss. A once-per-worktree-slug dedup sentinel means it warns ONCE per session,
not on every prompt/tool. Slugs are unique per Desktop worktree, so once-per-slug
== once-per-session.

Fail-open: any error -> silent continue (a nudge must never block a session).
Bypass: VAULT_WORKTREE_WARN_BYPASS=1.
Test knobs: VAULT_WORKTREE_WARN_NODEDUP=1 (skip dedup), VAULT_WORKTREE_WARN_STATE_DIR
(redirect the sentinel dir).

Canonical: ai-brain-starter/hooks/ (installed to ~/.claude/skills/ai-brain-starter/
hooks/ and wired into ~/.claude/settings.json by scripts/install-hooks-user-level.py).
Negative-control test: warn-vault-session-in-worktree.test.sh.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

WORKTREE_SEGMENT = "/.claude/worktrees/"
# Claude Code encodes the session cwd into the ~/.claude/projects/<dir> name by
# replacing path separators (and the leading dot of `.claude`) with dashes, so a
# worktree session's transcript path carries this literal marker -- WHEN the
# harness passes a worktree-rooted transcript_path (not guaranteed at SessionStart).
PROJECTS_WORKTREE_MARKER = "--claude-worktrees-"


def _silent() -> int:
    print(json.dumps({"continue": True, "suppressOutput": True}))
    return 0


def _read_payload() -> tuple[str, str]:
    """Hook stdin provides `cwd` + `transcript_path`. Returns ("", "") on anything odd."""
    cwd = ""
    transcript = ""
    try:
        raw = sys.stdin.read()
        if raw.strip():
            data = json.loads(raw)
            if isinstance(data, dict):
                cwd = data.get("cwd") or data.get("workingDirectory") or ""
                transcript = data.get("transcript_path") or data.get("transcriptPath") or ""
    except Exception:
        pass
    return cwd, transcript


def _git_toplevel(cwd: str) -> str:
    """`git rev-parse --show-toplevel` from `cwd`; "" on any failure. Bounded (2s)."""
    if not cwd:
        return ""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return ""


def _detect(payload_cwd: str, transcript: str) -> tuple[str, Path] | tuple[None, None]:
    """(worktree_path, main_root) if a worktree session on any channel, else (None, None).

    The `.obsidian/` vault gate is applied by the caller, not here.
    """
    # Channel A -- any payload cwd that contains the worktree segment.
    if payload_cwd and WORKTREE_SEGMENT in payload_cwd:
        return payload_cwd, Path(payload_cwd[: payload_cwd.index(WORKTREE_SEGMENT)])

    # Channel B -- transcript marker (Desktop mode, when the marker is present).
    if payload_cwd and transcript and PROJECTS_WORKTREE_MARKER in transcript:
        slug = transcript.split(PROJECTS_WORKTREE_MARKER, 1)[1].split("/", 1)[0]
        if slug:
            return str(Path(payload_cwd) / ".claude" / "worktrees" / slug), Path(payload_cwd)

    # Channel C -- git ground truth, payload-INDEPENDENT. Ask git from the hook's
    # own process cwd AND the payload cwd (either may be the worktree even when the
    # other is reported as main). Catches the Desktop-SessionStart miss.
    try:
        proc_cwd = os.getcwd()
    except OSError:
        proc_cwd = ""
    for gcwd in dict.fromkeys([proc_cwd, payload_cwd]):  # de-dup, preserve order
        toplevel = _git_toplevel(gcwd)
        if toplevel and WORKTREE_SEGMENT in toplevel:
            return toplevel, Path(toplevel[: toplevel.index(WORKTREE_SEGMENT)])

    return None, None


def _already_warned(slug: str) -> bool:
    """Once-per-worktree-slug dedup so the re-firing events (UserPromptSubmit each
    turn / every Bash) warn ONCE. Slugs are unique per Desktop worktree, so
    once-per-slug == once-per-session. Stale sentinels for archived worktrees are
    harmless (a slug never recurs)."""
    if os.environ.get("VAULT_WORKTREE_WARN_NODEDUP") == "1":
        return False
    state_dir = os.environ.get("VAULT_WORKTREE_WARN_STATE_DIR") or tempfile.gettempdir()
    sentinel = Path(state_dir) / f".vault-worktree-warned-{slug}"
    try:
        if sentinel.exists():
            return True
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.touch()
    except OSError:
        pass  # fail-open: if we cannot record, warn (better loud than silent)
    return False


def main() -> int:
    if os.environ.get("VAULT_WORKTREE_WARN_BYPASS") == "1":
        return _silent()

    payload_cwd, transcript = _read_payload()
    worktree_path, main_root = _detect(payload_cwd, transcript)
    if worktree_path is None:
        return _silent()  # not a worktree session on any channel

    try:
        is_vault = (main_root / ".obsidian").is_dir()
    except OSError:
        return _silent()
    if not is_vault:
        return _silent()  # a code-repo worktree -- cheap + correct, not the melt

    slug = Path(worktree_path).name
    if _already_warned(slug):
        return _silent()  # already warned this worktree -- do not nag every turn

    body = (
        "SURFACE THIS TO THE USER IMMEDIATELY, before any other work:\n\n"
        "🛑 [vault-worktree] This vault session is running INSIDE a git worktree:\n"
        f"    {worktree_path}\n\n"
        "An Obsidian vault must NEVER run in worktree mode. The Desktop app's\n"
        "per-session worktree checkbox created a multi-thousand-file checkout inside\n"
        "Obsidian's watched tree → runaway CPU / RAM / crash, AND this worktree can\n"
        "be SILENTLY DELETED mid-session, taking any worktree-only files with it.\n\n"
        "DO THIS NOW:\n"
        "  1. Close this session.\n"
        f"  2. Relaunch the vault PLAIN: `cd {main_root} && claude`\n"
        "     (or, in the Desktop app, open the vault with the worktree box UNCHECKED).\n\n"
        "UNTIL YOU DO: any file created that lives ONLY in this worktree is discarded\n"
        f"when the worktree is archived. Edit shared/canonical files at the MAIN vault\n"
        f"path ({main_root}/...) and commit them there — never the worktree path. The\n"
        "Stop-hook snapshot net backstops divergent files, but the only safe state is a\n"
        "plain (non-worktree) vault session.\n\n"
        "Bypass this warning: VAULT_WORKTREE_WARN_BYPASS=1"
    )
    print(json.dumps({"continue": True, "additionalContext": body}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail-open: never let a nudge crash a session start / tool call.
        try:
            print(json.dumps({"continue": True, "suppressOutput": True}))
        except Exception:
            pass
        sys.exit(0)
