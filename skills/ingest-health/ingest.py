#!/usr/bin/env python3
"""ingest.py: Apple Health to DuckDB orchestrator for the ingest-health skill.

Thin shim around the health-mcp tools. The skill resolves the mode + path,
hands a JSON payload to this script on stdin, and the script issues the
correct health-mcp tool call via stdio.

Stdin shape:
{
  "mode": "xml" | "csv" | "tcp",
  "path": "/abs/path/to/file_or_folder",
  "force": false,
  "tcp": {"host": "localhost", "port": 9000, "metric": "heart_rate",
          "start": "2026-05-09", "end": "2026-05-10"}
}

Stdout: human-readable summary.
Exit non-zero on failure.

This script does NOT call the FastMCP server directly — it is invoked as a
sibling to the LLM, which makes the actual MCP tool call. This script
formats arguments and renders the response.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _format_xml_csv_response(resp: dict) -> str:
    if resp.get("skipped"):
        return (
            f"Skipped: {resp.get('file_sha', '')[:12]} already imported.\n"
            "Pass --force to re-import."
        )
    lines = [
        f"Imported {resp.get('rows_inserted', 0):,} rows in {resp.get('elapsed_s', 0)}s.",
        f"  Records: {resp.get('records_count', 0):,}",
        f"  Workouts: {resp.get('workouts_count', 0):,}",
        f"  Sleep segments: {resp.get('sleep_count', 0):,}",
        f"  File SHA: {resp.get('file_sha', '')[:16]}",
        "",
        "Try: health_status() for top metric types,",
        "     health_recovery_score(\"YYYY-MM-DD\") for an end-to-end smoke check.",
    ]
    return "\n".join(lines)


def _format_tcp_response(resp: dict) -> str:
    if "error" in resp:
        return f"TCP query failed: {resp['error']}\nHint: {resp.get('hint', '')}"
    result = resp.get("result", {})
    return f"Live query returned {len(result) if isinstance(result, list) else 1} record(s).\n{json.dumps(result, indent=2)[:1000]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="ingest-health orchestrator")
    parser.add_argument("--in", dest="payload_file", default="-",
                        help="JSON payload path; '-' for stdin")
    args = parser.parse_args()

    raw = sys.stdin.read() if args.payload_file == "-" else Path(args.payload_file).read_text()
    payload = json.loads(raw)

    mode = payload.get("mode", "xml")
    path = payload.get("path")
    force = bool(payload.get("force", False))

    # The actual MCP tool call is made by the LLM that owns this skill.
    # This script just validates arguments and renders the response that the
    # LLM hands back via stdin in the "response" key, OR issues a "request"
    # block on stdout for the LLM to execute.
    if "response" in payload:
        response = payload["response"]
        if mode in ("xml", "csv"):
            print(_format_xml_csv_response(response))
        elif mode == "tcp":
            print(_format_tcp_response(response))
        return 0

    # First call: emit the request block.
    if mode == "xml":
        if not path:
            print("ERROR: xml mode requires a path", file=sys.stderr)
            return 2
        print(json.dumps({
            "request": {
                "tool": "health_import_xml",
                "args": {"zip_or_xml_path": path, "force": force},
            }
        }))
    elif mode == "csv":
        if not path:
            print("ERROR: csv mode requires a folder path", file=sys.stderr)
            return 2
        print(json.dumps({
            "request": {
                "tool": "health_import_csv",
                "args": {"folder_path": path, "force": force},
            }
        }))
    elif mode == "tcp":
        tcp = payload.get("tcp", {})
        print(json.dumps({
            "request": {
                "tool": "health_live_query",
                "args": {
                    "metric": tcp.get("metric", "heart_rate"),
                    "host": tcp.get("host", "localhost"),
                    "port": tcp.get("port", 9000),
                    "start": tcp.get("start"),
                    "end": tcp.get("end"),
                },
            }
        }))
    else:
        print(f"ERROR: unknown mode {mode}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
