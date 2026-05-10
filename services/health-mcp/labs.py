"""Lab CSV ingestion for LabCorp / Quest / Function Health / generic exports.

Format heuristics — Apple Health does NOT capture clinical lab panels (it
captures glucose/oxygen/etc., but not the full chemistry panel). Users with
fasting insulin, hs-CRP, ApoB, full thyroid, sex hormones, etc. need to
export from their patient portal and import here.

CSV format (generic — what we standardize to internally):
  test_date,panel,marker,value,unit,range_low,range_high,status,source

Recognized vendor exports:
  - LabCorp patient-portal CSV (column "Test Name" + "Result" + "Reference Range")
  - Quest Diagnostics MyQuest CSV (column "Test" + "Value" + "Range")
  - Function Health CSV (column "biomarker" + "value" + "range")
  - Generic (already in canonical shape — just import)

Why this matters (Boham, panel 2026-05-10): the substrate's recovery-score
formula does not see fasting insulin or hs-CRP. A user with metabolic syndrome
will keep getting "rest more" recommendations when the actual prescription is
"address your labs." Exposing the panel here lets the journal / coaching /
panel skills pull lab context alongside biometrics.

The recommended-panel reference list lives in `recommended_panels()` so the
substrate can tell users WHICH labs would benefit them and why.
"""
from __future__ import annotations

import csv
import hashlib
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator


def _parse_date(s: str) -> date | None:
    if not s:
        return None
    s = s.strip()
    # Try ISO datetime first (handles trailing time component); then ISO date;
    # then US/EU short forms.
    if "T" in s or " " in s:
        try:
            return datetime.fromisoformat(s.split("T")[0].split(" ")[0]).date()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


_RANGE_RE = re.compile(r"\s*(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)\s*")


def _parse_range(s: str) -> tuple[float | None, float | None]:
    if not s:
        return None, None
    m = _RANGE_RE.search(s)
    if m:
        return float(m.group(1)), float(m.group(2))
    if s.startswith("<"):
        try:
            return None, float(s[1:].strip())
        except ValueError:
            return None, None
    if s.startswith(">"):
        try:
            return float(s[1:].strip()), None
        except ValueError:
            return None, None
    return None, None


def _classify(value: float | None, lo: float | None, hi: float | None) -> str:
    """status: 'low' | 'in_range' | 'high' | 'unknown'."""
    if value is None:
        return "unknown"
    if lo is not None and value < lo:
        return "low"
    if hi is not None and value > hi:
        return "high"
    if lo is not None or hi is not None:
        return "in_range"
    return "unknown"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _detect_format(headers: list[str]) -> str:
    h = [c.lower().strip() for c in headers]
    if any("test name" in c for c in h):
        return "labcorp"
    if any("test" == c for c in h) and any("value" in c for c in h):
        return "quest"
    if "biomarker" in h:
        return "function"
    if {"marker", "value", "test_date"}.issubset(h):
        return "generic"
    return "generic"


def _parse_labcorp(reader: csv.DictReader) -> Iterator[dict[str, Any]]:
    for row in reader:
        d = _parse_date(row.get("Date Collected", row.get("Date", "")))
        if not d:
            continue
        marker = row.get("Test Name", "").strip()
        try:
            value = float(row.get("Result", "").strip())
        except (ValueError, AttributeError):
            value = None
        unit = row.get("Units", row.get("Unit", "")).strip()
        lo, hi = _parse_range(row.get("Reference Range", row.get("Range", "")))
        yield {
            "test_date": d,
            "panel": row.get("Test Group", "general"),
            "marker": marker,
            "value": value,
            "unit": unit,
            "range_low": lo,
            "range_high": hi,
            "status": _classify(value, lo, hi),
            "source": "labcorp",
        }


