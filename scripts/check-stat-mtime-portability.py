#!/usr/bin/env python3
"""Gate: no tracked shell script reintroduces the BSD-first `stat` mtime bug.

WHY THIS EXISTS

scripts/PORTABILITY.md #1 documents the trap: GNU coreutils' `-f` flag means
`--file-system`, not "custom format" the way BSD/macOS's `-f` does. So
`stat -f %m FILE` on real GNU/Linux does not fail the way a BSD-first
`A || B` exit-code chain assumes -- depending on the exact invocation and
coreutils build, it can hand back non-numeric text on stdout, or fail for a
reason unrelated to which stat dialect is right, and either way a caller that
trusted the exit code alone is now computing on garbage. Measured concretely:
this broke hooks/check-claude-code-version.sh's cache-freshness read outright
(an unbound-variable abort under `set -u` on real GNU coreutils 9.4) before
this gate existed. The safe shape -- GNU attempt first, validate the result
is a plain integer, THEN try BSD, validate again -- is documented in
PORTABILITY.md and implemented once, canonically, as `_close_lock_mtime` in
scripts/_session_close_guard.sh.

This gate fails loud at CI time on any tracked *.sh that calls
`stat -f %m` / `stat -f%m` in the unsafe (BSD-attempted-without-a-preceding-
validated-GNU-attempt) shape, instead of waiting for the next Linux-only
crash to surface it. Bug class: SILENT-NO-OP... no -- this one is not silent,
it is LOUD in the wrong way (a bash internal error, not a clean fallback),
which is exactly why a gate belongs here rather than a runbook note.

DETECTION, PRECISELY

A line is a CANDIDATE if it is not a pure-comment line (first non-blank
character is not `#`) and matches `stat -f ?%m` (spaced or glued). A
candidate is SAFE iff a GNU attempt (`stat -c ?%Y`) appears either earlier on
the SAME line (catches a same-line `stat -f %m ... || stat -c %Y ...` chain:
BSD attempted first is unsafe regardless of what validation follows) or on
one of the two PRECEDING lines (catches the reference shape: the GNU attempt
on the line right above, inside a `case ... *[!0-9]*)` guard). This is a
textual, line-window heuristic, not a shell parser -- it does not track which
variable each attempt targets. That is a deliberate scope limit: every real
occurrence in this repo (checked with --self-test and a full-tree run before
this gate was wired in) fits the reference's exact two-line shape, and a
heuristic that is simple enough to read in one sitting is worth more here
than one that is perfect against adversarial code nobody is going to write.

EXEMPT is for a known, already-tracked violation this gate must not block on
-- see the entries below for why each one is there and when to remove it.
It is not a place to launder a new violation; every entry names a reason and
a way to tell when it stops being true.

Usage:
    check-stat-mtime-portability.py               # the gate
    check-stat-mtime-portability.py --self-test    # the negative controls

stdlib only, no third-party deps -- runs under `python3 -S`.
"""
# exit-contract: ENFORCING

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

STAT_BSD_RE = re.compile(r"stat\s+-f\s?%m")
STAT_GNU_RE = re.compile(r"stat\s+-c\s?%Y")

# Known, already-tracked violations this gate must not block on. Every entry
# names WHY and the condition under which it should be removed -- an
# allowlist entry with no removal condition is a permanent hole, not an
# exemption.
EXEMPT = {
    "scripts/graph-context-hook.sh": (
        "pre-existing instance of this exact bug (measured on origin/main and "
        "on PR #682's head, 2026-09-25: still the raw "
        '`stat -f %m ... || stat -c %Y ... || echo 0` one-liner). Out of '
        "scope for the PR that added this gate, which was explicitly told "
        "not to touch this file because PR #682 "
        "(fix/graph-context-env-overrides) owns it. Remove this entry once "
        "#682 or a follow-up lands a GNU-first + validated read here -- "
        "until then, this gate would otherwise ship red on main."
    ),
}


def is_comment_only(line: str) -> bool:
    return line.strip().startswith("#")


def find_violations_in_text(lines: list[str]) -> list[tuple[int, str]]:
    """Return (1-based line number, line text) for every unsafe candidate."""
    violations = []
    for i, line in enumerate(lines):
        if is_comment_only(line):
            continue
        m = STAT_BSD_RE.search(line)
        if not m:
            continue
        safe = bool(STAT_GNU_RE.search(line[: m.start()]))
        if not safe:
            for back in (1, 2):
                j = i - back
                if j < 0:
                    break
                if is_comment_only(lines[j]):
                    continue
                if STAT_GNU_RE.search(lines[j]):
                    safe = True
                    break
        if not safe:
            violations.append((i + 1, line.rstrip("\n")))
    return violations


