#!/usr/bin/env python3
"""A close in a shared vault never files the member's journal seeds there (tickets#5721).

Journal seeds are the member's own words: feelings, reflections on their life
or work. The close used to append them to the Captures file of whatever vault
the session ran in, so a session in a team vault put them in the team's brain,
where teammates read it, and the member's next journal never saw them.

The only proof a vault is the member's own is the journal config /journal
keeps in it. Assertions, each on the REAL text and session shell the hook builds:
  1. Own vault (holds the config): closes exactly as before (NEGATIVE CONTROL).
  2. A team vault, personal vault named by $VAULT_ROOT: seeds go to the personal
     vault's Session Captures, tagged [emotional]; the team shell doesn't ask.
  3. Same with $VAULT_ROOT unset: the one vault with a config is found.
  4. $VAULT_ROOT names ANOTHER shared vault (Meta, no config): never used.
  5. A team vault that does not declare its own close, and $VAULT_ROOT set to
     the team vault itself: seeds still go to the personal vault.
  6. Two vaults with a config, or none while in a team vault: held, shown.
  7. A brand-new member (no config anywhere) in their default vault: as before.
  8. main() end to end: the injected context names the personal vault.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
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
OLD_STEP = "Append journal seeds to Captures."
HELD = "Write journal seeds NOWHERE"


def make_vault(root: Path, name: str, *, declares: bool, journals: bool) -> Path:
    vault = root / name
    meta = vault / "Meta"
    (meta / "Sessions").mkdir(parents=True)
    (meta / "Decisions").mkdir()
    if declares:  # a separate vault that owns its close, the way a team vault can
        (vault / "CLAUDE.md").write_text("# Team\n\n## Session End\n", encoding="utf-8")
    if journals:
        (meta / "journal-config.md").write_text("---\n---\n", encoding="utf-8")
    return vault


def close(cwd: Path, env_vault: Path | None) -> tuple[str, str]:
    """(cascade text, session shell text) for a close fired from `cwd`."""
    env = str(env_vault) if env_vault else None
    vault = mod.resolve_vault_root(cwd, env)
    meta = mod.find_meta_dir(vault)
    seeds = mod.journal_seeds_destination(cwd, vault, env)
    shell_path = mod.pre_build_session_shell(
        meta / "Sessions", "2026-11-06T18-00", "main", "2026-11-06 18:00",
        "s1", seeds_elsewhere=seeds[0] != mod.SEEDS_HERE,
    )
    shell = shell_path.read_text(encoding="utf-8")
    shell_path.unlink()
    text = mod.build_injected_context(
        confidence="high", matched="bye", timestamp_human="2026-11-06 18:00",
        timestamp_file="2026-11-06T18-00", worktree="main", vault_root=vault,
        meta_dir=meta, session_file=meta / "Sessions" / "s.md",
        decisions_dir=meta / "Decisions", captures_file=meta / "Session Captures.md",
        pending_outcomes=[], is_trivial=False, is_ambiguous=False,
        journal_seeds=seeds,
    )
    return text, shell


def expect_personal(text: str, shell: str, personal: Path, label: str) -> None:
    dest = personal / "Meta" / "Session Captures.md"
    if f"Journal seeds:    {dest}" not in text:
        failures.append(f"{label}: seeds were not sent to the personal vault")
    if OLD_STEP in text:
        failures.append(f"{label}: the shared vault was still told to take the seeds")
    if "[emotional]" not in text.split("PHASE 2", 1)[-1]:
        failures.append(f"{label}: routed seeds are not tagged [emotional], so /journal would drop them")
    if "When unsure whether something" not in text:
        failures.append(f"{label}: no rule keeps an unsure or mixed message out of the shared vault")
    if "Journal seeds (verbatim)" in shell:
        failures.append(f"{label}: the shared vault's session file still asks for journal seeds")


def expect_held(text: str, label: str) -> None:
    if HELD not in text or OLD_STEP in text or "Journal seeds:    /" in text:
        failures.append(f"{label}: seeds were not held back from every vault")


def run_main(cwd: Path, env_vault: Path) -> str:
    payload = json.dumps({"prompt": "bye", "session_id": "t", "cwd": str(cwd)})
    old_stdin = sys.stdin
    try:
        sys.stdin = io.StringIO(payload)
        os.environ["VAULT_ROOT"] = str(env_vault)
        buf = io.StringIO()
        with redirect_stdout(buf):
            mod.main()
        return buf.getvalue()
    finally:
        sys.stdin = old_stdin


saved_env = {k: os.environ.get(k) for k in ("HOME", "VAULT_ROOT")}
with tempfile.TemporaryDirectory() as tmp:
    home = Path(tmp).resolve()
    os.environ["HOME"] = str(home)  # Path.home() bounds the walk-up and the search
    os.environ.pop("VAULT_ROOT", None)
    try:
        personal = make_vault(home, "notes", declares=False, journals=True)
        team = make_vault(home, "team", declares=True, journals=False)
        client = make_vault(home, "client", declares=False, journals=False)
        loose_team = make_vault(home, "shared", declares=False, journals=False)

        # 1. Own vault: unchanged.
        text, shell = close(personal, personal)
        if OLD_STEP not in text or "Journal seeds:    " in text:
            failures.append("own vault: seeds no longer go to the member's own Captures")
        if "Journal seeds (verbatim)" not in shell:
            failures.append("own vault: the session shell changed")

        # 2-3. Team vault, with and without VAULT_ROOT.
        expect_personal(*close(team, personal), personal, "team vault + VAULT_ROOT")
        expect_personal(*close(team, None), personal, "team vault, no VAULT_ROOT")

        # 4. VAULT_ROOT names another shared vault: never trusted.
        expect_personal(*close(team, client), personal, "VAULT_ROOT is another client's vault")

        # 5. Undeclared shared vault, and VAULT_ROOT set to it.
        expect_personal(*close(loose_team, loose_team), personal, "undeclared shared vault as VAULT_ROOT")
        expect_personal(*close(team, team), personal, "VAULT_ROOT is the team vault itself")

        # 8. main() end to end.
        out = run_main(team, personal)
        try:
            ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        except (ValueError, KeyError, TypeError):
            ctx = ""
        if f"Journal seeds:    {personal / 'Meta' / 'Session Captures.md'}" not in ctx:
            failures.append("main(): the injected close does not send seeds to the personal vault")
        os.environ.pop("VAULT_ROOT", None)

        # 6. Two vaults with a config: ambiguous, held.
        other = make_vault(home, "other-notes", declares=False, journals=True)
        expect_held(close(team, None)[0], "two journaling vaults")
        expect_held(close(team, client)[0], "two journaling vaults + VAULT_ROOT is a client vault")
        shutil.rmtree(other)

        # 6/7. No config anywhere.
        (personal / "Meta" / "journal-config.md").unlink()
        expect_held(close(team, None)[0], "no personal vault, team vault")
        text, _ = close(personal, personal)
        if OLD_STEP not in text:
            failures.append("new member's own default vault: seeds no longer saved there")
    finally:
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

if failures:
    print("FAILED — a close can file a member's personal reflections in a shared vault:")
    for f in failures:
        print(f"  ✗ {f}")
    sys.exit(1)
print("OK - own vault unchanged; a shared vault's journal seeds go to the personal vault or nowhere")
