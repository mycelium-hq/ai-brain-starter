"""DuckDB schema + connection for health-mcp.

Single local file at ~/.claude/health-mcp/health.duckdb. Single-writer; tools
open a fresh connection per call and close it on return so concurrent stdio
tool invocations do not collide.

Schema:
  records        — quantity + category records from Apple Health
  workouts       — workout sessions
  sleep          — sleep stage segments (parsed out of HKCategoryTypeIdentifierSleepAnalysis)
  imports        — file ingest log; SHA-256 of source file used for idempotent re-imports

Idempotency:
  imports.file_sha is the natural dedup key. health_import_xml / _csv hash the
  source file, look it up in `imports`, skip if found unless force=True.
  Within a single import, record-level dedup uses the natural key
  (type, source_name, start_date, end_date, value) so partial re-imports do
  not duplicate rows.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import duckdb


def db_path() -> Path:
    """Default DB location. Honors HEALTH_MCP_DB env override."""
    override = os.environ.get("HEALTH_MCP_DB")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "health-mcp" / "health.duckdb"


def init_schema(con: "duckdb.DuckDBPyConnection") -> None:
    """Create tables if they don't exist. Safe to run repeatedly."""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            type        VARCHAR NOT NULL,
            source_name VARCHAR,
            unit        VARCHAR,
            start_date  TIMESTAMP NOT NULL,
            end_date    TIMESTAMP NOT NULL,
            value       DOUBLE,
            value_str   VARCHAR
        );
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS workouts (
            activity_type   VARCHAR NOT NULL,
            duration_min    DOUBLE,
            distance_km     DOUBLE,
            energy_kcal     DOUBLE,
            start_date      TIMESTAMP NOT NULL,
            end_date        TIMESTAMP NOT NULL,
            source_name     VARCHAR
        );
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS sleep (
            start_date  TIMESTAMP NOT NULL,
            end_date    TIMESTAMP NOT NULL,
            stage       VARCHAR NOT NULL,
            source_name VARCHAR
        );
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS imports (
            file_sha    VARCHAR NOT NULL,
            kind        VARCHAR NOT NULL,
            file_path   VARCHAR,
            imported_at TIMESTAMP NOT NULL,
            row_count   BIGINT
        );
        """
    )
    # Speed up the common time-window queries.
    con.execute("CREATE INDEX IF NOT EXISTS idx_records_type_start ON records(type, start_date);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_workouts_start ON workouts(start_date);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_sleep_start ON sleep(start_date);")


@contextmanager
def connect(read_only: bool = False) -> Iterator["duckdb.DuckDBPyConnection"]:
    """Open a DuckDB connection. Creates parent dir + schema on first use."""
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(p), read_only=read_only)
    try:
        if not read_only:
            init_schema(con)
        yield con
    finally:
        con.close()


def file_already_imported(con: "duckdb.DuckDBPyConnection", file_sha: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM imports WHERE file_sha = ? LIMIT 1;", [file_sha]
    ).fetchone()
    return row is not None


def log_import(
    con: "duckdb.DuckDBPyConnection",
    file_sha: str,
    kind: str,
    file_path: str,
    row_count: int,
) -> None:
    con.execute(
        "INSERT INTO imports (file_sha, kind, file_path, imported_at, row_count) "
        "VALUES (?, ?, ?, NOW(), ?);",
        [file_sha, kind, file_path, row_count],
    )


def stats(con: "duckdb.DuckDBPyConnection") -> dict[str, Any]:
    """Per-table counts + last import timestamp."""
    out: dict[str, Any] = {}
    for table in ("records", "workouts", "sleep", "imports"):
        row = con.execute(f"SELECT COUNT(*) FROM {table};").fetchone()
        out[f"{table}_count"] = row[0] if row else 0
    last = con.execute(
        "SELECT MAX(imported_at), MIN(imported_at) FROM imports;"
    ).fetchone()
    out["last_import"] = str(last[0]) if last and last[0] else None
    out["first_import"] = str(last[1]) if last and last[1] else None
    out["db_path"] = str(db_path())
    return out


def types_with_counts(con: "duckdb.DuckDBPyConnection") -> list[dict[str, Any]]:
    """For health_schema: return each record type with its row count + date range."""
    rows = con.execute(
        """
        SELECT type, COUNT(*) AS n, MIN(start_date) AS first, MAX(start_date) AS last
        FROM records
        GROUP BY type
        ORDER BY n DESC;
        """
    ).fetchall()
    return [
        {"type": r[0], "count": r[1], "first": str(r[2]), "last": str(r[3])}
        for r in rows
    ]
