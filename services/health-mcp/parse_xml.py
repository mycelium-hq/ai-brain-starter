"""Apple Health export.zip / export.xml streaming parser.

Routes records into the appropriate DuckDB table based on the type registry
in hk_types.py:

  HKQuantityType*                    -> records (with unit + value)
  HKCategoryTypeIdentifierSleepAnalysis -> sleep (with stage)
  HKCategoryTypeIdentifierMenstrualFlow + reproductive types -> cycle
  HKCategoryTypeIdentifier{Symptom}    -> symptoms (with severity)
  HKWorkout                           -> workouts
  HKElectrocardiogram                  -> ecg
  HKStateOfMind                       -> state_of_mind (iOS 17+)
  HKCategoryTypeIdentifierMindfulSession -> records (duration math)

Uses lxml.etree.iterparse with `clear()` after each element so memory stays
bounded on multi-million-record exports.
"""
from __future__ import annotations

import hashlib
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

try:
    from lxml import etree as ET  # type: ignore
except ImportError:  # pragma: no cover - dep is hard-required in pyproject
    import xml.etree.ElementTree as ET  # fallback; slower, higher RAM

from hk_types import (
    CERVICAL_MUCUS_MAP,
    HK_CATEGORY_TYPES,
    OVULATION_TEST_MAP,
    PREGNANCY_TEST_MAP,
    SLEEP_STAGE_MAP,
    SYMPTOM_SEVERITY_MAP,
)


# Apple Health date format: "2026-01-01 08:00:00 -0500"
_HEALTH_DT_FMT = "%Y-%m-%d %H:%M:%S %z"


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, _HEALTH_DT_FMT)
    except ValueError:
        try:
            return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_xml_from_zip(zip_path: Path, scratch_dir: Path) -> Path:
    scratch_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        candidates = [n for n in zf.namelist() if n.endswith("/export.xml") or n == "export.xml"]
        if not candidates:
            raise FileNotFoundError(
                f"No export.xml found inside {zip_path}. "
                "Expected an Apple Health export.zip from iOS Health > Profile > Export All Health Data."
            )
        out = scratch_dir / "export.xml"
        with zf.open(candidates[0]) as src, open(out, "wb") as dst:
            for chunk in iter(lambda: src.read(1 << 20), b""):
                dst.write(chunk)
    return out


def resolve_xml_path(input_path: str) -> tuple[Path, str, Path | None]:
    p = Path(input_path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"{input_path} does not exist")
    sha = _sha256_file(p)
    if p.suffix.lower() == ".zip":
        scratch = p.parent / "health-mcp-extract"
        xml = _extract_xml_from_zip(p, scratch)
        return xml, sha, scratch
    if p.suffix.lower() == ".xml":
        return p, sha, None
    raise ValueError(f"Unsupported file type: {p.suffix}. Expected .zip or .xml.")


_CYCLE_VALUE_MAPS = {
    "HKCategoryTypeIdentifierMenstrualFlow": {
        "HKCategoryValueMenstrualFlowUnspecified": "unspecified",
        "HKCategoryValueMenstrualFlowLight": "light",
        "HKCategoryValueMenstrualFlowMedium": "medium",
        "HKCategoryValueMenstrualFlowHeavy": "heavy",
        "HKCategoryValueMenstrualFlowNone": "none",
    },
    "HKCategoryTypeIdentifierCervicalMucusQuality": CERVICAL_MUCUS_MAP,
    "HKCategoryTypeIdentifierOvulationTestResult": OVULATION_TEST_MAP,
    "HKCategoryTypeIdentifierPregnancyTestResult": PREGNANCY_TEST_MAP,
    "HKCategoryTypeIdentifierProgesteroneTestResult": {
        "HKCategoryValueProgesteroneTestResultNegative": "negative",
        "HKCategoryValueProgesteroneTestResultPositive": "positive",
        "HKCategoryValueProgesteroneTestResultIndeterminate": "indeterminate",
    },
    "HKCategoryTypeIdentifierContraceptive": {
        "HKCategoryValueContraceptiveUnspecified": "unspecified",
        "HKCategoryValueContraceptiveImplant": "implant",
        "HKCategoryValueContraceptiveInjection": "injection",
        "HKCategoryValueContraceptiveIntrauterineDevice": "iud",
        "HKCategoryValueContraceptiveIntravaginalRing": "ring",
        "HKCategoryValueContraceptiveOral": "oral",
        "HKCategoryValueContraceptivePatch": "patch",
    },
}


def _map_cycle_value(type_id: str, raw: str) -> str:
    table = _CYCLE_VALUE_MAPS.get(type_id, {})
    if raw in table:
        return table[raw]
    if raw.startswith("HKCategoryValue"):
        return raw.replace("HKCategoryValue", "").lower()
    return raw or "unknown"


def _record_kind_for(type_id: str) -> str:
    """Decide which downstream table a Record element belongs to."""
    if type_id == "HKCategoryTypeIdentifierSleepAnalysis":
        return "sleep"
    meta = HK_CATEGORY_TYPES.get(type_id)
    if meta:
        if meta.get("category") == "cycle":
            return "cycle"
        if meta.get("category") in {"symptom", "cardio_event", "sensory", "lifestyle"}:
            return "symptom"
        if meta.get("category") == "mindfulness":
            return "record_duration"
    return "record"


