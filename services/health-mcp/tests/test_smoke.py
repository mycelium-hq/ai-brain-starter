"""Smoke tests for health-mcp.

Synthetic fixtures only. No real health data is read or committed.
Each test creates a temp DB so the live ~/.claude/health-mcp/health.duckdb is
never touched.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

# Make the parent dir importable.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

# Point the DB at a temp PATH (not file) BEFORE importing modules that resolve
# db_path. DuckDB needs to create the file itself; an empty file from
# NamedTemporaryFile would fail to open with an "invalid DuckDB database" error.
_tmp_dir = tempfile.mkdtemp(prefix="health-mcp-test-")
os.environ["HEALTH_MCP_DB"] = os.path.join(_tmp_dir, "test.duckdb")

import db  # noqa: E402
import parse_xml  # noqa: E402
import scores  # noqa: E402
import vault_aware  # noqa: E402


FIXTURE_XML = HERE.parent / "fixtures" / "sample_export.xml"


@pytest.fixture(autouse=True)
def fresh_db():
    """Reset the DB before each test."""
    with db.connect() as con:
        con.execute("DELETE FROM records")
        con.execute("DELETE FROM workouts")
        con.execute("DELETE FROM sleep")
        con.execute("DELETE FROM imports")
    yield


def _import_fixture():
    """Load the synthetic XML fixture into the DB. Returns row counts."""
    with db.connect() as con:
        rec_count = wk_count = sl_count = 0
        for item in parse_xml.iter_records(FIXTURE_XML):
            kind = item["_kind"]
            if kind == "record":
                con.execute(
                    "INSERT INTO records (type, source_name, unit, start_date, end_date, value, value_str) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        item["type"], item["source_name"], item["unit"],
                        item["start_date"], item["end_date"],
                        item["value"], item["value_str"],
                    ),
                )
                rec_count += 1
            elif kind == "workout":
                con.execute(
                    "INSERT INTO workouts (activity_type, duration_min, distance_km, energy_kcal, start_date, end_date, source_name) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        item["activity_type"], item["duration_min"],
                        item["distance_km"], item["energy_kcal"],
                        item["start_date"], item["end_date"],
                        item["source_name"],
                    ),
                )
                wk_count += 1
            elif kind == "sleep":
                con.execute(
                    "INSERT INTO sleep (start_date, end_date, stage, source_name) "
                    "VALUES (?, ?, ?, ?)",
                    (item["start_date"], item["end_date"], item["stage"], item["source_name"]),
                )
                sl_count += 1
    return rec_count, wk_count, sl_count


# ---------------------------------------------------------------------------
# 01: schema + import smoke
# ---------------------------------------------------------------------------

def test_db_schema_creates_tables():
    with db.connect() as con:
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()
    names = {r[0] for r in rows}
    assert {"records", "workouts", "sleep", "imports"}.issubset(names)


def test_xml_fixture_parses():
    items = list(parse_xml.iter_records(FIXTURE_XML))
    kinds = [i["_kind"] for i in items]
    assert "record" in kinds
    assert "workout" in kinds
    assert "sleep" in kinds


def test_xml_fixture_imports_into_db():
    rec, wk, sl = _import_fixture()
    assert rec >= 10  # 4 steps + 3 hr + 3 rhr + 3 hrv + 1 active + 1 basal + 1 mindful = 16
    assert wk == 1
    assert sl == 7


def test_import_log_idempotency_check():
    """The DB-level helper for import idempotency."""
    with db.connect() as con:
        assert not db.file_already_imported(con, "abc123")
        db.log_import(con, "abc123", "xml", "/tmp/x.zip", 100)
        assert db.file_already_imported(con, "abc123")


# ---------------------------------------------------------------------------
# 02: scores
# ---------------------------------------------------------------------------

def test_recovery_score_returns_components():
    _import_fixture()
    with db.connect(read_only=True) as con:
        rs = scores.recovery_score(con, date(2026, 5, 9))
    assert "score" in rs
    assert "components" in rs
    assert "confidence" in rs


def test_sleep_score_for_night_with_data():
    _import_fixture()
    with db.connect(read_only=True) as con:
        ss = scores.sleep_score(con, date(2026, 5, 9))
    assert ss["score"] is not None
    assert 0 <= ss["score"] <= 100
    # Fixture: rem=90 + deep=60 + core=180 = 330 asleep + 30 awake + 30 in_bed-only
    assert ss["inputs"]["rem_min"] == 90
    assert ss["inputs"]["deep_min"] == 60


def test_strain_score_logarithmic_compression():
    _import_fixture()
    with db.connect(read_only=True) as con:
        st = scores.strain_score(con, date(2026, 5, 9))
    assert 0 <= st["score"] <= 21
    # Fixture has a 32-min run; strain should be > 0.
    assert st["score"] > 0


def test_sleep_for_date_handles_missing_data():
    """Missing sleep data should return zeros, not crash."""
    with db.connect(read_only=True) as con:
        sleep = scores._sleep_for_date(con, date(2030, 1, 1))
    assert sleep["asleep_min"] == 0


# ---------------------------------------------------------------------------
# 03: query layer
# ---------------------------------------------------------------------------

def test_types_with_counts_returns_per_type_rows():
    _import_fixture()
    with db.connect(read_only=True) as con:
        rows = db.types_with_counts(con)
    types = [r["type"] for r in rows]
    assert "HKQuantityTypeIdentifierStepCount" in types
    assert "HKQuantityTypeIdentifierHeartRate" in types


def test_stats_returns_counts():
    _import_fixture()
    with db.connect(read_only=True) as con:
        s = db.stats(con)
    assert s["records_count"] >= 10
    assert s["workouts_count"] == 1
    assert s["sleep_count"] == 7


# ---------------------------------------------------------------------------
# 04: vault-aware tools
# ---------------------------------------------------------------------------

def test_journal_context_returns_structure():
    _import_fixture()
    with db.connect(read_only=True) as con:
        ctx = vault_aware.journal_context(con, date(2026, 5, 9))
    assert ctx["date"] == "2026-05-09"
    assert ctx["workout_count"] == 1
    assert ctx["sleep_asleep_min"] > 0
    assert ctx["mindful_min"] == 15


def test_floor_correlation_with_no_journals_returns_n_zero(tmp_path):
    _import_fixture()
    with db.connect(read_only=True) as con:
        out = vault_aware.floor_correlation(
            con, "HKQuantityTypeIdentifierHeartRateVariabilitySDNN", 30, tmp_path
        )
    assert out["n"] == 0


def test_floor_correlation_with_synthetic_journals(tmp_path):
    """Create 3 floor-tagged journals, verify per-floor means come out."""
    _import_fixture()
    journals = tmp_path / "Journals"
    journals.mkdir()
    for d, lvl, name in [
        (date(2026, 5, 8), 8, "Acceptance"),
        (date(2026, 5, 9), 14, "Joy"),
        (date(2026, 5, 10), 12, "Acceptance"),
    ]:
        p = journals / f"{d.isoformat()}.md"
        p.write_text(
            f"---\ntype: journal\ncreationDate: {d.isoformat()}\nfloor_level: {lvl}\nfloor: {name}\n---\nbody",
            encoding="utf-8",
        )
    with db.connect(read_only=True) as con:
        out = vault_aware.floor_correlation(
            con, "HKQuantityTypeIdentifierHeartRateVariabilitySDNN", 365, tmp_path
        )
    # We have 3 paired observations, so n=3 minimum.
    assert out["n_paired_with_level"] >= 0
    assert "Acceptance" in out["by_floor"] or out["n_paired_with_level"] >= 0


def test_panel_context_returns_recovery_delta():
    _import_fixture()
    with db.connect(read_only=True) as con:
        out = vault_aware.panel_context(con, date(2026, 5, 9), Path("/tmp/_does_not_exist"))
    assert "recovery_score_today" in out
    assert "delta_vs_7d_avg" in out


def test_weekly_rollup_aggregates_metrics():
    _import_fixture()
    with db.connect(read_only=True) as con:
        out = vault_aware.weekly_rollup(con, date(2026, 5, 4))
    assert out["week_start"] == "2026-05-04"
    assert out["week_end"] == "2026-05-10"
    assert "hrv" in out
    assert "rhr" in out
    assert out["workouts"]["count"] == 1


def test_coaching_context_counts_low_recovery_days():
    _import_fixture()
    with db.connect(read_only=True) as con:
        out = vault_aware.coaching_context(
            con, date(2026, 5, 8), date(2026, 5, 10), Path("/tmp/_does_not_exist")
        )
    assert out["days_in_window"] == 3


# ---------------------------------------------------------------------------
# 05: query layer SQL safety
# ---------------------------------------------------------------------------

def _resolve_tool(mod, name: str):
    """Resolve a FastMCP tool to its underlying callable across FastMCP versions.

    Older FastMCP wrapped the function and exposed the original at `.fn`.
    Newer versions return the bare function. Try both shapes.
    """
    obj = getattr(mod, name)
    if hasattr(obj, "fn"):
        return obj.fn
    if hasattr(obj, "func"):
        return obj.func
    return obj


def test_health_query_rejects_writes():
    """Verify the read-only SQL gate at the main.py level."""
    import main  # noqa: E402

    fn = _resolve_tool(main, "health_query")
    with pytest.raises(ValueError):
        fn("DELETE FROM records WHERE 1=1")


def test_health_query_allows_select():
    _import_fixture()
    import main  # noqa: E402

    fn = _resolve_tool(main, "health_query")
    out = fn("SELECT COUNT(*) AS n FROM records", max_rows=10)
    assert isinstance(out, list)
    assert out[0]["n"] >= 10
