#!/usr/bin/env python3
"""
validate-skill-frontmatter.py - PreToolUse Write|Edit|MultiEdit hook.

Validates frontmatter on every Write or Edit operation against the skill schema
at templates/schemas/skill.json. Fires only on file paths matching skills/**/SKILL.md.

Same permanent-fix pattern as lint-vault-frontmatter.py: catches malformed YAML
or schema violations at the write boundary instead of letting a structurally
broken SKILL.md silently degrade the skill catalog.

Hook contract (Claude Code PreToolUse):
  Input (stdin JSON): {"tool_name": "Write|Edit|MultiEdit", "tool_input": {...}}
  Output (stdout JSON):
    - {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}} -> allow
    - {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}} -> block

Behavior:
  - Only fires on files matching skills/**/SKILL.md
  - Silent allow for any other file
  - Projects the post-edit content (current file + Edit substitution) before linting
  - Blocks with a clear stderr message naming the schema violation
  - Bypass: SKILL_VALIDATION_BYPASS=1 in env
  - Fail-open: any internal error returns allow (never blocks the user spuriously)

Performance budget: <200ms.

Stdlib + PyYAML + jsonschema. PyYAML and jsonschema are dependencies of the
broader hook stack already; if missing, the hook fails open.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


def log_debug(msg: str) -> None:
    if os.environ.get("SKILL_VALIDATION_DEBUG") == "1":
        print(f"[validate-skill-frontmatter] {msg}", file=sys.stderr)


def emit_allow() -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }))


def emit_deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    print(reason, file=sys.stderr)


def is_skill_md(file_path: str) -> bool:
    """True if file_path matches skills/**/SKILL.md (any depth under a skills/ dir)."""
    if not file_path:
        return False
    p = Path(file_path)
    if p.name != "SKILL.md":
        return False
    return "skills" in p.parts


def project_post_edit_content(tool_name: str, tool_input: dict) -> str | None:
    """Return what the file content WILL be after the operation completes."""
    file_path = tool_input.get("file_path")
    if not file_path:
        return None

    if tool_name == "Write":
        return tool_input.get("content") or ""

    if tool_name == "Edit":
        try:
            existing = Path(file_path).read_text(encoding="utf-8")
        except (OSError, FileNotFoundError):
            existing = ""
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        if tool_input.get("replace_all"):
            return existing.replace(old, new)
        return existing.replace(old, new, 1)

    if tool_name == "MultiEdit":
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except (OSError, FileNotFoundError):
            content = ""
        for edit in tool_input.get("edits", []):
            old = edit.get("old_string", "")
            new = edit.get("new_string", "")
            if edit.get("replace_all"):
                content = content.replace(old, new)
            else:
                content = content.replace(old, new, 1)
        return content

    return None


def find_schema() -> Path | None:
    """Locate templates/schemas/skill.json relative to this hook."""
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "templates" / "schemas" / "skill.json",
        Path.home() / ".claude" / "skills" / "ai-brain-starter" / "templates" / "schemas" / "skill.json",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def extract_frontmatter(text: str) -> tuple[str | None, str | None]:
    """Extract frontmatter block. Returns (frontmatter_text, error)."""
    if not text.startswith("---"):
        return None, "missing frontmatter (file does not start with '---')"
    m = re.match(r"^---\n(.*?)\n---\s*", text, re.DOTALL)
    if not m:
        return None, "frontmatter delimiter '---' not properly closed"
    return m.group(1), None


def main() -> int:
    if os.environ.get("SKILL_VALIDATION_BYPASS") == "1":
        emit_allow()
        return 0

    try:
        raw = sys.stdin.read()
        if not raw.strip():
            emit_allow()
            return 0
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as e:
        log_debug(f"hook input read failed: {e}")
        emit_allow()
        return 0

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}

    if tool_name not in ("Write", "Edit", "MultiEdit"):
        emit_allow()
        return 0

    file_path = tool_input.get("file_path", "")
    if not is_skill_md(file_path):
        emit_allow()
        return 0

    projected = project_post_edit_content(tool_name, tool_input)
    if projected is None:
        emit_allow()
        return 0

    fm_text, fm_err = extract_frontmatter(projected)
    if fm_err:
        emit_deny(
            f"Skill validator: {fm_err} in {Path(file_path).name}. "
            f"Bypass with SKILL_VALIDATION_BYPASS=1 if intentional."
        )
        return 1

    try:
        import yaml  # type: ignore
    except ImportError:
        log_debug("PyYAML not installed; skipping validation")
        emit_allow()
        return 0

    try:
        parsed = yaml.safe_load(fm_text)
    except yaml.YAMLError as e:
        emit_deny(
            f"Skill validator: YAML parse error in {Path(file_path).name}: {e}\n"
            f"Bypass with SKILL_VALIDATION_BYPASS=1 if intentional."
        )
        return 1

    if parsed is None or not isinstance(parsed, dict):
        emit_deny(
            f"Skill validator: frontmatter in {Path(file_path).name} must be a YAML mapping, "
            f"got {type(parsed).__name__ if parsed is not None else 'null'}."
        )
        return 1

    schema_path = find_schema()
    if not schema_path:
        log_debug("schema file not found; skipping validation")
        emit_allow()
        return 0

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log_debug(f"schema load failed: {e}")
        emit_allow()
        return 0

    try:
        import jsonschema  # type: ignore
    except ImportError:
        log_debug("jsonschema not installed; skipping validation")
        emit_allow()
        return 0

    try:
        validator = jsonschema.Draft7Validator(schema)
        errors = sorted(validator.iter_errors(parsed), key=lambda e: list(e.absolute_path))
    except jsonschema.SchemaError as e:
        log_debug(f"schema is itself invalid: {e}")
        emit_allow()
        return 0

    if errors:
        details = []
        for err in errors[:5]:
            loc = ".".join(str(x) for x in err.absolute_path) or "<root>"
            details.append(f"  - {loc}: {err.message}")
        if len(errors) > 5:
            details.append(f"  ... and {len(errors) - 5} more")
        emit_deny(
            f"Skill validator blocked write to {Path(file_path).name}:\n"
            + "\n".join(details)
            + f"\nFix the frontmatter or bypass with SKILL_VALIDATION_BYPASS=1."
        )
        return 1

    emit_allow()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log_debug(f"unexpected error: {e!r}")
        emit_allow()
        sys.exit(0)
