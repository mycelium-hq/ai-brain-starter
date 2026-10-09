#!/usr/bin/env python3
"""Gate: no tracked shell script reintroduces the BSD-first `stat` bug.

WHY THIS EXISTS

scripts/PORTABILITY.md #1 documents the trap: GNU coreutils' `-f` flag means
`--file-system`, not "custom format" the way BSD/macOS's `-f` does. So
`stat -f %m FILE` (or `%z`, or any other BSD custom-format letter) on real
GNU/Linux does not fail the way a BSD-first `A || B` exit-code chain assumes
-- depending on the exact invocation and coreutils build, it can hand back
non-numeric text on stdout, or fail for a reason unrelated to which stat
dialect is right, and either way a caller that trusted the exit code alone
is now computing on garbage. Measured concretely: this broke
hooks/check-claude-code-version.sh's cache-freshness read (`%m`, mtime) and
bootstrap.sh's log-rotation check (`%z`, size) outright -- both an
unbound-variable abort under `set -u` on real GNU coreutils 9.4 -- before
this gate existed. The safe shape -- GNU attempt first, validate the result
is a plain integer, THEN try BSD, validate again -- is documented in
PORTABILITY.md and implemented once per field, canonically, as
`_close_lock_mtime` (mtime) and `_close_lock_size` (size) in
scripts/_session_close_guard.sh.

This gate fails loud at CI time on any tracked *.sh that calls
`stat -f %<letter>` in the unsafe (BSD-attempted-without-a-preceding-
validated-GNU-attempt) shape, instead of waiting for the next Linux-only
crash to surface it. It first shipped scoped to `%m` only (mtime); broadened
to any BSD custom-format letter after the same bug turned up, independently,
at `%z` (size) in six more sites across the repo the day this gate was
written -- the class was never just mtime.

DETECTION, PRECISELY

A line is a CANDIDATE if it is not a pure-comment line (first non-blank
character is not `#`) and matches `stat -f ?%<letter>` (spaced or glued; any
single letter), with or without a quote before the `%`. `stat -f "%Sm"`
counts: an unquoted-only pattern missed the one real `%Sm` site this repo
had. Each BSD letter maps to exactly one GNU file-format letter
with the same meaning (BSD_TO_GNU_LETTER below); a BSD letter with no entry
there is UNCONDITIONALLY a violation -- not because it is necessarily unsafe,
but because this gate cannot yet verify that it is safe, and a silent pass on
an unrecognized shape defeats the point of a gate (fail loud, not a silent
no-op: add the letter to the map once you have verified its GNU pairing, the
way `%z -> %s` and `%m -> %Y` were verified here).

A candidate IS safe iff the matching GNU attempt (`stat -c ?%<gnu-letter>`)
appears either earlier on the SAME line (catches a same-line
`stat -f %z ... || stat -c %s ...` chain: BSD attempted first is unsafe
regardless of what validation follows) or on one of the two PRECEDING lines
(catches the reference shape: the GNU attempt on the line right above,
inside a `case ... *[!0-9]*)` guard). This is a textual, line-window
heuristic, not a shell parser -- it does not track which variable each
attempt targets, and it requires the SPECIFIC paired GNU letter, not just any
`-c %something` (a `%s`-then-`%m` mismatch is still flagged). That is a
deliberate scope limit: every real occurrence in this repo (checked with
--self-test and a full-tree run before this gate was broadened) fits the
reference's exact two-line shape, and a heuristic that is simple enough to
read in one sitting is worth more here than one that is perfect against
adversarial code nobody is going to write.

EXEMPT is for a known, already-tracked violation this gate must not block on
-- see the entries below for why each one is there and when to remove it.
It is not a place to launder a new violation; every entry names a reason and
a way to tell when it stops being true.

Usage:
    check-stat-portability.py               # the gate
    check-stat-portability.py --self-test    # the negative controls

stdlib only, no third-party deps -- runs under `python3 -S`.
"""
# exit-contract: ENFORCING

# PEP 604 `X | None` below needs this on Python 3.9 (macOS system /usr/bin/python3
# is 3.9) -- see scripts/ci.sh's own header for the class of bug this avoids.
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

STAT_BSD_RE = re.compile(r"stat\s+-f\s?['\"]?%([A-Za-z])")

# BSD `stat -f` custom-format letter -> the GNU `stat` file-format letter
# with the same meaning. Deliberately an explicit table, not a wildcard: a
# letter with no entry here is flagged unconditionally (see module
# docstring) so a future format nobody has verified the pairing for cannot
# quietly ride through as "safe".
BSD_TO_GNU_LETTER = {
    "m": "Y",  # mtime, epoch seconds
    "z": "s",  # size, bytes
}

