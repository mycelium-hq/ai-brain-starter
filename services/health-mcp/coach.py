"""Longevity + fitness coach state layer.

Tracks prescribed and completed workouts so the next prescription reads from
the previous one. Implements progressive overload (fail-twice-drop-10%,
complete-twice-add-2.5-5kg, 4-week deload), reads the existing health-mcp
recovery/sleep/cycle/somatic surfaces to decide intensity, and surfaces the
prescription as a structured dict the /coach skill renders to the user.

This module is the DATA + DECISION layer. The coach VOICE lives in
skills/coach/SKILL.md. Together they make a daily prescription that:
  - respects sleep + HRV + cycle phase
  - reads last session's actuals to drive next session's loading
  - flags out-of-range labs that should change the prescription
  - pairs the workout with the user's Floor (emotional state) if today's
    journal exists
"""
from __future__ import annotations

import hashlib
import json
import statistics
from datetime import date, datetime, timedelta
from typing import Any

import duckdb


# Workout-type catalog the coach can prescribe. Each shape comes with a
# base structure that gets parameterized by user profile + recovery state.
WORKOUT_TYPES = {
    "upper_body_strength": "Upper body strength (push + pull, compound + accessory)",
    "lower_body_strength": "Lower body strength (squat / hinge / single-leg)",
    "full_body_strength": "Full body strength (compounds + carries)",
    "zone2_cardio": "Zone 2 cardio (60-70% HRmax, conversational pace)",
    "hiit": "HIIT intervals (90s-3min hard / equal rest)",
    "tempo_run": "Tempo run (lactate threshold pace)",
    "long_steady": "Long steady-state aerobic",
    "mobility_yoga": "Mobility + yoga (45-60 min flow)",
    "active_recovery": "Active recovery (gentle walk + stretching, 20-30 min)",
    "rest_day": "Rest day (no structured movement)",
    "strain_test": "Strain test (CrossFit-style WOD or AMRAP)",
}


# Major lifts the coach tracks progression on. Customizable per profile.
MAJOR_LIFTS = [
    "squat", "front_squat", "deadlift", "romanian_deadlift",
    "bench_press", "overhead_press", "row", "pull_up",
    "kettlebell_swing", "goblet_squat", "split_squat",
]


def prescription_id(date_iso: str, workout_type: str) -> str:
    """Stable ID per (date, workout_type) so re-running the same day's
    prescription is idempotent."""
    return "rx_" + hashlib.sha1(f"{date_iso}|{workout_type}".encode()).hexdigest()[:12]


def get_last_lift(con: "duckdb.DuckDBPyConnection", lift_name: str) -> dict[str, Any] | None:
    """Most recent lift progression row, or None if user hasn't logged this lift yet."""
    row = con.execute(
        """
        SELECT last_session_date, last_weight_kg, last_reps_completed, last_sets_completed,
               consecutive_full_sets, consecutive_failures, current_top_set_kg
        FROM coach_lift_progress WHERE lift_name = ? ORDER BY updated_at DESC LIMIT 1
        """,
        [lift_name],
    ).fetchone()
    if not row:
        return None
    return {
        "lift_name": lift_name,
        "last_session_date": str(row[0]) if row[0] else None,
        "last_weight_kg": float(row[1]) if row[1] is not None else None,
        "last_reps_completed": int(row[2]) if row[2] is not None else None,
        "last_sets_completed": int(row[3]) if row[3] is not None else None,
        "consecutive_full_sets": int(row[4] or 0),
        "consecutive_failures": int(row[5] or 0),
        "current_top_set_kg": float(row[6]) if row[6] is not None else None,
    }


def next_lift_load(state: dict[str, Any] | None, prescribed_reps: int, prescribed_sets: int) -> dict[str, Any]:
    """Apply progressive overload to figure out next session's load.

    Rules (from the Claude Fitness Coach prompt, panel-validated):
      - First time logging this lift: caller supplies starting weight
      - 2+ consecutive full completions: add 2.5kg upper body / 5kg lower body
      - 1 failure: hold weight
      - 2 failures: drop 10%, build back up
    """
    if not state:
        return {"action": "first_session", "weight_kg": None, "note": "First time logging this lift. Pick a weight you can complete all sets with 2 reps in reserve."}
    last_w = state.get("last_weight_kg") or 0
    consec_full = state.get("consecutive_full_sets") or 0
    consec_fail = state.get("consecutive_failures") or 0
    lift = state["lift_name"]
    upper_lifts = {"bench_press", "overhead_press", "row", "pull_up"}
    increment = 2.5 if lift in upper_lifts else 5.0
    if consec_fail >= 2:
        new_w = round(last_w * 0.9, 1)
        return {"action": "drop_10pct", "weight_kg": new_w, "note": f"Two failures in a row. Drop 10% to {new_w}kg, build back up."}
    if consec_full >= 2:
        new_w = round(last_w + increment, 1)
        return {"action": "add_increment", "weight_kg": new_w, "note": f"Two full completions in a row. Move to {new_w}kg ({increment}kg increment)."}
    return {"action": "hold", "weight_kg": last_w, "note": f"Hold at {last_w}kg. Need {2 - consec_full} more full session(s) to add weight."}


