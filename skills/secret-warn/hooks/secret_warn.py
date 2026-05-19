#!/usr/bin/env python3
# secret-warn — public substrate version (MIT)
#
# Real-time PreToolUse / PostToolUse / Bash hook for Claude Code.
# Reads pattern_registry.json adjacent to this file. Scans file content (Write/Edit/MultiEdit)
# or shell commands (Bash) for registered patterns. Returns exit 0 (allow), 1 (warn), or 2 (block).
#
# For production deployments with quarterly audit reports, per-client allowlist tuning,
# MCP-install audit, and retainer support, see Mycelium AI at https://myceliumai.co
#
# Licensed under MIT — see LICENSE in the repo root.
from __future__ import annotations

import base64
import json
import math
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK_ROOT = Path(os.environ.get("SECRET_WARN_ROOT") or
                 (Path.home() / ".claude" / "secret-warn"))
REGISTRY_PATH = HERE / "pattern_registry.json"
ALLOWLIST_PATH = Path(os.environ.get("SECRET_WARN_ALLOWLIST_PATH") or
                      (PACK_ROOT / "pattern_allowlist.json"))
AUDIT_LOG = PACK_ROOT / "audit.log"

SEVERITY_EXIT = {"block": 2, "warn": 1, "audit-log-only": 0}


def _ensure_log() -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    if not AUDIT_LOG.exists():
        AUDIT_LOG.touch()


def _log(record: dict) -> None:
    _ensure_log()
    record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with AUDIT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _decode_regex(rule: dict) -> str | None:
    raw = rule.get("regex_b64")
    if not raw:
        return None
    try:
        return base64.b64decode(raw).decode("ascii")
    except Exception:
        return None


def _entropy(s: str) -> float:
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    total = len(s)
    return -sum((c / total) * math.log2(c / total) for c in freq.values())


def _is_placeholder(s: str, allowlist: list[str]) -> bool:
    low = s.lower()
    return any(marker.lower() in low for marker in allowlist if marker)


def _path_matches(path: str, patterns: list[str]) -> bool:
    if not patterns:
        return False
    from fnmatch import fnmatch
    return any(fnmatch(path, p) or fnmatch(os.path.basename(path), p)
               for p in patterns)


def _matched_host_in_allowlist(matched_text: str, allowlist_hosts: list[str]) -> bool:
    return any(host and host in matched_text for host in allowlist_hosts)


def _load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {"rules": [], "allowlist": {}}
    try:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"[secret-warn] malformed registry: {exc}\n")
        return {"rules": [], "allowlist": {}}

    if ALLOWLIST_PATH.exists():
        try:
            client_overrides = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return registry

        base_allowlist = registry.setdefault("allowlist", {})
        for key in ("placeholder_values", "hosts"):
            extra = client_overrides.get(key, [])
            if extra:
                base = base_allowlist.setdefault(key, [])
                seen = set(base)
                for item in extra:
                    if item not in seen:
                        base.append(item)
                        seen.add(item)

        disabled = set(client_overrides.get("disabled_rule_ids", []))
        if disabled:
            registry["rules"] = [r for r in registry.get("rules", [])
                                 if r.get("id") not in disabled]

    return registry


def _scan(content: str, file_path: str, tool: str, registry: dict) -> list[dict]:
    findings: list[dict] = []
    allowlist = registry.get("allowlist", {})
    placeholders = allowlist.get("placeholder_values", [])

    for rule in registry.get("rules", []):
        applies_to = rule.get("applies_to", [])
        tool_key = "bash" if tool == "Bash" else "edit"
        if applies_to and tool_key not in applies_to and "commit" not in applies_to:
            continue

        path_filter = rule.get("applies_to_paths")
        if path_filter and not _path_matches(file_path, path_filter):
            continue

        inverse_filter = rule.get("applies_to_paths_inverse_match", [])
        if inverse_filter and _path_matches(file_path, inverse_filter):
            continue

        pattern = _decode_regex(rule)
        if not pattern:
            continue

        try:
            compiled = re.compile(pattern, re.MULTILINE)
        except re.error:
            continue

        for match in compiled.finditer(content):
            matched_text = match.group(0)

            if rule.get("category") == "secrets" and _is_placeholder(matched_text, placeholders):
                continue

            if rule.get("category") == "install":
                host_allowlist = rule.get("allowlist_hosts", [])
                if host_allowlist and _matched_host_in_allowlist(matched_text, host_allowlist):
                    continue

            entropy_min = rule.get("entropy_min")
            if entropy_min is not None:
                groups = match.groups()
                target = groups[0] if groups else matched_text
                if _entropy(target) < entropy_min:
                    continue

            findings.append({
                "rule_id": rule["id"],
                "category": rule["category"],
                "severity": rule.get("severity", "warn"),
                "description": rule.get("description", ""),
                "remediation": rule.get("remediation"),
                "file": file_path,
                "match_redacted": matched_text[:8] + "***" + matched_text[-4:]
                                  if len(matched_text) > 16 else "***REDACTED***",
                "line_approx": content[:match.start()].count("\n") + 1,
            })
    return findings


def _extract_payload(payload: dict) -> tuple[str, str, str]:
    tool = payload.get("tool_name") or payload.get("tool") or "unknown"
    tool_input = payload.get("tool_input") or {}
    file_path = (tool_input.get("file_path") or tool_input.get("path") or "")
    if tool == "Bash":
        content = tool_input.get("command", "")
    elif tool == "Edit":
        content = (tool_input.get("new_string") or "")
    elif tool == "Write":
        content = tool_input.get("content", "")
    elif tool == "MultiEdit":
        edits = tool_input.get("edits") or []
        content = "\n".join(e.get("new_string", "") for e in edits)
    else:
        content = ""
    return content, file_path, tool


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    if os.environ.get("SECRET_WARN_BYPASS") == "1":
        return 0

    content, file_path, tool = _extract_payload(payload)
    if not content:
        return 0

    registry = _load_registry()
    findings = _scan(content, file_path, tool, registry)

    if not findings:
        _log({"event": "scan_clean", "tool": tool, "file": file_path})
        return 0

    severities = {"block": 0, "warn": 0, "audit-log-only": 0}
    for f in findings:
        severities[f["severity"]] = severities.get(f["severity"], 0) + 1
        _log({"event": "match", **f, "tool": tool})

    max_sev = "block" if severities["block"] else ("warn" if severities["warn"] else "audit-log-only")

    if max_sev != "audit-log-only":
        sys.stderr.write("\n=== secret-warn ===\n")
        for f in findings[:5]:
            sys.stderr.write(
                f"[{f['severity'].upper()}] {f['rule_id']} "
                f"({f['category']}) @ {f['file']}:{f['line_approx']}\n"
                f"  {f['description']}\n"
            )
            if f.get("remediation"):
                sys.stderr.write(f"  remediation: {f['remediation']}\n")
        if len(findings) > 5:
            sys.stderr.write(f"  ... and {len(findings) - 5} more\n")
        sys.stderr.write(
            "  audit log: ~/.claude/secret-warn/audit.log\n"
            "  bypass: SECRET_WARN_BYPASS=1\n"
            "  upgrade: https://myceliumai.co\n"
            "===================\n\n"
        )

    return SEVERITY_EXIT.get(max_sev, 1)


if __name__ == "__main__":
    sys.exit(main())