# Known, already-tracked violations this gate must not block on. Every entry
# names WHY and the condition under which it should be removed -- an
# allowlist entry with no removal condition is a permanent hole, not an
# exemption. Empty: the one entry this gate shipped with
# (scripts/graph-context-hook.sh) was fixed by PR #682, so that file now has
# to pass like every other one.
EXEMPT: dict[str, str] = {}


def is_comment_only(line: str) -> bool:
    return line.strip().startswith("#")


def _gnu_re_for(letter: str) -> re.Pattern | None:
    gnu_letter = BSD_TO_GNU_LETTER.get(letter)
    if gnu_letter is None:
        return None
    return re.compile(r"stat\s+-c\s?['\"]?%" + re.escape(gnu_letter) + r"\b")


def find_violations_in_text(lines: list[str]) -> list[tuple[int, str]]:
    """Return (1-based line number, line text) for every unsafe candidate."""
    violations = []
    for i, line in enumerate(lines):
        if is_comment_only(line):
            continue
        m = STAT_BSD_RE.search(line)
        if not m:
            continue
        letter = m.group(1)
        gnu_re = _gnu_re_for(letter)
        if gnu_re is None:
            # Unmapped BSD format letter: cannot verify a safe pairing exists.
            violations.append((i + 1, line.rstrip("\n")))
            continue
        safe = bool(gnu_re.search(line[: m.start()]))
        if not safe:
            for back in (1, 2):
                j = i - back
                if j < 0:
                    break
                if is_comment_only(lines[j]):
                    continue
                if gnu_re.search(lines[j]):
                    safe = True
                    break
        if not safe:
            violations.append((i + 1, line.rstrip("\n")))
    return violations


def tracked_shell_scripts() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--", "*.sh"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
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
                f"::error file={rel},line={lineno}::stat -f %<letter> used "
                f"without a paired GNU-first, numeric-validated attempt "
                f"first (PORTABILITY.md #1) -- {line.strip()}"
            )
    if total_violations:
        print(
            f"FAIL: {total_violations} unsafe stat-mtime/size call(s). Fix: "
            "try the paired GNU form first (`stat -c %Y` for `%m`, `stat -c "
            "%s` for `%z`, ...), validate the result is a plain integer "
            "(`case \"$m\" in ''|*[!0-9]*) ... ;; esac`), THEN fall back to "
            "the BSD form, validate again. If the BSD letter has no entry in "
            "BSD_TO_GNU_LETTER, add one (verified) first. Reference: "
            "_close_lock_mtime / _close_lock_size in "
            "scripts/_session_close_guard.sh; doc: scripts/PORTABILITY.md #1."
        )
        return 1
    print("OK: no tracked shell script calls stat -f %<letter> without a "
          "paired GNU-first, numeric-validated attempt first.")
    return 0


# --- self-test: the negative controls --------------------------------------

_BSD_FIRST_SAMPLE = [
    'last=$(stat -f %m "$CACHE_FILE" 2>/dev/null || stat -c %Y "$CACHE_FILE" 2>/dev/null || echo 0)\n',
]

_GLUED_BSD_FIRST_SAMPLE = [
    'lock_age=$(( $(date +%s) - $(stat -f%m "${LOCK_FILE}" 2>/dev/null || stat -c%Y "${LOCK_FILE}" 2>/dev/null || date +%s) ))\n',
]

# The broadened case this self-test must cover per the task that added it:
# a planted `-f%z` (size) sample, same shape as the mtime one, must also be
# flagged.
_BSD_FIRST_SIZE_SAMPLE = [
    'log_size=$(stat -f %z "$BOOTSTRAP_LOG" 2>/dev/null || stat -c %s "$BOOTSTRAP_LOG" 2>/dev/null || echo 0)\n',
]

_GLUED_BSD_FIRST_SIZE_SAMPLE = [
    'lock_size=$(stat -f%z "${LOCK_FILE}" 2>/dev/null || stat -c%s "${LOCK_FILE}" 2>/dev/null || echo "999")\n',
]

_REFERENCE_SAMPLE = [
    'm=$(stat -c %Y "$1" 2>/dev/null)                                   # GNU/Linux\n',
    "case \"$m\" in ''|*[!0-9]*) m=$(stat -f %m \"$1\" 2>/dev/null) ;; esac # BSD/macOS\n",
    "case \"$m\" in ''|*[!0-9]*) m=\"\" ;; esac\n",
]

_REFERENCE_SIZE_SAMPLE = [
    's=$(stat -c %s "$1" 2>/dev/null)              # GNU/Linux\n',
    "case \"$s\" in ''|*[!0-9]*) s=$(stat -f %z \"$1\" 2>/dev/null) ;; esac   # BSD/macOS\n",
    "case \"$s\" in ''|*[!0-9]*) s=\"\" ;; esac\n",
]

