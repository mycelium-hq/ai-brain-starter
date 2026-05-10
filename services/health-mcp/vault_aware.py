"""Vault-aware tools: read journal frontmatter, correlate biometrics with
Floor (emotional consciousness) tags, surface health context for daily-journal,
coaching, advisory-panel, and insights skills.

These are the substrate-differentiating tools — no other Apple Health MCP has
them, because no other Apple Health MCP knows about Obsidian Floor frontmatter.

vault_root semantics:
  Caller passes the absolute path to their personal vault. The MCP NEVER
  WRITES to vault. Only reads.

  Floor frontmatter is expected in journals at <vault>/Journals/ or
  <vault>/📓 Journals/. The MCP looks for `floor_level: <int>` and/or
  `floor: <str>` and `creationDate: <ISO>` (or filename pattern YYYY-MM-DD).

Pearson r is computed in stdlib (no scipy dep) so install footprint stays
tiny. Sample size is reported alongside r so callers know the confidence.
"""
from __future__ import annotations

import math
import re
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
_FLOOR_LEVEL_RE = re.compile(r"^floor_level:\s*(-?\d+)", re.MULTILINE)
_FLOOR_NAME_RE = re.compile(r"^floor:\s*\"?([^\"\n]+?)\"?\s*$", re.MULTILINE)
_DATE_RE = re.compile(r"^creationDate:\s*(\S+)", re.MULTILINE)
_FILENAME_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _journal_dirs(vault_root: Path) -> list[Path]:
    """Find candidate journal directories. Looks for both bare and emoji forms."""
    candidates: list[Path] = []
    for sub in ("Journals", "📓 Journals", "Daily Logs", "📅 Daily Logs"):
        d = vault_root / sub
        if d.is_dir():
            candidates.append(d)
    return candidates


def _read_frontmatter(p: Path) -> dict[str, Any] | None:
    """Read floor_level / floor / creationDate from a markdown file's
    frontmatter. Returns None if no frontmatter or no Floor tag."""
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    fm = m.group(1)
    out: dict[str, Any] = {}
    fl = _FLOOR_LEVEL_RE.search(fm)
    if fl:
        try:
            out["floor_level"] = int(fl.group(1))
        except ValueError:
            pass
    fn = _FLOOR_NAME_RE.search(fm)
    if fn:
        out["floor"] = fn.group(1).strip()
    cd = _DATE_RE.search(fm)
    date_str = cd.group(1) if cd else None
    if not date_str:
        m2 = _FILENAME_DATE_RE.search(p.name)
        if m2:
            date_str = m2.group(1)
    if date_str:
        try:
            out["date"] = datetime.fromisoformat(date_str.rstrip("Z").replace("Z", "")).date()
        except ValueError:
            try:
                out["date"] = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            except ValueError:
                return None
    if "date" not in out or ("floor_level" not in out and "floor" not in out):
        return None
    return out


def _floor_tagged_dates(vault_root: Path, days: int) -> list[dict[str, Any]]:
    """Return list of {date, floor_level, floor} for journal entries in the
    last N days that have a Floor tag."""
    cutoff = date.today() - timedelta(days=days)
    out: list[dict[str, Any]] = []
    for d in _journal_dirs(vault_root):
        for p in d.rglob("*.md"):
            fm = _read_frontmatter(p)
            if not fm or fm.get("date") is None or fm["date"] < cutoff:
                continue
            out.append(
                {
                    "date": fm["date"],
                    "floor_level": fm.get("floor_level"),
                    "floor": fm.get("floor"),
                    "path": str(p),
                }
            )
    return out


def _pearson(xs: list[float], ys: list[float]) -> tuple[float, int]:
    """Pearson correlation coefficient. Returns (r, n)."""
    paired = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(paired)
    if n < 3:
        return 0.0, n
    xs2 = [p[0] for p in paired]
    ys2 = [p[1] for p in paired]
    mx = statistics.mean(xs2)
    my = statistics.mean(ys2)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs2))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys2))
    if sx == 0 or sy == 0:
        return 0.0, n
    cov = sum((x - mx) * (y - my) for x, y in paired)
    return cov / (sx * sy), n


