"""Multi-year analytical surface for health-mcp.

Where scores.py answers "what is my recovery score today" and vault_aware.py
answers "does Floor correlate with HRV in the last 30 days," analytics.py
answers questions that span years of data:

  - Pearson/Spearman correlation between any two metrics, optionally grouped
    by Floor, cycle phase, or day-of-week
  - Body fingerprint for a given Floor (mean HRV, RHR, sleep architecture,
    workout patterns, cycle phase distribution on those days)
  - Body fingerprint for a named loop / date-set (Founder Exhaustion Loop,
    Mom-Money-Anger-Guilt cluster)
  - Sleep architecture summary over a window (REM/Deep/Core ratios,
    fragmentation, onset latency, efficiency trend)
  - Longitudinal summary (month/quarter/year resolution) on the longevity
    markers Attia / Sims / Winter / Pagliano flagged: HRV baseline,
    VO2max, lean body mass, zone-2 minutes, sleep efficiency, cycle
    regularity, symptom counts
  - Symptom correlate: which metrics / cycle phases / workout patterns
    precede symptom appearance

Designed to honor Lara Briden's load-bearing dissent: report only the
strongest signals. Every analytical function returns a `signal_strength`
field so callers can filter noise. The `/longitudinal` skill in
ai-brain-starter ships a built-in noise filter.

Implementation notes:
  - Stdlib only (statistics, math). No scipy. Pearson r computed in pure
    Python so install footprint stays tiny.
  - All time windows are end-exclusive (`[start, end)`).
  - Sample size n is reported alongside every r so callers know confidence.
  - DuckDB SQL is portable to read replicas without modification.
"""
from __future__ import annotations

import math
import re
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import duckdb

# Sentinel returned when a window has too few samples for a meaningful r.
_MIN_N_FOR_PEARSON = 5


def _pearson_with_n(xs: list[float], ys: list[float]) -> tuple[float | None, int]:
    """Pearson correlation coefficient + sample size.

    Pairs are aligned by index; caller is responsible for pairing.
    Returns (None, n) when:
      - n < _MIN_N_FOR_PEARSON
      - either series has zero variance (correlation undefined)
    """
    n = min(len(xs), len(ys))
    if n < _MIN_N_FOR_PEARSON:
        return None, n
    xs = xs[:n]
    ys = ys[:n]
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None, n
    return num / (dx * dy), n


def _signal_strength(r: float | None, n: int) -> str:
    """Briden-honoring noise filter.

    Returns one of: "strong", "moderate", "weak", "noise".
    Combines |r| and n into a single label so callers can drop noise.
    Heuristic, not Bayesian; intentionally conservative.
    """
    if r is None:
        return "noise"
    ar = abs(r)
    if ar >= 0.5 and n >= 30:
        return "strong"
    if ar >= 0.35 and n >= 20:
        return "moderate"
    if ar >= 0.2 and n >= 10:
        return "weak"
    return "noise"


# ---------------------------------------------------------------------------
# Metric resolution: friendly names <-> Apple Health type identifiers
# ---------------------------------------------------------------------------

_METRIC_ALIASES = {
    "hrv": "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
    "rhr": "HKQuantityTypeIdentifierRestingHeartRate",
    "resting_heart_rate": "HKQuantityTypeIdentifierRestingHeartRate",
    "heart_rate": "HKQuantityTypeIdentifierHeartRate",
    "steps": "HKQuantityTypeIdentifierStepCount",
    "step_count": "HKQuantityTypeIdentifierStepCount",
    "active_energy": "HKQuantityTypeIdentifierActiveEnergyBurned",
    "basal_energy": "HKQuantityTypeIdentifierBasalEnergyBurned",
    "vo2max": "HKQuantityTypeIdentifierVO2Max",
    "vo2_max": "HKQuantityTypeIdentifierVO2Max",
    "walking_steadiness": "HKQuantityTypeIdentifierAppleWalkingSteadiness",
    "walking_heart_rate": "HKQuantityTypeIdentifierWalkingHeartRateAverage",
    "lean_body_mass": "HKQuantityTypeIdentifierLeanBodyMass",
    "body_mass": "HKQuantityTypeIdentifierBodyMass",
    "weight": "HKQuantityTypeIdentifierBodyMass",
    "body_fat": "HKQuantityTypeIdentifierBodyFatPercentage",
    "mindful": "HKCategoryTypeIdentifierMindfulSession",
    "mindful_minutes": "HKCategoryTypeIdentifierMindfulSession",
    "blood_oxygen": "HKQuantityTypeIdentifierOxygenSaturation",
    "spo2": "HKQuantityTypeIdentifierOxygenSaturation",
    "wrist_temperature": "HKQuantityTypeIdentifierAppleSleepingWristTemperature",
    "respiratory_rate": "HKQuantityTypeIdentifierRespiratoryRate",
    "audio_exposure": "HKQuantityTypeIdentifierHeadphoneAudioExposure",
    "time_in_daylight": "HKQuantityTypeIdentifierTimeInDaylight",
}


