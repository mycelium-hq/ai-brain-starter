"""v0.4 smoke tests for the coach state layer.

Tests the progressive-overload state machine, deload-week computation, and
the prescription decision tree (body_says_slow_down -> active recovery,
luteal HRV qualifier, deload rotation).
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

_tmp_dir = tempfile.mkdtemp(prefix="health-mcp-test-v04-")
os.environ["HEALTH_MCP_DB"] = os.path.join(_tmp_dir, "test.duckdb")

import coach  # noqa: E402
import db  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    with db.connect() as con:
        for tbl in ("coach_prescriptions", "coach_completions", "coach_lift_progress"):
            con.execute(f"DELETE FROM {tbl}")
    yield


def test_coach_tables_exist():
    with db.connect() as con:
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()
    names = {r[0] for r in rows}
    assert {"coach_prescriptions", "coach_completions", "coach_lift_progress"}.issubset(names)


def test_prescription_id_is_stable():
    """Same date + workout_type yields same id (idempotent)."""
    a = coach.prescription_id("2026-05-10", "upper_body_strength")
    b = coach.prescription_id("2026-05-10", "upper_body_strength")
    c = coach.prescription_id("2026-05-10", "zone2_cardio")
    assert a == b
    assert a != c


def test_next_lift_first_session():
    out = coach.next_lift_load(None, prescribed_reps=5, prescribed_sets=3)
    assert out["action"] == "first_session"
    assert out["weight_kg"] is None


def test_next_lift_complete_twice_adds_upper():
    state = {"lift_name": "bench_press", "last_weight_kg": 60, "consecutive_full_sets": 2, "consecutive_failures": 0}
    out = coach.next_lift_load(state, prescribed_reps=5, prescribed_sets=3)
    assert out["action"] == "add_increment"
    assert out["weight_kg"] == 62.5


def test_next_lift_complete_twice_adds_lower():
    state = {"lift_name": "squat", "last_weight_kg": 80, "consecutive_full_sets": 2, "consecutive_failures": 0}
    out = coach.next_lift_load(state, prescribed_reps=5, prescribed_sets=3)
    assert out["action"] == "add_increment"
    assert out["weight_kg"] == 85.0


def test_next_lift_fail_twice_drops_10pct():
    state = {"lift_name": "deadlift", "last_weight_kg": 100, "consecutive_full_sets": 0, "consecutive_failures": 2}
    out = coach.next_lift_load(state, prescribed_reps=5, prescribed_sets=3)
    assert out["action"] == "drop_10pct"
    assert out["weight_kg"] == 90.0


def test_next_lift_single_fail_holds():
    state = {"lift_name": "bench_press", "last_weight_kg": 60, "consecutive_full_sets": 0, "consecutive_failures": 1}
    out = coach.next_lift_load(state, prescribed_reps=5, prescribed_sets=3)
    assert out["action"] == "hold"


def test_log_completion_updates_lift_state():
    with db.connect() as con:
        con.execute(
            "INSERT INTO coach_prescriptions (prescribed_for, prescribed_at, workout_type, difficulty, "
            "duration_min, body_focus, exercises_json, why_today, prescription_id) "
            "VALUES (CURRENT_DATE, NOW(), 'upper_body_strength', 7, 45, 'push+pull', '', 'test', 'rx_test123')"
        )
        coach.log_completion(
            con, "rx_test123", rpe=7, notes="solid",
            lift_actuals=[{
                "lift_name": "bench_press",
                "weight_kg": 60,
                "sets_completed": 3,
                "reps_completed_per_set": [5, 5, 5],
                "prescribed_sets": 3,
                "prescribed_reps": 5,
            }],
        )
        state = coach.get_last_lift(con, "bench_press")
    assert state["last_weight_kg"] == 60
    assert state["consecutive_full_sets"] == 1
    assert state["consecutive_failures"] == 0


def test_log_completion_increments_failures_on_short_rep_set():
    with db.connect() as con:
        con.execute(
            "INSERT INTO coach_prescriptions (prescribed_for, prescribed_at, workout_type, difficulty, "
            "duration_min, body_focus, exercises_json, why_today, prescription_id) "
            "VALUES (CURRENT_DATE, NOW(), 'upper_body_strength', 7, 45, 'push+pull', '', 'test', 'rx_test456')"
        )
        coach.log_completion(
            con, "rx_test456", rpe=8, notes=None,
            lift_actuals=[{
                "lift_name": "bench_press",
                "weight_kg": 65,
                "sets_completed": 3,
                "reps_completed_per_set": [5, 4, 3],
                "prescribed_sets": 3,
                "prescribed_reps": 5,
            }],
        )
        state = coach.get_last_lift(con, "bench_press")
    assert state["consecutive_failures"] == 1
    assert state["consecutive_full_sets"] == 0


def test_log_completion_two_failures_then_drop():
    """Sequence: fail (4/5 rep set) twice -> next_lift_load returns drop_10pct."""
    with db.connect() as con:
        for i in range(2):
            con.execute(
                "INSERT INTO coach_prescriptions (prescribed_for, prescribed_at, workout_type, difficulty, "
                "duration_min, body_focus, exercises_json, why_today, prescription_id) "
                "VALUES (CURRENT_DATE, NOW(), 'upper_body_strength', 7, 45, 'push+pull', '', 'test', ?)",
                [f"rx_fail_{i}"],
            )
            coach.log_completion(
                con, f"rx_fail_{i}", rpe=9, notes=None,
                lift_actuals=[{
                    "lift_name": "overhead_press",
                    "weight_kg": 40,
                    "sets_completed": 3,
                    "reps_completed_per_set": [3, 2, 2],
                    "prescribed_sets": 3,
                    "prescribed_reps": 5,
                }],
            )
        state = coach.get_last_lift(con, "overhead_press")
    out = coach.next_lift_load(state, prescribed_reps=5, prescribed_sets=3)
    assert out["action"] == "drop_10pct"
    assert out["weight_kg"] == 36.0


def test_is_deload_week_every_4th():
    start = "2026-01-01"
    week_0 = date(2026, 1, 1)
    week_1 = date(2026, 1, 8)
    week_3 = date(2026, 1, 22)
    week_4 = date(2026, 1, 29)
    assert not coach.is_deload_week(start, week_0)
    assert not coach.is_deload_week(start, week_1)
    assert coach.is_deload_week(start, week_3)
    assert not coach.is_deload_week(start, week_4)


def test_decide_workout_body_says_slow_down_forces_active_recovery():
    profile = {"days_per_week": 4, "equipment": ["dumbbells"], "started_iso": "2026-01-01"}
    with db.connect() as con:
        out = coach.decide_workout_type(
            con, date(2026, 5, 10), profile,
            recovery={"score": 75}, sleep_score_val={"score": 70},
            cycle_ctx=None,
            somatic={"body_says_slow_down": True, "flags": ["HRV crashed"]},
        )
    assert out["workout_type"] == "active_recovery"
    assert out["intensity_factor"] <= 0.5


def test_decide_workout_luteal_qualifier_bumps_intensity():
    """Luteal phase with borderline recovery should NOT collapse intensity —
    the HRV dip is physiology not deficit (Sims, panel 2026-05-10)."""
    profile = {"days_per_week": 4, "equipment": ["dumbbells"], "started_iso": "2026-01-01"}
    with db.connect() as con:
        without_luteal = coach.decide_workout_type(
            con, date(2026, 5, 10), profile,
            recovery={"score": 60}, sleep_score_val={"score": 70},
            cycle_ctx=None,
            somatic={"body_says_slow_down": False},
        )
        with_luteal = coach.decide_workout_type(
            con, date(2026, 5, 10), profile,
            recovery={"score": 60}, sleep_score_val={"score": 70},
            cycle_ctx={"phase": "luteal"},
            somatic={"body_says_slow_down": False},
        )
    assert with_luteal["intensity_factor"] >= without_luteal["intensity_factor"]


def test_decide_workout_low_sleep_score_yields_rest():
    profile = {"days_per_week": 4, "equipment": ["dumbbells"], "started_iso": "2026-01-01"}
    with db.connect() as con:
        out = coach.decide_workout_type(
            con, date(2026, 5, 10), profile,
            recovery={"score": 65}, sleep_score_val={"score": 30},
            cycle_ctx=None,
            somatic={"body_says_slow_down": False},
        )
    assert out["workout_type"] == "rest_day"


def test_decide_workout_deload_week_cuts_intensity():
    profile = {"days_per_week": 4, "equipment": ["dumbbells"], "started_iso": "2026-04-15"}
    deload_week_date = date(2026, 5, 6)  # ~3 weeks after start, week index 3
    with db.connect() as con:
        out = coach.decide_workout_type(
            con, deload_week_date, profile,
            recovery={"score": 80}, sleep_score_val={"score": 80},
            cycle_ctx=None,
            somatic={"body_says_slow_down": False},
        )
    assert out["deload_week"] is True
    assert out["intensity_factor"] < 0.8
