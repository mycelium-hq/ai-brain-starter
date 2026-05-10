"""health-mcp main FastMCP server.

15 tools across 5 categories: ingestion (3), query (3), analytics (3),
vault-aware (5), live (1).

Stdio transport. Designed to be registered in .mcp.json as `health` and
launched per-session by Claude Code. Long-running ingest jobs hold the
DuckDB write lock; tool calls during an active import will queue.
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

import db
import live_tcp
import parse_csv
import parse_xml
import scores
import vault_aware

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("health-mcp")


@asynccontextmanager
async def lifespan(_app: FastMCP):
    """Print DB stats at startup so connection failures fail loudly."""
    with db.connect() as con:
        s = db.stats(con)
    log.info(
        "health-mcp ready: records=%d workouts=%d sleep=%d imports=%d db=%s",
        s["records_count"],
        s["workouts_count"],
        s["sleep_count"],
        s["imports_count"],
        s["db_path"],
    )
    yield


mcp = FastMCP("health-mcp", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(s: str) -> date:
    """Accept either YYYY-MM-DD or full ISO datetime; return date."""
    return datetime.fromisoformat(s.replace("Z", "")).date() if "T" in s else datetime.strptime(s[:10], "%Y-%m-%d").date()


def _bulk_insert_records(con, batch: list[dict[str, Any]]) -> tuple[int, int, int]:
    """Insert (records, workouts, sleep) batches into DuckDB. Returns counts."""
    rec_rows = []
    wk_rows = []
    sl_rows = []
    for item in batch:
        kind = item["_kind"]
        if kind == "record":
            rec_rows.append(
                (
                    item["type"],
                    item["source_name"],
                    item["unit"],
                    item["start_date"],
                    item["end_date"],
                    item["value"],
                    item["value_str"],
                )
            )
        elif kind == "workout":
            wk_rows.append(
                (
                    item["activity_type"],
                    item["duration_min"],
                    item["distance_km"],
                    item["energy_kcal"],
                    item["start_date"],
                    item["end_date"],
                    item["source_name"],
                )
            )
        elif kind == "sleep":
            sl_rows.append(
                (
                    item["start_date"],
                    item["end_date"],
                    item["stage"],
                    item["source_name"],
                )
            )
    if rec_rows:
        con.executemany(
            "INSERT INTO records (type, source_name, unit, start_date, end_date, value, value_str) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rec_rows,
        )
    if wk_rows:
        con.executemany(
            "INSERT INTO workouts (activity_type, duration_min, distance_km, energy_kcal, start_date, end_date, source_name) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            wk_rows,
        )
    if sl_rows:
        con.executemany(
            "INSERT INTO sleep (start_date, end_date, stage, source_name) "
            "VALUES (?, ?, ?, ?)",
            sl_rows,
        )
    return len(rec_rows), len(wk_rows), len(sl_rows)


# ---------------------------------------------------------------------------
# Ingestion tools
# ---------------------------------------------------------------------------

@mcp.tool()
def health_import_xml(zip_or_xml_path: str, force: bool = False) -> dict[str, Any]:
    """Import an Apple Health XML export.zip (or unzipped export.xml) into DuckDB.

    Args:
        zip_or_xml_path: Absolute path to the file. Apple Health writes
            export.zip; the user typically AirDrops or copies it to disk.
        force: If true, re-import even if the file SHA matches a prior import.

    Returns: {file_sha, kind, rows_inserted, records_count, workouts_count,
              sleep_count, skipped (bool), elapsed_s}
    """
    t0 = datetime.now()
    xml_path, file_sha, _scratch = parse_xml.resolve_xml_path(zip_or_xml_path)
    with db.connect() as con:
        if not force and db.file_already_imported(con, file_sha):
            return {
                "file_sha": file_sha,
                "skipped": True,
                "note": f"Already imported. Pass force=True to re-import.",
            }
        batch: list[dict[str, Any]] = []
        rec_total = wk_total = sl_total = 0
        BATCH = 5000
        for item in parse_xml.iter_records(xml_path):
            batch.append(item)
            if len(batch) >= BATCH:
                r, w, s = _bulk_insert_records(con, batch)
                rec_total += r
                wk_total += w
                sl_total += s
                batch.clear()
        if batch:
            r, w, s = _bulk_insert_records(con, batch)
            rec_total += r
            wk_total += w
            sl_total += s
        total = rec_total + wk_total + sl_total
        db.log_import(con, file_sha, "xml", str(xml_path), total)
    return {
        "file_sha": file_sha,
        "kind": "xml",
        "rows_inserted": total,
        "records_count": rec_total,
        "workouts_count": wk_total,
        "sleep_count": sl_total,
        "skipped": False,
        "elapsed_s": round((datetime.now() - t0).total_seconds(), 2),
    }


@mcp.tool()
def health_import_csv(folder_path: str, force: bool = False) -> dict[str, Any]:
    """Import a folder of Simple Health Export CSVs.

    Args:
        folder_path: Folder containing HKQuantityTypeIdentifier*.csv and/or
            HKCategoryTypeIdentifier*.csv files.
        force: If true, re-import even if the folder SHA matches.
    """
    t0 = datetime.now()
    folder, file_sha = parse_csv.folder_sha(folder_path)
    with db.connect() as con:
        if not force and db.file_already_imported(con, file_sha):
            return {
                "file_sha": file_sha,
                "skipped": True,
                "note": "Already imported. Pass force=True to re-import.",
            }
        batch: list[dict[str, Any]] = []
        rec_total = wk_total = sl_total = 0
        BATCH = 5000
        for item in parse_csv.iter_records(folder):
            batch.append(item)
            if len(batch) >= BATCH:
                r, w, s = _bulk_insert_records(con, batch)
                rec_total += r
                wk_total += w
                sl_total += s
                batch.clear()
        if batch:
            r, w, s = _bulk_insert_records(con, batch)
            rec_total += r
            wk_total += w
            sl_total += s
        total = rec_total + wk_total + sl_total
        db.log_import(con, file_sha, "csv", str(folder), total)
    return {
        "file_sha": file_sha,
        "kind": "csv",
        "rows_inserted": total,
        "records_count": rec_total,
        "workouts_count": wk_total,
        "sleep_count": sl_total,
        "skipped": False,
        "elapsed_s": round((datetime.now() - t0).total_seconds(), 2),
    }


@mcp.tool()
def health_status() -> dict[str, Any]:
    """Database stats: row counts, last import, available metric types."""
    with db.connect(read_only=True) as con:
        s = db.stats(con)
        s["top_types"] = db.types_with_counts(con)[:20]
    return s


# ---------------------------------------------------------------------------
# Query tools
# ---------------------------------------------------------------------------

@mcp.tool()
def health_schema() -> list[dict[str, Any]]:
    """List every record type in the DB with its row count + earliest/latest dates."""
    with db.connect(read_only=True) as con:
        return db.types_with_counts(con)


# Read-only SQL keywords (whitelist). DuckDB has many statement types; any
# DML/DDL is rejected before reaching the connection.
_SQL_FORBIDDEN = {
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE",
    "ATTACH", "DETACH", "COPY", "PRAGMA", "SET", "INSTALL", "LOAD",
}


@mcp.tool()
def health_query(sql: str, max_rows: int = 1000) -> list[dict[str, Any]]:
    """Run a read-only SQL query against DuckDB.

    Tables: records (type, source_name, unit, start_date, end_date, value, value_str),
            workouts (activity_type, duration_min, distance_km, energy_kcal, start_date, end_date, source_name),
            sleep (start_date, end_date, stage, source_name),
            imports (file_sha, kind, file_path, imported_at, row_count).

    Rejects any statement containing a write keyword. Caps result at max_rows.
    """
    upper = sql.strip().upper()
    first_word = upper.split()[0] if upper else ""
    if first_word in _SQL_FORBIDDEN:
        raise ValueError(f"Read-only query layer. Rejected first word: {first_word}")
    for tok in _SQL_FORBIDDEN:
        # Catch UPDATE/DELETE inside a subquery or after a comment.
        if f" {tok} " in f" {upper} ":
            raise ValueError(f"Read-only query layer. Rejected keyword: {tok}")
    with db.connect(read_only=True) as con:
        rows = con.execute(sql).fetchmany(max_rows)
        cols = [d[0] for d in con.description] if con.description else []
    return [dict(zip(cols, [str(v) if isinstance(v, datetime) else v for v in r])) for r in rows]


@mcp.tool()
def health_metric_series(
    metric: str,
    start: str,
    end: str,
    aggregation: str = "daily",
) -> list[dict[str, Any]]:
    """Time series for a quantity-type metric.

    Args:
        metric: e.g. HKQuantityTypeIdentifierStepCount, HKQuantityTypeIdentifierHeartRate
        start, end: YYYY-MM-DD or ISO datetime
        aggregation: "daily" (sum or mean per metric type), "hourly", or "raw"
    """
    sd = datetime.fromisoformat(start.replace("Z", ""))
    ed = datetime.fromisoformat(end.replace("Z", ""))
    sum_metrics = {
        "HKQuantityTypeIdentifierStepCount",
        "HKQuantityTypeIdentifierActiveEnergyBurned",
        "HKQuantityTypeIdentifierBasalEnergyBurned",
        "HKQuantityTypeIdentifierDistanceWalkingRunning",
        "HKQuantityTypeIdentifierFlightsClimbed",
    }
    agg = "SUM" if metric in sum_metrics else "AVG"
    with db.connect(read_only=True) as con:
        if aggregation == "raw":
            rows = con.execute(
                "SELECT start_date, value, source_name FROM records "
                "WHERE type = ? AND start_date >= ? AND start_date < ? "
                "ORDER BY start_date",
                [metric, sd, ed],
            ).fetchall()
            return [
                {"timestamp": str(r[0]), "value": float(r[1]) if r[1] is not None else None, "source": r[2]}
                for r in rows
            ]
        bucket = "hour" if aggregation == "hourly" else "day"
        rows = con.execute(
            f"""
            SELECT DATE_TRUNC('{bucket}', start_date) AS bucket, {agg}(value) AS v, COUNT(*) AS n
            FROM records WHERE type = ? AND start_date >= ? AND start_date < ?
            GROUP BY bucket ORDER BY bucket
            """,
            [metric, sd, ed],
        ).fetchall()
        return [
            {"bucket": str(r[0]), "value": round(float(r[1]), 3) if r[1] is not None else None, "n": int(r[2])}
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Analytics tools
# ---------------------------------------------------------------------------

@mcp.tool()
def health_workout_list(
    start: str, end: str, activity_type: str | None = None
) -> list[dict[str, Any]]:
    """List workouts in a date range, optionally filtered by activity_type."""
    sd = datetime.fromisoformat(start.replace("Z", ""))
    ed = datetime.fromisoformat(end.replace("Z", ""))
    where = "start_date >= ? AND start_date < ?"
    params: list[Any] = [sd, ed]
    if activity_type:
        where += " AND activity_type = ?"
        params.append(activity_type)
    with db.connect(read_only=True) as con:
        rows = con.execute(
            f"SELECT activity_type, start_date, end_date, duration_min, distance_km, energy_kcal, source_name "
            f"FROM workouts WHERE {where} ORDER BY start_date",
            params,
        ).fetchall()
    return [
        {
            "activity_type": r[0],
            "start": str(r[1]),
            "end": str(r[2]),
            "duration_min": round(float(r[3]), 1) if r[3] is not None else None,
            "distance_km": round(float(r[4]), 2) if r[4] is not None else None,
            "energy_kcal": round(float(r[5])) if r[5] is not None else None,
            "source": r[6],
        }
        for r in rows
    ]


@mcp.tool()
def health_sleep_summary(start: str, end: str) -> list[dict[str, Any]]:
    """Per-night sleep summary in a date range. One row per night."""
    sd = _parse_date(start)
    ed = _parse_date(end)
    out: list[dict[str, Any]] = []
    with db.connect(read_only=True) as con:
        cur = sd
        while cur <= ed:
            sleep = scores._sleep_for_date(con, cur)
            if sleep["asleep_min"] > 0 or sleep["in_bed_min"] > 0:
                out.append(
                    {
                        "night_of": cur.isoformat(),
                        "asleep_min": round(sleep["asleep_min"]),
                        "in_bed_min": round(sleep["in_bed_min"]),
                        "rem_min": round(sleep["rem_min"]),
                        "deep_min": round(sleep["deep_min"]),
                        "core_min": round(sleep["core_min"]),
                        "awake_min": round(sleep["awake_min"]),
                        "efficiency": round(sleep["efficiency"], 3),
                    }
                )
            cur += timedelta(days=1)
    return out


@mcp.tool()
def health_recovery_score(date_str: str) -> dict[str, Any]:
    """Recovery score 0-100 for a date.

    Open algorithm: 40% HRV vs baseline, 20% RHR, 25% sleep duration,
    15% sleep efficiency. Returns components + confidence.
    """
    target = _parse_date(date_str)
    with db.connect(read_only=True) as con:
        return scores.recovery_score(con, target)


@mcp.tool()
def health_sleep_score(date_str: str) -> dict[str, Any]:
    """Sleep score 0-100 for a date.

    40% duration, 25% efficiency, 20% REM%, 15% deep%.
    """
    target = _parse_date(date_str)
    with db.connect(read_only=True) as con:
        return scores.sleep_score(con, target)


@mcp.tool()
def health_strain_score(date_str: str) -> dict[str, Any]:
    """Strain score 0-21 (Whoop-shape scale, open formula).

    Inputs: active vs basal kcal ratio, HR-elevated minutes, workout minutes.
    Logarithmic mapping for asymptotic shape.
    """
    target = _parse_date(date_str)
    with db.connect(read_only=True) as con:
        return scores.strain_score(con, target)


# ---------------------------------------------------------------------------
# Vault-aware tools (substrate differentiator)
# ---------------------------------------------------------------------------

@mcp.tool()
def health_journal_context(date_str: str) -> dict[str, Any]:
    """24h health roll-up for the daily-journal skill. Read-only DB query;
    no vault read required for this tool (other vault-aware tools do read).
    """
    target = _parse_date(date_str)
    with db.connect(read_only=True) as con:
        return vault_aware.journal_context(con, target)


@mcp.tool()
def health_floor_correlation(
    metric: str, days: int = 30, vault_root: str = ""
) -> dict[str, Any]:
    """Correlate a daily biometric (e.g. HRV) with Floor tags from the user's
    journal frontmatter.

    Args:
        metric: e.g. HKQuantityTypeIdentifierHeartRateVariabilitySDNN
        days: lookback window
        vault_root: absolute path to the personal vault. Required for floor lookup.
    """
    if not vault_root:
        return {
            "metric": metric,
            "n": 0,
            "note": "vault_root is required. Pass the absolute path to your personal vault.",
        }
    vr = Path(vault_root).expanduser().resolve()
    if not vr.is_dir():
        return {
            "metric": metric,
            "n": 0,
            "note": f"vault_root {vr} does not exist or is not a directory",
        }
    with db.connect(read_only=True) as con:
        return vault_aware.floor_correlation(con, metric, days, vr)


@mcp.tool()
def health_coaching_context(
    start: str, end: str, theme: str | None = None, vault_root: str = ""
) -> dict[str, Any]:
    """Recovery-vs-stress markers + Floor distribution over a coaching window.

    The `theme` arg is reserved for v0.2 (filtering Floor tags by theme).
    """
    sd = _parse_date(start)
    ed = _parse_date(end)
    vr = Path(vault_root).expanduser().resolve() if vault_root else Path("/")
    with db.connect(read_only=True) as con:
        return vault_aware.coaching_context(con, sd, ed, vr)


@mcp.tool()
def health_panel_context(date_str: str, vault_root: str = "") -> dict[str, Any]:
    """Same-day stress/recovery snapshot for advisory-panel decision moments."""
    target = _parse_date(date_str)
    vr = Path(vault_root).expanduser().resolve() if vault_root else Path("/")
    with db.connect(read_only=True) as con:
        return vault_aware.panel_context(con, target, vr)


@mcp.tool()
def health_weekly_rollup(week_start: str) -> dict[str, Any]:
    """Feeds /insights weekly-review skill. Returns avg/min/max for HRV, RHR,
    sleep, steps, plus workout count + recovery trend."""
    sd = _parse_date(week_start)
    with db.connect(read_only=True) as con:
        return vault_aware.weekly_rollup(con, sd)


# ---------------------------------------------------------------------------
# Live tools (Health Auto Export TCP)
# ---------------------------------------------------------------------------

@mcp.tool()
def health_live_query(
    metric: str,
    host: str = "localhost",
    port: int = 9000,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Query the Health Auto Export iOS app over TCP for live data.

    Requires the Health Auto Export iOS app installed, the TCP server
    enabled in its settings, and the iPhone on the same Wi-Fi as this host.
    Returns the raw response or an error dict if the server is unreachable.
    """
    params: dict[str, Any] = {"metric": metric}
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    return live_tcp.query("health_metrics", params, host=host, port=port)


if __name__ == "__main__":
    mcp.run()
