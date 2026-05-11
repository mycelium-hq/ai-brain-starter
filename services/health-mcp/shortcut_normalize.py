"""Apple Shortcuts JSON -> DuckDB-row normalizer.

The companion iOS Shortcut (`shortcut/health-daily.shortcut`) reads HealthKit
data via the Shortcuts `Find Health Samples` action, builds a single JSON
document for the day, and writes it to iCloud Drive at:

    ~/Library/Mobile Documents/com~apple~CloudDocs/health-mcp/<YYYY-MM-DD>.json

This module reads that JSON and yields the same `_kind`-tagged dicts that
`parse_xml.iter_records` produces, so `_bulk_insert` works without
modification.

Why a JSON file over iCloud Drive instead of an HTTP server?

  - Zero lifecycle: no daemon to start/stop, no port to manage.
  - iCloud bridges iPhone -> Mac for free; the Shortcut just writes a file.
  - The Mac-side processor reads + ingests + moves the file to processed/
    on the daily journal-Stop chain. Idempotent via file SHA.
  - Works offline (queues in iCloud, processes when both devices online).

Payload shape (versioned via `schema_version`):

    {
      "schema_version": 1,
      "exported_at": "2026-05-10T06:00:00-05:00",
      "date": "2026-05-09",
      "device": "iPhone",
      "samples": {
        "HKQuantityTypeIdentifierHeartRate": [
          {"start": "2026-05-09T08:00:00-05:00",
           "end":   "2026-05-09T08:00:30-05:00",
           "value": 62, "unit": "count/min", "source": "Apple Watch"},
          ...
        ],
        "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": [...],
        ...
      },
      "sleep":    [{"start": "...", "end": "...", "stage": "REM",  "source": "Apple Watch"}],
      "workouts": [{"activity_type": "Running",
                    "start": "...", "end": "...",
                    "duration_min": 32, "distance_km": 5.2, "energy_kcal": 320,
                    "source": "Apple Watch"}],
      "mindful":  [{"start": "...", "end": "...", "duration_min": 10, "source": "Mindfulness"}],
      "cycle":    [{"type": "MenstrualFlow", "start": "...",
                    "end": "...", "value": "medium", "source": "Cycle Tracking"}],
      "state_of_mind": [{"start": "...", "end": "...",
                         "kind": "momentary", "valence": 0.4,
                         "labels": "calm,focused", "associations": "writing",
                         "source": "Mindfulness"}]
    }

Apple Shortcuts cannot read every HealthKit type. ECG records, for example,
are not exposed via `Find Health Samples`. Users who want full coverage
should run `health_import_xml` periodically alongside this auto-sync.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

# Sleep stage names from Apple Shortcuts -> our canonical SLEEP_STAGE_MAP keys.
# The Shortcuts surface uses friendlier names than the raw HKCategoryValueSleepAnalysis*
# constants. We accept both.
_SLEEP_STAGE_ALIASES = {
    "InBed": "InBed",
    "In Bed": "InBed",
    "Asleep": "AsleepUnspecified",
    "AsleepUnspecified": "AsleepUnspecified",
    "Awake": "Awake",
    "REM": "REM",
    "AsleepREM": "REM",
    "Core": "Core",
    "AsleepCore": "Core",
    "Deep": "Deep",
    "AsleepDeep": "Deep",
}


def _coerce_value(v: Any) -> tuple[float | None, str | None]:
    """Return (numeric, string) form of a value.
    Numeric goes into `value`, string into `value_str`. Mirrors parse_xml."""
    if v is None:
        return None, None
    if isinstance(v, (int, float)):
        return float(v), None
    if isinstance(v, str):
        try:
            return float(v), None
        except ValueError:
            return None, v
    return None, str(v)


def _norm_sleep_stage(s: str | None) -> str:
    if not s:
        return "Asleep"
    return _SLEEP_STAGE_ALIASES.get(s, s)


def iter_payload(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Walk a Shortcut payload dict and yield `_kind`-tagged dicts.

    Same output shape as parse_xml.iter_records, so _bulk_insert handles
    both without branching.
    """
    samples = payload.get("samples") or {}
    if not isinstance(samples, dict):
        samples = {}

    for type_id, entries in samples.items():
        if not isinstance(entries, list):
            continue
        for s in entries:
            if not isinstance(s, dict):
                continue
            v, vs = _coerce_value(s.get("value"))
            yield {
                "_kind": "record",
                "type": type_id,
                "source_name": s.get("source") or payload.get("device") or "Apple Health",
                "unit": s.get("unit") or "",
                "start_date": s.get("start"),
                "end_date": s.get("end") or s.get("start"),
                "value": v,
                "value_str": vs,
            }

    for w in payload.get("workouts") or []:
        if not isinstance(w, dict):
            continue
        yield {
            "_kind": "workout",
            "activity_type": w.get("activity_type") or w.get("type") or "Other",
            "duration_min": float(w["duration_min"]) if w.get("duration_min") is not None else None,
            "distance_km": float(w["distance_km"]) if w.get("distance_km") is not None else None,
            "energy_kcal": float(w["energy_kcal"]) if w.get("energy_kcal") is not None else None,
            "start_date": w.get("start"),
            "end_date": w.get("end") or w.get("start"),
            "source_name": w.get("source") or payload.get("device") or "Apple Watch",
        }

    for sl in payload.get("sleep") or []:
        if not isinstance(sl, dict):
            continue
        yield {
            "_kind": "sleep",
            "start_date": sl.get("start"),
            "end_date": sl.get("end") or sl.get("start"),
            "stage": _norm_sleep_stage(sl.get("stage")),
            "source_name": sl.get("source") or payload.get("device") or "Apple Watch",
        }

    for c in payload.get("cycle") or []:
        if not isinstance(c, dict):
            continue
        v_num, v_str = _coerce_value(c.get("value"))
        yield {
            "_kind": "cycle",
            "type": c.get("type"),
            "start_date": c.get("start"),
            "end_date": c.get("end") or c.get("start"),
            "value": v_str if v_str is not None else (str(v_num) if v_num is not None else None),
            "source_name": c.get("source") or payload.get("device") or "Cycle Tracking",
        }

    for sym in payload.get("symptoms") or []:
        if not isinstance(sym, dict):
            continue
        yield {
            "_kind": "symptom",
            "type": sym.get("type"),
            "start_date": sym.get("start"),
            "end_date": sym.get("end") or sym.get("start"),
            "severity": sym.get("severity") or "Present",
            "source_name": sym.get("source") or payload.get("device") or "Apple Health",
        }

    for som in payload.get("state_of_mind") or []:
        if not isinstance(som, dict):
            continue
        yield {
            "_kind": "state_of_mind",
            "start_date": som.get("start"),
            "end_date": som.get("end") or som.get("start"),
            "kind": som.get("kind") or "momentary",
            "valence": float(som["valence"]) if som.get("valence") is not None else None,
            "labels": som.get("labels") or "",
            "associations": som.get("associations") or "",
            "source_name": som.get("source") or payload.get("device") or "Mindfulness",
        }

    # Mindful sessions are stored as records with a duration_min in `value`,
    # mirroring the XML import path (parse_xml maps HKCategoryTypeIdentifierMindfulSession
    # this way so the journal/coaching skills can sum mindful minutes per day).
    for m in payload.get("mindful") or []:
        if not isinstance(m, dict):
            continue
        dur = m.get("duration_min")
        yield {
            "_kind": "record",
            "type": "HKCategoryTypeIdentifierMindfulSession",
            "source_name": m.get("source") or payload.get("device") or "Mindfulness",
            "unit": "min",
            "start_date": m.get("start"),
            "end_date": m.get("end") or m.get("start"),
            "value": float(dur) if dur is not None else None,
            "value_str": None,
        }


def load_payload_file(path: str | Path) -> dict[str, Any]:
    """Read a Shortcut payload JSON file and return the parsed dict.

    Raises FileNotFoundError if the file is missing, json.JSONDecodeError if
    the file is malformed. Caller is responsible for moving / archiving.
    """
    p = Path(path).expanduser()
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Shortcut payload at {p} is not a JSON object")
    return data


def payload_sha(path: str | Path) -> str:
    """Stable SHA over the payload file content for idempotency."""
    import hashlib
    p = Path(path).expanduser()
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def default_inbox() -> Path:
    """Where the iOS Shortcut writes payloads.

    iCloud Drive root differs by user; this is the standard macOS path for
    the iCloud Drive 'Shortcuts' bridge. The Shortcut writes to a
    health-mcp/ subfolder which the user creates once.
    """
    return Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "health-mcp"


def default_processed() -> Path:
    return default_inbox() / "processed"