def journal_context(con: "duckdb.DuckDBPyConnection", target: date) -> dict[str, Any]:
    """24h roll-up for the daily-journal skill.

    Returns: HRV (mean), RHR, sleep duration + efficiency + score, total steps,
    workouts (count + minutes), mindful minutes.
    """
    start = datetime.combine(target, datetime.min.time())
    end = start + timedelta(days=1)
    row = con.execute(
        """
        SELECT
          (SELECT AVG(value) FROM records
            WHERE type = 'HKQuantityTypeIdentifierHeartRateVariabilitySDNN'
              AND start_date >= ? AND start_date < ?) AS hrv_mean,
          (SELECT AVG(value) FROM records
            WHERE type = 'HKQuantityTypeIdentifierRestingHeartRate'
              AND start_date >= ? AND start_date < ?) AS rhr_mean,
          (SELECT SUM(value) FROM records
            WHERE type = 'HKQuantityTypeIdentifierStepCount'
              AND start_date >= ? AND start_date < ?) AS steps_total,
          (SELECT COUNT(*) FROM workouts
            WHERE start_date >= ? AND start_date < ?) AS workout_count,
          (SELECT COALESCE(SUM(duration_min), 0) FROM workouts
            WHERE start_date >= ? AND start_date < ?) AS workout_min,
          (SELECT COALESCE(SUM(EXTRACT(EPOCH FROM (end_date - start_date))) / 60.0, 0)
            FROM records
            WHERE type = 'HKCategoryTypeIdentifierMindfulSession'
              AND start_date >= ? AND start_date < ?) AS mindful_min
        """,
        [start, end] * 6,
    ).fetchone()
    from scores import _sleep_for_date

    sleep = _sleep_for_date(con, target)
    return {
        "date": target.isoformat(),
        "hrv_ms": round(float(row[0]), 1) if row[0] is not None else None,
        "rhr_bpm": round(float(row[1]), 1) if row[1] is not None else None,
        "steps_total": int(row[2]) if row[2] is not None else 0,
        "workout_count": int(row[3]) if row[3] is not None else 0,
        "workout_min": round(float(row[4])) if row[4] is not None else 0,
        "mindful_min": round(float(row[5])) if row[5] is not None else 0,
        "sleep_asleep_min": round(sleep["asleep_min"]),
        "sleep_efficiency": round(sleep["efficiency"], 3),
        "sleep_rem_min": round(sleep["rem_min"]),
        "sleep_deep_min": round(sleep["deep_min"]),
    }


