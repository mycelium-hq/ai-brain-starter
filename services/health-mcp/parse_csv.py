"""Simple Health Export CSV parser. Routes the same _kind dicts as parse_xml
so main.py uses one ingestion code path.
"""
from __future__ import annotations

import csv
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from hk_types import (
    HK_CATEGORY_TYPES,
    SLEEP_STAGE_MAP,
    SYMPTOM_SEVERITY_MAP,
)
from parse_xml import _CYCLE_VALUE_MAPS, _map_cycle_value, _record_kind_for

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
    h = hashlib.sha256()
    for p in sorted(folder.glob("*.csv")):
        st = p.stat()
        h.update(f"{p.name}|{st.st_size}|{int(st.st_mtime)}\n".encode("utf-8"))
    return h.hexdigest()


def folder_sha(folder_path: str) -> tuple[Path, str]:
    p = Path(folder_path).expanduser().resolve()
    if not p.is_dir():
        raise FileNotFoundError(f"{folder_path} is not a directory")
    if not list(p.glob("*.csv")):
        raise FileNotFoundError(
            f"No CSV files in {folder_path}. Expected HKQuantityTypeIdentifier*.csv "
            "and/or HKCategoryTypeIdentifier*.csv files from Simple Health Export."
        )
    return p, _sha256_folder(p)


def iter_records(folder: Path) -> Iterator[dict[str, Any]]:
    """Stream Simple Health Export CSVs into the unified record shape."""
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
                kind = _record_kind_for(rec_type)
                source = row.get("sourceName", "")
                raw_value = row.get("value", "")

                if kind == "sleep":
                    stage = SLEEP_STAGE_MAP.get(raw_value, "asleep_unspecified")
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
                        "value": _map_cycle_value(rec_type, raw_value),
                        "source_name": source,
                    }
                elif kind == "symptom":
                    severity = SYMPTOM_SEVERITY_MAP.get(raw_value, "event" if not raw_value else raw_value)
                    yield {
                        "_kind": "symptom",
                        "type": rec_type,
                        "start_date": start,
                        "end_date": end,
                        "severity": severity,
                        "source_name": source,
                    }
                elif kind == "record_duration":
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
                    yield {
                        "_kind": "record",
                        "type": rec_type,
                        "source_name": source,
                        "unit": "",
                        "start_date": start,
                        "end_date": end,
                        "value": None,
                        "value_str": raw_value,
                    }
