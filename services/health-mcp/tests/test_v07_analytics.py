"""v0.7 analytics tests: correlate, floor_body_fingerprint, loop_signature,
sleep_architecture, longitudinal_summary, symptom_correlate, top_signals.
"""
from __future__ import annotations

import math
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

_tmp_dir = tempfile.mkdtemp(prefix="health-mcp-test-v07-")
os.environ["HEALTH_MCP_DB"] = os.path.join(_tmp_dir, "test.duckdb")

import analytics  # noqa: E402
import db  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    with db.connect() as con:
        for tbl in ("records", "workouts", "sleep", "cycle", "symptoms", "ecg", "state_of_mind", "labs", "imports"):
            con.execute(f"DELETE FROM {tbl}")
    yield


# --- Pure helpers --------------------------------------------------------

def test_pearson_basic_positive():
    r, n = analytics._pearson_with_n([1, 2, 3, 4, 5, 6], [2, 4, 6, 8, 10, 12])
    assert n == 6
    assert r is not None and math.isclose(r, 1.0, abs_tol=1e-9)


def test_pearson_basic_negative():
    r, n = analytics._pearson_with_n([1, 2, 3, 4, 5, 6], [12, 10, 8, 6, 4, 2])
    assert r is not None and math.isclose(r, -1.0, abs_tol=1e-9)


def test_pearson_below_min_n_returns_none():
    r, n = analytics._pearson_with_n([1, 2, 3], [4, 5, 6])
    assert r is None
    assert n == 3


def test_pearson_zero_variance_returns_none():
    r, n = analytics._pearson_with_n([5, 5, 5, 5, 5, 5], [1, 2, 3, 4, 5, 6])
    assert r is None  # x has zero variance


def test_signal_strength_strong():
    assert analytics._signal_strength(0.7, 100) == "strong"
    assert analytics._signal_strength(-0.6, 50) == "strong"


def test_signal_strength_moderate():
    assert analytics._signal_strength(0.4, 25) == "moderate"


def test_signal_strength_weak():
    assert analytics._signal_strength(0.25, 15) == "weak"


def test_signal_strength_noise():
    assert analytics._signal_strength(0.1, 100) == "noise"
    assert analytics._signal_strength(0.9, 3) == "noise"  # too few samples
    assert analytics._signal_strength(None, 1000) == "noise"


def test_resolve_metric_aliases():
    assert analytics.resolve_metric("hrv") == "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"
    assert analytics.resolve_metric("HRV") == "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"
    assert analytics.resolve_metric("vo2max") == "HKQuantityTypeIdentifierVO2Max"
    assert analytics.resolve_metric("mindful_minutes") == "HKCategoryTypeIdentifierMindfulSession"
    # Pass-through for HK*
    assert analytics.resolve_metric("HKQuantityTypeIdentifierBodyTemperature") == "HKQuantityTypeIdentifierBodyTemperature"
    # Unknown returns input
    assert analytics.resolve_metric("xyznotreal") == "xyznotreal"


# --- DB-backed tests: seeded fixtures ----------------------------------

def _seed_records(con, metric: str, day_value_pairs: list[tuple[date, float]], unit: str = "count"):
    for d, v in day_value_pairs:
        start = datetime.combine(d, datetime.min.time()) + timedelta(hours=3)
        end = start + timedelta(seconds=1)
        con.execute(
            "INSERT INTO records (type, source_name, unit, start_date, end_date, value, value_str) "
            "VALUES (?, 'TestDevice', ?, ?, ?, ?, NULL)",
            [metric, unit, start, end, v],
        )


def test_correlate_finds_strong_positive():
    with db.connect() as con:
        days = [date(2026, 1, 1) + timedelta(days=i) for i in range(40)]
        # HRV linearly correlates with steps
        _seed_records(con, "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
                      [(d, 30 + i) for i, d in enumerate(days)], unit="ms")
        _seed_records(con, "HKQuantityTypeIdentifierStepCount",
                      [(d, 5000 + i * 100) for i, d in enumerate(days)], unit="count")
    with db.connect(read_only=True) as con:
        res = analytics.correlate(con, "hrv", "steps", lookback_days=365, end_date=date(2026, 2, 15))
    assert res["n"] >= 30
    assert res["r"] is not None and res["r"] > 0.95
    assert res["signal_strength"] == "strong"