def floor_correlation(
    con: "duckdb.DuckDBPyConnection",
    metric: str,
    days: int,
    vault_root: Path,
) -> dict[str, Any]:
    """Correlate a daily biometric with Floor (emotional level) tags from the
    user's journal frontmatter.

    Returns Pearson r between metric_value and floor_level. For callers using
    bare floor names without numeric levels, returns per-floor means.
    """
    tagged = _floor_tagged_dates(vault_root, days=days)
    if not tagged:
        return {
            "metric": metric,
            "n": 0,
            "note": f"No floor-tagged journals found in the last {days} days under {vault_root}. "
            "Floor tags are expected in journal frontmatter as `floor_level: <int>` and/or `floor: <name>`.",
        }
    starts = [datetime.combine(t["date"], datetime.min.time()) for t in tagged]
    starts_sorted = sorted(set(starts))
    if not starts_sorted:
        return {"metric": metric, "n": 0, "note": "no overlapping dates"}
    min_d = min(starts_sorted)
    max_d = max(starts_sorted) + timedelta(days=1)
    sum_metrics = {"HKQuantityTypeIdentifierStepCount", "HKQuantityTypeIdentifierActiveEnergyBurned"}
    agg = "SUM" if metric in sum_metrics else "AVG"
    rows = con.execute(
        f"""
        SELECT DATE_TRUNC('day', start_date)::DATE AS d, {agg}(value)
        FROM records WHERE type = ? AND start_date >= ? AND start_date < ?
        GROUP BY d
        """,
        [metric, min_d, max_d],
    ).fetchall()
    daily = {r[0]: float(r[1]) for r in rows if r[1] is not None}
    xs: list[float] = []
    ys: list[float] = []
    by_floor: dict[str, list[float]] = {}
    for t in tagged:
        v = daily.get(t["date"])
        if v is None:
            continue
        if t.get("floor_level") is not None:
            xs.append(float(t["floor_level"]))
            ys.append(v)
        if t.get("floor"):
            by_floor.setdefault(t["floor"], []).append(v)

    r, n = _pearson(xs, ys) if xs and ys else (0.0, 0)
    by_floor_summary = {
        name: {
            "mean": round(statistics.mean(vals), 2),
            "n": len(vals),
            "min": round(min(vals), 2),
            "max": round(max(vals), 2),
        }
        for name, vals in by_floor.items()
        if vals
    }
    return {
        "metric": metric,
        "days_window": days,
        "n_paired_with_level": n,
        "pearson_r": round(r, 3),
        "by_floor": by_floor_summary,
        "note": (
            "Pearson r between numeric floor_level and the daily metric. "
            "n>=3 for any signal; n>=10 for directional; n>=20 for confidence."
        ),
    }


def coaching_context(
    con: "duckdb.DuckDBPyConnection",
    start_date: date,
    end_date: date,
    vault_root: Path,
) -> dict[str, Any]:
    """Recovery-vs-stress markers + Floor distribution over a coaching window."""
    from scores import recovery_score, _sleep_for_date

    days = (end_date - start_date).days + 1
    daily_scores: list[dict[str, Any]] = []
    low_recovery_days = 0
    low_sleep_quality_days = 0
    cur = start_date
    while cur <= end_date:
        rs = recovery_score(con, cur)
        if rs.get("score") is not None:
            daily_scores.append({"date": cur.isoformat(), "score": rs["score"]})
            if rs["score"] < 50:
                low_recovery_days += 1
        sleep = _sleep_for_date(con, cur)
        if (sleep["rem_min"] + sleep["deep_min"]) < 60:
            low_sleep_quality_days += 1
        cur += timedelta(days=1)

    tagged = _floor_tagged_dates(vault_root, days=days + 1)
    in_window = [t for t in tagged if start_date <= t["date"] <= end_date]
    by_floor: dict[str, int] = {}
    for t in in_window:
        if t.get("floor"):
            by_floor[t["floor"]] = by_floor.get(t["floor"], 0) + 1

    avg_score = (
        round(statistics.mean(d["score"] for d in daily_scores))
        if daily_scores
        else None
    )
    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "days_in_window": days,
        "avg_recovery_score": avg_score,
        "days_with_low_recovery": low_recovery_days,
        "days_with_low_sleep_quality": low_sleep_quality_days,
        "daily_scores": daily_scores,
        "floor_distribution": by_floor,
        "n_floor_tagged_days": len(in_window),
    }


