#!/usr/bin/env python3
"""
PreToolUse hook for the Agent (Task) tool: warn when the prompt looks
unbounded, vague, bundles multiple tasks, OR cascades into other agents.

Why agents go off the rails:
  Empirically, vague briefings balloon to 20+ turns (target <8). The
  worst offenders share one or more failure patterns:
    - unbounded scope ("all", "every", "everything", "make sure")
    - no exit criterion (no count, no time cap, no done-when)
    - no file paths (vague target)
    - bundled multi-task work in one agent
    - delegation cascades (subagent told to spawn another subagent)
    - role overlap ("use code-reviewer OR code-architect OR ...")
    - skill-dir-relative paths in the prompt (subagents don't get
      ${CLAUDE_SKILL_DIR} / ./references/ / ./scripts/)
    - router-persona / meta-orchestrator framing (subagent told to
      DECIDE which other subagent to call)

This hook does NOT block. It nudges the parent session to refine the
prompt before spawning. Agents are still useful; vague briefings are not.

Bypass: AGENT_BRIEFING_BYPASS=1 in env. Use sparingly — Explore and Plan
agents are auto-exempted because they're inherently multi-step.

CONFIG (wire once in your ~/.claude/settings.json):

    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "/usr/bin/python3 ~/.claude/hooks/agent-briefing-check.py"
          }
        ]
      }
    ]

Then copy this file to ~/.claude/hooks/ (or symlink) so the path resolves.

Source: cherry-picked patterns from crewAI delegation taxonomy,
Hainrixz/cyber-neo skill-dir resolution gap, addyosmani/agent-skills
router-persona anti-pattern. See CLAUDE.md `# Agent (Task tool)
briefings` in this repo for the full provenance + the codified rule.
"""
from __future__ import annotations

import json
import os
import re
import sys


UNBOUNDED_RE = re.compile(
    r"\b(all|every|everything|each|whole|entire|make sure|ensure|optimize)\b",
    re.IGNORECASE,
)
COUNT_RE = re.compile(
    r"\b(\d+\s*(files?|items?|notes?|rows?|chunks?|max|maximum)|under \d+|"
    r"top \d+|first \d+|stop after|exit when|done when|until)\b",
    re.IGNORECASE,
)
PATH_RE = re.compile(r"(?:/[^\s]+|\.(md|py|sh|json|ts|tsx|js)\b)")
BUNDLE_HINT_RE = re.compile(
    r"(?im)^\s*(##\s|\d+\.\s|task\s*\d|step\s*\d).*(\n.*){0,40}^\s*(##\s|\d+\.\s|task\s*\d|step\s*\d)"
)
# Circular delegation: subagent told to spawn another subagent. Per the
# crewAI rule: "Setting all agents to allow_delegation=True without
# hierarchy creates infinite back-and-forth." Use a Plan agent in the
# parent session for nested planning instead of cascading Agent calls.
CIRCULAR_DELEGATION_RE = re.compile(
    r"\b(spawn|launch|invoke|create|dispatch)\s+(an?\s+)?(sub)?agent\b.*"
    r"(spawn|launch|invoke|create|dispatch).*(sub)?agent",
    re.IGNORECASE | re.DOTALL,
)
# Role overlap: prompt names 2+ overlapping subagent types without picking
# one. Pick the most specific match; the umbrella's job is to route, the
# caller's job is to choose.
ROLE_OVERLAP_HINT_RE = re.compile(
    r"\b(code-?(explorer|architect|reviewer)|feature-?dev|general-?purpose|plan|explore)\b.*"
    r"\b(or|and|either|also use|could use)\b.*"
    r"\b(code-?(explorer|architect|reviewer)|feature-?dev|general-?purpose|plan|explore)\b",
    re.IGNORECASE,
)
# Skill-dir-relative paths: subagents do NOT have access to
# ${CLAUDE_SKILL_DIR} / ${SKILL_DIR} / ${CLAUDE_PROJECT_DIR}/skills/ /
# ./references/ / ./scripts/. These resolve to empty or fail silently.
# Parent must resolve to absolute path before spawning, OR embed file
# CONTENTS directly into the prompt.
SKILL_DIR_RELATIVE_RE = re.compile(
    r"\$\{?CLAUDE_SKILL_DIR\}?|"
    r"\$\{?SKILL_DIR\}?|"
    r"\$\{?CLAUDE_PROJECT_DIR\}?/skills/|"
    r"(?<![\w/])\./references/|"
    r"(?<![\w/])\./scripts/",
    re.IGNORECASE,
)
# Router-persona / meta-orchestrator anti-pattern. A subagent whose job
# is to DECIDE which OTHER subagent to call. Pure routing layer with no
# domain value: adds two paraphrasing hops (information loss + roughly
# 2x token cost) and replicates work the umbrella dispatchers + intent
# mapping in CLAUDE.md already do. The umbrella IS the router; subagents
# should be specialists, never dispatchers. Sibling of
# CIRCULAR_DELEGATION_RE (which catches the cascading multi-hop case);
# this catches the single-hop dispatcher case.
ROUTER_PERSONA_RE = re.compile(
    r"\b("
    r"decide\s+which\s+|"
    r"pick\s+|"
    r"dispatch\s+to\s+|"
    r"route\s+to\s+|"
    r"delegate\s+to\s+|"
    r"choose\s+"
    r")"
    r"(the\s+|an?\s+)?"
    r"(right\s+|appropriate\s+|correct\s+|best\s+)?"
    r"(sub[-\s]?)?"
    r"(agent|persona|specialist)\b"
    r"|"
    r"\bmeta[-\s]?orchestrator\b"
    r"|"
    r"\brouter\s+(sub[-\s]?)?(agent|persona)\b"
    r"|"
    r"\bwhich\s+(persona|sub[-\s]?agent|specialist)\s+(should|to)\s+(call|spawn|invoke|use|run)\b",
    re.IGNORECASE,
)