def log_completion(
    con: "duckdb.DuckDBPyConnection",
    prescription_id: str,
    rpe: int | None,
    notes: str | None,
    lift_actuals: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Record a completed session + update per-lift progression state.

    lift_actuals: optional list of {lift_name, weight_kg, sets_completed,
    reps_completed_per_set, prescribed_sets, prescribed_reps}.
    For each, updates coach_lift_progress and increments consecutive_full_sets
    or consecutive_failures.
    """
    con.execute(
        "INSERT INTO coach_completions (prescription_id, completed_at, rpe, notes, actuals_json) "
        "VALUES (?, NOW(), ?, ?, ?)",
        [prescription_id, rpe, notes, json.dumps(lift_actuals or [])],
    )
    if not lift_actuals:
        return {"prescription_id": prescription_id, "lifts_updated": 0}

    updated = 0
    for entry in lift_actuals:
        lift = entry.get("lift_name")
        if not lift:
            continue
        weight = entry.get("weight_kg")
        sets_done = int(entry.get("sets_completed", 0))
        prescribed_sets = int(entry.get("prescribed_sets", sets_done))
        reps_per_set = entry.get("reps_completed_per_set", [])
        prescribed_reps = int(entry.get("prescribed_reps", 0))
        full_completion = (
            sets_done >= prescribed_sets
            and prescribed_reps > 0
            and all((r >= prescribed_reps) for r in (reps_per_set or [0] * sets_done))
        )

        prior = get_last_lift(con, lift) or {}
        consec_full = prior.get("consecutive_full_sets", 0)
        consec_fail = prior.get("consecutive_failures", 0)
        if full_completion:
            consec_full += 1
            consec_fail = 0
        else:
            consec_fail += 1
            consec_full = 0
        top_set = max((weight or 0), prior.get("current_top_set_kg", 0) or 0)
        con.execute(
            """
            INSERT INTO coach_lift_progress
              (lift_name, last_session_date, last_weight_kg, last_reps_completed,
               last_sets_completed, consecutive_full_sets, consecutive_failures,
               current_top_set_kg, updated_at)
            VALUES (?, CURRENT_DATE, ?, ?, ?, ?, ?, ?, NOW())
            """,
            [lift, weight, max(reps_per_set) if reps_per_set else None,
             sets_done, consec_full, consec_fail, top_set],
        )
        updated += 1
    return {"prescription_id": prescription_id, "lifts_updated": updated}


def is_deload_week(profile_start_iso: str, target: date) -> bool:
    """Every 4th week from profile start is a deload."""
    try:
        start = datetime.fromisoformat(profile_start_iso).date()
    except (TypeError, ValueError):
        return False
    weeks = (target - start).days // 7
    return weeks > 0 and weeks % 4 == 3


def _consecutive_days_with_workout(con: "duckdb.DuckDBPyConnection", target: date) -> int:
    """Look back from target until we hit a day with no completed workout."""
    streak = 0
    cur = target
    while True:
        start_dt = datetime.combine(cur, datetime.min.time())
        end_dt = start_dt + timedelta(days=1)
        row = con.execute(
            "SELECT COUNT(*) FROM workouts WHERE start_date >= ? AND start_date < ?",
            [start_dt, end_dt],
        ).fetchone()
        if not row or row[0] == 0:
            break
        streak += 1
        cur -= timedelta(days=1)
        if streak > 10:
            break
    return streak


def _days_since_workout(con: "duckdb.DuckDBPyConnection", target: date) -> int:
    """How many days since the most recent workout. 0 = today has one."""
    end_dt = datetime.combine(target, datetime.min.time()) + timedelta(days=1)
    row = con.execute(
        "SELECT MAX(start_date) FROM workouts WHERE start_date < ?",
        [end_dt],
    ).fetchone()
    if not row or not row[0]:
        return -1
    last = row[0].date() if hasattr(row[0], "date") else row[0]
    return (target - last).days


def decide_workout_type(
    con: "duckdb.DuckDBPyConnection",
    target: date,
    profile: dict[str, Any],
    recovery: dict[str, Any] | None,
    sleep_score_val: dict[str, Any] | None,
    cycle_ctx: dict[str, Any] | None,
    somatic: dict[str, Any] | None,
) -> dict[str, Any]:
    """Choose the workout shape for target date based on recovery + profile.

    Returns: {workout_type, intensity_factor (0-1), difficulty (1-10),
              why_today (one-line rationale), deload_week (bool)}
    """
    # First: somatic state check (panel rule from Levine — body says slow down).
    if somatic and somatic.get("body_says_slow_down"):
        return {
            "workout_type": "active_recovery",
            "intensity_factor": 0.4,
            "difficulty": 2,
            "why_today": "Recent HR/HRV volatility — body is in sympathetic activation. Regulate first.",
            "deload_week": False,
        }

    # Sleep check (continuous via sleep_score, NOT hardcoded hours tiers).
    sleep_s = (sleep_score_val or {}).get("score")
    rec_s = (recovery or {}).get("score")

    if sleep_s is not None and sleep_s < 35:
        return {
            "workout_type": "rest_day",
            "intensity_factor": 0,
            "difficulty": 1,
            "why_today": f"Sleep score {sleep_s}/100 — body needs the day off.",
            "deload_week": False,
        }

    if sleep_s is not None and sleep_s < 55:
        return {
            "workout_type": "active_recovery",
            "intensity_factor": 0.5,
            "difficulty": 3,
            "why_today": f"Sleep score {sleep_s}/100 — gentle movement only.",
            "deload_week": False,
        }

    # Cycle phase qualifier (Sims). If luteal AND recovery is borderline, don't
    # over-fire on the recovery score — it would be capturing physiology.
    phase = (cycle_ctx or {}).get("phase")

    # Deload check (every 4th week from profile start).
    deload = is_deload_week(profile.get("started_iso", "2026-01-01"), target)

    # Compute base intensity from recovery score with cycle qualifier.
    if rec_s is None:
        # No HRV / RHR / sleep data yet. Default to medium.
        intensity = 0.7
    else:
        intensity = max(0.4, min(1.0, rec_s / 100.0))
        if phase == "luteal" and intensity < 0.7:
            # Bump intensity back up because luteal HRV dips are physiology
            # (Sims, panel 2026-05-10), not actual recovery deficit.
            intensity = max(intensity, 0.7)

    if deload:
        intensity *= 0.6  # deload week: 40% volume drop, 20% intensity drop
        intensity = max(0.4, intensity)

    # Pick workout shape based on profile + day-of-week rotation + intensity.
    days_per_week = int(profile.get("days_per_week", 4))
    available = profile.get("equipment", [])
    has_weights = any(e in available for e in {"full_gym", "dumbbells", "barbell", "kettlebell"})
    day_idx = target.weekday()  # 0=Mon, 6=Sun

    if days_per_week >= 5:
        rotation = ["upper_body_strength", "zone2_cardio", "lower_body_strength", "mobility_yoga", "full_body_strength", "long_steady", "rest_day"]
    elif days_per_week == 4:
        rotation = ["upper_body_strength", "zone2_cardio", "lower_body_strength", "active_recovery", "full_body_strength", "mobility_yoga", "rest_day"]
    elif days_per_week == 3:
        rotation = ["full_body_strength", "active_recovery", "zone2_cardio", "active_recovery", "full_body_strength", "active_recovery", "rest_day"]
    else:
        rotation = ["full_body_strength", "active_recovery", "rest_day", "zone2_cardio", "active_recovery", "rest_day", "rest_day"]
    wt = rotation[day_idx]

    if wt in {"upper_body_strength", "lower_body_strength", "full_body_strength"} and not has_weights:
        wt = "zone2_cardio" if day_idx % 2 == 0 else "mobility_yoga"

    if deload and wt in {"upper_body_strength", "lower_body_strength", "full_body_strength"}:
        why = f"Recovery {rec_s}/100, sleep {sleep_s}/100. Deload week — 40% volume drop on lifts. Keep movement quality, drop intensity."
    elif phase == "luteal" and rec_s and rec_s < 70:
        why = f"Recovery {rec_s}/100, but you're in luteal phase. The HRV dip is physiology, not a deficit. Train normally."
    elif rec_s is None:
        why = "No HRV/RHR/sleep data yet. Default to moderate intensity. Pull your wearable data to get sharper prescriptions."
    else:
        why = f"Recovery {rec_s}/100, sleep {sleep_s if sleep_s is not None else '?'}/100. {WORKOUT_TYPES[wt]} fits today."

    return {
        "workout_type": wt,
        "intensity_factor": round(intensity, 2),
        "difficulty": min(10, max(1, round(intensity * 10))),
        "why_today": why,
        "deload_week": deload,
    }