def panel_context(
    con: "duckdb.DuckDBPyConnection", target: date, vault_root: Path
) -> dict[str, Any]:
    """Same-day stress/recovery snapshot for advisory-panel decision moments."""
    from scores import recovery_score

    today = recovery_score(con, target)
    last_7 = []
    for i in range(1, 8):
        rs = recovery_score(con, target - timedelta(days=i))
        if rs.get("score") is not None:
            last_7.append(rs["score"])
    avg_7 = round(statistics.mean(last_7)) if last_7 else None
    delta = (
        today["score"] - avg_7
        if (today.get("score") is not None and avg_7 is not None)
        else None
    )
    floor_tag: dict[str, Any] | None = None
    for d in _journal_dirs(vault_root):
        for p in d.rglob(f"*{target.isoformat()}*.md"):
            fm = _read_frontmatter(p)
            if fm and (fm.get("floor_level") is not None or fm.get("floor")):
                floor_tag = {
                    "floor_level": fm.get("floor_level"),
                    "floor": fm.get("floor"),
                    "journal_path": str(p),
                }
                break
        if floor_tag:
            break
    return {
        "date": target.isoformat(),
        "recovery_score_today": today.get("score"),
        "recovery_score_7d_avg": avg_7,
        "delta_vs_7d_avg": delta,
        "today_floor_tag": floor_tag,
        "interpretation_hint": (
            "delta < -10 + low floor: consider deferring high-stakes calls. "
            "delta > +10 + high floor: green light for difficult conversations."
        ),
    }


def weekly_rollup(con: "duckdb.DuckDBPyConnection", week_start: date) -> dict[str, Any]:
    """Feeds the /insights weekly-review skill."""
    from scores import recovery_score

    week_end = week_start + timedelta(days=6)
    start = datetime.combine(week_start, datetime.min.time())
    end = datetime.combine(week_end, datetime.min.time()) + timedelta(days=1)

    def _agg(metric: str) -> dict[str, Any]:
        row = con.execute(
            "SELECT AVG(value), MIN(value), MAX(value), COUNT(*) FROM records "
            "WHERE type = ? AND start_date >= ? AND start_date < ?",
            [metric, start, end],
        ).fetchone()
        if not row or row[3] == 0:
            return {"avg": None, "min": None, "max": None, "n": 0}
        return {
            "avg": round(float(row[0]), 2),
            "min": round(float(row[1]), 2),
            "max": round(float(row[2]), 2),
            "n": int(row[3]),
        }

    steps = con.execute(
        """
        SELECT SUM(daily) AS total, AVG(daily) AS avg, MIN(daily) AS min, MAX(daily) AS max
        FROM (
          SELECT DATE_TRUNC('day', start_date) AS d, SUM(value) AS daily
          FROM records WHERE type = 'HKQuantityTypeIdentifierStepCount'
            AND start_date >= ? AND start_date < ?
          GROUP BY d
        )
        """,
        [start, end],
    ).fetchone()
    workouts = con.execute(
        "SELECT COUNT(*), COALESCE(SUM(duration_min), 0), COALESCE(SUM(distance_km), 0) "
        "FROM workouts WHERE start_date >= ? AND start_date < ?",
        [start, end],
    ).fetchone()
    daily_recovery: list[dict[str, Any]] = []
    cur = week_start
    while cur <= week_end:
        rs = recovery_score(con, cur)
        if rs.get("score") is not None:
            daily_recovery.append({"date": cur.isoformat(), "score": rs["score"]})
        cur += timedelta(days=1)
    trend = None
    if len(daily_recovery) >= 2:
        trend = daily_recovery[-1]["score"] - daily_recovery[0]["score"]

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "hrv": _agg("HKQuantityTypeIdentifierHeartRateVariabilitySDNN"),
        "rhr": _agg("HKQuantityTypeIdentifierRestingHeartRate"),
        "steps": {
            "total": int(steps[0]) if steps and steps[0] else 0,
            "daily_avg": round(float(steps[1])) if steps and steps[1] else 0,
            "daily_min": round(float(steps[2])) if steps and steps[2] else 0,
            "daily_max": round(float(steps[3])) if steps and steps[3] else 0,
        },
        "workouts": {
            "count": int(workouts[0]) if workouts else 0,
            "total_min": round(float(workouts[1])) if workouts else 0,
            "total_km": round(float(workouts[2]), 2) if workouts else 0,
        },
        "recovery_trend": trend,
        "daily_recovery": daily_recovery,
    }