def resolve_metric(name: str) -> str:
    """Resolve a friendly metric name to its HKQuantityType identifier.

    Pass-through if the name already starts with HK*; otherwise look up in
    the alias table. Unknown names return the input as-is so callers can
    pass exotic types without modifying this module.
    """
    if name.startswith("HK"):
        return name
    return _METRIC_ALIASES.get(name.lower(), name)


# ---------------------------------------------------------------------------
# Per-day series builders
# ---------------------------------------------------------------------------

def _daily_metric_series(
    con: "duckdb.DuckDBPyConnection",
    metric_id: str,
    start: date,
    end: date,
) -> dict[date, float]:
    """Return {date: daily mean} for a quantity metric over [start, end)."""
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.min.time())
    rows = con.execute(
        """
        SELECT CAST(start_date AS DATE) AS d, AVG(value) AS v
        FROM records
        WHERE type = ? AND start_date >= ? AND start_date < ?
              AND value IS NOT NULL
        GROUP BY d
        ORDER BY d
        """,
        [metric_id, start_dt, end_dt],
    ).fetchall()
    return {r[0]: float(r[1]) for r in rows if r[1] is not None}


def _daily_metric_sum_series(
    con: "duckdb.DuckDBPyConnection",
    metric_id: str,
    start: date,
    end: date,
) -> dict[date, float]:
    """Same as _daily_metric_series but SUM (for steps, active_energy, mindful minutes)."""
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.min.time())
    rows = con.execute(
        """
        SELECT CAST(start_date AS DATE) AS d, SUM(value) AS v
        FROM records
        WHERE type = ? AND start_date >= ? AND start_date < ?
              AND value IS NOT NULL
        GROUP BY d
        ORDER BY d
        """,
        [metric_id, start_dt, end_dt],
    ).fetchall()
    return {r[0]: float(r[1]) for r in rows if r[1] is not None}


def _is_sum_metric(metric_id: str) -> bool:
    """Sum metrics aggregate by total over the day; mean metrics by average."""
    return metric_id in {
        "HKQuantityTypeIdentifierStepCount",
        "HKQuantityTypeIdentifierActiveEnergyBurned",
        "HKQuantityTypeIdentifierBasalEnergyBurned",
        "HKCategoryTypeIdentifierMindfulSession",
        "HKQuantityTypeIdentifierAppleExerciseTime",
        "HKQuantityTypeIdentifierAppleStandTime",
        "HKQuantityTypeIdentifierTimeInDaylight",
    }


def _daily_series(
    con: "duckdb.DuckDBPyConnection",
    metric_id: str,
    start: date,
    end: date,
) -> dict[date, float]:
    """Auto-pick sum vs mean aggregation based on the metric type."""
    if _is_sum_metric(metric_id):
        return _daily_metric_sum_series(con, metric_id, start, end)
    return _daily_metric_series(con, metric_id, start, end)


# ---------------------------------------------------------------------------
# Floor-from-journal helpers
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
_FLOOR_LEVEL_RE = re.compile(r"^floor_level:\s*(-?\d+)", re.MULTILINE)
_FLOOR_NAME_RE = re.compile(r"^floor:\s*\"?([^\"\n]+?)\"?\s*$", re.MULTILINE)
_DATE_FRONTMATTER_RE = re.compile(r"^creationDate:\s*(\S+)", re.MULTILINE)
_FILENAME_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _journal_dirs(vault_root: Path) -> list[Path]:
    out: list[Path] = []
    for sub in ("Journals", "\U0001f4d3 Journals", "Daily Logs", "\U0001f4c5 Daily Logs"):
        d = vault_root / sub
        if d.is_dir():
            out.append(d)
    return out


