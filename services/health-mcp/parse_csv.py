"""Simple Health Export CSV parser.

Simple Health Export (free iOS app, App Store) writes one CSV per HKQuantity /
HKCategory type. The user dumps the folder to disk and points health_import_csv
at it. File-naming pattern (verified against neiltron/apple-health-mcp's docs
and the app's own README):

  HKQuantityTypeIdentifierStepCount.csv
  HKQuantityTypeIdentifierHeartRate.csv
  HKCategoryTypeIdentifierSleepAnalysis.csv
  ... etc.

Schema columns (consistent across all files):
  type, sourceName, sourceVersion, unit, startDate, endDate, value

For sleep, value is a stage label string (matches the XML category values).
"""
from __future__ import annotations

import csv
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from parse_xml import SLEEP_STAGE_MAP

_HEALTH_DT_FMT = "%Y-%m-%d %H:%M:%S %z"


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, _HEALTH_DT_FMT)
    except ValueError:
        try:
            return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def _sha256_folder(folder: Path) -> str:
    """Hash the sorted (filename, size, mtime) tuple set of all *.csv files in
    the folder. Cheaper than hashing contents and stable across re-export of
    the same dataset.
    """
    h = hashlib.sha256()
    for p in sorted(folder.glob("*.csv")):
        st = p.stat()
        h.update(f"{p.name}|{st.st_size}|{int(st.st_mtime)}\n".encode("utf-8"))
    return h.hexdigest()


def folder_sha(folder_path: str) -> tuple[Path, str]:
    """Resolve folder + return its sha. Raises if folder is missing or empty."""
    p = Path(folder_path).expanduser().resolve()
    if not p.is_dir():
        raise FileNotFoundError(f"{folder_path} is not a directory")
    if not list(p.glob("*.csv")):
        raise FileNotFoundError(
            f"No CSV files in {folder_path}. "
            "Expected a folder of HKQuantityTypeIdentifier*.csv / HKCategoryTypeIdentifier*.csv "
            "from the Simple Health Export iOS app."
        )
    return p, _sha256_folder(p)


def iter_records(folder: Path) -> Iterator[dict[str, Any]]:
    """Stream Simple Health Export CSVs into the unified record shape.

    Yields the same dict shapes as parse_xml.iter_records:
      record / sleep
    Workouts are not in Simple Health Export's standard set; if the user has a
    HKWorkout*.csv file, we surface the rows but as records (caller can filter).
    """
    for csv_path in sorted(folder.glob("HKQuantityTypeIdentifier*.csv")):
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                start = _parse_dt(row.get("startDate", ""))
                end = _parse_dt(row.get("endDate", ""))
                if not (start and end):
                    continue
                value_str = row.get("value", "")
                try:
                    value = float(value_str) if value_str else None
                except ValueError:
                    value = None
                yield {
                    "_kind": "record",
                    "type": row.get("type", csv_path.stem),
                    "source_name": row.get("sourceName", ""),
                    "unit": row.get("unit", ""),
                    "start_date": start,
                    "end_date": end,
                    "value": value,
                    "value_str": value_str if value is None else None,
                }

    for csv_path in sorted(folder.glob("HKCategoryTypeIdentifier*.csv")):
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                start = _parse_dt(row.get("startDate", ""))
                end = _parse_dt(row.get("endDate", ""))
                if not (start and end):
                    continue
                rec_type = row.get("type", csv_path.stem)
                if rec_type == "HKCategoryTypeIdentifierSleepAnalysis":
                    stage = SLEEP_STAGE_MAP.get(row.get("value", ""), "asleep_unspecified")
                    yield {
                        "_kind": "sleep",
                        "start_date": start,
                        "end_date": end,
                        "stage": stage,
                        "source_name": row.get("sourceName", ""),
                    }
                else:
                    # Mindful sessions, menstrual, etc. — surface as records
                    # so they're queryable through the same SQL surface.
                    yield {
                        "_kind": "record",
                        "type": rec_type,
                        "source_name": row.get("sourceName", ""),
                        "unit": "",
                        "start_date": start,
                        "end_date": end,
                        "value": None,
                        "value_str": row.get("value", ""),
                    }
