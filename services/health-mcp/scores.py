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


# ---------------------------------------------------------------------------
# Sleep regularity (Winter, panel 2026-05-10)
# ---------------------------------------------------------------------------

def sleep_regularity(con: "duckdb.DuckDBPyConnection", start_date: date, end_date: date) -> dict[str, Any]:
    """Sleep Regularity Index over the window. Lower variance in bed/wake
    time = higher regularity. Includes nap detection (asleep < 90min flagged
    separately) and average sleep latency.

    Components surfaced:
      - bed_time_stdev_h, wake_time_stdev_h, duration_stdev_h
      - mean_latency_min: average minutes from in_bed to first asleep stage
      - nap_count: count of asleep blocks under 90 minutes (excluded from
        regularity stats)
      - regularity_score: 0-100 derived from inverse of weighted stdevs
    """
    days = (end_date - start_date).days + 1
    bed_times: list[float] = []  # decimal hours (0-24)
    wake_times: list[float] = []
    durations: list[float] = []  # hours
    latencies: list[float] = []  # minutes
    naps = 0
    cur = start_date
    while cur <= end_date:
        win_start = datetime.combine(cur - timedelta(days=1), datetime.min.time()) + timedelta(hours=18)
        win_end = datetime.combine(cur, datetime.min.time()) + timedelta(hours=12)
        rows = con.execute(
            """
            SELECT start_date, end_date, stage FROM sleep
            WHERE start_date >= ? AND start_date < ?
            ORDER BY start_date
            """,
            [win_start, win_end],
        ).fetchall()
        if rows:
            in_bed_starts = [r[0] for r in rows if r[2] == "in_bed"]
            asleep_blocks = [(r[0], r[1]) for r in rows if r[2] in {"core", "deep", "rem", "asleep_unspecified"}]
            if asleep_blocks:
                first_asleep = min(b[0] for b in asleep_blocks)
                last_asleep = max(b[1] for b in asleep_blocks)
                duration_h = sum((b[1] - b[0]).total_seconds() for b in asleep_blocks) / 3600.0
                if duration_h * 60 < 90:
                    naps += 1
                else:
                    bed_times.append(first_asleep.hour + first_asleep.minute / 60.0)
                    wake_times.append(last_asleep.hour + last_asleep.minute / 60.0)
                    durations.append(duration_h)
                    if in_bed_starts:
                        latency = (first_asleep - min(in_bed_starts)).total_seconds() / 60.0
                        if latency >= 0:
                            latencies.append(latency)
        cur += timedelta(days=1)

    def _stdev(xs: list[float]) -> float:
        return statistics.stdev(xs) if len(xs) > 1 else 0.0

    bed_stdev = _stdev(bed_times)
    wake_stdev = _stdev(wake_times)
    dur_stdev = _stdev(durations)
    weighted = (bed_stdev * 0.4 + wake_stdev * 0.4 + dur_stdev * 0.2)
    regularity = max(0.0, min(100.0, 100.0 - weighted * 25.0))

    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "n_nights_used": len(durations),
        "nap_count": naps,
        "bed_time_stdev_h": round(bed_stdev, 2),
        "wake_time_stdev_h": round(wake_stdev, 2),
        "duration_stdev_h": round(dur_stdev, 2),
        "mean_latency_min": round(statistics.mean(latencies), 1) if latencies else None,
        "regularity_score": round(regularity),
        "interpretation_hint": (
            "Regularity > 80 = consistent bed/wake. "
            "60-80 = some drift. <60 = chronic dysregulation in sleep timing. "
            "Latency >30min often signals stress; <5min often signals sleep deprivation."
        ),
    }


# ---------------------------------------------------------------------------
# Longevity panel (Attia + Patrick, panel 2026-05-10)
# ---------------------------------------------------------------------------

