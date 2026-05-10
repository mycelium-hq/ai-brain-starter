"""v0.5 smoke tests for the auto-trigger hooks.

The hooks shell out to scripts that import health-mcp modules. We don't run
the hooks end-to-end (would require real Oura/Fitbit credentials). We test:
  - The Python files compile cleanly (no syntax errors)
  - The fallback paths emit valid JSON to stdout
  - The bypass env var short-circuits
  - The hook files exist at the expected locations
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK_AUTO_SYNC = REPO_ROOT / "hooks" / "health-auto-sync.py"
HOOK_AUTO_COACH = REPO_ROOT / "hooks" / "coach-auto-prescribe-on-journal.py"
HOOKS_JSON = REPO_ROOT / "hooks.json"
DOCTOR_SKILL = REPO_ROOT / "skills" / "health-doctor" / "SKILL.md"
AUTOMATION_DOC = REPO_ROOT / "docs" / "AUTOMATION.md"


def test_hook_files_exist():
    assert HOOK_AUTO_SYNC.is_file(), f"missing {HOOK_AUTO_SYNC}"
    assert HOOK_AUTO_COACH.is_file(), f"missing {HOOK_AUTO_COACH}"


def test_hooks_compile_clean():
    for hook in (HOOK_AUTO_SYNC, HOOK_AUTO_COACH):
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", str(hook)],
            capture_output=True, text=True, check=False, timeout=10,
        )
        assert proc.returncode == 0, f"{hook.name} did not compile: {proc.stderr}"


def test_auto_sync_bypass_emits_silent_json():
    env = {**os.environ, "HEALTH_AUTO_SYNC_BYPASS": "1"}
    proc = subprocess.run(
        [sys.executable, str(HOOK_AUTO_SYNC)],
        capture_output=True, text=True, env=env, check=False, timeout=10,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data.get("continue") is True
    assert data.get("suppressOutput") is True


def test_auto_coach_bypass_emits_silent_json():
    env = {**os.environ, "COACH_AUTO_PRESCRIBE_BYPASS": "1"}
    proc = subprocess.run(
        [sys.executable, str(HOOK_AUTO_COACH)],
        capture_output=True, text=True, env=env, check=False, timeout=10,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data.get("continue") is True
    assert data.get("suppressOutput") is True


def test_auto_sync_no_env_credentials_emits_silent():
    """Without OURA_PERSONAL_ACCESS_TOKEN or FITBIT_ACCESS_TOKEN, exit silently."""
    env = {k: v for k, v in os.environ.items()
           if k not in {"OURA_PERSONAL_ACCESS_TOKEN", "OURA_PAT", "FITBIT_ACCESS_TOKEN"}}
    env.pop("HEALTH_AUTO_SYNC_BYPASS", None)
    proc = subprocess.run(
        [sys.executable, str(HOOK_AUTO_SYNC)],
        capture_output=True, text=True, env=env, check=False, timeout=15,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data.get("continue") is True


def test_auto_coach_no_profile_emits_silent():
    """Without VAULT_ROOT/Meta/coach-profile.yaml, exit silently."""
    env = {k: v for k, v in os.environ.items()
           if k not in {"VAULT_ROOT", "COACH_AUTO_PRESCRIBE_BYPASS"}}
    proc = subprocess.run(
        [sys.executable, str(HOOK_AUTO_COACH)],
        capture_output=True, text=True, env=env, check=False, timeout=15,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data.get("continue") is True


def test_hooks_json_includes_journal_chain_hook():
    """hooks.json template wires the Stop-on-journal hook as the single
    daily-once entry point (codified 2026-05-10 after per-SessionStart
    firing was flagged as wasteful for users with ~20 sessions/day).

    The SessionStart sync hook stays in the repo as an OPT-IN power-user
    file but is NOT wired by default.
    """
    text = HOOKS_JSON.read_text(encoding="utf-8")
    data = json.loads(text)
    stops = data.get("hooks", {}).get("Stop", [])
    stop_blob = json.dumps(stops)
    assert "coach-auto-prescribe-on-journal.py" in stop_blob
    # SessionStart should NOT include health-auto-sync.py by default
    # (would fire on every session — over-firing for ~20 sessions/day users).
    session_starts = data.get("hooks", {}).get("SessionStart", [])
    session_blob = json.dumps(session_starts)
    assert "health-auto-sync.py" not in session_blob, (
        "health-auto-sync.py should NOT be wired in SessionStart by default. "
        "It's available as an opt-in for users who want per-session sync, "
        "but the default chain fires on /journal Stop only."
    )


def test_health_doctor_skill_exists():
    assert DOCTOR_SKILL.is_file()
    text = DOCTOR_SKILL.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "name: health-doctor" in text


def test_automation_doc_exists():
    assert AUTOMATION_DOC.is_file()
    text = AUTOMATION_DOC.read_text(encoding="utf-8")
    assert "Auto-trigger" in text or "auto-trigger" in text
    assert "Bainbridge" in text  # The dissent-integration anchor must remain documented


def test_doctor_skill_lists_six_sections():
    """The /health doctor skill must enumerate the six observability sections."""
    text = DOCTOR_SKILL.read_text(encoding="utf-8")
    for section in [
        "Data freshness", "Last prescription", "Auto-trigger hooks",
        "Coach profile", "Lab status flags", "Cycle phase",
    ]:
        assert section in text, f"missing section '{section}' in /health doctor skill"


def test_auto_sync_output_is_valid_json_under_failure():
    """Even when the hook hits an unexpected condition, it must emit valid JSON
    (Claude Code blocks the prompt on invalid hook output)."""
    env = {**os.environ}
    env.pop("HEALTH_AUTO_SYNC_BYPASS", None)
    env["HEALTH_MCP_DB"] = "/tmp/nonexistent-health-mcp-test.duckdb"
    proc = subprocess.run(
        [sys.executable, str(HOOK_AUTO_SYNC)],
        capture_output=True, text=True, env=env, check=False, timeout=15,
    )
    assert proc.returncode == 0
    # Output should be valid JSON
    json.loads(proc.stdout)


def test_auto_coach_output_is_valid_json_under_failure():
    env = {**os.environ}
    env.pop("COACH_AUTO_PRESCRIBE_BYPASS", None)
    env["VAULT_ROOT"] = "/tmp/nonexistent-vault"
    proc = subprocess.run(
        [sys.executable, str(HOOK_AUTO_COACH)],
        capture_output=True, text=True, env=env, check=False, timeout=15,
    )
    assert proc.returncode == 0
    json.loads(proc.stdout)