_COMMENT_ONLY_SAMPLE = [
    "# stat -f %m FILE gives the epoch mtime on BSD/macOS, and stat -c %Y on GNU/Linux\n",
    "# stat -f %z FILE gives the size in bytes on BSD/macOS\n",
]

_BSD_FIRST_THEN_VALIDATED_SAMPLE = [
    # BSD attempted FIRST, in the "nicely validated" shape -- still unsafe:
    # order matters, not just whether validation happens afterward.
    'm=$(stat -f %m "$1" 2>/dev/null)\n',
    "case \"$m\" in ''|*[!0-9]*) m=$(stat -c %Y \"$1\" 2>/dev/null) ;; esac\n",
]

_UNMAPPED_LETTER_SAMPLE = [
    # No entry for %Sm in BSD_TO_GNU_LETTER -- must be flagged unconditionally,
    # even with what looks like a GNU-first attempt right above it, because
    # this gate has no verified pairing to check it against.
    'x=$(stat -c %Y "$1" 2>/dev/null)\n',
    'y=$(stat -f %Sm "$1" 2>/dev/null)\n',
]

# A mismatched pair (GNU size attempt, then a BSD MTIME fallback) must still
# be flagged: the letters do not correspond, so the "GNU attempt" above it
# does not actually cover this BSD call.
_MISMATCHED_PAIR_SAMPLE = [
    'x=$(stat -c %s "$1" 2>/dev/null)\n',
    "case \"$x\" in ''|*[!0-9]*) x=$(stat -f %m \"$1\" 2>/dev/null) ;; esac\n",
]

# A quoted format must not slip past: scripts/bootstrap-restore.sh shipped
# this exact BSD-first line for a display column, and a pattern that only
# matched an unquoted `%` never saw it.
_QUOTED_BSD_FIRST_SAMPLE = [
    'if mtime_h=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$f" 2>/dev/null) || \\\n',
]

_QUOTED_REFERENCE_SAMPLE = [
    "m=$(stat -c '%Y' \"$1\" 2>/dev/null)\n",
    "case \"$m\" in ''|*[!0-9]*) m=$(stat -f '%m' \"$1\" 2>/dev/null) ;; esac\n",
]


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def self_test() -> int:
    _assert(
        len(find_violations_in_text(_BSD_FIRST_SAMPLE)) == 1,
        "did not flag the planted same-line BSD-first `||` chain (mtime, spaced)",
    )
    _assert(
        len(find_violations_in_text(_GLUED_BSD_FIRST_SAMPLE)) == 1,
        "did not flag the planted same-line BSD-first `||` chain (mtime, glued)",
    )
    _assert(
        len(find_violations_in_text(_BSD_FIRST_SIZE_SAMPLE)) == 1,
        "did not flag the planted same-line BSD-first `||` chain (size %z, spaced)",
    )
    _assert(
        len(find_violations_in_text(_GLUED_BSD_FIRST_SIZE_SAMPLE)) == 1,
        "did not flag the planted same-line BSD-first `||` chain (size %z, glued)",
    )
    _assert(
        len(find_violations_in_text(_REFERENCE_SAMPLE)) == 0,
        "false-flagged the reference GNU-first + validated pattern (mtime)",
    )
    _assert(
        len(find_violations_in_text(_REFERENCE_SIZE_SAMPLE)) == 0,
        "false-flagged the reference GNU-first + validated pattern (size)",
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
    _assert(
        len(find_violations_in_text(_UNMAPPED_LETTER_SAMPLE)) == 1,
        "did not flag a BSD format letter with no verified GNU pairing "
        "(an unmapped letter must fail loud, never pass silently)",
    )
    _assert(
        len(find_violations_in_text(_MISMATCHED_PAIR_SAMPLE)) == 1,
        "did not flag a GNU attempt whose format letter does not match the "
        "BSD fallback's (a %s-then-%m mismatch is not a real safe pairing)",
    )
    _assert(
        len(find_violations_in_text(_QUOTED_BSD_FIRST_SAMPLE)) == 1,
        "did not flag a BSD-first read whose format is quoted "
        '(`stat -f "%Sm"` must not slip past an unquoted-only pattern)',
    )
    _assert(
        len(find_violations_in_text(_QUOTED_REFERENCE_SAMPLE)) == 0,
        "false-flagged the reference pattern written with quoted formats",
    )
    print(
        "OK: self-test -- 7 unsafe shapes flagged (same-line spaced/glued for "
        "both %m and %z, BSD-first-then-validated, an unmapped format "
        "letter, a mismatched GNU/BSD pair, a quoted format), the reference "
        "pattern for %m and %z (unquoted and quoted) and a documentation "
        "comment all pass clean."
    )
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    return run_gate()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
