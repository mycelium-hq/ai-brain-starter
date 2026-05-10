"""RescueTime MCP Server — pulls productivity data for daily journal integration.

Setup:
  1. pip install fastmcp httpx  (or: pipx install fastmcp)
  2. Get your API key from https://www.rescuetime.com/anapi/manage
  3. Copy this file to ~/.claude/rescuetime-mcp/server.py
  4. Add to your vault .mcp.json (see POWER_TOOLS.md for the snippet)

Tools exposed:
  - get_daily_summary   — productivity pulse + hours by category for a given day
  - get_top_activities  — top apps/websites ranked by time
  - get_categories      — time by category (Development, Communication, Social, etc.)
  - get_productivity_trend — pulse trend over N days
"""

from __future__ import annotations

import os
import httpx
from datetime import date, timedelta
from fastmcp import FastMCP

mcp = FastMCP("RescueTime")

API_KEY = os.environ.get("RESCUETIME_API_KEY", "")
BASE = "https://www.rescuetime.com/anapi"


async def _get(endpoint: str, params: dict | None = None) -> dict | list:
    """Make an authenticated GET request to the RescueTime API."""
    p = {"key": API_KEY, "format": "json"}
    if params:
        p.update(params)
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE}/{endpoint}", params=p, timeout=15)
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def get_daily_summary(day: str = "today") -> dict:
    """Get RescueTime daily summary: productivity pulse, hours by category, productive vs distracting time.

    Args:
        day: Date string "today", "yesterday", or "YYYY-MM-DD"
    """
    if day == "today":
        target = date.today()
    elif day == "yesterday":
        target = date.today() - timedelta(days=1)
    else:
        target = date.fromisoformat(day)

    data = await _get("daily_summary_feed", {
        "restrict_begin": target.isoformat(),
        "restrict_end": target.isoformat(),
    })

    if not data:
        return {"error": f"No data for {target.isoformat()}. RescueTime may not have synced yet."}

    d = data[0]
    return {
        "date": d.get("date"),
        "productivity_pulse": d.get("productivity_pulse"),
        "total_hours": round(d.get("total_hours", 0), 1),
        "very_productive_hours": round(d.get("very_productive_hours", 0), 1),
        "productive_hours": round(d.get("productive_hours", 0), 1),
        "neutral_hours": round(d.get("neutral_hours", 0), 1),
        "distracting_hours": round(d.get("distracting_hours", 0), 1),
        "very_distracting_hours": round(d.get("very_distracting_hours", 0), 1),
        "total_productive": round(d.get("very_productive_hours", 0) + d.get("productive_hours", 0), 1),
        "total_distracting": round(d.get("distracting_hours", 0) + d.get("very_distracting_hours", 0), 1),
    }


@mcp.tool()
async def get_top_activities(day: str = "today", limit: int = 10) -> list[dict]:
    """Get top activities (apps/websites) ranked by time spent.

    Args:
        day: Date string "today", "yesterday", or "YYYY-MM-DD"
        limit: Max number of activities to return (default 10)
    """
    if day == "today":
        target = date.today()
    elif day == "yesterday":
        target = date.today() - timedelta(days=1)
    else:
        target = date.fromisoformat(day)

    data = await _get("data", {
        "perspective": "rank",
        "restrict_kind": "activity",
        "restrict_begin": target.isoformat(),
        "restrict_end": target.isoformat(),
    })

    rows = data.get("rows", [])[:limit]
    results = []
    for row in rows:
        secs = row[1]
        results.append({
            "activity": row[3],
            "category": row[4],
            "hours": round(secs / 3600, 2),
            "minutes": round(secs / 60),
            "productivity_score": row[5],  # -2 (very distracting) to 2 (very productive)
        })
    return results


@mcp.tool()
async def get_categories(day: str = "today") -> list[dict]:
    """Get time breakdown by category (Development, Communication, Social, etc).

    Args:
        day: Date string "today", "yesterday", or "YYYY-MM-DD"
    """
    if day == "today":
        target = date.today()
    elif day == "yesterday":
        target = date.today() - timedelta(days=1)
    else:
        target = date.fromisoformat(day)

    data = await _get("data", {
        "perspective": "rank",
        "restrict_kind": "category",
        "restrict_begin": target.isoformat(),
        "restrict_end": target.isoformat(),
    })

    rows = data.get("rows", [])
    results = []
    for row in rows:
        secs = row[1]
        results.append({
            "category": row[3],
            "hours": round(secs / 3600, 2),
            "minutes": round(secs / 60),
            "productivity_score": row[5],
        })
    return results


@mcp.tool()
async def get_productivity_trend(days: int = 7) -> list[dict]:
    """Get productivity pulse trend over recent days.

    Args:
        days: Number of days to look back (default 7)
    """
    end = date.today()
    start = end - timedelta(days=days - 1)

    data = await _get("daily_summary_feed", {
        "restrict_begin": start.isoformat(),
        "restrict_end": end.isoformat(),
    })

    return [
        {
            "date": d.get("date"),
            "productivity_pulse": d.get("productivity_pulse"),
            "productive_hours": round(d.get("very_productive_hours", 0) + d.get("productive_hours", 0), 1),
            "distracting_hours": round(d.get("distracting_hours", 0) + d.get("very_distracting_hours", 0), 1),
            "total_hours": round(d.get("total_hours", 0), 1),
        }
        for d in sorted(data, key=lambda x: x.get("date", ""))
    ]
