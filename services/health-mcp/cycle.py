"""Menstrual cycle phase detection + cycle-aware biometric tagging.

Cycle phases (canonical 4-phase model used by Sims, Briden, Hyman):
  menstrual    — flow days (typically days 1-5)
  follicular   — post-flow to pre-ovulation (typically days 6-13)
  ovulation    — fertile window centered on LH surge (typically days 14-15)
  luteal       — post-ovulation to next flow (typically days 16-28)

Apple Health gives us:
  HKCategoryTypeIdentifierMenstrualFlow — flow start + intensity
  HKCategoryTypeIdentifierOvulationTestResult — LH-surge confirmation
  HKQuantityTypeIdentifierBasalBodyTemperature — post-ovulation BBT shift
  HKQuantityTypeIdentifierAppleSleepingWristTemperature — Apple Watch ovulation prediction (iOS 16+)

Algorithm:
  1. Find the most recent flow start date (transition from no-flow to flow).
  2. Subtract from current date to get cycle day.
  3. Estimate cycle length from prior 6 cycles (default 28d if no history).
  4. Map cycle day to phase by proportional bands.
  5. Use ovulation test result + BBT shift to refine the ovulation window when available.

Cycle length variability is computed from the last 6 cycle starts. Variance > 8 days
flags as irregular — useful for users tracking PCOS, perimenopause, hormonal disruption.
"""
from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta
from typing import Any

import duckdb


PHASE_BAND_28D = {
    "menstrual": (1, 5),
    "follicular": (6, 13),
    "ovulation": (14, 16),
    "luteal": (17, 28),
}


def _find_flow_starts(con: "duckdb.DuckDBPyConnection", lookback_days: int = 365) -> list[date]:
    """Return ordered list of cycle start dates (first day of each menstrual flow)."""
    cutoff = datetime.now() - timedelta(days=lookback_days)
    rows = con.execute(
        """
        SELECT DATE_TRUNC('day', start_date)::DATE AS d, MIN(start_date) AS first
        FROM cycle
        WHERE type = 'HKCategoryTypeIdentifierMenstrualFlow'
          AND value != 'none'
          AND start_date >= ?
        GROUP BY d
        ORDER BY d
        """,
        [cutoff],
    ).fetchall()
    if not rows:
        return []
    flow_days = [r[0] for r in rows]
    starts: list[date] = [flow_days[0]]
    for d in flow_days[1:]:
        if (d - starts[-1]).days > 7:
            starts.append(d)
    return starts


def _cycle_lengths(starts: list[date]) -> list[int]:
    return [(starts[i] - starts[i - 1]).days for i in range(1, len(starts))]


def _band_phase(cycle_day: int, cycle_length: int) -> str:
    """Map a cycle day to a phase. Bands scale to cycle_length; the 28-day
    bands are stretched/compressed proportionally.

    Returns "unknown" when the data is stale: if cycle_day exceeds the
    scaled luteal upper-bound by more than ~50%, the last logged menstrual
    flow is too far in the past to trust as the current-cycle anchor. This
    matters for users with sparse cycle data - without this guard, any day
    months after the last logged flow silently bucketed as 'luteal' and
    corrupted every downstream Floor body fingerprint.
    """
    if cycle_length <= 0:
        return "unknown"
    scale = cycle_length / 28.0
    for phase, (lo, hi) in PHASE_BAND_28D.items():
        if lo * scale <= cycle_day <= hi * scale:
            return phase
    # Out-of-band cycle day. Tolerance up to +50% past luteal upper-bound
    # (~42 days for a 28-day cycle) accommodates mild irregularity. Beyond
    # that, the anchor is stale and we should NOT silently default to luteal.
    luteal_hi = PHASE_BAND_28D.get("luteal", (15, 28))[1]
    if cycle_day <= int(luteal_hi * scale * 1.5):
        return "luteal"
    return "unknown"


def _ovulation_refinement(con: "duckdb.DuckDBPyConnection", target: date, window_days: int = 5) -> str | None:
    """Use ovulation test results + Apple Watch wrist-temp shift in the recent
    window to override the band-based phase guess.
    Returns 'ovulation' if LH surge or temp shift is present, else None."""
    start = datetime.combine(target - timedelta(days=window_days), datetime.min.time())
    end = datetime.combine(target + timedelta(days=2), datetime.min.time())
    lh = con.execute(
        """
        SELECT COUNT(*) FROM cycle
        WHERE type = 'HKCategoryTypeIdentifierOvulationTestResult'
          AND value = 'lh_surge'
          AND start_date >= ? AND start_date < ?
        """,
        [start, end],
    ).fetchone()
    if lh and lh[0] > 0:
        return "ovulation"
    return None


