#!/usr/bin/env python3
"""
post-tool-use-learnings.py — PostToolUse hook. Captures agent-during-execution
Learnings as episodic memory.

Fires after every Bash, Edit, Write, or Agent tool call. Two trigger conditions:

  1. Tool result indicates failure (non-zero exit, error string, exception).
  2. Tool result contains an explicit `<learning>...</learning>` annotation.

When either fires, the hook appends one Learning file to:

    <vault-root>/Meta/Learnings/<YYYY-MM-DD>-<sha8>.md

The file's frontmatter follows the closed-loop learning contract:

    type: learning
    memory_class: episodic
    captured_at: <ISO 8601 timestamp>
    source_tool: Bash | Edit | Write | Agent
    error_excerpt: <first ~500 chars of error output, optional>
    provenance:
      - source_type: claude-session
        source_id: <session_id>
        captured_at: <ISO 8601 timestamp>

The body carries the raw tool input + tool output (truncated) so a downstream
consolidation pass (scripts/promote-episodic-to-procedural.py) can group
similar Learnings and draft procedural-memory candidates for human review.

Idempotency: the sha8 in the filename is derived from
sha256(tool_call_id + captured_at). The hook never overwrites an existing
file; it skips silently if the target already exists.

Vault detection: walks up from cwd looking for a folder whose name ends in
'Meta'. If no vault is found, the hook emits a passthrough and exits without
writing.

Performance budget: <100ms. Hook never blocks the calling agent on errors.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


WATCHED_TOOLS = {"Bash", "Edit", "Write", "Agent", "Task"}
LEARNING_PATTERN = re.compile(r"<learning>(.*?)</learning>", re.DOTALL | re.IGNORECASE)
ERROR_TOKENS = (
    "error",
    "exception",
    "traceback",
    "failed",
    "fatal",
    "command not found",
    "permission denied",
    "no such file",
)


def emit_passthrough() -> None:
    print(json.dumps({"continue": True, "suppressOutput": True}))


def find_vault_root(cwd: Path) -> Path | None:
    """Walk up from cwd looking for a directory that contains a Meta folder.

    If we are inside a Claude Code git worktree (path contains
    `.claude/worktrees/<slug>/`), reset to the main vault root before walking
    up. Otherwise the hook writes episodic captures to the worktree's local
    `Meta/Learnings/`, which gets discarded as "unconfirmed changes" when the
    worktree is archived. The captures need to land in the main vault so the
    closed-loop promote-runs see them.
    """
    p = cwd.resolve()

    # Worktree detection: path matches `.../<vault>/.claude/worktrees/<slug>/...`
    parts = p.parts
    if ".claude" in parts:
        i = parts.index(".claude")
        if i + 1 < len(parts) and parts[i + 1] == "worktrees":
            # Main vault root is the parent of the `.claude` segment.
            if i > 0:
                p = Path(*parts[:i])

    for _ in range(8):
        if not p.is_dir():
            break
        for child in p.iterdir():
            if child.is_dir() and child.name.endswith("Meta"):
                return p
        if p.parent == p:
            break
        p = p.parent
    return None


def detect_failure(tool_response: dict, source_tool: str = "") -> tuple[bool, str]:
    """Return (failed, excerpt) for a tool response payload.

    For Write/Edit: a tool_response with `filePath`/`file_path` set is a
    success shape ({type: create|update, filePath, content}). Skip the
    generic content scan because the response carries the WRITTEN FILE
    CONTENT, which routinely contains words like "error", "exception",
    "permission denied" innocuously (in documentation, plist files, code
    comments, hookify cheatsheets). Treating those as failures was the
    false-positive bug that flooded Meta/Learnings/ with non-failures
    until 2026-05-08; one user accumulated 169 captures in 5 days, all
    successful Writes scanning their own content for error keywords.
    """
    if not isinstance(tool_response, dict):
        return False, ""

    # Bash-shaped responses: explicit exitCode is authoritative
    if "exitCode" in tool_response:
        try:
            if int(tool_response.get("exitCode") or 0) != 0:
                stderr = (tool_response.get("stderr") or "")[:500]
                stdout = (tool_response.get("stdout") or "")[:500]
                return True, (stderr or stdout)
        except (TypeError, ValueError):
            pass

    # Explicit isError flag is authoritative
    if tool_response.get("isError") or tool_response.get("is_error"):
        msg = tool_response.get("error") or tool_response.get("message") or ""
        return True, str(msg)[:500]

    # Write/Edit success short-circuit. Success shape carries filePath +
    # content; the content is the file written, not error output.
    if source_tool in ("Write", "Edit"):
        if tool_response.get("filePath") or tool_response.get("file_path"):
            return False, ""

    # Generic content scan (Bash, Agent, Task without exitCode/isError)
    content = tool_response.get("content") or tool_response.get("output") or ""
    if isinstance(content, list):
        joined = " ".join(str(c.get("text", c)) if isinstance(c, dict) else str(c) for c in content)
    else:
        joined = str(content)
    lower = joined.lower()
    if any(tok in lower for tok in ERROR_TOKENS):
        # Only treat as failure if there's no clear success signal
        if not any(s in lower for s in ("success", " ok ", "completed")):
            return True, joined[:500]
    return False, ""


def detect_learning_annotation(tool_response: dict) -> str | None:
    """Return the body of the first <learning>...</learning> block, if any."""
    if not isinstance(tool_response, dict):
        return None
    candidates = []
    for key in ("content", "output", "stdout", "stderr", "message", "error"):
        v = tool_response.get(key)
        if isinstance(v, list):
            for c in v:
                if isinstance(c, dict):
                    candidates.append(str(c.get("text", "")))
                else:
                    candidates.append(str(c))
        elif v:
            candidates.append(str(v))
    haystack = "\n".join(candidates)
    m = LEARNING_PATTERN.search(haystack)
    if m:
        return m.group(1).strip()
    return None


def stable_sha8(tool_call_id: str, captured_at: str) -> str:
    digest = hashlib.sha256(f"{tool_call_id}|{captured_at}".encode("utf-8")).hexdigest()
    return digest[:8]


def render_frontmatter(frontmatter: dict) -> str:
    """Render frontmatter without depending on PyYAML when it isn't installed."""
    if yaml is not None:
        return yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    # Minimal stdlib fallback. We control all keys so a hand-rolled writer is fine.
    lines = []
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                if isinstance(item, dict):
                    first = True
                    for k, v in item.items():
                        prefix = "  - " if first else "    "
                        lines.append(f"{prefix}{k}: {json.dumps(v, ensure_ascii=False)}")
                        first = False
                else:
                    lines.append(f"  - {json.dumps(item, ensure_ascii=False)}")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            for k, v in value.items():
                lines.append(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
        else:
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def write_learning(
    vault_root: Path,
    captured_at: str,
    sha8: str,
    source_tool: str,
    tool_input: dict,
    tool_response: dict,
    error_excerpt: str,
    learning_text: str | None,
    session_id: str,
) -> Path | None:
    learnings_dir = vault_root / "Meta" / "Learnings"
    try:
        learnings_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    date_part = captured_at[:10]
    target = learnings_dir / f"{date_part}-{sha8}.md"
    if target.exists():
        return target  # idempotent: do not overwrite

    frontmatter: dict = {
        "type": "learning",
        "memory_class": "episodic",
        "captured_at": captured_at,
        "source_tool": source_tool,
        "provenance": [
            {
                "source_type": "claude-session",
                "source_id": session_id,
                "captured_at": captured_at,
            }
        ],
    }
    if error_excerpt:
        frontmatter["error_excerpt"] = error_excerpt[:500]

    body_parts = ["---", render_frontmatter(frontmatter).rstrip(), "---", ""]

    if learning_text:
        body_parts.append("## Learning annotation")
        body_parts.append("")
        body_parts.append(learning_text)
        body_parts.append("")

    if error_excerpt:
        body_parts.append("## Error excerpt")
        body_parts.append("")
        body_parts.append("```")
        body_parts.append(error_excerpt[:1000])
        body_parts.append("```")
        body_parts.append("")

    body_parts.append("## Tool input")
    body_parts.append("")
    body_parts.append("```json")
    try:
        body_parts.append(json.dumps(tool_input, indent=2, ensure_ascii=False)[:1500])
    except (TypeError, ValueError):
        body_parts.append(str(tool_input)[:1500])
    body_parts.append("```")
    body_parts.append("")

    body_parts.append("## Tool response (excerpt)")
    body_parts.append("")
    body_parts.append("```")
    try:
        body_parts.append(json.dumps(tool_response, indent=2, ensure_ascii=False)[:1500])
    except (TypeError, ValueError):
        body_parts.append(str(tool_response)[:1500])
    body_parts.append("```")
    body_parts.append("")

    try:
        target.write_text("\n".join(body_parts), encoding="utf-8")
    except OSError:
        return None
    return target


def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            emit_passthrough()
            return 0
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        emit_passthrough()
        return 0

    tool_name = (data.get("tool_name") or data.get("toolName") or "").strip()
    if tool_name not in WATCHED_TOOLS:
        emit_passthrough()
        return 0

    tool_input = data.get("tool_input") or data.get("toolInput") or {}
    tool_response = data.get("tool_response") or data.get("toolResponse") or {}
    session_id = data.get("session_id") or data.get("sessionId") or "unknown"
    tool_call_id = data.get("tool_call_id") or data.get("toolCallId") or session_id
    cwd = Path(data.get("cwd") or os.getcwd())

    failed, excerpt = detect_failure(tool_response, source_tool=tool_name)
    learning_text = detect_learning_annotation(tool_response)
    if not failed and not learning_text:
        emit_passthrough()
        return 0

    vault_root = find_vault_root(cwd)
    if vault_root is None:
        emit_passthrough()
        return 0

    captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sha8 = stable_sha8(str(tool_call_id), captured_at)

    write_learning(
        vault_root=vault_root,
        captured_at=captured_at,
        sha8=sha8,
        source_tool=tool_name,
        tool_input=tool_input if isinstance(tool_input, dict) else {"_raw": str(tool_input)},
        tool_response=tool_response if isinstance(tool_response, dict) else {"_raw": str(tool_response)},
        error_excerpt=excerpt,
        learning_text=learning_text,
        session_id=session_id,
    )

    emit_passthrough()
    return 0


def _self_test() -> int:
    """Regression tests for detect_failure. Run with --self-test."""
    cases = [
        # (description, tool_response, source_tool, expected_failed)
        ("Bash exit 0 → not failure",
         {"exitCode": 0, "stdout": "ok"}, "Bash", False),
        ("Bash exit 1 → failure",
         {"exitCode": 1, "stderr": "boom"}, "Bash", True),
        ("Write of doc containing 'error' → not failure (regression-fp1)",
         {"type": "update", "filePath": "/tmp/x.md",
          "content": "## How to handle errors\nIf you see an error, retry."},
         "Write", False),
        ("Edit of plist with StandardErrorPath → not failure (regression-fp2)",
         {"type": "update", "filePath": "/tmp/x.plist",
          "content": "<key>StandardErrorPath</key>\n<string>/tmp/err.log</string>"},
         "Edit", False),
        ("Write of hookify rule mentioning 'permission denied' → not failure (regression-fp3)",
         {"type": "update", "filePath": "/tmp/rule.md",
          "content": "block 'permission denied' rm -rf commands"},
         "Write", False),
        ("Write of disambiguate_first_name docstring with 'unsafe' → not failure (regression-fp4)",
         {"type": "update", "filePath": "/tmp/d.py",
          "content": "auto-yes wikilink application is unsafe"},
         "Write", False),
        ("Agent isError true → failure",
         {"isError": True, "error": "agent crashed"}, "Agent", True),
        ("Bash with traceback in stdout → failure",
         {"content": "Traceback (most recent call last):\n  File 'x.py'"},
         "Bash", True),
        ("Bash with success signal alongside error keyword → not failure",
         {"content": "Error log cleared. Operation completed successfully."},
         "Bash", False),
        ("Write with no filePath (malformed response) → falls through to generic scan",
         {"content": "permission denied: /etc/passwd"},
         "Write", True),
    ]
    fails = 0
    for desc, response, tool, expected in cases:
        actual, excerpt = detect_failure(response, source_tool=tool)
        ok = actual == expected
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {desc}: expected={expected}, got={actual}")
        if not ok:
            fails += 1
            print(f"          excerpt={excerpt[:80]!r}")
    print(f"\n{len(cases) - fails}/{len(cases)} pass")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    try:
        main()
    except Exception:
        emit_passthrough()