def _parse_quest(reader: csv.DictReader) -> Iterator[dict[str, Any]]:
    for row in reader:
        d = _parse_date(row.get("Collected Date", row.get("Date", "")))
        if not d:
            continue
        marker = row.get("Test", row.get("Test Name", "")).strip()
        try:
            value = float(re.sub(r"[<>]", "", row.get("Value", row.get("Result", "")).strip()))
        except (ValueError, AttributeError):
            value = None
        unit = row.get("Units", row.get("Unit", "")).strip()
        lo, hi = _parse_range(row.get("Range", row.get("Reference Range", "")))
        yield {
            "test_date": d,
            "panel": row.get("Order Name", "general"),
            "marker": marker,
            "value": value,
            "unit": unit,
            "range_low": lo,
            "range_high": hi,
            "status": _classify(value, lo, hi),
            "source": "quest",
        }


def _parse_function(reader: csv.DictReader) -> Iterator[dict[str, Any]]:
    for row in reader:
        d = _parse_date(row.get("date", row.get("Date", "")))
        if not d:
            continue
        try:
            value = float(row.get("value", row.get("Value", "")).strip())
        except (ValueError, AttributeError):
            value = None
        lo, hi = _parse_range(row.get("range", row.get("Range", "")))
        yield {
            "test_date": d,
            "panel": row.get("category", "general"),
            "marker": row.get("biomarker", row.get("Biomarker", "")).strip(),
            "value": value,
            "unit": row.get("unit", row.get("Unit", "")).strip(),
            "range_low": lo,
            "range_high": hi,
            "status": _classify(value, lo, hi),
            "source": "function",
        }


def _parse_generic(reader: csv.DictReader) -> Iterator[dict[str, Any]]:
    for row in reader:
        d = _parse_date(row.get("test_date", ""))
        if not d:
            continue
        try:
            value = float(row.get("value", "").strip())
        except (ValueError, AttributeError):
            value = None
        lo = float(row["range_low"]) if row.get("range_low") not in (None, "") else None
        hi = float(row["range_high"]) if row.get("range_high") not in (None, "") else None
        yield {
            "test_date": d,
            "panel": row.get("panel", "general"),
            "marker": row.get("marker", "").strip(),
            "value": value,
            "unit": row.get("unit", "").strip(),
            "range_low": lo,
            "range_high": hi,
            "status": row.get("status") or _classify(value, lo, hi),
            "source": row.get("source", "generic"),
        }


