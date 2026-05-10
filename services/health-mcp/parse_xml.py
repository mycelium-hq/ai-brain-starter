"""Apple Health export.zip / export.xml streaming parser.

Apple Health export structure (typical 200-500 MB XML):
  <HealthData>
    <Record type="HKQuantityTypeIdentifierStepCount" sourceName="iPhone"
            unit="count" startDate="2026-01-01 08:00:00 -0500"
            endDate="2026-01-01 08:01:00 -0500" value="42"/>
    <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Watch"
            startDate="..." endDate="..." value="HKCategoryValueSleepAnalysisAsleepREM"/>
    <Workout workoutActivityType="HKWorkoutActivityTypeRunning"
             duration="32" durationUnit="min" totalDistance="5.1"
             totalDistanceUnit="km" totalEnergyBurned="320" totalEnergyBurnedUnit="kcal"
             startDate="..." endDate="..." sourceName="Watch"/>
  </HealthData>

We use `lxml.etree.iterparse` with `clear()` after each element so memory
stays bounded on multi-million-record exports.

Sleep stages:
  HKCategoryValueSleepAnalysisInBed                   -> "in_bed"
  HKCategoryValueSleepAnalysisAsleep                  -> "asleep_unspecified" (legacy)
  HKCategoryValueSleepAnalysisAwake                   -> "awake"
  HKCategoryValueSleepAnalysisAsleepCore              -> "core"
  HKCategoryValueSleepAnalysisAsleepDeep              -> "deep"
  HKCategoryValueSleepAnalysisAsleepREM               -> "rem"
  HKCategoryValueSleepAnalysisAsleepUnspecified       -> "asleep_unspecified"
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


SLEEP_STAGE_MAP = {
    "HKCategoryValueSleepAnalysisInBed": "in_bed",
    "HKCategoryValueSleepAnalysisAsleep": "asleep_unspecified",
    "HKCategoryValueSleepAnalysisAwake": "awake",
    "HKCategoryValueSleepAnalysisAsleepCore": "core",
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep_unspecified",
}

# Apple Health date format: "2026-01-01 08:00:00 -0500"
_HEALTH_DT_FMT = "%Y-%m-%d %H:%M:%S %z"


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, _HEALTH_DT_FMT)
    except ValueError:
        # Some exports use no offset; fall back to naive parse.
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
    """Pull export.xml out of an Apple Health export.zip into scratch_dir."""
    scratch_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        # Apple's export.zip puts export.xml at apple_health_export/export.xml
        candidates = [n for n in zf.namelist() if n.endswith("/export.xml") or n == "export.xml"]
        if not candidates:
            raise FileNotFoundError(
                f"No export.xml found inside {zip_path}. "
                "Expected an Apple Health export.zip from iOS Health → Profile → Export All Health Data."
            )
        xml_name = candidates[0]
        out = scratch_dir / "export.xml"
        with zf.open(xml_name) as src, open(out, "wb") as dst:
            for chunk in iter(lambda: src.read(1 << 20), b""):
                dst.write(chunk)
    return out


def resolve_xml_path(input_path: str) -> tuple[Path, str, Path | None]:
    """Resolve user input to (xml_path, file_sha, scratch_dir_to_clean).

    Accepts a path to .zip OR .xml. For zip, extracts export.xml into a
    sibling 'health-mcp-extract/' directory and returns its path. The caller
    is responsible for keeping (or pruning) the scratch dir.

    file_sha is computed against the ORIGINAL input (zip or xml) so re-import
    detection works on the user's intent (re-importing the same zip should
    skip even if extraction happens twice).
    """
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


def iter_records(xml_path: Path) -> Iterator[dict[str, Any]]:
    """Stream Record / Workout elements out of export.xml.

    Yields dicts shaped:
      {"_kind": "record", "type": "...", "source_name": "...", "unit": "...",
       "start_date": dt, "end_date": dt, "value": float | None, "value_str": str | None}
      {"_kind": "workout", "activity_type": "...", "duration_min": float,
       "distance_km": float | None, "energy_kcal": float | None,
       "start_date": dt, "end_date": dt, "source_name": "..."}
      {"_kind": "sleep", "start_date": dt, "end_date": dt,
       "stage": "rem|deep|core|awake|in_bed|asleep_unspecified",
       "source_name": "..."}
    """
    # iterparse with `events=("end",)` so we have full attrib at element close,
    # then clear() to release memory.
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

            if rec_type == "HKCategoryTypeIdentifierSleepAnalysis":
                stage_raw = attrib.get("value", "")
                stage = SLEEP_STAGE_MAP.get(stage_raw, "asleep_unspecified")
                yield {
                    "_kind": "sleep",
                    "start_date": start,
                    "end_date": end,
                    "stage": stage,
                    "source_name": attrib.get("sourceName", ""),
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
                    "source_name": attrib.get("sourceName", ""),
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
            duration_min = duration if duration_unit == "min" else duration * 60.0 if duration_unit in {"hr", "h"} else duration
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
        elif tag in ("HealthData", "Me", "ExportDate"):
            # Skip header tags but don't error.
            pass
        else:
            elem.clear()
    del context