def longevity_panel(con: "duckdb.DuckDBPyConnection", target: date) -> dict[str, Any]:
    """Surface VO2Max, walking steadiness, lean mass, Zone-2 minutes (proxied
    by HR-in-zone), and gait speed. The longevity-focused single-call view
    Attia and Patrick wanted on the panel."""
    end = datetime.combine(target, datetime.min.time()) + timedelta(days=1)
    start_30 = datetime.combine(target - timedelta(days=30), datetime.min.time())
    start_90 = datetime.combine(target - timedelta(days=90), datetime.min.time())

    def _last(metric: str) -> float | None:
        row = con.execute(
            "SELECT value FROM records WHERE type = ? ORDER BY start_date DESC LIMIT 1",
            [metric],
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else None

    def _avg_30(metric: str) -> float | None:
        row = con.execute(
            "SELECT AVG(value) FROM records WHERE type = ? AND start_date >= ? AND start_date < ?",
            [metric, start_30, end],
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else None

    def _avg_90(metric: str) -> float | None:
        row = con.execute(
            "SELECT AVG(value) FROM records WHERE type = ? AND start_date >= ? AND start_date < ?",
            [metric, start_90, end],
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else None

    vo2max = _avg_30("HKQuantityTypeIdentifierVO2Max") or _last("HKQuantityTypeIdentifierVO2Max")
    walking_speed = _avg_30("HKQuantityTypeIdentifierWalkingSpeed")
    walking_steadiness = _avg_30("HKQuantityTypeIdentifierAppleWalkingSteadiness")
    lean_mass = _last("HKQuantityTypeIdentifierLeanBodyMass")
    body_fat_pct = _last("HKQuantityTypeIdentifierBodyFatPercentage")
    body_mass = _last("HKQuantityTypeIdentifierBodyMass")
    six_min_walk = _avg_90("HKQuantityTypeIdentifierSixMinuteWalkTestDistance")

    # Zone 2: 60-70% of estimated HRmax (208 - 0.7*age). With no age, use
    # generic 100-130 bpm band as a useful default.
    zone2 = con.execute(
        """
        SELECT COALESCE(SUM(EXTRACT(EPOCH FROM (end_date - start_date))) / 60.0, 0)
        FROM records
        WHERE type = 'HKQuantityTypeIdentifierHeartRate'
          AND value BETWEEN 100 AND 130
          AND start_date >= ? AND start_date < ?
        """,
        [start_30, end],
    ).fetchone()[0]

    return {
        "as_of": target.isoformat(),
        "vo2max": round(float(vo2max), 1) if vo2max is not None else None,
        "walking_speed_m_s": round(float(walking_speed), 2) if walking_speed is not None else None,
        "walking_steadiness_pct": round(float(walking_steadiness), 1) if walking_steadiness is not None else None,
        "six_minute_walk_m_avg_90d": round(float(six_min_walk)) if six_min_walk is not None else None,
        "lean_body_mass_kg": round(float(lean_mass), 1) if lean_mass is not None else None,
        "body_fat_percentage": round(float(body_fat_pct), 1) if body_fat_pct is not None else None,
        "body_mass_kg": round(float(body_mass), 1) if body_mass is not None else None,
        "zone2_minutes_30d": round(float(zone2)),
        "interpretation_hint": (
            "VO2Max is the single most predictive longevity marker (Attia, *Outlive*). "
            "Walking steadiness < 80% flags fall risk; trending down = act now. "
            "Zone 2 minutes target: 180+/week (~26+/day) for cardio mitochondrial health."
        ),
    }


# ---------------------------------------------------------------------------
# Somatic state (Levine, panel 2026-05-10) — pre-coaching check
# ---------------------------------------------------------------------------

def somatic_state(con: "duckdb.DuckDBPyConnection", target: date, lookback_min: int = 30) -> dict[str, Any]:
    """Recent HR / HRV volatility. Returns body_says_slow_down boolean for the
    coaching skill to check before going into emotional inquiry."""
    end = datetime.now() if target == date.today() else datetime.combine(target, datetime.min.time()) + timedelta(days=1)
    start = end - timedelta(minutes=lookback_min)
    rows = con.execute(
        "SELECT value FROM records WHERE type = 'HKQuantityTypeIdentifierHeartRate' "
        "AND start_date >= ? AND start_date < ? ORDER BY start_date",
        [start, end],
    ).fetchall()
    hrs = [float(r[0]) for r in rows if r[0] is not None]
    hr_max = max(hrs) if hrs else None
    hr_min = min(hrs) if hrs else None
    hr_range = (hr_max - hr_min) if hrs else None

    today_start = datetime.combine(target, datetime.min.time())
    today_end = today_start + timedelta(days=1)
    hrv_today = con.execute(
        "SELECT AVG(value) FROM records WHERE type = 'HKQuantityTypeIdentifierHeartRateVariabilitySDNN' "
        "AND start_date >= ? AND start_date < ?",
        [today_start, today_end],
    ).fetchone()
    hrv_30d = con.execute(
        "SELECT AVG(value) FROM records WHERE type = 'HKQuantityTypeIdentifierHeartRateVariabilitySDNN' "
        "AND start_date >= ? AND start_date < ?",
        [today_start - timedelta(days=30), today_start],
    ).fetchone()

    today_hrv = float(hrv_today[0]) if hrv_today and hrv_today[0] is not None else None
    base_hrv = float(hrv_30d[0]) if hrv_30d and hrv_30d[0] is not None else None
    hrv_drop_pct = ((today_hrv - base_hrv) / base_hrv * 100) if (today_hrv and base_hrv and base_hrv > 0) else None

    body_says_slow_down = False
    flags: list[str] = []
    if hr_range is not None and hr_range > 30:
        body_says_slow_down = True
        flags.append(f"HR range {round(hr_range)} bpm in last {lookback_min}min (volatile)")
    if hr_max is not None and hr_max > 120:
        body_says_slow_down = True
        flags.append(f"HR peaked at {round(hr_max)} bpm in last {lookback_min}min")
    if hrv_drop_pct is not None and hrv_drop_pct < -25:
        body_says_slow_down = True
        flags.append(f"HRV {round(hrv_drop_pct)}% below 30-day baseline")
    if not flags:
        flags.append("body markers steady")

    return {
        "as_of": target.isoformat(),
        "lookback_min": lookback_min,
        "recent_hr_min_bpm": round(hr_min) if hr_min is not None else None,
        "recent_hr_max_bpm": round(hr_max) if hr_max is not None else None,
        "recent_hr_range_bpm": round(hr_range) if hr_range is not None else None,
        "n_hr_samples": len(hrs),
        "hrv_today_ms": round(today_hrv, 1) if today_hrv is not None else None,
        "hrv_30d_baseline_ms": round(base_hrv, 1) if base_hrv is not None else None,
        "hrv_delta_pct": round(hrv_drop_pct, 1) if hrv_drop_pct is not None else None,
        "body_says_slow_down": body_says_slow_down,
        "flags": flags,
        "interpretation_hint": (
            "If body_says_slow_down is True, the coaching skill should regulate "
            "first (breath, body scan, slow check-in) before emotional inquiry. "
            "Sympathetic activation makes reframe work counterproductive."
        ),
    }


# ---------------------------------------------------------------------------
# Nutrition summary (Braddock, panel 2026-05-10)
# ---------------------------------------------------------------------------

def nutrition_summary(con: "duckdb.DuckDBPyConnection", start_date: date, end_date: date) -> dict[str, Any]:
    """Daily kcal / protein / carb / fat / fiber / water / caffeine / alcohol
    averages over the window plus an under-fuel detector.

    Under-fuel rule: kcal_consumed < 0.7 * (basal + active). If 30%+ of days
    in the window are under-fueled, recovery score's "rest more" advice is
    mis-framed — the actual signal is "eat enough."
    """
    sd = datetime.combine(start_date, datetime.min.time())
    ed = datetime.combine(end_date, datetime.min.time()) + timedelta(days=1)

    def _daily_sum(metric: str) -> float:
        row = con.execute(
            "SELECT COALESCE(AVG(daily), 0) FROM "
            "(SELECT DATE_TRUNC('day', start_date) AS d, SUM(value) AS daily "
            " FROM records WHERE type = ? AND start_date >= ? AND start_date < ? "
            " GROUP BY d)",
            [metric, sd, ed],
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0

    avg_kcal = _daily_sum("HKQuantityTypeIdentifierDietaryEnergyConsumed")
    avg_protein = _daily_sum("HKQuantityTypeIdentifierDietaryProtein")
    avg_carbs = _daily_sum("HKQuantityTypeIdentifierDietaryCarbohydrates")
    avg_fat = _daily_sum("HKQuantityTypeIdentifierDietaryFatTotal")
    avg_fiber = _daily_sum("HKQuantityTypeIdentifierDietaryFiber")
    avg_sugar = _daily_sum("HKQuantityTypeIdentifierDietarySugar")
    avg_water = _daily_sum("HKQuantityTypeIdentifierDietaryWater")
    avg_caffeine = _daily_sum("HKQuantityTypeIdentifierDietaryCaffeine")
    avg_alcohol = _daily_sum("HKQuantityTypeIdentifierNumberOfAlcoholicBeverages")

    # Under-fuel detector
    under_fueled_days = 0
    counted_days = 0
    cur = start_date
    while cur <= end_date:
        d_start = datetime.combine(cur, datetime.min.time())
        d_end = d_start + timedelta(days=1)
        consumed = con.execute(
            "SELECT COALESCE(SUM(value), 0) FROM records "
            "WHERE type = 'HKQuantityTypeIdentifierDietaryEnergyConsumed' "
            "AND start_date >= ? AND start_date < ?",
            [d_start, d_end],
        ).fetchone()[0]
        active = con.execute(
            "SELECT COALESCE(SUM(value), 0) FROM records "
            "WHERE type = 'HKQuantityTypeIdentifierActiveEnergyBurned' "
            "AND start_date >= ? AND start_date < ?",
            [d_start, d_end],
        ).fetchone()[0]
        basal = con.execute(
            "SELECT COALESCE(SUM(value), 0) FROM records "
            "WHERE type = 'HKQuantityTypeIdentifierBasalEnergyBurned' "
            "AND start_date >= ? AND start_date < ?",
            [d_start, d_end],
        ).fetchone()[0]
        burned = float(active) + float(basal)
        if float(consumed) > 0 and burned > 0:
            counted_days += 1
            if float(consumed) < 0.7 * burned:
                under_fueled_days += 1
        cur += timedelta(days=1)

    under_fuel_pct = (under_fueled_days / counted_days * 100) if counted_days > 0 else None

    note = "No dietary data found. Connect a nutrition app (MyFitnessPal, Cronometer, etc.) to populate."
    if avg_kcal > 0:
        note = "Daily averages computed across window. Under-fuel detector runs only on days with both consumed AND burned data."

    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "daily_kcal_avg": round(avg_kcal),
        "daily_protein_g_avg": round(avg_protein),
        "daily_carbs_g_avg": round(avg_carbs),
        "daily_fat_g_avg": round(avg_fat),
        "daily_fiber_g_avg": round(avg_fiber),
        "daily_sugar_g_avg": round(avg_sugar),
        "daily_water_ml_avg": round(avg_water),
        "daily_caffeine_mg_avg": round(avg_caffeine),
        "daily_alcoholic_beverages_avg": round(avg_alcohol, 2),
        "n_days_with_complete_energy_data": counted_days,
        "under_fueled_days": under_fueled_days,
        "under_fuel_percent": round(under_fuel_pct, 1) if under_fuel_pct is not None else None,
        "under_fuel_signal": "high" if (under_fuel_pct or 0) > 30 else "moderate" if (under_fuel_pct or 0) > 10 else "low" if counted_days else "no_data",
        "note": note,
    }


# ---------------------------------------------------------------------------
# Long-window comparison (van der Kolk, panel 2026-05-10)
# ---------------------------------------------------------------------------

def long_window(
    con: "duckdb.DuckDBPyConnection",
    metric: str,
    years: int = 2,
    aggregation: str = "avg",
) -> dict[str, Any]:
    """Compare same-month-this-year vs same-month-last-year (and N-year stack)
    for a metric. Surfaces persistent asymmetries that 30-day windows miss."""
    today = date.today()
    months_back = years * 12
    rows = con.execute(
        """
        SELECT DATE_TRUNC('month', start_date) AS m, AVG(value)
        FROM records
        WHERE type = ?
          AND start_date >= DATE_TRUNC('month', NOW()) - INTERVAL '24 month'
        GROUP BY m
        ORDER BY m
        """,
        [metric],
    ).fetchall() if aggregation == "avg" else con.execute(
        """
        SELECT DATE_TRUNC('month', start_date) AS m, SUM(value)
        FROM records
        WHERE type = ?
          AND start_date >= DATE_TRUNC('month', NOW()) - INTERVAL '24 month'
        GROUP BY m
        ORDER BY m
        """,
        [metric],
    ).fetchall()

    by_month = {r[0].date() if hasattr(r[0], 'date') else r[0]: float(r[1]) for r in rows if r[1] is not None}
    if not by_month:
        return {"metric": metric, "note": "No data found in the last 24 months", "n_months": 0}

    # Year-over-year same-month comparison
    yoy = []
    for current_m, current_val in by_month.items():
        same_m_last_year = None
        for m, v in by_month.items():
            if m.month == current_m.month and m.year == current_m.year - 1:
                same_m_last_year = v
                break
        if same_m_last_year is not None:
            yoy.append({
                "month": current_m.isoformat() if hasattr(current_m, 'isoformat') else str(current_m),
                "this_year": round(current_val, 2),
                "last_year": round(same_m_last_year, 2),
                "delta_pct": round((current_val - same_m_last_year) / same_m_last_year * 100, 1) if same_m_last_year else None,
            })

    # Persistent asymmetry: 4+ consecutive months on the same side of the YoY delta
    persistent_signal = None
    if len(yoy) >= 4:
        recent_4 = yoy[-4:]
        if all((r.get("delta_pct") or 0) < -5 for r in recent_4):
            persistent_signal = "persistently_lower_than_last_year"
        elif all((r.get("delta_pct") or 0) > 5 for r in recent_4):
            persistent_signal = "persistently_higher_than_last_year"

    return {
        "metric": metric,
        "n_months": len(by_month),
        "year_over_year": yoy[-12:],
        "persistent_asymmetry": persistent_signal,
        "interpretation_hint": (
            "Persistent asymmetry over 4+ months suggests a long-running pattern "
            "that 30-day windows miss. Check for life-event coupling (relocation, "
            "loss, season). Trauma signatures often show up here first."
        ),
    }
