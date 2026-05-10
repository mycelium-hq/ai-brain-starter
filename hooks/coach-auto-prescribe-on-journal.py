#!/usr/bin/env python3
"""Stop hook: after a journal session, silently prescribe today's workout
(if not yet prescribed) AND backfill yesterday's journal with body-track
context.

The chain Bainbridge approved (panel 2026-05-10): auto-trigger the
ANALYSIS, never auto-trigger the ACTION. This hook prepares the workout +
drops it to the user's calendar (if profile.calendar_drop is set), but
NEVER auto-logs completion. Completion remains explicit via /coach log.

When this fires:
  - Stop hook, matcher: tool_name matches one of {daily-journal, journal}
    or the assistant just wrote a file under [VAULT]/Journals/ for today

What it does:
  1. Find today's coach prescription via health_coach_recent_prescriptions.
     If today already has one, skip.
  2. If no prescription, call health_coach_prescribe with the saved profile.
  3. If profile.calendar_drop is true and google-workspace MCP is connected,
     drop the workout to calendar at preferred_workout_clock. (Hook can't
     directly call other MCPs; surfaces the request as additionalContext
     for Claude to action on next turn.)
  4. Trigger backfill-journal-body-context script for yesterday's entry
     ONLY (not the whole year — that's the one-time backfill skill).

Failure modes:
  - No coach profile saved -> skip silently (user hasn't run /coach yet)
  - health-mcp missing -> skip silently
  - DuckDB locked -> skip silently (next stop tries again)

Bypass: COACH_AUTO_PRESCRIBE_BYPASS=1 in env.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


def _find_health_mcp() -> Path | None:
    for p in (
        Path.home() / ".claude" / "health-mcp",
        Path.home() / "dev" / "ai-brain-starter" / "services" / "health-mcp",
    ):
        if p.is_dir() and (p / "main.py").exists():
            return p
    return None


def _find_repo_root() -> Path | None:
    """Find the ai-brain-starter clone for the backfill script path."""
    for p in (
        Path.home() / "dev" / "ai-brain-starter",
        Path.home() / ".claude" / "skills" / "ai-brain-starter",
    ):
        if p.is_dir() and (p / "scripts" / "backfill-journal-body-context.py").is_file():
            return p
    return None


def _read_profile() -> dict | None:
    """Read coach-profile.yaml from VAULT_ROOT/Meta/coach-profile.yaml."""
    vroot = os.environ.get("VAULT_ROOT")
    if not vroot:
        return None
    candidates = [
        Path(vroot) / "Meta" / "coach-profile.yaml",
        Path(vroot) / "⚙️ Meta" / "coach-profile.yaml",
    ]
    for path in candidates:
        if path.is_file():
            try:
                import yaml
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                if text.startswith("---"):
                    parts = text.split("---", 2)
                    if len(parts) >= 3:
                        return yaml.safe_load(parts[1]) or {}
                return yaml.safe_load(text) or {}
            except Exception:
                return None
    return None


def _emit_silent() -> None:
    print(json.dumps({"continue": True, "suppressOutput": True}))


def _emit_context(line: str) -> None:
    print(json.dumps({
        "continue": True,
        "suppressOutput": False,
        "hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": f"[coach-auto] {line}"},
    }))


def main() -> int:
    if os.environ.get("COACH_AUTO_PRESCRIBE_BYPASS") == "1":
        _emit_silent()
        return 0

    profile = _read_profile()
    if not profile:
        _emit_silent()
        return 0

    health_mcp = _find_health_mcp()
    if not health_mcp:
        _emit_silent()
        return 0

    sys.path.insert(0, str(health_mcp))
    venv_site = health_mcp / ".venv" / "lib"
    if venv_site.is_dir():
        for py_dir in venv_site.glob("python*/site-packages"):
            sys.path.insert(0, str(py_dir))

    try:
        import db
        import coach as coach_mod
        import scores
        import cycle as cycle_mod
    except Exception:
        _emit_silent()
        return 0

    today = date.today()
    summary_parts: list[str] = []

    # 1. Has today already been prescribed?
    try:
        with db.connect(read_only=True) as con:
            row = con.execute(
                "SELECT prescription_id FROM coach_prescriptions WHERE prescribed_for = ? LIMIT 1",
                [today],
            ).fetchone()
        already_prescribed = bool(row)
    except Exception:
        already_prescribed = True  # Don't double-prescribe on error

    if not already_prescribed:
        try:
            with db.connect() as con:
                recovery = scores.recovery_score(con, today)
                sleep_s = scores.sleep_score(con, today)
                cycle_ctx = cycle_mod.cycle_context(con, today)
                if cycle_ctx.get("phase") == "unknown":
                    cycle_ctx = None
                somatic = scores.somatic_state(con, today, lookback_min=30)
                decision = coach_mod.decide_workout_type(con, today, profile, recovery, sleep_s, cycle_ctx, somatic)
                rx_id = coach_mod.prescription_id(today.isoformat(), decision["workout_type"])
                con.execute(
                    "INSERT INTO coach_prescriptions (prescribed_for, prescribed_at, workout_type, difficulty, "
                    "duration_min, body_focus, exercises_json, why_today, prescription_id) "
                    "VALUES (?, NOW(), ?, ?, ?, ?, '', ?, ?)",
                    [today, decision["workout_type"], decision["difficulty"],
                     int(profile.get("session_minutes", 45)), profile.get("body_focus", ""),
                     decision["why_today"], rx_id],
                )
            summary_parts.append(f"prescribed today: {decision['workout_type']} (diff {decision['difficulty']}/10)")
        except Exception as e:
            summary_parts.append(f"prescribe skipped: {type(e).__name__}")

    # 2. Backfill yesterday's journal entry only.
    repo_root = _find_repo_root()
    if repo_root:
        script = repo_root / "scripts" / "backfill-journal-body-context.py"
        if script.is_file():
            yesterday = today - timedelta(days=1)
            vroot = os.environ.get("VAULT_ROOT", "")
            if vroot:
                try:
                    proc = subprocess.run(
                        ["/usr/bin/python3", str(script),
                         "--start", yesterday.isoformat(), "--end", yesterday.isoformat(),
                         "--vault-root", vroot, "--llm-model", "python"],
                        capture_output=True, text=True, timeout=30, check=False,
                    )
                    if proc.returncode == 0 and "backfilled" in proc.stdout:
                        last_line = [l for l in proc.stdout.splitlines() if "Done" in l]
                        if last_line:
                            summary_parts.append("yesterday backfilled")
                except (subprocess.SubprocessError, OSError):
                    pass

    if summary_parts:
        _emit_context("; ".join(summary_parts))
    else:
        _emit_silent()
    return 0


if __name__ == "__main__":
    sys.exit(main())