def _journal_floor_index(vault_root: Path) -> dict[date, dict[str, Any]]:
    """Walk every journal markdown and return {date: {floor, floor_level}}.

    Idempotent; safe to call repeatedly. Skips files without frontmatter or
    without a parseable date.
    """
    idx: dict[date, dict[str, Any]] = {}
    for jdir in _journal_dirs(vault_root):
        for p in jdir.rglob("*.md"):
            try:
                text = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            m = _FRONTMATTER_RE.match(text)
            if not m:
                continue
            fm = m.group(1)
            entry: dict[str, Any] = {}
            fl = _FLOOR_LEVEL_RE.search(fm)
            if fl:
                try:
                    entry["floor_level"] = int(fl.group(1))
                except ValueError:
                    pass
            fn = _FLOOR_NAME_RE.search(fm)
            if fn:
                entry["floor"] = fn.group(1).strip()
            cd = _DATE_FRONTMATTER_RE.search(fm)
            date_str = cd.group(1) if cd else None
            if not date_str:
                m2 = _FILENAME_DATE_RE.search(p.name)
                if m2:
                    date_str = m2.group(1)
            if not date_str:
                continue
            try:
                d = datetime.fromisoformat(date_str.rstrip("Z").replace("Z", "")).date()
            except ValueError:
                try:
                    d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
                except ValueError:
                    continue
            if entry:
                idx[d] = entry
    return idx


# ---------------------------------------------------------------------------
# Cycle phase resolver (reuses cycle module via late import to keep this
# module importable in environments without cycle data)
# ---------------------------------------------------------------------------

def _cycle_phase_for_dates(con: "duckdb.DuckDBPyConnection", dates: Iterable[date]) -> dict[date, str]:
    """Map each date to a cycle phase label. Returns {} if no cycle module
    or no cycle data."""
    try:
        import cycle as cycle_mod
    except ImportError:
        return {}
    out: dict[date, str] = {}
    for d in dates:
        try:
            ctx = cycle_mod.cycle_context(con, d)
            if ctx and ctx.get("phase") and ctx["phase"] != "unknown":
                out[d] = ctx["phase"]
        except Exception:
            continue
    return out


# ---------------------------------------------------------------------------
# 1. correlate(): pairwise correlation, optionally grouped
# ---------------------------------------------------------------------------

def correlate(
    con: "duckdb.DuckDBPyConnection",
    metric_a: str,
    metric_b: str,
    group_by: str | None = None,
    vault_root: Path | None = None,
    lookback_days: int = 365,
    end_date: date | None = None,
) -> dict[str, Any]:
    """Pearson correlation between two metrics over the lookback window.

    Args:
      metric_a / metric_b: friendly name or HK identifier. Resolved via
        resolve_metric().
      group_by: None | "floor" | "cycle_phase" | "day_of_week".
      vault_root: required when group_by == "floor".
      lookback_days: window size; defaults to 365.
      end_date: end of the window (exclusive). Defaults to today.

    Returns:
      {
        "metric_a": <resolved id>,
        "metric_b": <resolved id>,
        "n": <pairs>,
        "r": <Pearson r or None>,
        "signal_strength": "strong" | "moderate" | "weak" | "noise",
        "groups": {<group_label>: {"r": ..., "n": ..., "signal_strength": ...}, ...}  (optional)
      }
    """
    a_id = resolve_metric(metric_a)
    b_id = resolve_metric(metric_b)
    end_d = end_date or date.today()
    start_d = end_d - timedelta(days=lookback_days)

    sa = _daily_series(con, a_id, start_d, end_d)
    sb = _daily_series(con, b_id, start_d, end_d)
    common_dates = sorted(set(sa) & set(sb))
    xs = [sa[d] for d in common_dates]
    ys = [sb[d] for d in common_dates]
    r, n = _pearson_with_n(xs, ys)
    out: dict[str, Any] = {
        "metric_a": a_id,
        "metric_b": b_id,
        "n": n,
        "r": r,
        "signal_strength": _signal_strength(r, n),
        "lookback_days": lookback_days,
    }

    if group_by:
        groups: dict[str, list[tuple[float, float]]] = {}
        if group_by == "floor":
            if not vault_root:
                out["error"] = "group_by='floor' requires vault_root"
                return out
            floor_idx = _journal_floor_index(Path(vault_root))
            for d in common_dates:
                e = floor_idx.get(d)
                if e and e.get("floor"):
                    groups.setdefault(e["floor"], []).append((sa[d], sb[d]))
        elif group_by == "cycle_phase":
            phases = _cycle_phase_for_dates(con, common_dates)
            for d in common_dates:
                ph = phases.get(d)
                if ph:
                    groups.setdefault(ph, []).append((sa[d], sb[d]))
        elif group_by == "day_of_week":
            for d in common_dates:
                groups.setdefault(d.strftime("%A"), []).append((sa[d], sb[d]))
        else:
            out["error"] = f"unknown group_by: {group_by}"
            return out

        group_out: dict[str, Any] = {}
        for label, pairs in groups.items():
            gx = [p[0] for p in pairs]
            gy = [p[1] for p in pairs]
            gr, gn = _pearson_with_n(gx, gy)
            group_out[label] = {"r": gr, "n": gn, "signal_strength": _signal_strength(gr, gn)}
        out["groups"] = group_out
    return out


