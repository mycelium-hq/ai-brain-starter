"""Open health-scoring algorithms.

Three scores: Recovery, Sleep, Strain. All deterministic Python, no LLM, no
proprietary API. Formulas documented inline so users can audit and adjust.

The component-weighting was chosen to be simple, defensible, and reproducible.
This is NOT a Whoop/Oura clinical-grade score — it is a directional signal
that pairs with the journaling + coaching + panel skills. Users who want a
research-grade score should plug in open-wearables for sleep_score /
resilience_score (Q1 2026 release).

References used while drafting (not redistributed, just consulted for ranges):
  - Whoop's published methodology (Strain 0-21, Recovery 0-100 anchored on HRV+RHR+sleep)
  - Oura's documentation on sleep score components (efficiency, latency, REM%, deep%, total)
  - WHO sleep duration guidance (7-9h adults)
  - HRV baseline literature (SDNN reference: ~30-50ms typical adult)

The output is INTERPRETIVE not DIAGNOSTIC. Surface as "directional", never as
medical advice. The substrate ships with that disclaimer in SETUP.md.
"""
from __future__ import annotations

import math
import statistics
from datetime import date, datetime, timedelta
from typing import Any

import duckdb


# ---------------------------------------------------------------------------
# Helpers: pull the inputs each score needs from the DuckDB connection
# ---------------------------------------------------------------------------

