#!/usr/bin/env python3
"""paths_scoped_rules.py - auto-apply per-language rules by path glob (MYC-254).

Each rules/<lang>/hooks.md declares `paths:` globs in its frontmatter. Given an
edited file path, this surfaces the matching rule block(s) - zero per-file config,
the glob does the routing. Two entry points:

  CLI:   paths_scoped_rules.py --path src/foo.ts
         Prints the matching rule heading(s); used in CI and by a human.

  Hook:  as a Claude Code PostToolUse(Write|Edit) hook, reads the hook JSON on
         stdin, pulls tool_input.file_path, and prints the matching guidance so the
         model sees which language rules govern the file it just touched.

The rules dir resolves to <script_dir>/../rules, correct both in the template
(agentic-os/bin -> agentic-os/rules) and after install (.claude/hooks ->
.claude/rules). Override with AGENTIC_OS_RULES_DIR.

Fail-open: any unexpected condition returns 0 with no output, so a PostToolUse
hook can never block the client's edit.
"""
from __future__ import annotations

import fnmatch
import json
import os
import sys
from pathlib import Path


def rules_dir():
    env = os.environ.get("AGENTIC_OS_RULES_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "rules"


def split_frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    body = []
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return body
        body.append(lines[i])
    return None


def parse_paths(fm_lines):
    """Pull the `paths:` globs (inline list or block list) from frontmatter lines."""
    i = 0
    n = len(fm_lines)
    while i < n:
        line = fm_lines[i].strip()
        if line.startswith("paths:"):
            val = line.partition(":")[2].strip()
            if val.startswith("[") and val.endswith("]"):
                return [g.strip().strip("\"'") for g in val[1:-1].split(",") if g.strip()]
            if val == "":
                globs = []
                j = i + 1
                while j < n and fm_lines[j].lstrip().startswith("- "):
                    globs.append(fm_lines[j].lstrip()[2:].strip().strip("\"'"))
                    j += 1
                return globs
            return [val.strip("\"'")]
        i += 1
    return []


def name_of(fm_lines, fallback):
    for line in fm_lines:
        s = line.strip()
        if s.startswith("name:"):
            return s.partition(":")[2].strip().strip("\"'") or fallback
    return fallback


def match_path(path, glob):
    # fnmatch's `*` already spans `/`, so `*.ts` matches src/a/b.ts. We also add the
    # `**/`-stripped variant so a root-level file (no slash) matches `**/*.ts` too.
    candidates = {glob}
    if glob.startswith("**/"):
        candidates.add(glob[3:])
    return any(fnmatch.fnmatch(path, g) for g in candidates)


def matching_rules(path):
    """Return [(name, hooks_md_path)] for every rule whose globs match `path`."""
    out = []
    rd = rules_dir()
    if not rd.is_dir():
        return out
    for hooks_md in sorted(rd.glob("*/hooks.md")):
        fm = split_frontmatter(hooks_md.read_text(encoding="utf-8"))
        if fm is None:
            continue
        globs = parse_paths(fm)
        if any(match_path(path, g) for g in globs):
            out.append((name_of(fm, hooks_md.parent.name), hooks_md))
    return out


def render(path, rules):
    lines = []
    for name, hooks_md in rules:
        lines.append(f"[paths-scoped rule: {name}] matched {path}")
        lines.append(f"  rules: {hooks_md}")
    return "\n".join(lines)


def file_path_from_stdin():
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 - hook must fail open on any malformed stdin
        return None
    tool_input = payload.get("tool_input") or {}
    return tool_input.get("file_path") or tool_input.get("path")


def main(argv):
    path = None
    if "--path" in argv:
        idx = argv.index("--path")
        if idx + 1 < len(argv):
            path = argv[idx + 1]
    if path is None and not sys.stdin.isatty():
        path = file_path_from_stdin()
    if not path:
        return 0  # nothing to evaluate; silent no-op (never block an edit)

    rules = matching_rules(path)
    if not rules:
        return 0  # non-matching path -> silent

    sys.stdout.write(render(path, rules) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