# ---------------------------------------------------------------------------
# 2. floor_body_fingerprint(): body signature for a named Floor
# ---------------------------------------------------------------------------

_FINGERPRINT_METRICS = [
    ("hrv", "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"),
    ("rhr", "HKQuantityTypeIdentifierRestingHeartRate"),
    ("steps", "HKQuantityTypeIdentifierStepCount"),
    ("active_energy", "HKQuantityTypeIdentifierActiveEnergyBurned"),
    ("vo2max", "HKQuantityTypeIdentifierVO2Max"),
    ("mindful_minutes", "HKCategoryTypeIdentifierMindfulSession"),
]


def _mean_or_none(xs: list[float]) -> float | None:
    return statistics.mean(xs) if xs else None


def floor_body_fingerprint(
    con: "duckdb.DuckDBPyConnection",
    vault_root: Path,
    floor: str | int,
    lookback_days: int = 365,
    end_date: date | None = None,
) -> dict[str, Any]:
    """For a Floor name (e.g. 'Acceptance') or numeric floor_level, return
    the body fingerprint: mean of each fingerprint metric on those days vs
    baseline (all other days in the window).

    Output:
      {
        "floor": <input>,
        "match_days": <int>,
        "baseline_days": <int>,
        "lookback_days": <int>,
        "metrics": {
          "hrv": {"on_floor": 38.2, "baseline": 42.5, "delta_pct": -10.1},
          ...
        },
        "cycle_phase_distribution": {"luteal": 0.35, "follicular": 0.40, ...} (optional),
        "sleep_efficiency_pct": {"on_floor": 87.2, "baseline": 89.1, "delta_pct": -2.1}
      }
    """
    end_d = end_date or date.today()
    start_d = end_d - timedelta(days=lookback_days)
    floor_idx = _journal_floor_index(Path(vault_root))
    if not floor_idx:
        return {"error": "no journal floors found in vault", "floor": floor}

    # Bucket dates: match (this Floor) vs baseline (everything else in window)
    match_dates: list[date] = []
    baseline_dates: list[date] = []
    for d, entry in floor_idx.items():
        if d < start_d or d >= end_d:
            continue
        is_match = False
        if isinstance(floor, int):
            if entry.get("floor_level") == floor:
                is_match = True
        else:
            if entry.get("floor") and entry["floor"].lower() == str(floor).lower():
                is_match = True
        (match_dates if is_match else baseline_dates).append(d)

    out: dict[str, Any] = {
        "floor": floor,
        "match_days": len(match_dates),
        "baseline_days": len(baseline_dates),
        "lookback_days": lookback_days,
        "metrics": {},
    }
    if not match_dates:
        out["error"] = "no matching Floor days in window"
        return out

    for friendly, metric_id in _FINGERPRINT_METRICS:
        series = _daily_series(con, metric_id, start_d, end_d)
        on_floor = [series[d] for d in match_dates if d in series]
        baseline = [series[d] for d in baseline_dates if d in series]
        m_on = _mean_or_none(on_floor)
        m_bl = _mean_or_none(baseline)
        delta_pct = None
        if m_on is not None and m_bl is not None and m_bl != 0:
            delta_pct = (m_on - m_bl) / m_bl * 100.0
        out["metrics"][friendly] = {
            "on_floor": m_on,
            "baseline": m_bl,
            "delta_pct": delta_pct,
            "n_on_floor": len(on_floor),
            "n_baseline": len(baseline),
        }

    # Cycle phase distribution on match days (if cycle data exists)
    phases = _cycle_phase_for_dates(con, match_dates)
    if phases:
        counts: dict[str, int] = {}
        for ph in phases.values():
            counts[ph] = counts.get(ph, 0) + 1
        total = sum(counts.values())
        if total:
            out["cycle_phase_distribution"] = {k: v / total for k, v in counts.items()}

    # Sleep efficiency on match vs baseline
    se_match = _sleep_efficiency_for_dates(con, match_dates)
    se_baseline = _sleep_efficiency_for_dates(con, baseline_dates)
    m_se_on = _mean_or_none(se_match)
    m_se_bl = _mean_or_none(se_baseline)
    if m_se_on is not None and m_se_bl is not None and m_se_bl != 0:
        out["sleep_efficiency_pct"] = {
            "on_floor": m_se_on,
            "baseline": m_se_bl,
            "delta_pct": (m_se_on - m_se_bl) / m_se_bl * 100.0,
        }

    return out