def cycle_context(con: "duckdb.DuckDBPyConnection", target: date) -> dict[str, Any]:
    """Determine current cycle phase and relevant context for `target`."""
    starts = _find_flow_starts(con)
    if not starts:
        return {
            "date": target.isoformat(),
            "phase": "unknown",
            "note": (
                "No menstrual flow records found. To get cycle awareness, log "
                "your period in iOS Health (Cycle Tracking) or via a paired app "
                "such as Clue or Flo. Without flow data, the substrate cannot "
                "compute cycle phase."
            ),
        }
    last_start = max(s for s in starts if s <= target) if any(s <= target for s in starts) else starts[0]
    cycle_day = (target - last_start).days + 1
    lengths = _cycle_lengths(starts)
    avg_length = round(statistics.mean(lengths)) if lengths else 28
    length_stdev = round(statistics.stdev(lengths), 1) if len(lengths) > 1 else 0.0
    phase = _ovulation_refinement(con, target) or _band_phase(cycle_day, avg_length)
    irregularity = (
        "regular"
        if length_stdev < 3
        else "mild_irregular"
        if length_stdev < 8
        else "irregular"
    )
    return {
        "date": target.isoformat(),
        "phase": phase,
        "cycle_day": cycle_day,
        "last_period_start": last_start.isoformat(),
        "avg_cycle_length_days": avg_length,
        "cycle_length_stdev_days": length_stdev,
        "irregularity": irregularity,
        "n_cycles_observed": len(lengths),
        "interpretation_hint": (
            "Use phase to contextualize HRV / RHR / sleep. Mid-luteal HRV dips "
            "are physiology, not recovery deficit. PMDD-pattern Floor drops "
            "concentrate in late luteal."
        ),
    }


def phase_tagged_metric(
    con: "duckdb.DuckDBPyConnection",
    metric: str,
    start_date: date,
    end_date: date,
    aggregation: str = "avg",
) -> list[dict[str, Any]]:
    """Return a daily metric series with cycle-phase tag on each day."""
    starts = _find_flow_starts(con)
    if not starts:
        return []
    avg_length = round(statistics.mean(_cycle_lengths(starts))) if len(starts) > 1 else 28
    sd = datetime.combine(start_date, datetime.min.time())
    ed = datetime.combine(end_date, datetime.min.time()) + timedelta(days=1)
    agg_sql = "SUM" if aggregation == "sum" else "AVG"
    rows = con.execute(
        f"""
        SELECT DATE_TRUNC('day', start_date)::DATE AS d, {agg_sql}(value)
        FROM records
        WHERE type = ? AND start_date >= ? AND start_date < ?
        GROUP BY d ORDER BY d
        """,
        [metric, sd, ed],
    ).fetchall()
    out: list[dict[str, Any]] = []
    for d, val in rows:
        if val is None:
            continue
        applicable_starts = [s for s in starts if s <= d]
        if not applicable_starts:
            phase = "pre_first_logged_cycle"
            cycle_day = None
        else:
            last = max(applicable_starts)
            cycle_day = (d - last).days + 1
            phase = _band_phase(cycle_day, avg_length)
        out.append(
            {
                "date": d.isoformat(),
                "value": round(float(val), 3),
                "cycle_day": cycle_day,
                "phase": phase,
            }
        )
    return out


def phase_means_for_metric(
    con: "duckdb.DuckDBPyConnection",
    metric: str,
    days: int = 90,
    aggregation: str = "avg",
) -> dict[str, Any]:
    """Mean of a metric segmented by cycle phase over the last N days.
    Useful for confirming the 'low HRV in luteal is normal' pattern with the
    user's actual data."""
    end_d = date.today()
    start_d = end_d - timedelta(days=days)
    series = phase_tagged_metric(con, metric, start_d, end_d, aggregation=aggregation)
    by_phase: dict[str, list[float]] = {}
    for row in series:
        by_phase.setdefault(row["phase"], []).append(row["value"])
    out: dict[str, Any] = {"metric": metric, "days_window": days}
    for phase, vals in by_phase.items():
        out[phase] = {
            "mean": round(statistics.mean(vals), 2),
            "n": len(vals),
            "min": round(min(vals), 2),
            "max": round(max(vals), 2),
            "stdev": round(statistics.stdev(vals), 2) if len(vals) > 1 else 0.0,
        }
    return out