def test_correlate_finds_noise_when_random():
    import random
    random.seed(42)
    with db.connect() as con:
        days = [date(2026, 1, 1) + timedelta(days=i) for i in range(40)]
        _seed_records(con, "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
                      [(d, random.uniform(20, 60)) for d in days])
        _seed_records(con, "HKQuantityTypeIdentifierRestingHeartRate",
                      [(d, random.uniform(55, 75)) for d in days])
    with db.connect(read_only=True) as con:
        res = analytics.correlate(con, "hrv", "rhr", lookback_days=365, end_date=date(2026, 2, 15))
    # Random data should not produce a strong signal
    assert res["signal_strength"] in ("weak", "noise")


def test_correlate_unknown_group_by_returns_error():
    with db.connect() as con:
        _seed_records(con, "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
                      [(date(2026, 1, 1) + timedelta(days=i), 30 + i) for i in range(10)])
        _seed_records(con, "HKQuantityTypeIdentifierStepCount",
                      [(date(2026, 1, 1) + timedelta(days=i), 5000 + i) for i in range(10)])
    with db.connect(read_only=True) as con:
        res = analytics.correlate(con, "hrv", "steps", group_by="bogus", lookback_days=365, end_date=date(2026, 2, 1))
    assert "error" in res


def test_sleep_architecture_computes_stage_percentages():
    with db.connect() as con:
        # One night: 8h total in bed, 5h Core, 1.5h REM, 1h Deep, 0.5h Awake
        night_start = datetime(2026, 5, 1, 23, 0, 0)
        segments = [
            (night_start, night_start + timedelta(hours=5), "Core"),
            (night_start + timedelta(hours=5), night_start + timedelta(hours=6, minutes=30), "REM"),
            (night_start + timedelta(hours=6, minutes=30), night_start + timedelta(hours=7, minutes=30), "Deep"),
            (night_start + timedelta(hours=7, minutes=30), night_start + timedelta(hours=8), "Awake"),
        ]
        for s, e, stage in segments:
            con.execute(
                "INSERT INTO sleep (start_date, end_date, stage, source_name) VALUES (?, ?, ?, 'TestDevice')",
                [s, e, stage],
            )
    with db.connect(read_only=True) as con:
        res = analytics.sleep_architecture(con, date(2026, 5, 1), date(2026, 5, 3))
    assert res["nights"] == 1
    # 1.5h REM / 7.5h asleep = 20%
    assert res["rem_pct_mean"] is not None and 19 < res["rem_pct_mean"] < 21
    # 1h Deep / 7.5h asleep = ~13.3%
    assert res["deep_pct_mean"] is not None and 12 < res["deep_pct_mean"] < 15
    # 5h Core / 7.5h asleep = ~66.7%
    assert res["core_pct_mean"] is not None and 65 < res["core_pct_mean"] < 68


def test_longitudinal_summary_monthly_buckets():
    with db.connect() as con:
        # 3 months of HRV: 35 in Jan, 40 in Feb, 45 in Mar
        for month_offset, mean_val in enumerate([35.0, 40.0, 45.0]):
            for day in range(1, 28):
                d = date(2026, 1 + month_offset, day)
                _seed_records(con, "HKQuantityTypeIdentifierHeartRateVariabilitySDNN", [(d, mean_val)], unit="ms")
    with db.connect(read_only=True) as con:
        res = analytics.longitudinal_summary(con, date(2026, 1, 1), date(2026, 4, 1), granularity="month")
    assert res["granularity"] == "month"
    assert len(res["buckets"]) == 3
    # Buckets sorted by date; check hrv_baseline values
    assert math.isclose(res["buckets"][0]["hrv_baseline"], 35.0, abs_tol=0.1)
    assert math.isclose(res["buckets"][1]["hrv_baseline"], 40.0, abs_tol=0.1)
    assert math.isclose(res["buckets"][2]["hrv_baseline"], 45.0, abs_tol=0.1)


