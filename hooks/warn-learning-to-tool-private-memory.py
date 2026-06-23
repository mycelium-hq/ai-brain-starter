#!/usr/bin/env python3
"""warn-learning-to-tool-private-memory.py — PreToolUse(Write/Edit/MultiEdit).

SOFT-warns (never blocks) when a LEARNING-shaped file is written to a TOOL-PRIVATE
memory store — Claude Code's per-project memory at
``~/.claude/projects/<key>/memory/`` whose ``memory`` dir is a REAL directory (not
a symlink into a shared / vault-backed brain).

Why
---
A reusable team principle (an operating rule, a lesson, "how we work better")
written to ONE tool's private memory cannot reach another AI account, another tool
(e.g. Codex), a teammate, CI, or a retrieval runtime. It can never change the
team's behavior — yet portability is the whole point of a memory system. This
guard catches a team-shaped learning at WRITE time and redirects it to a DURABLE,
cross-account home. It never blocks: local memory is still the right home for
genuinely-local facts.

The three homes (see docs/MEMORY_SYSTEM.md "The three homes")
------------------------------------------------------------
- a tool-agnostic principle a teammate / another AI account would follow → the
  team SHARED BRAIN (a git-backed store every account, tool, and teammate reads).
- a model-general agent guard → the SUBSTRATE that ships your hooks.
- genuinely local (your identity, this machine's quirks, this project's state) →
  fine to keep in tool-private memory; this guard stays silent.

What is ALLOWED (no nudge)
--------------------------
- A ``memory`` dir that is a SYMLINK (already wired into a shared / vault brain).
- Non-learning content (a scratch note, project state, a user-identity fact).
- Any path that is not a ``~/.claude/projects/*/memory`` store.

Why a WARN, not a block: "is this learning team-relevant?" is a zero-to-many
judgment a hook can't make perfectly, and a false-blocking gate teaches the
bypass that disables it. So this emits additionalContext (it reaches the model;
the write proceeds) and redirects — it never refuses the write.

Self-contained: pure stdlib, no shared ``_lib`` import, so it runs on a fresh
install with no extra deps. Fail-open on any error.

Bypass: ``TOOL_PRIVATE_MEMORY_BYPASS=1`` (document why).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Strong "this is a reusable learning, not a scratch note" signals. Keyed on
# STRUCTURED markers (frontmatter type, the **Rule.**/**Why:**/**How to apply:**
# shape, a "Bug class:") + learning-shaped filenames — never on free prose, so a
# genuinely-local note (user identity, a project pointer) does not false-fire.
LEARNING_TEXT_SIGNALS = (
    "type: feedback",
    "type: discovery",
    "type: operating-rule",
    "**Rule.**",
    "**Why:**",
    "**How to apply:**",
    "Bug class:",
    "bug class:",
    "BUG CLASS:",
    "codified",
    "Codified",
)
LEARNING_NAME_SIGNALS = ("feedback_", "discovery_", "operating rule", "lesson", "_lesson")


def _tool_private_memory_root(path: Path) -> Path | None:
    """Return the ``.../.claude/projects/<key>/memory`` ancestor of ``path``, or
    None if ``path`` is not inside a Claude-Code project memory store. Matches on
    the literal component names so it works for real ~/.claude paths and tmp test
    trees alike."""
    for anc in [path, *path.parents]:
        try:
            if (
                anc.name == "memory"
                and anc.parent.parent.name == "projects"
                and anc.parent.parent.parent.name == ".claude"
            ):
                return anc
        except AttributeError:
            continue
    return None


def _extract_content(tool: str, tool_input: dict) -> str:
    if tool == "Write":
        return tool_input.get("content") or ""
    if tool == "Edit":
        return tool_input.get("new_string") or ""
    if tool == "MultiEdit":
        return "\n".join(e.get("new_string", "") for e in tool_input.get("edits", []) or [])
    return ""


def _looks_like_learning(file_path: str, content: str) -> bool:
    name = os.path.basename(file_path).lower()
    if any(sig in name for sig in LEARNING_NAME_SIGNALS):
        return True
    return any(sig in content for sig in LEARNING_TEXT_SIGNALS)


def _nudge(file_path: str, memory_root: Path) -> str:
    return (
        f"[memory-routing] `{os.path.basename(file_path)}` reads like a reusable "
        f"learning being written to TOOL-PRIVATE memory (`{memory_root}` is a real "
        f"dir, not a symlink to a shared brain). Another AI account, another tool "
        f"(e.g. Codex), a teammate, CI, and any retrieval runtime CANNOT read it "
        f"there — so it cannot change the team's behavior. Pick the durable home "
        f"(docs/MEMORY_SYSTEM.md “The three homes”):\n"
        f"  - a tool-agnostic principle a teammate / another AI account would follow "
        f"→ your team's SHARED BRAIN (a git-backed store every account, tool, and "
        f"teammate reads), not this tool's private memory.\n"
        f"  - a model-general agent guard → the SUBSTRATE that ships your hooks.\n"
        f"  - genuinely local (your identity, this machine's quirks, this project's "
        f"state) → fine to keep here.\n"
        f"If this really must be tool-private, bypass: TOOL_PRIVATE_MEMORY_BYPASS=1 "
        f"(document why)."
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool = payload.get("tool_name", "")
    if tool not in ("Write", "Edit", "MultiEdit"):
        return 0

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not file_path:
        return 0

    target = Path(os.path.abspath(os.path.expanduser(file_path)))
    memory_root = _tool_private_memory_root(target)
    if memory_root is None:
        return 0  # not a Claude-Code project memory store
    if memory_root.is_symlink():
        return 0  # symlink → already a shared / vault-backed brain → allowed

    content = _extract_content(tool, tool_input)
    if not _looks_like_learning(file_path, content):
        return 0  # a scratch note / genuinely-local fact in tool-private memory is fine

    if os.environ.get("TOOL_PRIVATE_MEMORY_BYPASS") == "1":
        return 0

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": _nudge(file_path, memory_root),
    }}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail OPEN: a soft nudge must never break note-writing on a bug.
        sys.exit(0)
