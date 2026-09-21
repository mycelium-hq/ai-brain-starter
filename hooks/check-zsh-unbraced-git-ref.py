#!/usr/bin/env python3
"""
PreToolUse Bash hook: unbraced `$VAR:path` in a git object read.

zsh applies HISTORY MODIFIERS after `$VAR:`, so `git show "$SHA:src/app.py"`
expands to something else entirely and prints NOTHING. The command exits 0
with empty output, which is byte-identical to "this path does not exist at
this ref" — a silent false clean on an absence claim, and absence is the
most dangerous result a search can return. bash does not do this, so the bug
only appears on a zsh box and only for the person running it.

Witnessed twice: a session reported a LIVE fix as undeployed, and a later
session probed four branches for a security regression and got `<NONE FOUND>`
on all four while the symbol was plainly present. Only a positive control
caught the second one.

The fix is two characters and is correct in BOTH shells:
    git show "$SHA:path"     ->  git show "${SHA}:path"

Bypass: ZSH_COLON_BYPASS=1 (env OR inline prefix — both are honored, because
a guard whose advertised inline bypass cannot fire is a guard that lies).

Self-test: `check-zsh-unbraced-git-ref.py --selftest` proves it BOTH ways.
"""
import json
import os
import re
import sys

# A git read that resolves a <rev>:<path> object spec.
GIT_OBJECT_READ = re.compile(
    r"\bgit\b[^\n|;&]{0,200}?\b(show|cat-file|grep|diff|log|archive)\b"
)
# `$VAR:` with NO braces, followed by something path-shaped.
UNBRACED_REF = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*):(?=[A-Za-z0-9_./~-])")

BYPASS = "ZSH_COLON_BYPASS"


def inline_bypass(command: str) -> bool:
    """A `VAR=1 cmd` prefix never reaches os.environ — read the command too."""
    return re.search(rf"\b{BYPASS}=1\b", command) is not None


def offending(command: str):
    """Return the list of unbraced var names in a git object read, else []."""
    if not GIT_OBJECT_READ.search(command):
        return []
    return [m.group(1) for m in UNBRACED_REF.finditer(command)]


def _selftest() -> int:
    cases = [
        # (command, should_fire)
        ('git show "$SHA:src/app.py"', True),
        ("git show $SHA:src/app.py", True),
        ('git grep -n foo "$REF:path/x.py"', True),
        ('git show "${SHA}:src/app.py"', False),          # braced = correct
        ("git show origin/main:src/app.py", False),        # no variable
        ('echo "$MSG: done"', False),                      # not a git read
        ('git log --format="%H"', False),                  # no ref spec
        ('ZSH_COLON_BYPASS=1 git show "$SHA:x.py"', False),  # inline bypass
    ]
    bad = 0
    for cmd, want in cases:
        got = bool(offending(cmd)) and not inline_bypass(cmd)
        mark = "ok " if got == want else "FAIL"
        if got != want:
            bad += 1
        print(f"  [{mark}] fire={got!s:5} want={want!s:5}  {cmd}")
    print(f"\n{'PASS' if not bad else 'FAIL'}: {len(cases) - bad}/{len(cases)} cases")
    return 1 if bad else 0


def main() -> None:
    if "--selftest" in sys.argv:
        sys.exit(_selftest())

    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name", "") != "Bash":
        sys.exit(0)

    command = (data.get("tool_input", {}) or {}).get("command", "") or ""
    if os.environ.get(BYPASS) == "1" or inline_bypass(command):
        sys.exit(0)

    names = offending(command)
    if not names:
        sys.exit(0)

    first = names[0]
    reason = (
        f"BLOCKED by check-zsh-unbraced-git-ref: `${first}:` is unbraced in a git "
        f"object read.\n\n"
        f"Under zsh, `$VAR:` triggers a HISTORY MODIFIER. The command prints NOTHING "
        f"and exits 0 — indistinguishable from 'that path does not exist at that ref'. "
        f"Every absence you conclude from it is a false clean.\n\n"
        f"Brace it (correct in bash AND zsh):\n"
        f'    git show "${{{first}}}:path/to/file"\n\n'
        f"If you are asserting an ABSENCE from this command, also run a positive "
        f"control: the same command against a ref where the symbol is known present.\n\n"
        f"Bypass: ZSH_COLON_BYPASS=1 (only when the colon is genuinely not a ref spec)."
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