def parse_labs_csv(csv_path: str, lab_format: str = "auto") -> tuple[Path, str, list[dict[str, Any]]]:
    """Parse a labs CSV into canonical rows. Returns (path, sha, rows).
    Use lab_format='auto' to detect by header shape, or override with
    'labcorp'|'quest'|'function'|'generic'."""
    p = Path(csv_path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"{csv_path} not found")
    sha = _sha256_file(p)
    with open(p, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return p, sha, []
        fmt = lab_format if lab_format != "auto" else _detect_format(reader.fieldnames)
        if fmt == "labcorp":
            rows = list(_parse_labcorp(reader))
        elif fmt == "quest":
            rows = list(_parse_quest(reader))
        elif fmt == "function":
            rows = list(_parse_function(reader))
        else:
            rows = list(_parse_generic(reader))
    return p, sha, rows


# Recommended panel reference list — used by health_recommended_labs() to
# tell users which markers are most useful and why. Sourced from longevity-
# medicine consensus (Attia, Boham, Hyman) for the 2026-05-10 panel.
RECOMMENDED_PANEL = [
    {
        "marker": "ApoB",
        "category": "cardiovascular",
        "why": "Single most predictive lipid marker for atherosclerotic risk. Standard cholesterol panel undercounts risk for one in three adults.",
        "freq": "annual minimum, every 6 months if optimizing",
        "cost_band": "low",
    },
    {
        "marker": "Lp(a)",
        "category": "cardiovascular",
        "why": "Genetic atherosclerotic risk marker. Test once in adult life — value is essentially fixed.",
        "freq": "once",
        "cost_band": "low",
    },
    {
        "marker": "hs-CRP",
        "category": "inflammation",
        "why": "Chronic low-grade inflammation. Elevated hs-CRP underlies cardiovascular and metabolic disease and shows up before symptoms.",
        "freq": "annual",
        "cost_band": "low",
    },
    {
        "marker": "Fasting Insulin",
        "category": "metabolic",
        "why": "Earliest detectable signal for insulin resistance — years before fasting glucose moves. The recovery-score formula in this MCP cannot detect metabolic dysfunction; this lab can.",
        "freq": "annual",
        "cost_band": "low",
    },
    {
        "marker": "HbA1c",
        "category": "metabolic",
        "why": "Three-month average glucose. Pairs with fasting insulin to surface insulin resistance vs. impaired insulin secretion.",
        "freq": "annual",
        "cost_band": "low",
    },
    {
        "marker": "Fasting Glucose",
        "category": "metabolic",
        "why": "Standard metabolic screen. Useful as a same-day signal alongside HbA1c trend.",
        "freq": "annual",
        "cost_band": "low",
    },
    {
        "marker": "Triglyceride/HDL Ratio",
        "category": "metabolic",
        "why": "Quick proxy for insulin resistance. Below 1.5 is good; above 3.5 strongly suggests metabolic dysfunction.",
        "freq": "annual",
        "cost_band": "free with standard panel",
    },
    {
        "marker": "TSH + Free T3 + Free T4 + Reverse T3 + TPO antibodies",
        "category": "thyroid",
        "why": "Full thyroid panel surfaces subclinical hypothyroidism that a TSH-only screen misses. Untreated subclinical hypothyroidism mimics depression and chronic fatigue.",
        "freq": "annual; every 3 months if symptomatic",
        "cost_band": "medium",
    },
    {
        "marker": "Vitamin D (25-OH)",
        "category": "micronutrient",
        "why": "Deficiency is universal and affects mood, immunity, and recovery. Substrate users tracking Floor without checking D are missing a lever.",
        "freq": "annual; every 3 months if supplementing",
        "cost_band": "low",
    },
    {
        "marker": "Ferritin",
        "category": "micronutrient",
        "why": "Iron status. Low ferritin is a leading cause of fatigue in menstruating women and gets missed on a basic CBC.",
        "freq": "annual",
        "cost_band": "low",
    },
    {
        "marker": "B12 + Folate + Homocysteine",
        "category": "micronutrient",
        "why": "Methylation panel. Deficiency drives fatigue, mood instability, and elevated cardiovascular risk independently of cholesterol.",
        "freq": "annual",
        "cost_band": "low",
    },
    {
        "marker": "Magnesium (RBC)",
        "category": "micronutrient",
        "why": "Most magnesium is intracellular; serum magnesium misses deficiency. RBC magnesium is the more useful test for muscle cramps, sleep issues, and headaches.",
        "freq": "every 6 months",
        "cost_band": "medium",
    },
    {
        "marker": "Sex hormones (Estradiol, Progesterone, Testosterone, DHEA-S, SHBG)",
        "category": "hormonal",
        "why": "Cycle-phase-aware testing surfaces luteal-phase progesterone insufficiency, perimenopausal estradiol drift, and PCOS patterns. Pair with cycle_context tool.",
        "freq": "every 6 months; cycle-day-21 for progesterone",
        "cost_band": "medium",
    },
    {
        "marker": "Cortisol (4-point salivary or DUTCH)",
        "category": "hormonal",
        "why": "Single morning serum cortisol misses the diurnal rhythm. 4-point salivary surfaces stress-driven HPA dysregulation that pairs with low HRV.",
        "freq": "annual; every 3 months if Floor-low pattern persistent",
        "cost_band": "high",
    },
    {
        "marker": "Comprehensive Metabolic Panel (CMP)",
        "category": "general",
        "why": "Liver enzymes, kidney function, electrolytes. Standard of care, baseline for everything else.",
        "freq": "annual",
        "cost_band": "low",
    },
    {
        "marker": "Complete Blood Count (CBC) with differential",
        "category": "general",
        "why": "Anemia, immune patterns, hidden infection or inflammation. Pair with ferritin for iron-status accuracy.",
        "freq": "annual",
        "cost_band": "low",
    },
]
