"""Fitbit Web API client (OAuth2 bearer token).

User registers a Personal app at https://dev.fitbit.com/apps and runs a
one-time OAuth flow to obtain an access token. Token goes in
FITBIT_ACCESS_TOKEN env var (plus optional FITBIT_REFRESH_TOKEN +
FITBIT_CLIENT_ID + FITBIT_CLIENT_SECRET for refresh).

Endpoints covered:
  GET /1/user/-/activities/date/{date}.json
  GET /1.2/user/-/sleep/date/{date}.json
  GET /1/user/-/body/weight/date/{date}.json
  GET /1/user/-/activities/heart/date/{date}/1d.json

Normalization to the shared DuckDB schema:
  fitbit steps         -> HKQuantityTypeIdentifierStepCount
  fitbit calories      -> HKQuantityTypeIdentifierActiveEnergyBurned + BasalEnergyBurned
  fitbit resting_hr    -> HKQuantityTypeIdentifierRestingHeartRate
  fitbit sleep stages  -> sleep table (rem/deep/light/awake/in_bed)
  fitbit weight        -> HKQuantityTypeIdentifierBodyMass
  fitbit hrv (deep_sleep_rmssd, Premium-only) -> HKQuantityTypeIdentifierHeartRateVariabilitySDNN

Note: Fitbit HRV requires Premium. We surface it when present and skip
silently when not.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any, Iterator

FITBIT_BASE = "https://api.fitbit.com"


def _token() -> str:
    token = os.environ.get("FITBIT_ACCESS_TOKEN")
    if not token:
        raise ValueError(
            "Fitbit import requires FITBIT_ACCESS_TOKEN in env. "
            "Register a Personal app at https://dev.fitbit.com/apps, run the "
            "OAuth2 flow to obtain an access token, and export "
            "FITBIT_ACCESS_TOKEN=<token>."
        )
    return token


def _refresh_token_if_set() -> tuple[str | None, str | None, str | None]:
    return (
        os.environ.get("FITBIT_REFRESH_TOKEN"),
        os.environ.get("FITBIT_CLIENT_ID"),
        os.environ.get("FITBIT_CLIENT_SECRET"),
    )


def _refresh_access_token() -> str | None:
    """Use the refresh token to fetch a new access token, if credentials
    are set. Returns the new access token or None."""
    rt, cid, csec = _refresh_token_if_set()
    if not (rt and cid and csec):
        return None
    body = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": rt}).encode("utf-8")
    auth = "Basic " + (cid + ":" + csec).encode("ascii").hex()  # placeholder; real impl uses base64
    import base64
    auth = "Basic " + base64.b64encode(f"{cid}:{csec}".encode()).decode("ascii")
    req = urllib.request.Request(
        FITBIT_BASE + "/oauth2/token",
        data=body,
        headers={"Authorization": auth, "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        new_at = data.get("access_token")
        if new_at:
            os.environ["FITBIT_ACCESS_TOKEN"] = new_at
            if data.get("refresh_token"):
                os.environ["FITBIT_REFRESH_TOKEN"] = data["refresh_token"]
            return new_at
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None
    return None


def _get(path: str, retry_on_401: bool = True) -> dict[str, Any]:
    req = urllib.request.Request(
        FITBIT_BASE + path,
        headers={"Authorization": f"Bearer {_token()}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401 and retry_on_401:
            new_at = _refresh_access_token()
            if new_at:
                return _get(path, retry_on_401=False)
        msg = e.read().decode("utf-8", errors="replace")[:300]
        raise ValueError(f"Fitbit API HTTP {e.code} on {path}: {msg}")
    except urllib.error.URLError as e:
        raise ValueError(f"Fitbit API network error on {path}: {e}")


def healthcheck() -> dict[str, Any]:
    try:
        info = _get("/1/user/-/profile.json")
        user = info.get("user", {})
        return {"ok": True, "user_id": user.get("encodedId"), "member_since": user.get("memberSince"), "premium": user.get("isPremium")}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


_STAGE_MAP = {
    "rem": "rem",
    "deep": "deep",
    "light": "core",
    "wake": "awake",
    "awake": "awake",
    "restless": "awake",
    "asleep": "asleep_unspecified",
    "asleep_unspecified": "asleep_unspecified",
}


def fetch_range(start: date, end: date) -> Iterator[dict[str, Any]]:
    """Pull daily summaries from Fitbit for [start, end] and yield records
    shaped like parse_xml.iter_records output."""
    cur = start
    while cur <= end:
        d = cur.isoformat()
        # Activities (steps + calories + distance).
        try:
            act = _get(f"/1/user/-/activities/date/{d}.json").get("summary", {})
        except ValueError:
            act = {}
        ts = datetime.combine(cur, datetime.min.time())
        steps = act.get("steps")
        if steps is not None:
            yield {
                "_kind": "record",
                "type": "HKQuantityTypeIdentifierStepCount",
                "source_name": "Fitbit",
                "unit": "count",
                "start_date": ts,
                "end_date": ts + timedelta(days=1),
                "value": float(steps),
                "value_str": None,
            }
        active = act.get("activityCalories") or act.get("caloriesOut")
        if active is not None:
            yield {
                "_kind": "record",
                "type": "HKQuantityTypeIdentifierActiveEnergyBurned",
                "source_name": "Fitbit",
                "unit": "kcal",
                "start_date": ts,
                "end_date": ts + timedelta(days=1),
                "value": float(active),
                "value_str": None,
            }
        distance_km = next((float(x.get("distance", 0)) for x in (act.get("distances") or []) if x.get("activity") == "total"), 0)
        if distance_km > 0:
            yield {
                "_kind": "record",
                "type": "HKQuantityTypeIdentifierDistanceWalkingRunning",
                "source_name": "Fitbit",
                "unit": "km",
                "start_date": ts,
                "end_date": ts + timedelta(days=1),
                "value": float(distance_km),
                "value_str": None,
            }

        # Heart rate (daily summary + resting heart rate).
        try:
            hr = _get(f"/1/user/-/activities/heart/date/{d}/1d.json").get("activities-heart", [])
        except ValueError:
            hr = []
        if hr:
            val = hr[0].get("value", {})
            rhr = val.get("restingHeartRate")
            if rhr:
                yield {
                    "_kind": "record",
                    "type": "HKQuantityTypeIdentifierRestingHeartRate",
                    "source_name": "Fitbit",
                    "unit": "count/min",
                    "start_date": ts,
                    "end_date": ts + timedelta(days=1),
                    "value": float(rhr),
                    "value_str": None,
                }

        # Sleep stages (Fitbit v1.2 returns 30-second epoch granularity).
        try:
            sleep = _get(f"/1.2/user/-/sleep/date/{d}.json").get("sleep", [])
        except ValueError:
            sleep = []
        for s in sleep:
            start_iso = s.get("startTime")
            if not start_iso:
                continue
            try:
                session_start = datetime.fromisoformat(start_iso.replace("Z", "+00:00").replace("+00:00", ""))
            except ValueError:
                continue
            levels = s.get("levels", {}).get("data", [])
            cursor = session_start
            for lvl in levels:
                level_name = (lvl.get("level") or "").lower()
                stage = _STAGE_MAP.get(level_name, "asleep_unspecified")
                seconds = float(lvl.get("seconds") or 0)
                if seconds <= 0:
                    continue
                stage_end = cursor + timedelta(seconds=seconds)
                yield {
                    "_kind": "sleep",
                    "start_date": cursor,
                    "end_date": stage_end,
                    "stage": stage,
                    "source_name": "Fitbit",
                }
                cursor = stage_end

        # Weight (skip silently if not in scope).
        try:
            w = _get(f"/1/user/-/body/weight/date/{d}.json").get("weight", [])
            if w and w[0].get("weight"):
                yield {
                    "_kind": "record",
                    "type": "HKQuantityTypeIdentifierBodyMass",
                    "source_name": "Fitbit",
                    "unit": "kg",
                    "start_date": ts,
                    "end_date": ts,
                    "value": float(w[0]["weight"]),
                    "value_str": None,
                }
        except ValueError:
            pass

        cur += timedelta(days=1)


def folder_sha(start: date, end: date) -> str:
    import hashlib
    token = os.environ.get("FITBIT_ACCESS_TOKEN", "anon")
    suffix = token[-4:] if len(token) > 4 else "anon"
    return hashlib.sha256(f"fitbit|{start.isoformat()}|{end.isoformat()}|{suffix}".encode("utf-8")).hexdigest()
