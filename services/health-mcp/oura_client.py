"""Oura Ring v2 Cloud API client.

Personal Access Token only — no OAuth flow. User generates a PAT at
https://cloud.ouraring.com/personal-access-tokens and exports it as
OURA_PERSONAL_ACCESS_TOKEN. The token never leaves the local machine.

Endpoints covered (Oura v2):
  GET /v2/usercollection/daily_sleep      — daily sleep score
  GET /v2/usercollection/sleep            — sleep sessions (stages)
  GET /v2/usercollection/daily_readiness  — readiness / recovery
  GET /v2/usercollection/daily_activity   — daily steps + active kcal
  GET /v2/usercollection/heartrate        — heart-rate samples
  GET /v2/usercollection/workout          — workouts

Normalization: every Oura datum gets mapped to the same DuckDB row shapes
used by parse_xml so the rest of the substrate (scores, vault-aware tools)
doesn't need to know it came from Oura.

Apple Health type-id mapping (consistent metric names across vendors):
  Oura hrv (avg)      -> HKQuantityTypeIdentifierHeartRateVariabilitySDNN
  Oura resting_hr     -> HKQuantityTypeIdentifierRestingHeartRate
  Oura steps          -> HKQuantityTypeIdentifierStepCount
  Oura active_kcal    -> HKQuantityTypeIdentifierActiveEnergyBurned
  Oura sleep stages   -> sleep table (rem / deep / core / awake / in_bed)
  Oura workouts       -> workouts table
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any, Iterator

OURA_BASE = "https://api.ouraring.com/v2/usercollection"


def _token() -> str:
    token = os.environ.get("OURA_PERSONAL_ACCESS_TOKEN") or os.environ.get("OURA_PAT")
    if not token:
        raise ValueError(
            "Oura import requires OURA_PERSONAL_ACCESS_TOKEN in env. "
            "Generate one at https://cloud.ouraring.com/personal-access-tokens "
            "and export OURA_PERSONAL_ACCESS_TOKEN=<token>."
        )
    return token


def _get(path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    qs = ""
    if params:
        qs = "?" + "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(
        OURA_BASE + path + qs,
        headers={"Authorization": f"Bearer {_token()}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")[:300]
        raise ValueError(f"Oura API HTTP {e.code} on {path}: {msg}")
    except urllib.error.URLError as e:
        raise ValueError(f"Oura API network error on {path}: {e}")


def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def healthcheck() -> dict[str, Any]:
    """Verify the token and return basic account info."""
    try:
        info = _get("/personal_info")
        return {"ok": True, "user_id": info.get("id"), "age": info.get("age"), "weight": info.get("weight")}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


def fetch_range(start: date, end: date) -> Iterator[dict[str, Any]]:
    """Pull all daily summaries + sleep + workouts in [start, end] and
    yield records shaped like parse_xml.iter_records output.
    Yields dicts with _kind in {record, sleep, workout}.
    """
    params = {"start_date": start.isoformat(), "end_date": end.isoformat()}

    # Daily sleep (sleep score) + Sleep sessions (stages).
    sleep_summary = _get("/daily_sleep", params).get("data", [])
    for d in sleep_summary:
        day = d.get("day")
        score = d.get("score")
        if day and score is not None:
            # Surface the daily sleep score as a generic record. Apple Health
            # does not have a canonical type id for "sleep score", so we use a
            # vendor-prefixed pseudo-id that health_metric_series can still query.
            ts = datetime.fromisoformat(day)
            yield {
                "_kind": "record",
                "type": "OuraDailySleepScore",
                "source_name": "Oura",
                "unit": "score",
                "start_date": ts,
                "end_date": ts,
                "value": float(score),
                "value_str": None,
            }

    sleep_sessions = _get("/sleep", params).get("data", [])
    for s in sleep_sessions:
        start_dt = _parse_iso(s.get("bedtime_start", ""))
        end_dt = _parse_iso(s.get("bedtime_end", ""))
        if not (start_dt and end_dt):
            continue
        # Oura splits sleep into rem/deep/light/awake (seconds since bedtime_start).
        # We emit one sleep row per stage as a contiguous block. Approximation,
        # since Oura returns aggregate per-stage minutes not stage transitions.
        rem_s = float(s.get("rem_sleep_duration") or 0)
        deep_s = float(s.get("deep_sleep_duration") or 0)
        light_s = float(s.get("light_sleep_duration") or 0)
        awake_s = float(s.get("awake_time") or 0)
        in_bed_s = float(s.get("time_in_bed") or 0)
        cursor = start_dt
        for stage_name, dur_s in (
            ("rem", rem_s),
            ("deep", deep_s),
            ("core", light_s),
            ("awake", awake_s),
        ):
            if dur_s <= 0:
                continue
            stage_end = cursor + timedelta(seconds=dur_s)
            yield {
                "_kind": "sleep",
                "start_date": cursor,
                "end_date": stage_end,
                "stage": stage_name,
                "source_name": "Oura",
            }
            cursor = stage_end
        # Emit an in-bed envelope marker so sleep_efficiency math works.
        if in_bed_s > 0:
            yield {
                "_kind": "sleep",
                "start_date": start_dt,
                "end_date": start_dt + timedelta(seconds=in_bed_s),
                "stage": "in_bed",
                "source_name": "Oura",
            }

        # Surface HRV + RHR from the sleep session as quantity records.
        hrv_avg = s.get("hrv", {}).get("average") if isinstance(s.get("hrv"), dict) else s.get("average_hrv")
        if hrv_avg:
            yield {
                "_kind": "record",
                "type": "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
                "source_name": "Oura",
                "unit": "ms",
                "start_date": start_dt,
                "end_date": end_dt,
                "value": float(hrv_avg),
                "value_str": None,
            }
        rhr = s.get("lowest_heart_rate") or s.get("average_heart_rate")
        if rhr:
            yield {
                "_kind": "record",
                "type": "HKQuantityTypeIdentifierRestingHeartRate",
                "source_name": "Oura",
                "unit": "count/min",
                "start_date": start_dt,
                "end_date": end_dt,
                "value": float(rhr),
                "value_str": None,
            }
        temp_dev = s.get("temperature_deviation")
        if temp_dev is not None:
            # Surface as wrist-temperature proxy. Note units differ from Apple
            # (Oura is celsius deviation, Apple is degF absolute) — caller
            # should not directly compare across vendors.
            yield {
                "_kind": "record",
                "type": "OuraTemperatureDeviationC",
                "source_name": "Oura",
                "unit": "degC_delta",
                "start_date": start_dt,
                "end_date": end_dt,
                "value": float(temp_dev),
                "value_str": None,
            }

    # Daily readiness (Oura's recovery score).
    readiness = _get("/daily_readiness", params).get("data", [])
    for r in readiness:
        day = r.get("day")
        score = r.get("score")
        if day and score is not None:
            ts = datetime.fromisoformat(day)
            yield {
                "_kind": "record",
                "type": "OuraReadinessScore",
                "source_name": "Oura",
                "unit": "score",
                "start_date": ts,
                "end_date": ts,
                "value": float(score),
                "value_str": None,
            }

    # Daily activity (steps + calories).
    activity = _get("/daily_activity", params).get("data", [])
    for a in activity:
        day = a.get("day")
        if not day:
            continue
        ts = datetime.fromisoformat(day)
        steps = a.get("steps")
        if steps is not None:
            yield {
                "_kind": "record",
                "type": "HKQuantityTypeIdentifierStepCount",
                "source_name": "Oura",
                "unit": "count",
                "start_date": ts,
                "end_date": ts + timedelta(days=1),
                "value": float(steps),
                "value_str": None,
            }
        active = a.get("active_calories")
        if active is not None:
            yield {
                "_kind": "record",
                "type": "HKQuantityTypeIdentifierActiveEnergyBurned",
                "source_name": "Oura",
                "unit": "kcal",
                "start_date": ts,
                "end_date": ts + timedelta(days=1),
                "value": float(active),
                "value_str": None,
            }
        total = a.get("total_calories")
        if total is not None and active is not None:
            yield {
                "_kind": "record",
                "type": "HKQuantityTypeIdentifierBasalEnergyBurned",
                "source_name": "Oura",
                "unit": "kcal",
                "start_date": ts,
                "end_date": ts + timedelta(days=1),
                "value": float(total) - float(active),
                "value_str": None,
            }

    # Workouts.
    workouts = _get("/workout", params).get("data", [])
    for w in workouts:
        start_dt = _parse_iso(w.get("start_datetime", ""))
        end_dt = _parse_iso(w.get("end_datetime", ""))
        if not (start_dt and end_dt):
            continue
        duration_min = (end_dt - start_dt).total_seconds() / 60.0
        yield {
            "_kind": "workout",
            "activity_type": w.get("activity", "OuraWorkout"),
            "duration_min": duration_min,
            "distance_km": (float(w.get("distance") or 0)) / 1000.0 if w.get("distance") else None,
            "energy_kcal": float(w.get("calories")) if w.get("calories") else None,
            "start_date": start_dt,
            "end_date": end_dt,
            "source_name": "Oura",
        }


def folder_sha(start: date, end: date) -> str:
    """Hash for idempotency. Oura imports are date-range scoped so we hash
    the range + token suffix (NOT the actual token — privacy)."""
    import hashlib
    token = _token()
    suffix = token[-4:] if len(token) > 4 else "anon"
    return hashlib.sha256(f"oura|{start.isoformat()}|{end.isoformat()}|{suffix}".encode("utf-8")).hexdigest()