# ---------------------------------------------------------------------------
# Body literacy prompt (Bainbridge, panel 2026-05-10)
# ---------------------------------------------------------------------------

def journal_body_question(con: "duckdb.DuckDBPyConnection", target: date) -> dict[str, Any]:
    """Return a context-aware embodiment question — not a number — for the
    daily-journal prompt. The question lands differently depending on what
    the body did.
    """
    from voice_bridge import render_body_question  # late import; voice_bridge imports nothing heavy

    ctx = journal_context(con, target)
    return {
        "date": target.isoformat(),
        "question": render_body_question(ctx),
        "body_summary": ctx,
        "interpretation_hint": (
            "Use the question as a journal prompt. Use body_summary as private "
            "context for the LLM, NOT to repeat back to the user verbatim."
        ),
    }


# ---------------------------------------------------------------------------
# Symptoms correlation (Pagliano, panel 2026-05-10)
# ---------------------------------------------------------------------------

def symptom_correlation(
    con: "duckdb.DuckDBPyConnection",
    symptom_type: str,
    days: int,
    vault_root: Path,
) -> dict[str, Any]:
    """Correlate occurrences of a specific symptom (HKCategoryTypeIdentifier*)
    with Floor tags from the journal.

    Returns: per-floor symptom-day frequency. n_paired = days where both a
    floor tag and a symptom log exist.
    """
    cutoff = datetime.combine(date.today() - timedelta(days=days), datetime.min.time())
    rows = con.execute(
        """
        SELECT DATE_TRUNC('day', start_date)::DATE AS d, severity
        FROM symptoms
        WHERE type = ? AND start_date >= ?
        GROUP BY d, severity
        """,
        [symptom_type, cutoff],
    ).fetchall()
    by_date: dict[date, str] = {}
    for d, sev in rows:
        by_date[d] = sev or "event"

    tagged = _floor_tagged_dates(vault_root, days=days)
    by_floor: dict[str, dict[str, int]] = {}
    n_paired = 0
    for t in tagged:
        if t["date"] not in by_date:
            continue
        n_paired += 1
        floor = t.get("floor") or f"level_{t.get('floor_level')}" or "unspecified"
        by_floor.setdefault(floor, {"days_with_symptom": 0, "total_floor_days": 0})
        by_floor[floor]["days_with_symptom"] += 1

    for t in tagged:
        floor = t.get("floor") or f"level_{t.get('floor_level')}" or "unspecified"
        if floor in by_floor:
            by_floor[floor]["total_floor_days"] += 1

    for floor, counts in by_floor.items():
        total = counts["total_floor_days"]
        counts["incidence_pct"] = round(counts["days_with_symptom"] / total * 100, 1) if total else 0

    return {
        "symptom": symptom_type,
        "days_window": days,
        "n_days_with_symptom": len(by_date),
        "n_paired_with_floor_tag": n_paired,
        "by_floor": by_floor,
        "interpretation_hint": (
            "Higher incidence_pct on a given floor = symptom co-occurs with "
            "that emotional state. Useful for pelvic / migraine / GI patterns "
            "that may be Floor-linked."
        ),
    }


def long_window_with_journal(
    con: "duckdb.DuckDBPyConnection",
    metric: str,
    years: int,
    vault_root: Path,
) -> dict[str, Any]:
    """Pair scores.long_window with journal Floor tags from the same months.
    Surfaces seasonal Floor-body coupling (van der Kolk's 'anniversary'
    pattern)."""
    from scores import long_window

    base = long_window(con, metric, years=years)
    tagged = _floor_tagged_dates(vault_root, days=years * 365)
    by_month: dict[str, dict[str, int]] = {}
    for t in tagged:
        m = t["date"].strftime("%Y-%m")
        by_month.setdefault(m, {})
        floor = t.get("floor") or f"level_{t.get('floor_level')}"
        by_month[m][floor] = by_month[m].get(floor, 0) + 1
    base["floor_distribution_by_month"] = by_month
    return base

