#!/usr/bin/env python3
"""A close in a shared vault never files the member's journal seeds there (tickets#5721).

Journal seeds are the member's own words: feelings, reflections on their life
or work. The close used to append them to the Captures file of whatever vault
the session ran in, so a session in a team vault put them in the team's brain,
where teammates read it, and the member's next journal never saw them.

Assertions, each on the REAL cascade text and session shell the hook builds:
  1. The member's own vault (it holds the journal config) closes exactly as
     before: seeds go to its Captures (NEGATIVE CONTROL).
  2. A team vault that declares its own close, with the member's personal
     vault named by $VAULT_ROOT: seeds go to the personal vault's Session
     Captures, tagged [emotional]; the team vault is never named as their home,
     and its session shell does not invite them.
  3. Same, with $VAULT_ROOT unset: the one vault on the machine that holds a
     journal config is found and used.
  4. A team vault with no personal vault findable: seeds are written nowhere
     and shown to the member instead.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "detect_closing_signal", HOOKS / "detect-closing-signal.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

failures = []
OLD_STEP = "Append journal seeds to Captures."


def make_vault(root: Path, name: str, *, team: bool, journals: bool) -> Path:
    vault = root / name
    meta = vault / "Meta"
    (meta / "Sessions").mkdir(parents=True)
    (meta / "Decisions").mkdir()
    if team:  # a separate vault that owns its close, the way a team vault does
        (vault / "CLAUDE.md").write_text("# Team\n\n## Session End\n", encoding="utf-8")
    if journals:
        (meta / "journal-config.md").write_text("---\n---\n", encoding="utf-8")
    return vault


def close(cwd: Path, env_vault: str | None) -> tuple[str, str]:
    """(cascade text, session shell text) for a close fired from `cwd`."""
    vault = mod.resolve_vault_root(cwd, env_vault)
    meta = mod.find_meta_dir(vault)
    seeds = mod.journal_seeds_destination(cwd, vault, env_vault)
    shell = mod.pre_build_session_shell(
        meta / "Sessions", "2026-11-06T18-00", "main", "2026-11-06 18:00",
        "s1", seeds_elsewhere=seeds[0] != mod.SEEDS_HERE,
    ).read_text(encoding="utf-8")
    text = mod.build_injected_context(
        confidence="high", matched="bye", timestamp_human="2026-11-06 18:00",
        timestamp_file="2026-11-06T18-00", worktree="main", vault_root=vault,
        meta_dir=meta, session_file=meta / "Sessions" / "s.md",
        decisions_dir=meta / "Decisions", captures_file=meta / "Session Captures.md",
        pending_outcomes=[], is_trivial=False, is_ambiguous=False,
        journal_seeds=seeds,
    )
    return text, shell


def check_team_close(text: str, shell: str, personal: Path, label: str) -> None:
    dest = personal / "Meta" / "Session Captures.md"
    if f"Journal seeds:    {dest}" not in text:
        failures.append(f"{label}: seeds were not sent to the personal vault ({dest})")
    if OLD_STEP in text:
        failures.append(f"{label}: the team vault was still told to take the journal seeds")
    if "[emotional]" not in text.split("PHASE 2", 1)[-1]:
        failures.append(f"{label}: routed seeds are not tagged [emotional], so /journal would drop them")
    if "When unsure whether something" not in text:
        failures.append(f"{label}: no rule to keep an unsure or mixed message out of the team vault")
    if "Journal seeds (verbatim)" in shell:
        failures.append(f"{label}: the team vault's session file still invites journal seeds")


real_home = os.environ.get("HOME")
with tempfile.TemporaryDirectory() as tmp:
    home = Path(tmp).resolve()
    os.environ["HOME"] = str(home)  # Path.home() bounds the vault walk-up and search
    try:
        personal = make_vault(home, "notes", team=False, journals=True)
        team = make_vault(home, "team", team=True, journals=False)

        # 1. Own vault: unchanged.
        text, shell = close(personal, str(personal))
        if OLD_STEP not in text or "Journal seeds:    " in text:
            failures.append("own vault: the close no longer files seeds in the member's own Captures")
        if "Journal seeds (verbatim)" not in shell:
            failures.append("own vault: the session shell changed")

        # 2. Team vault, personal vault named by VAULT_ROOT.
        text, shell = close(team, str(personal))
        check_team_close(text, shell, personal, "team vault + VAULT_ROOT")

        # 3. Team vault, VAULT_ROOT unset: the one journaling vault is found.
        text, shell = close(team, None)
        check_team_close(text, shell, personal, "team vault, no VAULT_ROOT")

        # 4. No findable personal vault: held, written nowhere.
        (personal / "Meta" / "journal-config.md").unlink()
        text, _ = close(team, None)
        if "Write journal seeds NOWHERE" not in text:
            failures.append("no personal vault: seeds were not held back")
        if OLD_STEP in text:
            failures.append("no personal vault: the team vault was told to take the seeds")
    finally:
        if real_home is not None:
            os.environ["HOME"] = real_home

if failures:
    print("FAILED — a close can file a member's personal reflections in a shared vault:")
    for f in failures:
        print(f"  ✗ {f}")
    sys.exit(1)
print("OK - own vault unchanged; a shared vault's journal seeds go to the personal vault or nowhere")
