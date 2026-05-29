#!/usr/bin/env python3
"""
inject-instinct-context.py — UserPromptSubmit (once-per-session) hook.

Realizes the project-scoping half of the Instinct Engine: at session start,
load the high-confidence instincts whose `project_id` is the CURRENT project
OR `global`, and EXCLUDE instincts scoped to other projects. That exclusion is
the isolation feature — a repo-specific convention does not bleed into
unrelated work.

Silent if the engine isn't installed or nothing clears the confidence floor.
Fail-open: any error -> neutral passthrough, never blocks the prompt.

Tunables (env):
  INSTINCT_INJECT_MIN_CONFIDENCE  default 0.80
  INSTINCT_INJECT_LIMIT           default 12
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

PASS = '{"continue": true, "suppressOutput": true}'
SCRIPTS = os.path.expanduser("~/.claude/skills/ai-brain-starter/scripts")
MIN_CONF = float(os.environ.get("INSTINCT_INJECT_MIN_CONFIDENCE", "0.80"))
LIMIT = int(os.environ.get("INSTINCT_INJECT_LIMIT", "12"))


def main() -> None:
    # consume stdin (the prompt payload) but we don't need it
    try:
        sys.stdin.read()
    except Exception:
        pass
    try:
        sys.path.insert(0, SCRIPTS)
        import instinct_lib as il
    except Exception:
        print(PASS)
        return
    try:
        md = il.resolve_memory_dir()
        if not md:
            print(PASS)
            return
        today = datetime.now(timezone.utc).date()
        proj = il.current_project_id()
        rows = []
        for p in il.iter_instinct_paths(md):
            inst = il.parse_instinct(p)
            fm = inst.fm
            pid = fm.get("project_id", il.PROJECT_GLOBAL)
            if pid not in (proj, il.PROJECT_GLOBAL):
                continue  # ISOLATION: other-project instincts excluded
            c = il.parse_float(fm.get("confidence"), il.seed_confidence(fm.get("strength")))
            ls = il.parse_date(fm.get("last_seen")) or il.file_mtime_date(p)
            eff = il.decayed_confidence(c, ls, today)
            if eff < MIN_CONF:
                continue
            rows.append((round(eff, 2), pid, fm.get("name", inst.slug)))
        if not rows:
            print(PASS)
            return
        rows.sort(reverse=True)
        rows = rows[:LIMIT]
        lines = [f"[instinct-engine] High-confidence instincts in scope "
                 f"(project={proj}; project-scoped + global only, "
                 f">= {MIN_CONF:.2f}):"]
        for eff, pid, name in rows:
            tag = "" if pid == il.PROJECT_GLOBAL else f" [{pid}]"
            lines.append(f"- ({eff:.2f}) {name}{tag}")
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(lines),
        }}))
    except Exception:
        print(PASS)


if __name__ == "__main__":
    main()
