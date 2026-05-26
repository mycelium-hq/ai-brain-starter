#!/usr/bin/env python3
"""
PreToolUse hook: block Write/Edit of handoff files that lack a non-empty
`consumes_when:` frontmatter field.

Why: handoff files are cross-session context bridges. Without an explicit
completion signal recorded at create time, the next session has no way to
know whether the bridged work is done — they pile up indefinitely. Vault
audit on 2026-04-26 found three long-shipped handoffs still in
`⚙️ Meta/`, each silently outdated.

A file is a handoff if EITHER:
  - filename matches *Handoff*.md / *handoff*.md / *-handoff-*.md /
    next-session-*.md, OR
  - frontmatter `type:` is handoff / session-handoff / session-starter /
    prompt

This hook fires on Write and Edit. It scopes to the personal vault
($HOME/vault/, including its
.claude/worktrees/ children) so it never fires on unrelated Anthropic
projects elsewhere on disk.

Bypass: HANDOFF_FRONTMATTER_BYPASS=1 in the environment.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

VAULT_ROOT = Path(os.environ.get("VAULT_ROOT", str(Path.home() / "vault")))

HANDOFF_FILENAME_RE = re.compile(
    r"(?:^|/)(?:[^/]*[Hh]andoff[^/]*|next-session-[^/]+)\.md$"
)

HANDOFF_TYPES = {"handoff", "session-handoff", "session-starter", "prompt"}

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
TYPE_LINE_RE = re.compile(r"^type:\s*(\S+)\s*$", re.MULTILINE)
CONSUMES_LINE_RE = re.compile(r"^consumes_when:\s*(.*?)\s*$", re.MULTILINE)


def in_vault(path: Path) -> bool:
    try:
        path.resolve().relative_to(VAULT_ROOT.resolve())
        return True
    except ValueError:
        return False


def filename_matches(path: Path) -> bool:
    return bool(HANDOFF_FILENAME_RE.search(str(path)))


def get_frontmatter_type(content: str) -> str | None:
    """Return the frontmatter `type:` value, or None if no type or no frontmatter."""
    fm_match = FRONTMATTER_RE.match(content)
    if not fm_match:
        return None
    type_match = TYPE_LINE_RE.search(fm_match.group(1))
    if not type_match:
        return None
    return type_match.group(1).strip().strip("\"'")


def is_handoff(file_path: Path, content: str) -> bool:
    """Frontmatter type is authoritative. Filename match is a fallback ONLY
    when the file has no frontmatter type at all (raw markdown). A file with
    `type: decision` whose filename happens to contain 'handoff' (e.g. a
    decision log about the handoff system) is NOT a handoff."""
    fm_type = get_frontmatter_type(content)
    if fm_type is not None:
        return fm_type in HANDOFF_TYPES
    return filename_matches(file_path)


def has_valid_consumes_when(content: str) -> bool:
    fm_match = FRONTMATTER_RE.match(content)
    if not fm_match:
        return False
    consumes_match = CONSUMES_LINE_RE.search(fm_match.group(1))
    if not consumes_match:
        return False
    value = consumes_match.group(1).strip().strip("\"'")
    return bool(value)


def simulate_edit(current: str, old_string: str, new_string: str,
                  replace_all: bool) -> str | None:
    if old_string not in current:
        return None
    if replace_all:
        return current.replace(old_string, new_string)
    return current.replace(old_string, new_string, 1)


def main() -> None:
    if os.environ.get("HANDOFF_FRONTMATTER_BYPASS") == "1":
        sys.exit(0)

    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = payload.get("tool_name") or ""
    if tool_name not in {"Write", "Edit"}:
        sys.exit(0)

    tool_input = payload.get("tool_input") or {}
    file_path_str = tool_input.get("file_path") or ""
    if not file_path_str:
        sys.exit(0)

    file_path = Path(file_path_str)
    if not in_vault(file_path):
        sys.exit(0)

    if tool_name == "Write":
        proposed = tool_input.get("content") or ""
    else:
        old_string = tool_input.get("old_string") or ""
        new_string = tool_input.get("new_string") or ""
        replace_all = bool(tool_input.get("replace_all"))
        if not file_path.exists():
            sys.exit(0)
        try:
            current = file_path.read_text(encoding="utf-8")
        except Exception:
            sys.exit(0)
        result = simulate_edit(current, old_string, new_string, replace_all)
        if result is None:
            sys.exit(0)
        proposed = result

    if not is_handoff(file_path, proposed):
        sys.exit(0)

    if has_valid_consumes_when(proposed):
        sys.exit(0)

    sys.stderr.write(
        "HANDOFF FRONTMATTER MISSING `consumes_when:`\n"
        f"  file: {file_path}\n"
        "\n"
        "This file is a handoff (filename or `type:` frontmatter matches the "
        "handoff pattern). Every handoff MUST include a non-empty "
        "`consumes_when:` field naming the completion signal — without it, "
        "the next session-close scan cannot tell whether the bridged work "
        "shipped, and stale handoffs accumulate.\n"
        "\n"
        "Examples of valid `consumes_when:` values:\n"
        "  consumes_when: graph reaches >8000 nodes via Stage 5D Option B\n"
        "  consumes_when: claude-meeting-todos repo published on github.com/github-username\n"
        "  consumes_when: private-concierge.example.com production launch complete\n"
        "\n"
        "If you cannot name a concrete signal, the bridged work isn't "
        "concrete enough to ship — write a clearer plan first.\n"
        "\n"
        "Convention: handoff files live in `⚙️ Meta/Handoffs/`, not at "
        "`⚙️ Meta/` top-level. Consumed handoffs move to `Handoffs/Archive/`.\n"
        "\n"
        "Full lifecycle rule: ⚙️ Meta/rules/handoff-files.md\n"
        "Bypass (rare): HANDOFF_FRONTMATTER_BYPASS=1\n"
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
