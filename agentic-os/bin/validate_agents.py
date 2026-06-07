#!/usr/bin/env python3
"""validate_agents.py - enforce the declarative tool-surface safety boundary.

MYC-254. A read-only agent (role planner / reviewer / research, or `readonly: true`)
MUST NOT declare a mutating tool (Write / Edit / MultiEdit / NotebookEdit / Bash).
Claude Code restricts a subagent to exactly its `tools:` list, so a tool absent
from the list cannot be called - absence IS the enforcement. This validator makes
that invariant checkable and FAILS LOUD on a violation, so a "read-only" planner
that lies about its tools never ships.

Usage:
    validate_agents.py <agents-dir> [<agents-dir> ...]

Exit 0  every agent spec is clean (or the dir holds no specs).
Exit 1  at least one violation (printed to stderr).
Exit 2  bad input (missing / unreadable directory).
"""
from __future__ import annotations

import sys
from pathlib import Path

MUTATING_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"}
READONLY_ROLES = {"planner", "reviewer", "research", "researcher"}
# Claude Code accepts the bare aliases or a full model id; an invalid value has no
# documented safe fallback, so a typo would silently mis-pin. `_model_ok` rejects it.
MODEL_ALIASES = {"opus", "sonnet", "haiku", "inherit"}


def _model_ok(model):
    m = model.strip().lower()
    return m in MODEL_ALIASES or m.startswith("claude-")


def split_frontmatter(text):
    """Return the list of frontmatter lines between the first two `---`, or None."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    body = []
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return body
        body.append(lines[i])
    return None  # unterminated frontmatter == not a valid spec


def parse_frontmatter(fm_lines):
    """Tiny YAML subset: `key: value` plus block lists (`key:` then `  - item`)."""
    data = {}
    i = 0
    n = len(fm_lines)
    while i < n:
        line = fm_lines[i].strip()
        i += 1
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val == "":
            items = []
            while i < n and fm_lines[i].lstrip().startswith("- "):
                items.append(fm_lines[i].lstrip()[2:].strip())
                i += 1
            data[key] = items if items else ""
        else:
            data[key] = val
    return data


def parse_tools(value):
    """Accept an inline `[A, B]` list, an already-parsed block list, or a scalar."""
    if isinstance(value, list):
        return [v.strip().strip("\"'") for v in value if v.strip()]
    v = value.strip()
    if v.startswith("[") and v.endswith("]"):
        return [t.strip().strip("\"'") for t in v[1:-1].split(",") if t.strip()]
    if v == "":
        return []
    return [v.strip("\"'")]


def validate_file(path):
    """Return (is_agent_spec, [violations]) for one markdown file."""
    text = path.read_text(encoding="utf-8")
    fm = split_frontmatter(text)
    if fm is None:
        return (False, [])
    data = parse_frontmatter(fm)
    if "name" not in data:
        return (False, [])  # frontmatter doc that is not an agent spec (e.g. README)

    rel = path.name
    violations = []

    model = data.get("model", "")
    if not (isinstance(model, str) and model.strip()):
        violations.append(f"{rel}: missing `model:` pin (every agent must pin a model)")
    elif not _model_ok(model):
        violations.append(
            f"{rel}: invalid `model:` value '{model.strip()}' - use opus/sonnet/haiku/inherit "
            f"or a full claude-* id (an invalid alias has no documented fallback)"
        )

    if "tools" not in data:
        violations.append(f"{rel}: missing `tools:` (declare the exact tool surface)")
        return (True, violations)
    tools = parse_tools(data["tools"])
    if not tools:
        violations.append(f"{rel}: empty `tools:` list")
        return (True, violations)

    role = data.get("role", "")
    role = role.strip().lower() if isinstance(role, str) else ""
    readonly_flag = str(data.get("readonly", "")).strip().lower() in {"true", "yes", "1"}
    is_readonly = role in READONLY_ROLES or readonly_flag

    declared_mutators = sorted(set(tools) & MUTATING_TOOLS)
    if is_readonly and declared_mutators:
        violations.append(
            f"{rel}: read-only role '{role or 'readonly'}' declares mutating tool(s) "
            f"{declared_mutators} - a read-only agent must not be able to "
            f"{', '.join(declared_mutators)}"
        )
    return (True, violations)


def main(argv):
    dirs = argv[1:]
    if not dirs:
        sys.stderr.write("usage: validate_agents.py <agents-dir> [...]\n")
        return 2

    specs = []
    for d in dirs:
        p = Path(d)
        if not p.exists():
            sys.stderr.write(f"validate_agents: no such directory: {d}\n")
            return 2
        if p.is_dir():
            specs.extend(sorted(p.glob("*.md")))
        else:
            specs.append(p)

    all_violations = []
    checked = 0
    for spec in specs:
        is_spec, violations = validate_file(spec)
        if not is_spec:
            continue
        checked += 1
        all_violations.extend(violations)

    if all_violations:
        sys.stderr.write("validate_agents: FAIL - declarative tool-surface boundary violated\n")
        for v in all_violations:
            sys.stderr.write(f"  - {v}\n")
        return 1

    if checked == 0:
        sys.stderr.write("validate_agents: no agent specs found (nothing to check)\n")
        return 0

    print(f"validate_agents: OK - {checked} agent spec(s) clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