def warn(message: str) -> None:
    sys.stderr.write(f"AGENT BRIEFING WARN: {message}\n")
    sys.stderr.flush()


def main() -> None:
    if os.environ.get("AGENT_BRIEFING_BYPASS") == "1":
        sys.exit(0)

    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if payload.get("tool_name") != "Agent":
        sys.exit(0)

    tin = payload.get("tool_input", {}) or {}
    prompt = tin.get("prompt", "") or ""
    subagent = tin.get("subagent_type") or "general-purpose"

    # Explore agents are inherently multi-step — relax the check for them.
    if subagent in {"Explore", "explore", "Plan"}:
        sys.exit(0)

    issues: list[str] = []

    if len(prompt) < 150:
        issues.append(
            f"prompt is {len(prompt)} chars — too short to brief a subagent. "
            "Brief like a colleague who walked in cold: file paths, expected "
            "output, exit criterion."
        )

    if UNBOUNDED_RE.search(prompt) and not COUNT_RE.search(prompt):
        issues.append(
            "unbounded scope (uses 'all'/'every'/'everything'/'make sure') "
            "with no count or exit criterion. Add a bound: 'top 20', "
            "'first 10 files', 'stop after 30 minutes', or list specific paths."
        )

    if not PATH_RE.search(prompt):
        issues.append(
            "no file paths or extensions in prompt. Subagent has no anchor "
            "for what to read. Include absolute paths or specific filenames."
        )

    if "report" not in prompt.lower() and "return" not in prompt.lower() \
       and "output" not in prompt.lower():
        issues.append(
            "no expected output format. State 'report under 200 words', "
            "'return JSON with fields X/Y/Z', or 'list of paths only'."
        )

    if BUNDLE_HINT_RE.search(prompt) and prompt.lower().count("\n## ") >= 2:
        issues.append(
            "prompt looks like multiple bundled tasks (2+ ## sections). "
            "Split into separate Agent calls or run sequentially in main."
        )

    if CIRCULAR_DELEGATION_RE.search(prompt):
        issues.append(
            "circular delegation hint: prompt tells the subagent to spawn "
            "another subagent. Nested Agent calls usually indicate the parent "
            "should plan the work directly (Plan agent) instead of cascading. "
            "Per crewAI anti-pattern: 'Setting all agents to allow_delegation=True "
            "without hierarchy creates infinite back-and-forth.'"
        )

    if ROLE_OVERLAP_HINT_RE.search(prompt):
        issues.append(
            "role overlap hint: prompt names 2+ overlapping subagent types "
            "(e.g. code-explorer OR code-architect OR general-purpose) without "
            "picking one. Pick the most specific match; the umbrella's job is "
            "to route, the caller's job is to choose."
        )

    if SKILL_DIR_RELATIVE_RE.search(prompt):
        issues.append(
            "skill-dir-relative path in subagent prompt: subagents do NOT have "
            "access to ${CLAUDE_SKILL_DIR} / ${SKILL_DIR} / ${CLAUDE_PROJECT_DIR}/skills/ "
            "/ ./references/ / ./scripts/. The path resolves to empty or fails "
            "silently. Instead: (1) resolve to absolute path in the parent and "
            "interpolate the resolved value, OR (2) embed the file CONTENTS "
            "directly in the prompt."
        )

    if ROUTER_PERSONA_RE.search(prompt):
        issues.append(
            "router-persona / meta-orchestrator anti-pattern: prompt asks the "
            "subagent to decide WHICH OTHER agent / persona / specialist to "
            "call. Subagents are specialists, not dispatchers. The parent "
            "picks the specialist in the parent session; never delegate the "
            "picking. Pure routing layer = info-loss + ~2x token cost + "
            "duplicates umbrella dispatch. Fix: caller picks one specific "
            "subagent_type and brief THAT one with the work."
        )

    if not issues:
        sys.exit(0)

    warn(
        f"Agent briefing has likely-verbose patterns for {subagent}. "
        "Vague briefings empirically balloon to 20+ turns when target is <8. "
        "Issues:"
    )
    for i, msg in enumerate(issues, 1):
        warn(f"  [{i}] {msg}")
    warn(
        "Refine before spawning, or set AGENT_BRIEFING_BYPASS=1 if this is a "
        "deliberately exploratory call."
    )
    # Exit 0 = warn only, don't block.
    sys.exit(0)


if __name__ == "__main__":
    main()
