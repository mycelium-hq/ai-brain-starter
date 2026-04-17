#!/usr/bin/env python3
"""
UserPromptSubmit hook: auto-inject key vault files as context for strategic questions.

Fires before Claude responds. Detects strategic keywords in the prompt and injects
⚙️ Meta/Current Priorities.md and ⚙️ Meta/Open Loops.md as additionalContext so
Claude has your actual current state — not generic knowledge — when answering.

Vault root auto-detection (in order):
  1. VAULT_ROOT env var (set in settings.json "env" section)
  2. Walk up from cwd looking for ⚙️ Meta/Current Priorities.md
  3. Silent fallback: no injection if vault can't be found

Customization: add your own TOPIC_MAP entries for project-specific files.

Wire into settings.json:
  "UserPromptSubmit": [{"matcher": "", "hooks": [
    {"type": "command", "command": "python3 ~/.claude/hooks/vault-context.py"}
  ]}]
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

MAX_CHARS = 4000  # per-file truncation


# ─── Files always injected for strategic questions ─────────────────────────

CORE_FILES = [
    "⚙️ Meta/Current Priorities.md",
    "⚙️ Meta/Open Loops.md",
]

# ─── Optional topic-specific extras ───────────────────────────────────────
# Format: (list_of_keyword_patterns, list_of_vault_relative_paths)
# Add your own project files here. All paths are relative to vault root.

TOPIC_MAP: list[tuple[list[str], list[str]]] = [
    # Example: fundraising/investor questions → load your raise dashboard
    # (
    #     [r"\braise\b", r"\binvestor", r"\bpitch\b", r"\bseed\b"],
    #     ["🚀 Company/💰 Raise/Raise Dashboard.md"],
    # ),
]

# ─── Strategic keyword signals ─────────────────────────────────────────────

STRATEGIC_SIGNALS = [
    r"\bstrateg", r"\braise\b", r"\binvestor", r"\bpitch\b",
    r"\bdecision\b", r"\bprioritiz", r"\bpriorities\b",
    r"\bplan\b", r"\bfocus\b", r"\bnext step", r"\bopen loop",
    r"\bwhat should (i|we)\b", r"\bhow (should|do) (i|we)\b",
    r"\bwhat.s (my|our|the) (plan|status|situation)\b",
    r"\bwhere (am|are) (i|we)\b", r"\bpending\b",
    r"\bwhat (am|are) (i|we) (doing|working)\b",
    r"\brevenue\b", r"\bclient\b", r"\bproduct\b",
    r"\bsales\b", r"\bconsulting\b", r"\bgoal\b",
    r"\bwriting\b", r"\bproject\b",
]


def find_vault_root() -> str | None:
    # 1. Explicit env var override
    if env := os.environ.get("VAULT_ROOT"):
        p = Path(env)
        if (p / "⚙️ Meta" / "Current Priorities.md").exists():
            return str(p)

    # 2. Walk up from cwd
    cwd = Path(os.getcwd()).resolve()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "⚙️ Meta" / "Current Priorities.md").exists():
            return str(candidate)

    return None


def read_file(vault_root: str, rel_path: str) -> str | None:
    try:
        content = (Path(vault_root) / rel_path).read_text(encoding="utf-8")
        if len(content) > MAX_CHARS:
            content = content[:MAX_CHARS] + "\n...[truncated — read full file if needed]"
        return content
    except Exception:
        return None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    prompt = (payload.get("prompt") or "").lower().strip()
    if not prompt:
        sys.exit(0)

    # Only fire on strategic topics
    if not any(re.search(sig, prompt) for sig in STRATEGIC_SIGNALS):
        sys.exit(0)

    vault_root = find_vault_root()
    if not vault_root:
        sys.exit(0)

    # Build file list: core + any matched topic extras
    files_to_load = list(CORE_FILES)
    for signals, extras in TOPIC_MAP:
        if any(re.search(s, prompt) for s in signals):
            files_to_load.extend(extras)

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for f in files_to_load:
        if f not in seen:
            seen.add(f)
            unique.append(f)

    parts = ["[vault-context] Vault files auto-loaded for this query:\n"]
    for rel_path in unique:
        content = read_file(vault_root, rel_path)
        if content:
            parts.append(f"\n=== {rel_path} ===\n{content}")

    if len(parts) <= 1:
        sys.exit(0)

    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(parts),
        }
    }
    print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()