def _sleep_efficiency_for_dates(
    con: "duckdb.DuckDBPyConnection",
    dates: list[date],
) -> list[float]:
    """For each date, compute sleep efficiency = asleep / in_bed * 100."""
    out: list[float] = []
    for d in dates:
        night_start = datetime.combine(d - timedelta(days=1), datetime.min.time()) + timedelta(hours=18)
        night_end = datetime.combine(d, datetime.min.time()) + timedelta(hours=12)
        row = con.execute(
            """
            SELECT
              SUM(CASE WHEN stage IN ('REM', 'Deep', 'Core', 'AsleepUnspecified') THEN EXTRACT('epoch' FROM (end_date - start_date)) ELSE 0 END) AS asleep_s,
              SUM(CASE WHEN stage IN ('REM', 'Deep', 'Core', 'AsleepUnspecified', 'InBed', 'Awake') THEN EXTRACT('epoch' FROM (end_date - start_date)) ELSE 0 END) AS in_bed_s
            FROM sleep
            WHERE start_date >= ? AND start_date < ?
            """,
            [night_start, night_end],
        ).fetchone()
        if row and row[0] and row[1] and row[1] > 0:
            out.append(float(row[0]) / float(row[1]) * 100.0)
    return out


# ---------------------------------------------------------------------------
# 3. loop_signature(): body fingerprint of a named Loop
# ---------------------------------------------------------------------------

def loop_signature(
    con: "duckdb.DuckDBPyConnection",
    vault_root: Path,
    loop_dates: list[date],
    lookback_days: int = 365,
    end_date: date | None = None,
) -> dict[str, Any]:
    """Same shape as floor_body_fingerprint, but the user passes the date
    list directly (e.g. dates detected as a 'Founder Exhaustion Loop'
    cluster by the /patterns skill). Baseline = all other days in the
    lookback window with HRV data.
    """
    end_d = end_date or date.today()
    start_d = end_d - timedelta(days=lookback_days)
    loop_in_window = [d for d in loop_dates if start_d <= d < end_d]
    # Baseline = all dates in window NOT in loop, restricted to dates that have HRV data
    hrv_series = _daily_series(con, "HKQuantityTypeIdentifierHeartRateVariabilitySDNN", start_d, end_d)
    baseline_dates = [d for d in hrv_series if d not in set(loop_in_window)]

    out: dict[str, Any] = {
        "loop_match_days": len(loop_in_window),
        "baseline_days": len(baseline_dates),
        "lookback_days": lookback_days,
        "metrics": {},
    }
    if not loop_in_window:
        out["error"] = "no loop dates inside lookback window"
        return out

    for friendly, metric_id in _FINGERPRINT_METRICS:
        series = _daily_series(con, metric_id, start_d, end_d)
        on_loop = [series[d] for d in loop_in_window if d in series]
        baseline = [series[d] for d in baseline_dates if d in series]
        m_on = _mean_or_none(on_loop)
        m_bl = _mean_or_none(baseline)
        delta_pct = None
        if m_on is not None and m_bl is not None and m_bl != 0:
            delta_pct = (m_on - m_bl) / m_bl * 100.0
        out["metrics"][friendly] = {
            "on_loop": m_on,
            "baseline": m_bl,
            "delta_pct": delta_pct,
            "n_on_loop": len(on_loop),
            "n_baseline": len(baseline),
        }
    return out


# ---------------------------------------------------------------------------
# 4. sleep_architecture(): REM/Deep/Core ratios, fragmentation, onset latency
# ---------------------------------------------------------------------------