def _hrv_for_date(con: "duckdb.DuckDBPyConnection", target: date) -> float | None:
    """Mean HRV (SDNN) over the sleep window that ENDS on `target` morning.
    HKQuantityTypeIdentifierHeartRateVariabilitySDNN is recorded by Apple
    Watch during sleep; we average all readings inside [target-1, target].
    """
    start = datetime.combine(target - timedelta(days=1), datetime.min.time())
    end = datetime.combine(target, datetime.min.time()) + timedelta(hours=12)
    row = con.execute(
        """
        SELECT AVG(value) FROM records
        WHERE type = 'HKQuantityTypeIdentifierHeartRateVariabilitySDNN'
          AND start_date >= ? AND start_date < ?
        """,
        [start, end],
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _hrv_baseline(con: "duckdb.DuckDBPyConnection", target: date, days: int = 30) -> float | None:
    """Trailing N-day mean HRV used as the reference for a per-day z-score."""
    start = datetime.combine(target - timedelta(days=days), datetime.min.time())
    end = datetime.combine(target, datetime.min.time())
    rows = con.execute(
        """
        SELECT AVG(value) AS daily
        FROM records
        WHERE type = 'HKQuantityTypeIdentifierHeartRateVariabilitySDNN'
          AND start_date >= ? AND start_date < ?
        GROUP BY DATE_TRUNC('day', start_date)
        """,
        [start, end],
    ).fetchall()
    daily = [float(r[0]) for r in rows if r[0] is not None]
    return statistics.mean(daily) if daily else None


def _rhr_for_date(con: "duckdb.DuckDBPyConnection", target: date) -> float | None:
    """Resting heart rate for `target` (HKQuantityTypeIdentifierRestingHeartRate
    is recorded once per day on iOS)."""
    start = datetime.combine(target, datetime.min.time())
    end = start + timedelta(days=1)
    row = con.execute(
        """
        SELECT AVG(value) FROM records
        WHERE type = 'HKQuantityTypeIdentifierRestingHeartRate'
          AND start_date >= ? AND start_date < ?
        """,
        [start, end],
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _sleep_for_date(con: "duckdb.DuckDBPyConnection", target: date) -> dict[str, Any]:
    """Sum sleep stage minutes for the night ending on `target` morning.
    Apple Watch / iPhone records sleep with timestamps spanning midnight, so
    "the night that produced today" is bounded [target-1 18:00, target 12:00]."""
    start = datetime.combine(target - timedelta(days=1), datetime.min.time()) + timedelta(hours=18)
    end = datetime.combine(target, datetime.min.time()) + timedelta(hours=12)
    rows = con.execute(
        """
        SELECT stage, SUM(EXTRACT(EPOCH FROM (end_date - start_date))) / 60.0 AS minutes
        FROM sleep
        WHERE start_date >= ? AND start_date < ?
        GROUP BY stage
        """,
        [start, end],
    ).fetchall()
    by_stage = {r[0]: float(r[1]) for r in rows}
    asleep_min = sum(
        by_stage.get(k, 0.0)
        for k in ("rem", "deep", "core", "asleep_unspecified")
    )
    in_bed_min = by_stage.get("in_bed", asleep_min + by_stage.get("awake", 0.0))
    return {
        "asleep_min": asleep_min,
        "in_bed_min": in_bed_min,
        "rem_min": by_stage.get("rem", 0.0),
        "deep_min": by_stage.get("deep", 0.0),
        "core_min": by_stage.get("core", 0.0),
        "awake_min": by_stage.get("awake", 0.0),
        "efficiency": (asleep_min / in_bed_min) if in_bed_min > 0 else 0.0,
    }


# ---------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------

def recovery_score(con: "duckdb.DuckDBPyConnection", target: date) -> dict[str, Any]:
    """Recovery score 0-100.

    Inputs:
      hrv_today        — mean HRV (SDNN) over the sleep window ending today
      hrv_baseline     — trailing 30-day mean HRV
      rhr_today        — resting heart rate today
      sleep_asleep_min — total minutes asleep last night
      sleep_efficiency — asleep / in_bed

    Components (each 0-1, clipped):
      hrv_component   = sigmoid((hrv_today - baseline) / max(baseline*0.15, 1))   weight 0.40
      rhr_component   = clip(1.0 - (rhr_today - 50) / 30, 0, 1)                    weight 0.20
                          (50bpm = excellent, 80bpm = poor)
      sleep_dur_comp  = clip(asleep_min / 480, 0, 1)                               weight 0.25
                          (8h = full credit; oversleep treated as ceiling)
      sleep_eff_comp  = clip((efficiency - 0.7) / 0.25, 0, 1)                      weight 0.15
                          (70% = floor, 95% = full credit)

    Final: round(100 * sum(weight * component)) clipped to [0, 100].
    Missing inputs lower the available_weight and renormalize so partial data
    still yields a comparable 0-100 score, with a confidence flag.
    """
    hrv_today = _hrv_for_date(con, target)
    hrv_base = _hrv_baseline(con, target)
    rhr_today = _rhr_for_date(con, target)
    sleep = _sleep_for_date(con, target)

    components: dict[str, float] = {}
    weights: dict[str, float] = {}

    if hrv_today is not None and hrv_base is not None and hrv_base > 0:
        delta = (hrv_today - hrv_base) / max(hrv_base * 0.15, 1.0)
        components["hrv"] = 1.0 / (1.0 + math.exp(-delta))
        weights["hrv"] = 0.40
    if rhr_today is not None:
        components["rhr"] = max(0.0, min(1.0, 1.0 - (rhr_today - 50) / 30))
        weights["rhr"] = 0.20
    if sleep["asleep_min"] > 0:
        components["sleep_duration"] = max(0.0, min(1.0, sleep["asleep_min"] / 480))
        weights["sleep_duration"] = 0.25
        components["sleep_efficiency"] = max(0.0, min(1.0, (sleep["efficiency"] - 0.7) / 0.25))
        weights["sleep_efficiency"] = 0.15

    total_weight = sum(weights.values())
    if total_weight == 0:
        return {
            "date": target.isoformat(),
            "score": None,
            "components": {},
            "confidence": "none",
            "note": "No HRV, RHR, or sleep data available for the target date",
        }

    score = 100 * sum(weights[k] * components[k] for k in weights) / total_weight
    return {
        "date": target.isoformat(),
        "score": round(score),
        "components": {k: round(v, 3) for k, v in components.items()},
        "weights_applied": weights,
        "inputs": {
            "hrv_today_ms": round(hrv_today, 2) if hrv_today is not None else None,
            "hrv_baseline_ms": round(hrv_base, 2) if hrv_base is not None else None,
            "rhr_today_bpm": round(rhr_today, 1) if rhr_today is not None else None,
            "sleep_asleep_min": round(sleep["asleep_min"]),
            "sleep_efficiency": round(sleep["efficiency"], 3),
        },
        "confidence": "high" if total_weight >= 0.85 else "medium" if total_weight >= 0.4 else "low",
    }


def sleep_score(con: "duckdb.DuckDBPyConnection", target: date) -> dict[str, Any]:
    """Sleep score 0-100. Inputs from _sleep_for_date.

    Components:
      duration_comp   = clip(asleep_min / 480, 0, 1)               weight 0.40
      efficiency_comp = clip((efficiency - 0.7) / 0.25, 0, 1)      weight 0.25
      rem_pct_comp    = clip((rem_min / asleep_min) / 0.20, 0, 1)  weight 0.20
                          (20% REM = full credit)
      deep_pct_comp   = clip((deep_min / asleep_min) / 0.13, 0, 1) weight 0.15
                          (13% deep = full credit)
    """
    sleep = _sleep_for_date(con, target)
    if sleep["asleep_min"] == 0:
        return {
            "date": target.isoformat(),
            "score": None,
            "components": {},
            "note": "No sleep data for target date",
        }
    rem_pct = sleep["rem_min"] / sleep["asleep_min"]
    deep_pct = sleep["deep_min"] / sleep["asleep_min"]
    components = {
        "duration": max(0.0, min(1.0, sleep["asleep_min"] / 480)),
        "efficiency": max(0.0, min(1.0, (sleep["efficiency"] - 0.7) / 0.25)),
        "rem_pct": max(0.0, min(1.0, rem_pct / 0.20)),
        "deep_pct": max(0.0, min(1.0, deep_pct / 0.13)),
    }
    weights = {"duration": 0.40, "efficiency": 0.25, "rem_pct": 0.20, "deep_pct": 0.15}
    score = 100 * sum(weights[k] * components[k] for k in weights)
    return {
        "date": target.isoformat(),
        "score": round(score),
        "components": {k: round(v, 3) for k, v in components.items()},
        "weights_applied": weights,
        "inputs": {
            "asleep_min": round(sleep["asleep_min"]),
            "rem_min": round(sleep["rem_min"]),
            "deep_min": round(sleep["deep_min"]),
            "core_min": round(sleep["core_min"]),
            "awake_min": round(sleep["awake_min"]),
            "in_bed_min": round(sleep["in_bed_min"]),
            "efficiency": round(sleep["efficiency"], 3),
            "rem_pct": round(rem_pct, 3),
            "deep_pct": round(deep_pct, 3),
        },
    }


def strain_score(con: "duckdb.DuckDBPyConnection", target: date) -> dict[str, Any]:
    """Strain score 0-21 (Whoop scale, but our open formula).

    Inputs:
      active_kcal      — sum of HKQuantityTypeIdentifierActiveEnergyBurned today
      basal_kcal       — sum of HKQuantityTypeIdentifierBasalEnergyBurned today
      hr_elevated_min  — minutes spent at HR > 0.6 * (220 - age_proxy_30) ≈ HR>114
      workout_count    — count of workouts started on `target`
      workout_min      — total workout minutes

    Mapping: ratio = (active_kcal / basal_kcal) + hr_elevated_min/120 + workout_min/60
    Strain = clip(7 * ln(1 + ratio), 0, 21).
    Logarithmic compression matches the Whoop scale shape (asymptotic toward 21).
    """
    start = datetime.combine(target, datetime.min.time())
    end = start + timedelta(days=1)
    active = con.execute(
        "SELECT COALESCE(SUM(value), 0) FROM records "
        "WHERE type = 'HKQuantityTypeIdentifierActiveEnergyBurned' "
        "AND start_date >= ? AND start_date < ?",
        [start, end],
    ).fetchone()[0]
    basal = con.execute(
        "SELECT COALESCE(SUM(value), 0) FROM records "
        "WHERE type = 'HKQuantityTypeIdentifierBasalEnergyBurned' "
        "AND start_date >= ? AND start_date < ?",
        [start, end],
    ).fetchone()[0]
    hr_elev = con.execute(
        "SELECT COALESCE(SUM(EXTRACT(EPOCH FROM (end_date - start_date))) / 60.0, 0) "
        "FROM records "
        "WHERE type = 'HKQuantityTypeIdentifierHeartRate' AND value > 114 "
        "AND start_date >= ? AND start_date < ?",
        [start, end],
    ).fetchone()[0]
    workout_row = con.execute(
        "SELECT COUNT(*), COALESCE(SUM(duration_min), 0) FROM workouts "
        "WHERE start_date >= ? AND start_date < ?",
        [start, end],
    ).fetchone()
    w_count = int(workout_row[0]) if workout_row else 0
    w_min = float(workout_row[1]) if workout_row else 0.0

    ratio_active = (float(active) / float(basal)) if basal and basal > 0 else 0.0
    ratio = ratio_active + (float(hr_elev) / 120.0) + (w_min / 60.0)
    score = max(0.0, min(21.0, 7.0 * math.log(1.0 + ratio)))

    return {
        "date": target.isoformat(),
        "score": round(score, 1),
        "scale_max": 21,
        "components": {
            "active_kcal": round(float(active)),
            "basal_kcal": round(float(basal)),
            "hr_elevated_min": round(float(hr_elev)),
            "workout_count": w_count,
            "workout_min": round(w_min),
        },
        "ratio": round(ratio, 3),
    }
