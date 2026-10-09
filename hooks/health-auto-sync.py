#!/usr/bin/env python3
"""SessionStart hook: silently refresh wearable data if it's stale.

Fires at the start of every Claude Code session. Checks the freshness of
the most recent Oura / Fitbit import via the health-mcp DuckDB and triggers
an in-process backfill for missed days if the data is more than 24 hours
old.

This is the load-bearing piece of the auto-trigger chain: the user doesn't
have to remember to sync wearables, because the substrate does it whenever
they open Claude Code.

Failure modes handled:
  - health-mcp install not present       -> exit silently (0)
  - DuckDB unavailable                    -> exit silently (0)
  - Vendor API rate-limit / network error -> log, exit (0); next session
                                              tries again
  - No env vars set for a vendor          -> skip that vendor; never error
  - User has only Apple Health (no Oura / no Fitbit) -> short-circuit
                                              entirely

Output is JSON to stdout per Claude Code hook spec:
  {"continue": true, "suppressOutput": false,
   "hookSpecificOutput": {"additionalContext": "...summary..."}}

If a sync ran, the summary line surfaces in the session start context so
the user (and Claude) can see what just happened. If nothing was stale,
the hook is silent.

Bypass: set HEALTH_AUTO_SYNC_BYPASS=1 in env to skip entirely.
"""
from __future__ import annotations

import json
import os
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


def _emit_silent() -> None:
    print(json.dumps({"continue": True, "suppressOutput": True}))


def _emit_context(line: str) -> None:
    print(json.dumps({
        "continue": True,
        "suppressOutput": False,
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": f"[health-auto-sync] {line}",
        },
    }))


def main() -> int:
    if os.environ.get("HEALTH_AUTO_SYNC_BYPASS") == "1":
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
    except Exception:
        _emit_silent()
        return 0

    have_oura = bool(os.environ.get("OURA_PERSONAL_ACCESS_TOKEN") or os.environ.get("OURA_PAT"))
    have_fitbit = bool(os.environ.get("FITBIT_ACCESS_TOKEN"))
    if not (have_oura or have_fitbit):
        _emit_silent()
        return 0

    today = date.today()
    yesterday = today - timedelta(days=1)
    summary_parts: list[str] = []

    if have_oura:
        try:
            with db.connect(read_only=True) as con:
                row = con.execute(
                    "SELECT MAX(imported_at) FROM imports WHERE kind = 'oura'"
                ).fetchone()
            last_iso = row[0] if row and row[0] else None
            stale = True
            if last_iso:
                last_dt = last_iso if isinstance(last_iso, datetime) else datetime.fromisoformat(str(last_iso))
                stale = (datetime.now() - last_dt) > timedelta(hours=24)
            if stale:
                import oura_client
                with db.connect() as con:
                    sha = oura_client.folder_sha(yesterday, today)
                    if not db.file_already_imported(con, sha):
                        rows_total = 0
                        for item in oura_client.fetch_range(yesterday, today):
                            kind = item["_kind"]
                            if kind == "record":
                                con.execute(
                                    "INSERT INTO records (type, source_name, unit, start_date, end_date, value, value_str) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                    (item["type"], item["source_name"], item.get("unit", ""), item["start_date"], item["end_date"], item.get("value"), item.get("value_str")),
                                )
                            elif kind == "workout":
                                con.execute(
                                    "INSERT INTO workouts (activity_type, duration_min, distance_km, energy_kcal, start_date, end_date, source_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                    (item["activity_type"], item["duration_min"], item.get("distance_km"), item.get("energy_kcal"), item["start_date"], item["end_date"], item.get("source_name", "Oura")),
                                )
                            elif kind == "sleep":
                                con.execute(
                                    "INSERT INTO sleep (start_date, end_date, stage, source_name) VALUES (?, ?, ?, ?)",
                                    (item["start_date"], item["end_date"], item["stage"], item.get("source_name", "Oura")),
                                )
                            rows_total += 1
                        db.log_import(con, sha, "oura", f"oura:{yesterday.isoformat()}..{today.isoformat()}", rows_total)
                        summary_parts.append(f"Oura {rows_total} rows ({yesterday.isoformat()}..{today.isoformat()})")
        except Exception as e:
            summary_parts.append(f"Oura sync skipped: {type(e).__name__}")

    if have_fitbit:
        try:
            with db.connect(read_only=True) as con:
                row = con.execute(
                    "SELECT MAX(imported_at) FROM imports WHERE kind = 'fitbit'"
                ).fetchone()
            last_iso = row[0] if row and row[0] else None
            stale = True
            if last_iso:
                last_dt = last_iso if isinstance(last_iso, datetime) else datetime.fromisoformat(str(last_iso))
                stale = (datetime.now() - last_dt) > timedelta(hours=24)
            if stale:
                import fitbit_client
                with db.connect() as con:
                    sha = fitbit_client.folder_sha(yesterday, today)
                    if not db.file_already_imported(con, sha):
                        rows_total = 0
                        for item in fitbit_client.fetch_range(yesterday, today):
                            kind = item["_kind"]
                            if kind == "record":
                                con.execute(
                                    "INSERT INTO records (type, source_name, unit, start_date, end_date, value, value_str) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                    (item["type"], item["source_name"], item.get("unit", ""), item["start_date"], item["end_date"], item.get("value"), item.get("value_str")),
                                )
                            elif kind == "sleep":
                                con.execute(
                                    "INSERT INTO sleep (start_date, end_date, stage, source_name) VALUES (?, ?, ?, ?)",
                                    (item["start_date"], item["end_date"], item["stage"], item.get("source_name", "Fitbit")),
                                )
                            rows_total += 1
                        db.log_import(con, sha, "fitbit", f"fitbit:{yesterday.isoformat()}..{today.isoformat()}", rows_total)
                        summary_parts.append(f"Fitbit {rows_total} rows ({yesterday.isoformat()}..{today.isoformat()})")
        except Exception as e:
            summary_parts.append(f"Fitbit sync skipped: {type(e).__name__}")

    if summary_parts:
        _emit_context("; ".join(summary_parts))
    else:
        _emit_silent()
    return 0


if __name__ == "__main__":
    sys.exit(main())