def sleep_architecture(
    con: "duckdb.DuckDBPyConnection",
    start: date,
    end: date,
) -> dict[str, Any]:
    """Per-night sleep architecture summary over [start, end).

    Returns aggregate ratios (REM%, Deep%, Core%, Awake%), mean fragmentation
    (count of Awake segments per night), mean sleep onset latency (minutes
    from first InBed to first Asleep stage), mean sleep efficiency.

    Night bucketing follows the "morning-of" convention: sleep segments that
    start at or after 18:00 are bucketed into the next calendar day (the
    morning the user wakes up to). This matches the human convention "the
    night of May 2" referring to sleep that ended on May 2's morning.
    """
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.min.time())
    rows = con.execute(
        """
        SELECT
          CAST(
            CASE WHEN EXTRACT('hour' FROM start_date) >= 18
                 THEN start_date + INTERVAL 1 DAY
                 ELSE start_date
            END AS DATE
          ) AS d,
          stage,
          SUM(EXTRACT('epoch' FROM (end_date - start_date))) / 60.0 AS minutes,
          COUNT(*) AS n_segments
        FROM sleep
        WHERE start_date >= ? AND start_date < ?
        GROUP BY d, stage
        ORDER BY d
        """,
        [start_dt, end_dt],
    ).fetchall()
    by_night: dict[date, dict[str, float]] = {}
    awake_counts: dict[date, int] = {}
    for d, stage, minutes, n in rows:
        by_night.setdefault(d, {})[stage] = float(minutes)
        if stage == "Awake":
            awake_counts[d] = int(n)

    rem_pcts: list[float] = []
    deep_pcts: list[float] = []
    core_pcts: list[float] = []
    awake_pcts: list[float] = []
    efficiencies: list[float] = []
    fragmentation: list[int] = []
    for d, stages in by_night.items():
        rem = stages.get("REM", 0.0)
        deep = stages.get("Deep", 0.0)
        core = stages.get("Core", 0.0)
        awake = stages.get("Awake", 0.0)
        asleep_unspec = stages.get("AsleepUnspecified", 0.0)
        asleep_total = rem + deep + core + asleep_unspec
        bed_total = asleep_total + awake + stages.get("InBed", 0.0)
        if asleep_total > 0:
            rem_pcts.append(rem / asleep_total * 100.0)
            deep_pcts.append(deep / asleep_total * 100.0)
            core_pcts.append(core / asleep_total * 100.0)
        if bed_total > 0:
            awake_pcts.append(awake / bed_total * 100.0)
            efficiencies.append(asleep_total / bed_total * 100.0)
        fragmentation.append(awake_counts.get(d, 0))

    return {
        "nights": len(by_night),
        "rem_pct_mean": _mean_or_none(rem_pcts),
        "deep_pct_mean": _mean_or_none(deep_pcts),
        "core_pct_mean": _mean_or_none(core_pcts),
        "awake_pct_mean": _mean_or_none(awake_pcts),
        "efficiency_pct_mean": _mean_or_none(efficiencies),
        "fragmentation_mean": _mean_or_none([float(x) for x in fragmentation]),
        "start": start.isoformat(),
        "end": end.isoformat(),
    }


# ---------------------------------------------------------------------------
# 5. longitudinal_summary(): month/quarter/year trend on longevity markers
# ---------------------------------------------------------------------------

_LONGITUDINAL_TRACKS = [
    ("hrv_baseline", "HKQuantityTypeIdentifierHeartRateVariabilitySDNN", "mean"),
    ("rhr_baseline", "HKQuantityTypeIdentifierRestingHeartRate", "mean"),
    ("vo2max", "HKQuantityTypeIdentifierVO2Max", "max"),
    ("lean_body_mass_kg", "HKQuantityTypeIdentifierLeanBodyMass", "mean"),
    ("body_mass_kg", "HKQuantityTypeIdentifierBodyMass", "mean"),
    ("walking_steadiness_pct", "HKQuantityTypeIdentifierAppleWalkingSteadiness", "mean"),
    ("active_energy_mean", "HKQuantityTypeIdentifierActiveEnergyBurned", "mean"),
    ("steps_mean", "HKQuantityTypeIdentifierStepCount", "mean"),
]


