#!/usr/bin/env python3
"""Block writing POPULATED personal data into a public-bound skill file —
PreToolUse(Write|Edit|MultiEdit). The write-time half of MYC-1765 (Jackie's 2nd
isolation plane).

personal-pii-scrub.yml catches NAMES + vault paths at commit time. This catches
the OTHER class at WRITE time: a real floor / deal / counterparty / amount /
tenant-id introduced into a public-repo skill template — content that carries no
name and so slips the name-scrub. Detection logic is shared with the CI gate via
hooks/_lib/template_purity.py (one source of truth, no drift).

Scope: markdown skill files (`*/skills/*.md|.mdx|.markdown`) under a PUBLIC
substrate root. Scoping is a POSITIVE allowlist of public roots (default: the
public substrate repo's own name) — never an exclusion list of private paths,
which would both leak a private name into public source and break the two-layer
principle. Extend via TEMPLATE_PURITY_PUBLIC_ROOTS (colon-separated substrings)
for other public Mycelium-HQ repos. Private/local skill repos legitimately hold
real data and simply don't match a public root, so they're out of scope. The CI
gate (--skills, run inside the public repo) is the authoritative backstop; this
hook is the early, write-time convenience block.

Only blocks data being INTRODUCED: for an Edit it scans the new text, so scrubbing
real data OUT of a public skill is never blocked.

Bypass: TEMPLATE_PURITY_BYPASS=1  (self-referential docs: this hook, the detector
module, a doc quoting a populated example, CLAUDE.md).

Only a deny speaks. Every other path prints nothing, so Claude Code's own
permission prompt stays in charge of the write.

WIRING (PreToolUse, matcher "Write|Edit|MultiEdit"):
  {"type": "command",
   "command": "if [ -f ${CLAUDE_PLUGIN_ROOT}/hooks/block-populated-public-skill.py ]; then python3 ${CLAUDE_PLUGIN_ROOT}/hooks/block-populated-public-skill.py; fi"}
"""
from __future__ import annotations

# utf8-stdout-ok: the only console write in this module is `print(json.dumps(...))`,
# and json.dumps defaults to ensure_ascii=True, so non-ASCII in the deny reason is
# escaped to \uXXXX before it reaches stdout -- there is no cp1252 console crash
# to guard against here. Replaces this file's SEV-4-json-encoded row in
# scripts/utf8-stdout-baseline.txt, per that file's rule: rows are DELETED, never
# re-pinned to stay quiet.

import json
import os
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOK_DIR))

try:
    from _lib.template_purity import scan_text
except Exception:
    scan_text = None  # fail-open below

NOTE_EXTS = {".md", ".mdx", ".markdown"}
# Public substrate root(s) whose skill markdown ships publicly. POSITIVE
# allowlist by the public repo's own name (public, so naming it here leaks
# nothing). Private/local skill repos simply don't match and are out of scope.
_DEFAULT_PUBLIC_ROOTS = ("ai-brain-starter",)


def _public_roots() -> tuple:
    extra = os.environ.get("TEMPLATE_PURITY_PUBLIC_ROOTS", "")
    return _DEFAULT_PUBLIC_ROOTS + tuple(r for r in extra.split(":") if r.strip())


def _deny(reason: str) -> int:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}))
    return 0


def _is_public_skill_path(fp: str) -> bool:
    if "/skills/" not in fp:
        return False
    if Path(fp).suffix.lower() not in NOTE_EXTS:
        return False
    return any(root in fp for root in _public_roots())


def main() -> int:
    if os.environ.get("TEMPLATE_PURITY_BYPASS") == "1" or scan_text is None:
        return 0
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0

    ti = data.get("tool_input") or {}
    fp = ti.get("file_path") or ti.get("path") or ""
    if not _is_public_skill_path(fp):
        return 0

    # Only the text being INTRODUCED (Write.content / Edit new strings). Scanning
    # new text means scrubbing real data OUT of a public skill is never blocked.
    chunks: list[str] = []
    if "content" in ti:
        chunks.append(str(ti.get("content") or ""))
    if "new_string" in ti:
        chunks.append(str(ti.get("new_string") or ""))
    for e in ti.get("edits") or []:
        chunks.append(str((e or {}).get("new_string") or ""))
    text = "\n".join(chunks)
    if not text.strip():
        return 0

    violations = scan_text(text)
    if violations:
        v = violations[0]
        more = (" (+%d more)" % (len(violations) - 1)) if len(violations) > 1 else ""
        return _deny(
            "Blocked: this write would put POPULATED personal data into the "
            "public skill '%s' — %s '%s' (L%d)%s. Open artifacts must be empty "
            "templates: use a placeholder (<floor-name>, $<amount>, tnt_<id>, "
            "EXAMPLE). The name-scrub catches names; this catches populated "
            "shapes (MYC-1765). If this is a self-referential doc/example, set "
            "TEMPLATE_PURITY_BYPASS=1 for this write."
            % (Path(fp).name, v.rule, v.excerpt, v.line, more)
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail OPEN: a write-time convenience guard must never block legitimate
        # writing on a bug. The CI gate (--skills) is the real backstop. Open means
        # no decision.
        sys.exit(0)
