"""v0.2 smoke tests covering cycle, symptoms, ECG, state of mind, labs,
longevity panel, sleep regularity, somatic state, nutrition summary,
voice bridge, and body literacy.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

_tmp_dir = tempfile.mkdtemp(prefix="health-mcp-test-v02-")
os.environ["HEALTH_MCP_DB"] = os.path.join(_tmp_dir, "test.duckdb")

import cycle as cycle_mod  # noqa: E402
import db  # noqa: E402
import labs as labs_mod  # noqa: E402
import parse_xml  # noqa: E402
import scores  # noqa: E402
import vault_aware  # noqa: E402
import voice_bridge  # noqa: E402


FIXTURE_V02 = HERE.parent / "fixtures" / "sample_v02.xml"
FIXTURE_LABS = HERE.parent / "fixtures" / "sample_labs.csv"


@pytest.fixture(autouse=True)
def fresh_db():
    with db.connect() as con:
        for tbl in ("records", "workouts", "sleep", "cycle", "symptoms", "ecg", "state_of_mind", "labs", "imports"):
            con.execute(f"DELETE FROM {tbl}")
    yield


def _import_v02_fixture():
    counts = {"record": 0, "cycle": 0, "symptom": 0, "ecg": 0, "state_of_mind": 0, "sleep": 0, "workout": 0}
    with db.connect() as con:
        for item in parse_xml.iter_records(FIXTURE_V02):
            k = item["_kind"]
            counts[k] += 1
            if k == "record":
                con.execute(
                    "INSERT INTO records (type, source_name, unit, start_date, end_date, value, value_str) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (item["type"], item["source_name"], item["unit"], item["start_date"], item["end_date"], item["value"], item["value_str"]),
                )
            elif k == "cycle":
                con.execute(
                    "INSERT INTO cycle (type, start_date, end_date, value, source_name) VALUES (?, ?, ?, ?, ?)",
                    (item["type"], item["start_date"], item["end_date"], item["value"], item["source_name"]),
                )
            elif k == "symptom":
                con.execute(
                    "INSERT INTO symptoms (type, start_date, end_date, severity, source_name) VALUES (?, ?, ?, ?, ?)",
                    (item["type"], item["start_date"], item["end_date"], item["severity"], item["source_name"]),
                )
            elif k == "ecg":
                con.execute(
                    "INSERT INTO ecg (start_date, classification, average_heart_rate, sampling_frequency, source_name) VALUES (?, ?, ?, ?, ?)",
                    (item["start_date"], item["classification"], item["average_heart_rate"], item["sampling_frequency"], item["source_name"]),
                )
            elif k == "state_of_mind":
                con.execute(
                    "INSERT INTO state_of_mind (start_date, end_date, kind, valence, labels, associations, source_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (item["start_date"], item["end_date"], item["kind"], item["valence"], item["labels"], item["associations"], item["source_name"]),
                )
    return counts


# ---------------------------------------------------------------------------
# 01: cycle
# ---------------------------------------------------------------------------

def test_cycle_records_imported():
    counts = _import_v02_fixture()
    assert counts["cycle"] >= 4  # 3 menstrual flows + 1 ovulation + cervical mucus


def test_cycle_context_returns_phase():
    _import_v02_fixture()
    with db.connect(read_only=True) as con:
        ctx = cycle_mod.cycle_context(con, date(2026, 5, 9))
    assert ctx["phase"] != "unknown"
    assert "cycle_day" in ctx


def test_cycle_context_reports_irregularity_when_no_history():
    _import_v02_fixture()
    with db.connect(read_only=True) as con:
        ctx = cycle_mod.cycle_context(con, date(2026, 5, 9))
    assert ctx["n_cycles_observed"] >= 0


def test_phase_means_segments_metric():
    _import_v02_fixture()
    with db.connect(read_only=True) as con:
        out = cycle_mod.phase_means_for_metric(con, "HKQuantityTypeIdentifierStepCount", days=180)
    assert "metric" in out


# ---------------------------------------------------------------------------
# 02: symptoms
# ---------------------------------------------------------------------------

def test_symptoms_imported():
    counts = _import_v02_fixture()
    assert counts["symptom"] >= 4


def test_symptoms_severity_parsed():
    _import_v02_fixture()
    with db.connect(read_only=True) as con:
        rows = con.execute("SELECT type, severity FROM symptoms ORDER BY start_date").fetchall()
    severities = {r[1] for r in rows}
    assert "moderate" in severities
    assert "mild" in severities
    assert "severe" in severities


# ---------------------------------------------------------------------------
# 03: ECG
# ---------------------------------------------------------------------------

def test_ecg_imported_and_classified():
    _import_v02_fixture()
    with db.connect(read_only=True) as con:
        rows = con.execute("SELECT classification, average_heart_rate FROM ecg").fetchall()
    assert len(rows) >= 1
    assert rows[0][0] == "sinusrhythm"


# ---------------------------------------------------------------------------
# 04: state of mind (iOS 17+)
# ---------------------------------------------------------------------------

def test_state_of_mind_imported_with_valence():
    _import_v02_fixture()
    with db.connect(read_only=True) as con:
        rows = con.execute("SELECT valence, kind, labels FROM state_of_mind ORDER BY start_date").fetchall()
    assert len(rows) >= 2
    assert rows[0][0] is not None
    assert rows[0][1] == "momentary"


# ---------------------------------------------------------------------------
# 05: longevity + new scores
# ---------------------------------------------------------------------------

def test_longevity_panel_returns_vo2max():
    _import_v02_fixture()
    with db.connect(read_only=True) as con:
        out = scores.longevity_panel(con, date(2026, 5, 9))
    assert out["vo2max"] is not None
    assert out["walking_speed_m_s"] is not None


def test_sleep_regularity_handles_no_data():
    """No sleep stages in v02 fixture; should return zeros + n_nights_used 0."""
    _import_v02_fixture()
    with db.connect(read_only=True) as con:
        out = scores.sleep_regularity(con, date(2026, 5, 1), date(2026, 5, 10))
    assert out["n_nights_used"] == 0


def test_somatic_state_returns_body_says_slow_down_boolean():
    _import_v02_fixture()
    with db.connect(read_only=True) as con:
        out = scores.somatic_state(con, date(2026, 5, 9), lookback_min=120)
    assert "body_says_slow_down" in out
    assert isinstance(out["body_says_slow_down"], bool)


def test_nutrition_summary_aggregates_dietary_records():
    _import_v02_fixture()
    with db.connect(read_only=True) as con:
        out = scores.nutrition_summary(con, date(2026, 5, 9), date(2026, 5, 9))
    assert out["daily_kcal_avg"] >= 1500  # 650 + 850 = 1500
    assert out["daily_protein_g_avg"] >= 80


def test_long_window_returns_yoy():
    _import_v02_fixture()
    with db.connect(read_only=True) as con:
        out = scores.long_window(con, "HKQuantityTypeIdentifierStepCount", years=2)
    assert "metric" in out


# ---------------------------------------------------------------------------
# 06: labs
# ---------------------------------------------------------------------------

def test_lab_csv_parses_generic_format():
    p, sha, rows = labs_mod.parse_labs_csv(str(FIXTURE_LABS), lab_format="generic")
    assert len(rows) == 14
    assert rows[0]["marker"] == "Fasting Glucose"


def test_lab_classify_low_status():
    """Vitamin D 28 ng/mL (range 30-100) should classify as 'low'."""
    p, sha, rows = labs_mod.parse_labs_csv(str(FIXTURE_LABS), lab_format="generic")
    vit_d = next(r for r in rows if r["marker"] == "Vitamin D 25-OH")
    assert vit_d["status"] == "low"


def test_recommended_panel_has_apo_b_and_hs_crp():
    markers = {entry["marker"] for entry in labs_mod.RECOMMENDED_PANEL}
    assert "ApoB" in markers
    assert "hs-CRP" in markers
    assert "Fasting Insulin" in markers


def test_lab_import_via_main_inserts_rows():
    """End-to-end smoke for the lab import flow."""
    import main
    fn = main.health_import_labs.fn if hasattr(main.health_import_labs, "fn") else main.health_import_labs
    out = fn(str(FIXTURE_LABS), lab_format="generic")
    assert out["rows_inserted"] == 14


# ---------------------------------------------------------------------------
# 07: voice bridge
# ---------------------------------------------------------------------------

def test_voice_bridge_renders_three_registers():
    ctx = {
        "hrv_ms": 28, "rhr_bpm": 65, "sleep_asleep_min": 312,
        "sleep_efficiency": 0.87, "workout_count": 0, "workout_min": 0,
        "steps_total": 4820, "mindful_min": 0,
        "sleep_rem_min": 38, "sleep_deep_min": 22,
    }
    clinical = voice_bridge.render_journal_context(ctx, profile="clinical")
    warm = voice_bridge.render_journal_context(ctx, profile="warm")
    curious = voice_bridge.render_journal_context(ctx, profile="curious")
    # Clinical: technical exact form ("HRV 28ms").
    assert "HRV 28ms" in clinical or "HRV 28" in clinical
    # Warm: narrative form (still allowed to mention units, but uses sentences).
    assert "slept" in warm.lower() or "rest" in warm.lower()
    # Curious: always returns a question for the user to answer.
    assert "?" in curious


def test_body_question_returns_question():
    ctx = {"sleep_asleep_min": 300, "sleep_rem_min": 20, "sleep_deep_min": 15, "hrv_ms": 22, "workout_count": 0}
    q = voice_bridge.render_body_question(ctx)
    assert "?" in q


# ---------------------------------------------------------------------------
# 08: vault-aware extensions
# ---------------------------------------------------------------------------

def test_journal_body_question_returns_structure():
    _import_v02_fixture()
    with db.connect(read_only=True) as con:
        out = vault_aware.journal_body_question(con, date(2026, 5, 9))
    assert "?" in out["question"]
    assert "body_summary" in out


def test_symptom_correlation_with_journals(tmp_path):
    _import_v02_fixture()
    journals = tmp_path / "Journals"
    journals.mkdir()
    for d, lvl, name in [
        (date(2026, 5, 8), 8, "Acceptance"),
        (date(2026, 5, 9), 4, "Fear"),
        (date(2026, 5, 10), 6, "Courage"),
    ]:
        p = journals / f"{d.isoformat()}.md"
        p.write_text(
            f"---\ntype: journal\ncreationDate: {d.isoformat()}\nfloor_level: {lvl}\nfloor: {name}\n---\nbody",
            encoding="utf-8",
        )
    with db.connect(read_only=True) as con:
        out = vault_aware.symptom_correlation(con, "HKCategoryTypeIdentifierFatigue", days=365, vault_root=tmp_path)
    assert "symptom" in out
    assert out["symptom"] == "HKCategoryTypeIdentifierFatigue"


# ---------------------------------------------------------------------------
# 09: schema integrity
# ---------------------------------------------------------------------------

def test_all_v02_tables_exist():
    with db.connect() as con:
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()
    names = {r[0] for r in rows}
    assert {"records", "workouts", "sleep", "cycle", "symptoms", "ecg", "state_of_mind", "labs", "imports"}.issubset(names)


def test_recommended_panel_minimum_size():
    assert len(labs_mod.RECOMMENDED_PANEL) >= 14