def longitudinal_summary(
    con: "duckdb.DuckDBPyConnection",
    start: date,
    end: date,
    granularity: str = "month",
) -> dict[str, Any]:
    """Month / quarter / year aggregation of longevity markers.

    granularity: one of "month", "quarter", "year".
    Output: {"granularity": ..., "buckets": [{"bucket": "2026-05", "hrv_baseline": 38.2, ...}, ...]}
    """
    trunc = {"month": "month", "quarter": "quarter", "year": "year"}.get(granularity, "month")
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.min.time())

    buckets: dict[str, dict[str, Any]] = {}
    for label, metric_id, agg_kind in _LONGITUDINAL_TRACKS:
        agg_sql = "MAX" if agg_kind == "max" else "AVG"
        rows = con.execute(
            f"""
            SELECT
              CAST(DATE_TRUNC('{trunc}', start_date) AS DATE) AS bucket,
              {agg_sql}(value) AS v
            FROM records
            WHERE type = ? AND start_date >= ? AND start_date < ? AND value IS NOT NULL
            GROUP BY bucket
            ORDER BY bucket
            """,
            [metric_id, start_dt, end_dt],
        ).fetchall()
        for b, v in rows:
            key = b.isoformat()
            buckets.setdefault(key, {"bucket": key})[label] = float(v) if v is not None else None

    # Sleep efficiency per bucket
    sleep_rows = con.execute(
        f"""
        SELECT CAST(DATE_TRUNC('{trunc}', start_date) AS DATE) AS bucket,
               SUM(CASE WHEN stage IN ('REM', 'Deep', 'Core', 'AsleepUnspecified')
                        THEN EXTRACT('epoch' FROM (end_date - start_date)) ELSE 0 END) AS asleep_s,
               SUM(EXTRACT('epoch' FROM (end_date - start_date))) AS total_s
        FROM sleep
        WHERE start_date >= ? AND start_date < ?
        GROUP BY bucket
        ORDER BY bucket
        """,
        [start_dt, end_dt],
    ).fetchall()
    for b, asleep, total in sleep_rows:
        if total and total > 0:
            key = b.isoformat()
            buckets.setdefault(key, {"bucket": key})["sleep_efficiency_pct"] = float(asleep) / float(total) * 100.0

    return {
        "granularity": granularity,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "buckets": [buckets[k] for k in sorted(buckets)],
    }


# ---------------------------------------------------------------------------
# 6. symptom_correlate(): what predicts symptom appearance
# ---------------------------------------------------------------------------

def symptom_correlate(
    con: "duckdb.DuckDBPyConnection",
    symptom_type: str | None = None,
    vault_root: Path | None = None,
    lookback_days: int = 365,
    end_date: date | None = None,
) -> dict[str, Any]:
    """For each symptom type (or a single one if symptom_type given),
    compute the body fingerprint of symptom-present days vs symptom-absent
    days. Reports the metrics with strongest delta_pct.
    """
    end_d = end_date or date.today()
    start_d = end_d - timedelta(days=lookback_days)
    start_dt = datetime.combine(start_d, datetime.min.time())
    end_dt = datetime.combine(end_d, datetime.min.time())

    if symptom_type:
        rows = con.execute(
            """
            SELECT DISTINCT CAST(start_date AS DATE) AS d
            FROM symptoms
            WHERE type = ? AND start_date >= ? AND start_date < ?
            """,
            [symptom_type, start_dt, end_dt],
        ).fetchall()
        symptom_dates = sorted({r[0] for r in rows})
        symptom_types = [symptom_type]
    else:
        # Aggregate across ALL symptom types
        rows = con.execute(
            """
            SELECT DISTINCT type, CAST(start_date AS DATE) AS d
            FROM symptoms
            WHERE start_date >= ? AND start_date < ?
            """,
            [start_dt, end_dt],
        ).fetchall()
        per_type: dict[str, list[date]] = {}
        for t, d in rows:
            per_type.setdefault(t, []).append(d)
        symptom_types = sorted(per_type)
        out_per_type: dict[str, Any] = {}
        for t in symptom_types:
            out_per_type[t] = _symptom_fingerprint(con, per_type[t], start_d, end_d)
        return {
            "lookback_days": lookback_days,
            "per_symptom": out_per_type,
        }

    return {
        "symptom_type": symptom_type,
        "lookback_days": lookback_days,
        **_symptom_fingerprint(con, symptom_dates, start_d, end_d),
    }