def iter_records(xml_path: Path) -> Iterator[dict[str, Any]]:
    """Stream Record / Workout / ECG / StateOfMind elements out of export.xml.

    Yields dicts shaped per their target table. The first key `_kind` is
    'record' | 'record_duration' | 'workout' | 'sleep' | 'cycle' | 'symptom'
    | 'ecg' | 'state_of_mind'. The MCP main.py routes the inserts.
    """
    context = ET.iterparse(str(xml_path), events=("end",))
    for _, elem in context:
        tag = elem.tag

        if tag == "Record":
            attrib = elem.attrib
            rec_type = attrib.get("type", "")
            start = _parse_dt(attrib.get("startDate"))
            end = _parse_dt(attrib.get("endDate"))
            if not (rec_type and start and end):
                elem.clear()
                continue

            kind = _record_kind_for(rec_type)
            source = attrib.get("sourceName", "")

            if kind == "sleep":
                stage_raw = attrib.get("value", "")
                stage = SLEEP_STAGE_MAP.get(stage_raw, "asleep_unspecified")
                yield {
                    "_kind": "sleep",
                    "start_date": start,
                    "end_date": end,
                    "stage": stage,
                    "source_name": source,
                }
            elif kind == "cycle":
                yield {
                    "_kind": "cycle",
                    "type": rec_type,
                    "start_date": start,
                    "end_date": end,
                    "value": _map_cycle_value(rec_type, attrib.get("value", "")),
                    "source_name": source,
                }
            elif kind == "symptom":
                raw = attrib.get("value", "")
                severity = SYMPTOM_SEVERITY_MAP.get(raw, "event" if raw == "" else raw)
                yield {
                    "_kind": "symptom",
                    "type": rec_type,
                    "start_date": start,
                    "end_date": end,
                    "severity": severity,
                    "source_name": source,
                }
            elif kind == "record_duration":
                # Mindful sessions: store as records with duration encoded via
                # start/end so health_metric_series can sum minutes.
                yield {
                    "_kind": "record",
                    "type": rec_type,
                    "source_name": source,
                    "unit": "min",
                    "start_date": start,
                    "end_date": end,
                    "value": (end - start).total_seconds() / 60.0,
                    "value_str": None,
                }
            else:
                value_str = attrib.get("value", "")
                try:
                    value = float(value_str) if value_str else None
                except ValueError:
                    value = None
                yield {
                    "_kind": "record",
                    "type": rec_type,
                    "source_name": source,
                    "unit": attrib.get("unit", ""),
                    "start_date": start,
                    "end_date": end,
                    "value": value,
                    "value_str": value_str if value is None else None,
                }
            elem.clear()

        elif tag == "Workout":
            attrib = elem.attrib
            start = _parse_dt(attrib.get("startDate"))
            end = _parse_dt(attrib.get("endDate"))
            if not (start and end):
                elem.clear()
                continue
            try:
                duration = float(attrib.get("duration", "0") or 0)
            except ValueError:
                duration = 0.0
            duration_unit = attrib.get("durationUnit", "min")
            duration_min = (
                duration
                if duration_unit == "min"
                else duration * 60.0
                if duration_unit in {"hr", "h"}
                else duration / 60.0
                if duration_unit in {"sec", "s"}
                else duration
            )
            try:
                distance = float(attrib.get("totalDistance", "0") or 0)
            except ValueError:
                distance = 0.0
            distance_unit = attrib.get("totalDistanceUnit", "km")
            distance_km = (
                distance
                if distance_unit in {"km", "kilometer"}
                else distance * 1.609344
                if distance_unit in {"mi", "mile"}
                else distance / 1000.0
                if distance_unit in {"m", "meter"}
                else distance
            )
            try:
                energy = float(attrib.get("totalEnergyBurned", "0") or 0)
            except ValueError:
                energy = 0.0
            yield {
                "_kind": "workout",
                "activity_type": attrib.get("workoutActivityType", "HKWorkoutActivityTypeOther"),
                "duration_min": duration_min,
                "distance_km": distance_km if distance > 0 else None,
                "energy_kcal": energy if energy > 0 else None,
                "start_date": start,
                "end_date": end,
                "source_name": attrib.get("sourceName", ""),
            }
            elem.clear()

        elif tag == "ElectrocardiogramRecord" or tag == "Electrocardiogram":
            attrib = elem.attrib
            start = _parse_dt(attrib.get("startDate"))
            if not start:
                elem.clear()
                continue
            classification = attrib.get("classification", attrib.get("symptomsStatus", "")) or "unknown"
            try:
                avg_hr = float(attrib.get("averageHeartRate", "0") or 0)
            except ValueError:
                avg_hr = 0.0
            try:
                sf = float(attrib.get("samplingFrequency", "0") or 0)
            except ValueError:
                sf = 0.0
            yield {
                "_kind": "ecg",
                "start_date": start,
                "classification": classification.replace("HKElectrocardiogramClassification", "").lower() or "unknown",
                "average_heart_rate": avg_hr if avg_hr > 0 else None,
                "sampling_frequency": sf if sf > 0 else None,
                "source_name": attrib.get("sourceName", ""),
            }
            elem.clear()

        elif tag == "StateOfMind":
            attrib = elem.attrib
            start = _parse_dt(attrib.get("startDate"))
            end = _parse_dt(attrib.get("endDate")) or start
            if not start:
                elem.clear()
                continue
            try:
                valence = float(attrib.get("valence", "0") or 0)
            except ValueError:
                valence = 0.0
            yield {
                "_kind": "state_of_mind",
                "start_date": start,
                "end_date": end,
                "kind": attrib.get("kind", ""),
                "valence": valence,
                "labels": attrib.get("labels", ""),
                "associations": attrib.get("associations", ""),
                "source_name": attrib.get("sourceName", ""),
            }
            elem.clear()

        elif tag in ("HealthData", "Me", "ExportDate"):
            pass
        else:
            elem.clear()
    del context