def test_loop_signature_compares_match_to_baseline():
    with db.connect() as con:
        # 30 days of HRV. First 5 days are the "loop" with HRV=25. Other 25 are HRV=40.
        days = [date(2026, 5, 1) + timedelta(days=i) for i in range(30)]
        for i, d in enumerate(days):
            v = 25.0 if i < 5 else 40.0
            _seed_records(con, "HKQuantityTypeIdentifierHeartRateVariabilitySDNN", [(d, v)], unit="ms")
    loop_dates = days[:5]
    with db.connect(read_only=True) as con:
        res = analytics.loop_signature(con, Path("/tmp/nonexistent"), loop_dates,
                                       lookback_days=60, end_date=date(2026, 6, 30))
    assert res["loop_match_days"] == 5
    hrv = res["metrics"]["hrv"]
    assert hrv["on_loop"] is not None and math.isclose(hrv["on_loop"], 25.0, abs_tol=0.1)
    assert hrv["baseline"] is not None and math.isclose(hrv["baseline"], 40.0, abs_tol=0.1)
    # Loop HRV is 37.5% below baseline
    assert hrv["delta_pct"] is not None and -40 < hrv["delta_pct"] < -35


def test_correlate_resolves_friendly_names():
    """The friendly aliases work end-to-end."""
    with db.connect() as con:
        days = [date(2026, 1, 1) + timedelta(days=i) for i in range(20)]
        _seed_records(con, "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
                      [(d, 30 + i) for i, d in enumerate(days)], unit="ms")
        _seed_records(con, "HKQuantityTypeIdentifierActiveEnergyBurned",
                      [(d, 400 + i * 10) for i, d in enumerate(days)], unit="kcal")
    with db.connect(read_only=True) as con:
        res = analytics.correlate(con, "hrv", "active_energy", lookback_days=365, end_date=date(2026, 2, 1))
    assert res["metric_a"] == "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"
    assert res["metric_b"] == "HKQuantityTypeIdentifierActiveEnergyBurned"
    assert res["n"] >= 15


def test_correlate_handles_no_data():
    with db.connect(read_only=True) as con:
        res = analytics.correlate(con, "hrv", "steps", lookback_days=30, end_date=date(2030, 1, 1))
    assert res["n"] == 0
    assert res["r"] is None
    assert res["signal_strength"] == "noise"


def test_symptom_correlate_with_no_symptom_data():
    with db.connect(read_only=True) as con:
        res = analytics.symptom_correlate(con, lookback_days=30, end_date=date(2026, 5, 10))
    assert "per_symptom" in res or "metrics" in res
    # No symptom data means per_symptom is empty
    if "per_symptom" in res:
        assert res["per_symptom"] == {}


def test_top_signals_filters_below_min_strength():
    """top_signals with min_strength='strong' should drop weak signals."""
    import random
    random.seed(0)
    with db.connect() as con:
        days = [date(2026, 1, 1) + timedelta(days=i) for i in range(40)]
        _seed_records(con, "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
                      [(d, random.uniform(30, 50)) for d in days])
        _seed_records(con, "HKQuantityTypeIdentifierRestingHeartRate",
                      [(d, random.uniform(55, 70)) for d in days])
        _seed_records(con, "HKQuantityTypeIdentifierStepCount",
                      [(d, random.uniform(5000, 12000)) for d in days])
    with db.connect(read_only=True) as con:
        res_strong = analytics.top_signals(con, lookback_days=365, end_date=date(2026, 3, 1), min_strength="strong")
        res_weak = analytics.top_signals(con, lookback_days=365, end_date=date(2026, 3, 1), min_strength="weak")
    # Strong filter should yield 0 or very few; weak filter may include more
    assert res_strong["signal_count"] <= res_weak["signal_count"]