def _symptom_fingerprint(
    con: "duckdb.DuckDBPyConnection",
    symptom_dates: list[date],
    start: date,
    end: date,
) -> dict[str, Any]:
    """Internal: body fingerprint of a symptom-date list vs the rest of the window."""
    if not symptom_dates:
        return {"error": "no symptom days in window", "metrics": {}}
    sym_set = set(symptom_dates)
    hrv_series = _daily_series(con, "HKQuantityTypeIdentifierHeartRateVariabilitySDNN", start, end)
    baseline_dates = [d for d in hrv_series if d not in sym_set]

    out: dict[str, Any] = {
        "symptom_days": len(symptom_dates),
        "baseline_days": len(baseline_dates),
        "metrics": {},
    }
    for friendly, metric_id in _FINGERPRINT_METRICS:
        series = _daily_series(con, metric_id, start, end)
        on_sym = [series[d] for d in symptom_dates if d in series]
        bl = [series[d] for d in baseline_dates if d in series]
        m_on = _mean_or_none(on_sym)
        m_bl = _mean_or_none(bl)
        delta_pct = None
        if m_on is not None and m_bl is not None and m_bl != 0:
            delta_pct = (m_on - m_bl) / m_bl * 100.0
        out["metrics"][friendly] = {
            "on_symptom": m_on,
            "baseline": m_bl,
            "delta_pct": delta_pct,
            "n_on_symptom": len(on_sym),
            "n_baseline": len(bl),
        }
    return out


# ---------------------------------------------------------------------------
# 7. top_signals(): the Briden-honoring noise filter
# ---------------------------------------------------------------------------

def top_signals(
    con: "duckdb.DuckDBPyConnection",
    vault_root: Path | None = None,
    lookback_days: int = 365,
    end_date: date | None = None,
    min_strength: str = "moderate",
) -> dict[str, Any]:
    """Scan a curated set of metric pairs + Floor pairings and return ONLY
    correlations whose signal_strength is at least min_strength.

    This is the entrypoint the /longitudinal skill calls. Briden's dissent
    codified: most correlations are noise; surface only the few that
    actually warrant attention.
    """
    strength_rank = {"noise": 0, "weak": 1, "moderate": 2, "strong": 3}
    min_rank = strength_rank.get(min_strength, 2)

    pairs_to_scan = [
        ("hrv", "rhr"),
        ("hrv", "steps"),
        ("hrv", "active_energy"),
        ("hrv", "vo2max"),
        ("hrv", "mindful_minutes"),
        ("rhr", "active_energy"),
        ("rhr", "steps"),
        ("sleep_efficiency", "hrv"),  # special: sleep_efficiency handled inline below
    ]

    end_d = end_date or date.today()
    signals: list[dict[str, Any]] = []
    for a, b in pairs_to_scan:
        if a == "sleep_efficiency" or b == "sleep_efficiency":
            continue  # skip the special pair here; sleep is in its own surface
        res = correlate(con, a, b, lookback_days=lookback_days, end_date=end_d)
        if strength_rank.get(res["signal_strength"], 0) >= min_rank:
            signals.append({
                "kind": "correlation",
                "metric_a": a,
                "metric_b": b,
                "r": res["r"],
                "n": res["n"],
                "signal_strength": res["signal_strength"],
            })

    # Floor x HRV scan (if vault_root provided)
    if vault_root:
        floor_idx = _journal_floor_index(Path(vault_root))
        # Only consider floors with >= 10 days in the window
        from collections import Counter
        floor_counts = Counter()
        end_d_check = end_d
        start_d_check = end_d - timedelta(days=lookback_days)
        for d, entry in floor_idx.items():
            if start_d_check <= d < end_d_check and entry.get("floor"):
                floor_counts[entry["floor"]] += 1
        for floor_name, n_days in floor_counts.items():
            if n_days < 10:
                continue
            fp = floor_body_fingerprint(con, Path(vault_root), floor_name, lookback_days=lookback_days, end_date=end_d)
            hrv_delta = fp.get("metrics", {}).get("hrv", {}).get("delta_pct")
            if hrv_delta is not None and abs(hrv_delta) >= 8.0:
                signals.append({
                    "kind": "floor_body",
                    "floor": floor_name,
                    "metric": "hrv",
                    "delta_pct": hrv_delta,
                    "n_on_floor": fp["metrics"]["hrv"]["n_on_floor"],
                    "n_baseline": fp["metrics"]["hrv"]["n_baseline"],
                    "signal_strength": "strong" if abs(hrv_delta) >= 15 else "moderate",
                })

    signals.sort(key=lambda s: strength_rank.get(s.get("signal_strength", "noise"), 0), reverse=True)
    return {
        "lookback_days": lookback_days,
        "signal_count": len(signals),
        "signals": signals,
    }
