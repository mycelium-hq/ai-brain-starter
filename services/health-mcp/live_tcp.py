"""Health Auto Export iOS app TCP-live client (v1 shim).

The Health Auto Export iOS app exposes a JSON-RPC 2.0 TCP server on the
iPhone/iPad over Wi-Fi (default port 9000). Tool surface mirrors HealthyApps's
MCP, with method names like `health_metrics`, `workouts`, `sleep`, `ecg`,
`heart_notifications`, `cycle_tracking`, `state_of_mind`, `medications`,
`symptoms`.

This module ships the v1 shim that issues the JSON-RPC call and returns the
raw response. v0.2 will normalize into the same record shape as XML/CSV
imports so the same SQL surface works.

Auth: none on the local network. The user is responsible for keeping the
iPhone on a trusted Wi-Fi when the server is enabled.
"""
from __future__ import annotations

import json
import socket
from typing import Any


def query(
    method: str,
    params: dict[str, Any] | None = None,
    host: str = "localhost",
    port: int = 9000,
    timeout_s: float = 5.0,
) -> dict[str, Any]:
    """Issue a JSON-RPC 2.0 callTool request and return the parsed response.

    The Health Auto Export app accepts requests of shape:
      {"jsonrpc":"2.0","id":1,"method":"callTool","params":{"name":<method>,"arguments":<params>}}

    Returns the response's `result` field on success, or a dict with `error`
    on failure (network, timeout, protocol error). Never raises — callers
    expect a structured response so the MCP tool can surface the error to
    the LLM cleanly.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "callTool",
        "params": {"name": method, "arguments": params or {}},
    }
    body = (json.dumps(payload) + "\n").encode("utf-8")
    try:
        with socket.create_connection((host, port), timeout=timeout_s) as sock:
            sock.sendall(body)
            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(1 << 16)
                if not chunk:
                    break
                chunks.append(chunk)
                # JSON-RPC responses are line-delimited in this protocol;
                # break early if we've seen a newline.
                if b"\n" in chunk:
                    break
        raw = b"".join(chunks).decode("utf-8").strip()
        if not raw:
            return {"error": "empty response from Health Auto Export"}
        # In some firmware versions the response is the JSON object directly,
        # in others it's wrapped {"result": ...}. Handle both.
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return {"error": f"bad JSON from Health Auto Export: {e}", "raw": raw[:500]}
        if isinstance(data, dict) and "error" in data and data["error"]:
            return {"error": data["error"]}
        if isinstance(data, dict) and "result" in data:
            return {"result": data["result"]}
        return {"result": data}
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        return {
            "error": f"could not reach Health Auto Export at {host}:{port}: {e}",
            "hint": "Ensure the iOS app is running, the TCP server is enabled in its settings, and the iPhone is on the same Wi-Fi.",
        }
