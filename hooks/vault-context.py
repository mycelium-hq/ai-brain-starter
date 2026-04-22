#!/usr/bin/env python3
"""
UserPromptSubmit hook: auto-inject personalized vault context on strategic prompts.

Fires on every prompt. If the prompt contains a strategic keyword, reads
`⚙️ Meta/Current Priorities.md` and `⚙️ Meta/Open Loops.md` (always), plus any
files routed by the user's topic map for the keywords it detects.

Personalization:
  Edit `⚙️ Meta/topic-map.json` in your vault to define your own topics.
  Each topic has a name, a list of trigger keywords, and a list of vault files
  to inject when any trigger matches.

  Example entry:
      {
        "name": "fundraising",
        "triggers": ["raise", "investor", "pitch", "seed", "angel"],
        "files": ["🚀 Company/💰 Raise/Dashboard.md"]
      }

  If `topic-map.json` does not exist, the hook ships core files only.

Vault root auto-detection (in order):
  1. VAULT_ROOT env var
  2. Walk up from cwd looking for ⚙️ Meta/Current Priorities.md
  3. Silent exit if not found

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

# ─── Default strategic keyword signals ─────────────────────────────────────
# Override by creating a "_signals" key at the top of topic-map.json:
#   {"_signals": ["strateg", "plan", ...], "topics": [...]}

DEFAULT_SIGNALS = [
    r"\bstrateg", r"\braise\b", r"\binvestor", r"\bpitch\b",
    r"\bdecision\b", r"\bprioritiz", r"\bpriorities\b",
    r"\bplan\b", r"\bfocus\b", r"\bnext step", r"\bopen loop",
    r"\bwhat should (i|we)\b", r"\bhow (should|do) (i|we)\b",
    r"\bwhat.s (my|our|the) (plan|status|situation)\b",
    r"\bwhere (am|are) (i|we)\b", r"\bpending\b",
    r"\bwhat (am|are) (i|we) (doing|working)\b",
    r"\brevenue\b", r"\bclient\b", r"\bproduct\b",
    r"\bsales\b", r"\bconsulting\b", r"\bgoal\b",
    r"\bwriting\b", r"\bproject\b", r"\bmeeting\b",
]


def find_vault_root() -> str | None:
    if env := os.environ.get("VAULT_ROOT"):
        p = Path(env)
        if (p / "⚙️ Meta" / "Current Priorities.md").exists():
            return str(p)

    cwd = Path(os.getcwd()).resolve()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "⚙️ Meta" / "Current Priorities.md").exists():
            return str(candidate)

    return None


def load_topic_map(vault_root: str) -> tuple[list[str], list[tuple[list[str], list[str]]]]:
    """
    Returns (signals, topics) where signals is a list of regex strings and
    topics is a list of (triggers, files) tuples. Falls back to defaults if
    the config is missing or malformed.
    """
    config_path = Path(vault_root) / "⚙️ Meta" / "topic-map.json"
    if not config_path.exists():
        return DEFAULT_SIGNALS, []

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_SIGNALS, []

    # Supports two shapes:
    #   [ {name, triggers, files}, ... ]                  (simple)
    #   { "_signals": [...], "topics": [...] }            (extended)
    if isinstance(raw, dict):
        signals = raw.get("_signals") or DEFAULT_SIGNALS
        topics_raw = raw.get("topics") or []
    elif isinstance(raw, list):
        signals = DEFAULT_SIGNALS
        topics_raw = raw
    else:
        return DEFAULT_SIGNALS, []

    topics: list[tuple[list[str], list[str]]] = []
    for entry in topics_raw:
        if not isinstance(entry, dict):
            continue
        triggers = entry.get("triggers") or []
        files = entry.get("files") or []
        if not isinstance(triggers, list) or not isinstance(files, list):
            continue
        # Wrap bare keywords in word-boundary regex for safety
        patterns = [t if any(c in t for c in r".*+?^$()[]{}\|") else rf"\b{re.escape(t)}\b"
                    for t in triggers if isinstance(t, str)]
        file_list = [f for f in files if isinstance(f, str)]
        if patterns and file_list:
            topics.append((patterns, file_list))

    return signals, topics


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

    vault_root = find_vault_root()
    if not vault_root:
        sys.exit(0)

    signals, topics = load_topic_map(vault_root)

    if not any(re.search(sig, prompt) for sig in signals):
        sys.exit(0)

    files_to_load = list(CORE_FILES)
    for triggers, extras in topics:
        if any(re.search(t, prompt) for t in triggers):
            files_to_load.extend(extras)

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