def tracked_shell_scripts() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--", "*.sh"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    return [p for p in out.stdout.splitlines() if p]


def run_gate() -> int:
    total_violations = 0
    for rel in tracked_shell_scripts():
        if rel in EXEMPT:
            continue
        path = REPO_ROOT / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"::error::could not read {rel}: {exc}")
            total_violations += 1
            continue
        violations = find_violations_in_text(text.splitlines())
        for lineno, line in violations:
            total_violations += 1
            print(
                f"::error file={rel},line={lineno}::stat -f %m used without a "
                f"GNU-first, numeric-validated attempt first (PORTABILITY.md "
                f"#1) -- {line.strip()}"
            )
    if total_violations:
        print(
            f"FAIL: {total_violations} unsafe stat-mtime call(s). Fix: try "
            "`stat -c %Y` first, validate the result is a plain integer "
            "(`case \"$m\" in ''|*[!0-9]*) ... ;; esac`), THEN fall back to "
            "`stat -f %m`, validate again. Reference: _close_lock_mtime in "
            "scripts/_session_close_guard.sh; doc: scripts/PORTABILITY.md #1."
        )
        return 1
    print("OK: no tracked shell script calls stat -f %m without a GNU-first, "
          "numeric-validated attempt first.")
    return 0


# --- self-test: the negative controls --------------------------------------

_BSD_FIRST_SAMPLE = [
    'last=$(stat -f %m "$CACHE_FILE" 2>/dev/null || stat -c %Y "$CACHE_FILE" 2>/dev/null || echo 0)\n',
]

_GLUED_BSD_FIRST_SAMPLE = [
    'lock_age=$(( $(date +%s) - $(stat -f%m "${LOCK_FILE}" 2>/dev/null || stat -c%Y "${LOCK_FILE}" 2>/dev/null || date +%s) ))\n',
]

_REFERENCE_SAMPLE = [
    'm=$(stat -c %Y "$1" 2>/dev/null)                                   # GNU/Linux\n',
    "case \"$m\" in ''|*[!0-9]*) m=$(stat -f %m \"$1\" 2>/dev/null) ;; esac # BSD/macOS\n",
    "case \"$m\" in ''|*[!0-9]*) m=\"\" ;; esac\n",
]

_COMMENT_ONLY_SAMPLE = [
    "# stat -f %m FILE gives the epoch mtime on BSD/macOS, and stat -c %Y on GNU/Linux\n",
]

_BSD_FIRST_THEN_VALIDATED_SAMPLE = [
    # BSD attempted FIRST, in the "nicely validated" shape -- still unsafe:
    # order matters, not just whether validation happens afterward.
    'm=$(stat -f %m "$1" 2>/dev/null)\n',
    "case \"$m\" in ''|*[!0-9]*) m=$(stat -c %Y \"$1\" 2>/dev/null) ;; esac\n",
]


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def self_test() -> int:
    _assert(
        len(find_violations_in_text(_BSD_FIRST_SAMPLE)) == 1,
        "did not flag the planted same-line BSD-first `||` chain (spaced)",
    )
    _assert(
        len(find_violations_in_text(_GLUED_BSD_FIRST_SAMPLE)) == 1,
        "did not flag the planted same-line BSD-first `||` chain (glued %m)",
    )
    _assert(
        len(find_violations_in_text(_REFERENCE_SAMPLE)) == 0,
        "false-flagged the reference GNU-first + validated pattern",
    )
    _assert(
        len(find_violations_in_text(_COMMENT_ONLY_SAMPLE)) == 0,
        "false-flagged a pure-comment line documenting the trap",
    )
    _assert(
        len(find_violations_in_text(_BSD_FIRST_THEN_VALIDATED_SAMPLE)) == 1,
        "did not flag BSD-attempted-first even when validated afterward "
        "(order matters, not just presence of validation)",
    )
    print(
        "OK: self-test -- 3 unsafe shapes flagged (same-line spaced, "
        "same-line glued, BSD-first-then-validated), reference pattern and "
        "a documentation comment both pass clean."
    )
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    return run_gate()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
