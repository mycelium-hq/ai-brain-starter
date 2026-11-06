#!/usr/bin/env python3
"""A close files each thing in the workspace it belongs to, and asks when unsure (tickets#964).

The close used to file everything said in a session into the vault the session
ran in. Another company's work said in one company's vault went into that
company's brain; a company's work said in the member's personal vault never
reached the company. Assertions, each on the REAL text the hook builds:
  1. A member with one vault, working in it: the close is unchanged
     (NEGATIVE CONTROL: no routing text at all).
  2. A team vault, with the personal vault and a second team vault on the
     computer: the close names the personal brain (its to-dos, About Me), the
     other workspace's files, and holds unclear items in the PERSONAL vault,
     never the team vault.
  3. The personal vault, with a team vault on the computer: the team vault is
     listed, held items stay in the personal vault, and the member is asked.
  4. Two copies of one workspace (same git origin): never written into, and
     both folders are named so the member can remove one.
     The same holds when one copy's remote is https and the other's ssh, and
     when a copy has no git remote but the same workspace name.
  5. A second copy of the session's own vault is not "another workspace",
     whether it shares the remote or only the workspace name.
  6. `workspace:` in a vault's CLAUDE.md frontmatter names its workspace.
  9. The member is asked BEFORE anything is written, and the team broadcast
     never posts to another workspace without a yes.
  10. A vault with an unreadable git pointer never breaks the close.
  7. No personal vault found: held items go nowhere but the close summary.
  8. main() end to end: the injected close carries the routing rule.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS))
spec = importlib.util.spec_from_file_location(
    "detect_closing_signal", HOOKS / "detect-closing-signal.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

failures = []
RULE = "Where each thing goes."


def make_vault(root: Path, name: str, *, team: bool, origin: str = "",
               workspace: str = "") -> Path:
    vault = root / name
    meta = vault / "Meta"
    (meta / "Sessions").mkdir(parents=True)
    (meta / "Decisions").mkdir()
    if team:  # a separate vault that owns its close, the way a team vault does
        front = f"---\nworkspace: {workspace}\n---\n" if workspace else ""
        (vault / "CLAUDE.md").write_text(front + "# Team\n\n## Session End\n", encoding="utf-8")
    else:
        (meta / "journal-config.md").write_text("---\n---\n", encoding="utf-8")
        (meta / "About Me.md").write_text("# About me\n", encoding="utf-8")
        (vault / "To do.md").write_text("- [ ] x\n", encoding="utf-8")
    if origin:
        (vault / ".git").mkdir()
        (vault / ".git" / "config").write_text(
            f'[core]\n\tbare = false\n[remote "origin"]\n\turl = {origin}\n', encoding="utf-8")
    return vault


def close(vault: Path) -> str:
    meta = mod.find_meta_dir(vault)
    seeds = mod.journal_seeds_destination(vault, vault, None)
    return mod.build_injected_context(
        confidence="high", matched="bye", timestamp_human="2026-11-06 18:00",
        timestamp_file="2026-11-06T18-00", worktree="main", vault_root=vault,
        meta_dir=meta, session_file=meta / "Sessions" / "s.md",
        decisions_dir=meta / "Decisions", captures_file=meta / "Session Captures.md",
        pending_outcomes=[], is_trivial=False, is_ambiguous=False,
        journal_seeds=seeds, others=mod.other_workspaces(vault),
    )


def needs_a_home(text: str) -> str:
    line = next((l for l in text.splitlines() if l.strip().startswith("Needs a home:")), "")
    return line.split(":", 1)[1].strip() if line else ""


saved_env = dict(os.environ)
try:
    # 1. One vault, working in it.
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp).resolve()
        os.environ["HOME"] = str(home)
        os.environ["USERPROFILE"] = str(home)  # Path.home() on Windows
        os.environ.pop("VAULT_ROOT", None)
        solo = make_vault(home, "notes", team=False)
        text = close(solo)
        if RULE in text or "Other workspace:" in text or "Needs a home" in text:
            failures.append("one vault: the close changed for a member with nothing to route")

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp).resolve()
        os.environ["HOME"] = str(home)
        os.environ["USERPROFILE"] = str(home)  # Path.home() on Windows
        personal = make_vault(home, "notes", team=False)
        alpha = make_vault(home, "alpha", team=True, origin="https://example.com/a/alpha.git")
        beta = make_vault(home, "beta", team=True, origin="git@example.com:b/beta",
                          workspace="Beta Co")

        # 2. A team vault session.
        text = close(alpha)
        if RULE not in text:
            failures.append("team vault: no rule says where each thing goes")
        if f"Personal brain:   {personal}" not in text or "About Me:" not in text:
            failures.append("team vault: the personal brain (to-dos, About Me) is not named")
        if f"Other workspace:  Beta Co: {beta}" not in text:
            failures.append("team vault: the other workspace is not listed with its vault")
        if not needs_a_home(text).startswith(str(personal)):
            failures.append(f"team vault: held items do not go to the personal vault ({needs_a_home(text)})")
        if "Add these to <name>?" not in text or "Where does this go?" not in text:
            failures.append("team vault: the member is never asked")
        # 9. Asked before the writes, and no broadcast elsewhere without a yes.
        if "ASK BEFORE PHASE 2" not in text or "WAIT for the answer" not in text:
            failures.append("team vault: the question is not asked before the writes")
        if "Phase 1.8 posts only to this workspace" not in text:
            failures.append("team vault: the team broadcast can still post to another workspace")
        if "committed in ITS vault" not in text:
            failures.append("team vault: writes outside this vault are left uncommitted")

        # 3. A personal vault session.
        text = close(personal)
        if f"Other workspace:  alpha: {alpha}" not in text:
            failures.append("personal vault: a team vault on the computer is not listed")
        if not needs_a_home(text).startswith(str(personal)):
            failures.append("personal vault: held items do not stay in the personal vault")
        if "Only the member's own things are filed in this personal vault." not in text:
            failures.append("personal vault: company work is still filed here")

        # 4. Two copies of one workspace.
        alpha2 = make_vault(home, "alpha-copy", team=True, origin="git@example.com:a/alpha.git")
        alpha3 = make_vault(home, "alpha-old", team=True, workspace="alpha")  # no remote
        text = close(personal)
        line = next((l for l in text.splitlines() if l.startswith("  Other workspace:  alpha")), "")
        if "its Captures:" in text.split("Other workspace:  Beta Co", 1)[0] or "never" not in line:
            failures.append("two copies: a copy was still offered as a place to write")
        if not all(str(v) in text for v in (alpha, alpha2, alpha3)):
            failures.append("two copies: the member is not told which folders they are")

        # 5. A copy of the session's own vault.
        text = close(alpha)
        if "Other workspace:  alpha" in text:
            failures.append("own copy: a second copy of this vault was listed as another workspace")

        # 10. An unreadable git pointer.
        odd = make_vault(home, "odd", team=True)
        gitdir = home / "odd-gitdir"
        gitdir.mkdir()
        (gitdir / "commondir").write_bytes(b"\xff\xfe..\n")  # not UTF-8
        (odd / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
        try:
            mod.other_workspaces(personal)
            close(personal)
        except Exception as exc:
            failures.append(f"odd git pointer: the close crashed ({exc!r})")

        # 6. `workspace:` names it (checked in 2: "Beta Co", not "beta").

        # 8. main() end to end.
        payload = json.dumps({"prompt": "bye", "session_id": "t", "cwd": str(beta)})
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(payload)
            buf = io.StringIO()
            with redirect_stdout(buf):
                mod.main()
        finally:
            sys.stdin = old_stdin
        out = buf.getvalue()
        if RULE not in out or "This workspace:   Beta Co" not in out:
            failures.append("main(): the injected close carries no routing rule")
        for p in (beta / "Meta" / "Sessions").glob("*.md"):
            p.unlink()

    # 7. No personal vault.
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp).resolve()
        os.environ["HOME"] = str(home)
        os.environ["USERPROFILE"] = str(home)  # Path.home() on Windows
        alpha = make_vault(home, "alpha", team=True)
        text = close(alpha)
        if "hold in the close summary only" not in text or "written NOWHERE" not in text:
            failures.append("no personal vault: held items were given somewhere to be written")
        if str(alpha) in needs_a_home(text):
            failures.append("no personal vault: held items were put in the team vault")
finally:
    os.environ.clear()
    os.environ.update(saved_env)

if failures:
    print("FAIL")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("OK - each thing goes to its workspace; anything for another workspace or unclear is held and asked")
