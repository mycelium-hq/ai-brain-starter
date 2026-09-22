#!/usr/bin/env python3
"""Controls for check-zsh-unbraced-git-ref.py.

THE NEGATIVE CONTROL IS THE POINT. A guard earns trust only by failing on the
thing it catches. This hook's whole job is to refuse a command shape that,
under zsh, prints NOTHING and exits 0 -- so a guard that silently did nothing
would be indistinguishable from the bug it exists to prevent, and from a
correctly-quiet run. Every leg below drives the REAL hook as a subprocess over
REAL stdin JSON and asserts on the signal a caller actually reads.

WHY EXIT CODE IS NOT THE ASSERTION, and this is the load-bearing detail: the
hook exits 0 on EVERY path, deny included. The refusal travels as
`hookSpecificOutput.permissionDecision == "deny"` on stdout. A test asserting
`returncode != 0` would pass identically against a hook that had been gutted to
`sys.exit(0)`. So every leg here asserts the PARSED DECISION, never the status.

The defect being guarded, for whoever reads this next: under zsh `$VAR:` is a
history modifier, so `git show "$SHA:src/app.py"` emits nothing and succeeds.
Every absence concluded from that command is a false clean. bash does not do
this, so it only bites on a zsh box -- which is every machine this ships to.

Legs:
   1. DENIES  git show "$SHA:path"                  <- the incident shape
   2. DENIES  git show $SHA:path                    <- unquoted, same hazard
   3. DENIES  git grep -n foo "$REF:path"           <- not just `show`
   4. SILENT  git show "${SHA}:path"                <- the correct form
   5. SILENT  git show origin/main:path             <- literal ref, no variable
   6. SILENT  echo "$MSG: done"                     <- a colon after a var is
                                                       not a git object read
   7. SILENT  git log --format="%H"                 <- ordinary git
   8. SILENT  non-Bash tool                         <- wrong tool, no opinion
   9. SILENT  malformed stdin                       <- fail-open, never crash
  10. Bypass honored from the ENVIRONMENT
  11. Bypass honored INLINE (VAR=1 prefix)
  12. DENIES when the bypass token appears only in a HEREDOC BODY, with a real
      offending command chained after it. A guard whose own bypass token can be
      smuggled in as decoration is disarmed by ordinary text -- the MYC-4724
      GUARD-DISARMED-BY-ITS-OWN-OUTPUT class.
  13. The deny reason names the offending variable AND shows the braced fix, so
      the refusal is actionable rather than merely obstructive.

Stdlib only. Exit 0 = all pass.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "check-zsh-unbraced-git-ref.py"
BYPASS = "ZSH_COLON_BYPASS"

FAILURES: list[str] = []


def run(command: str, *, tool: str = "Bash", env: dict | None = None,
        raw: str | None = None) -> tuple[int, str]:
    """Drive the real hook over real stdin. Returns (returncode, stdout)."""
    payload = raw if raw is not None else json.dumps(
        {"tool_name": tool, "tool_input": {"command": command}}
    )
    child_env = dict(os.environ)
    child_env.pop(BYPASS, None)  # never inherit a bypass from the runner
    if env:
        child_env.update(env)
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        env=child_env,
    )
    return proc.returncode, proc.stdout


def decision(stdout: str) -> str | None:
    """The signal a caller actually reads. None when the hook stayed silent."""
    if not stdout.strip():
        return None
    try:
        parsed = json.loads(stdout)
    except Exception:
        return f"UNPARSEABLE:{stdout[:80]}"
    return (parsed.get("hookSpecificOutput") or {}).get("permissionDecision")


def expect_deny(label: str, command: str, **kw) -> None:
    code, out = run(command, **kw)
    got = decision(out)
    if got != "deny":
        FAILURES.append(f"{label}: expected deny, got {got!r} (rc={code})")
    elif code != 0:
        # The contract is "deny via stdout, always exit 0". A non-zero exit here
        # would break the wrapper, which treats a crash as fail-open.
        FAILURES.append(f"{label}: denied but exited {code}, expected 0")


def expect_silent(label: str, command: str, **kw) -> None:
    code, out = run(command, **kw)
    got = decision(out)
    if got is not None:
        FAILURES.append(f"{label}: expected silence, got {got!r}")
    elif code != 0:
        FAILURES.append(f"{label}: silent but exited {code}, expected 0")


def main() -> int:
    if not HOOK.exists():
        print(f"FAIL: hook not found at {HOOK}")
        return 1

    # --- 1-3: the shapes that must be refused --------------------------------
    expect_deny("1 quoted $SHA:path", 'git show "$SHA:src/app.py"')
    expect_deny("2 bare $SHA:path", "git show $SHA:src/app.py")
    expect_deny("3 git grep with $REF:path", 'git grep -n foo "$REF:path/x.py"')

    # --- 4-7: the shapes that must NOT be refused ----------------------------
    # A guard that fires on these trains a reflexive bypass, which disables it.
    expect_silent("4 braced ${SHA}:path", 'git show "${SHA}:src/app.py"')
    expect_silent("5 literal ref", "git show origin/main:src/app.py")
    expect_silent("6 colon after a var, not a ref", 'echo "$MSG: done"')
    expect_silent("7 ordinary git", 'git log --format="%H"')

    # --- 8-9: out of scope, and never crash ----------------------------------
    expect_silent("8 non-Bash tool", 'git show "$SHA:x.py"', tool="Read")
    code, out = run("", raw="{not json at all")
    if decision(out) is not None or code != 0:
        FAILURES.append(f"9 malformed stdin: expected silent exit 0, got rc={code}")

    # --- 10-11: the bypass works both ways -----------------------------------
    expect_silent("10 env bypass", 'git show "$SHA:x.py"', env={BYPASS: "1"})
    expect_silent("11 inline bypass", f'{BYPASS}=1 git show "$SHA:x.py"')

    # --- 12: the bypass token cannot be smuggled in as decoration ------------
    # A heredoc BODY is not the command line. If the hook split on newlines and
    # honored a bypass found on any segment, this decoration would disarm it.
    smuggled = f'cat <<EOF\n{BYPASS}=1\nEOF\ngit show "$SHA:x.py"'
    expect_deny("12 heredoc-smuggled bypass still denies", smuggled)

    # --- 13: the refusal is actionable ---------------------------------------
    _, out = run('git show "$SHA:src/app.py"')
    parsed = json.loads(out) if out.strip() else {}
    reason = (parsed.get("hookSpecificOutput") or {}).get("permissionDecisionReason", "")
    if "SHA" not in reason:
        FAILURES.append("13 reason does not name the offending variable")
    if "${SHA}" not in reason:
        FAILURES.append("13 reason does not show the braced fix")
    if BYPASS in reason:
        # Printing the bypass token in the refusal is how a guard teaches its
        # own defeat (MYC-4724). The doc should carry it, not the deny message.
        FAILURES.append("13 reason prints the bypass token")

    total = 13
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} of {total} control(s) failed")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"PASS: {total}/{total} controls")
    return 0


if __name__ == "__main__":
    sys.exit(main())
