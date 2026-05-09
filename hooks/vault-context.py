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

MAX_CHARS = 2500  # per-file truncation (tightened from 4000 — see token-burn audit)

# ─── Files always injected for high-confidence strategic-INTENT questions ──

CORE_FILES = [
    "⚙️ Meta/Current Priorities.md",
    "⚙️ Meta/Open Loops.md",
]

# ─── INTENT signals (high-confidence strategy questions) ──────────────────
# Match → load CORE_FILES + matching topic files. These are explicit asks
# for direction, status, priority, decision-shape — not bare topic mentions.
# Override by creating a "_signals" key at the top of topic-map.json.
#
# Tightened design (lesson from token-burn audit): the prior version fired on
# bare topic words like \braise\b / \bclient\b / \bplan\b, pulling 8-50KB of
# context into routine builds, fixes, and file ops. Now requires explicit
# strategy intent (what / how / should / status / priority / decision-shape).

DEFAULT_SIGNALS = [
    r"\bstrateg",
    r"\bprioritiz", r"\bpriorities\b",
    r"\bdecision\b", r"\bdeciding\b", r"\bdecide\b",
    r"\bnext step",
    r"\bopen loop",
    r"\bwhat should (i|we)\b", r"\bhow (should|do|can) (i|we)\b",
    r"\bwhat.s (my|our|the) (plan|status|situation|focus|priority|next)\b",
    r"\bwhere (am|are) (i|we)\b",
    r"\bwhat (am|are) (i|we) (doing|working|missing)\b",
    r"\bpending\b",
    r"\bfocus(ing|ed)? on\b",
    r"\bwhat.s left\b",
    r"\bplan (week|morning|review|touch|today|tomorrow)\b",
    r"\bstatus (of|on|update)\b",
]

# ─── TOPIC-only signals (load topic files but NOT core) ───────────────────
# Override by creating a "_topic_only_signals" key at the top of topic-map.json.

DEFAULT_TOPIC_ONLY_SIGNALS = [
    r"\braise\b", r"\binvestor", r"\bpitch\b",
    r"\brevenue\b", r"\bclient\b", r"\bproduct\b",
    r"\bsales\b", r"\bconsulting\b",
    r"\bwriting\b", r"\bnewsletter\b", r"\bessay\b",
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

    # Intent + topic split: routine builds/fixes/file-ops with no strategic
    # intent and no topic mention exit silently (no context injection).
    # Topic mention without intent loads topic files only, NOT core.
    # Intent signal loads CORE_FILES + matching topic files.
    has_intent = any(re.search(sig, prompt) for sig in signals)
    has_topic_only = any(re.search(sig, prompt) for sig in DEFAULT_TOPIC_ONLY_SIGNALS)

    if not has_intent and not has_topic_only:
        sys.exit(0)

    files_to_load = list(CORE_FILES) if has_intent else []
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
