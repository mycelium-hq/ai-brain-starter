"""Regression tests for the two git-global-flag scanners in
hooks/session-lock.py (CodeQL py/redos, high severity).

The defect: both patterns stepped over git's global flags with

    (?:--?[\\w-]+(?:=\\S+)?\\s+)*

Inside one iteration `--?` and `[\\w-]+` BOTH match `-`, so a token made of
three or more dashes has two valid parses (`-`+`--` and `--`+`-`). Token
boundaries are pinned by the trailing `\\s+`, so N such tokens give 2**N
distinct parses of the whole run. When the tail (`-C` / `--git-dir`) never
arrives, the engine walks all of them: measured 0.0026s at N=14, 0.157s at
N=20, 2.52s at N=24, and past a 5s wall clock at N=26 — a clean doubling per
added token.

The fix pins the character after the dashes to a word character
(`--?[\\w][\\w-]*`), which leaves every flag token exactly ONE parse.

These tests read the pattern text straight out of the committed source rather
than re-declaring it, so they bind to what actually ships. Re-declared copies
would pass while the real hook stayed vulnerable.

No network, no imports from the hook module (it is a PreToolUse hook and its
filename is not a valid module name); the source is parsed as text with `ast`.
The timing probe runs in a subprocess so a pathological pattern is KILLED by
the timeout instead of hanging the suite.

Run with:
    python3 -m pytest tests/test_session_lock_redos.py -v
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SESSION_LOCK = REPO_ROOT / "hooks" / "session-lock.py"

# N=28 dash-run tokens. Under the OLD pattern this is ~2**28 parses (~40s,
# extrapolated from the measured doubling); under the fixed pattern the
# starred group cannot consume a bare dash-run at all, so it fails in
# microseconds no matter how long the run is.
PATHOLOGICAL = "git " + "--- " * 28

# Generous: the fixed pattern measures ~0.0001s. A full four orders of
# magnitude of headroom keeps this from flaking on a loaded CI runner while
# still being ~5 orders below the vulnerable pattern's cost at this size.
BUDGET_SECONDS = 1.0

# Hard kill for the child. The vulnerable pattern blows through this by ~8x at
# N=28, so a timeout here is an unambiguous RED, not a slow-runner artifact.
KILL_SECONDS = 5.0

# Child measures ONLY the re.search call, so interpreter startup is excluded
# from the number the parent asserts against.
_CHILD = """
import re, sys, time
pattern, payload = sys.argv[1], sys.argv[2]
start = time.perf_counter()
re.search(pattern, payload)
print(time.perf_counter() - start)
"""


def _extract_flag_scanner_patterns() -> dict[str, str]:
    """Pull the two git-global-flag regex literals out of the committed source.

    Matches on the shape of the pattern (a starred git-global-flag group plus
    the tail it is scanning for), not on a line number, so the test survives
    the file moving around.
    """
    tree = ast.parse(SESSION_LOCK.read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and node.args):
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            continue
        pattern = first.value
        if r"\bgit\s+(?:--?" not in pattern:
            continue
        if pattern.endswith(r"-C\s+(\S+)"):
            found["dash_c"] = pattern
        elif "--git-dir" in pattern:
            found["git_dir"] = pattern
    return found


PATTERNS = _extract_flag_scanner_patterns()


def _time_search(pattern: str, payload: str) -> float:
    """Run one re.search in a child process; return the seconds it took.

    Raises subprocess.TimeoutExpired (child killed) if it overruns.
    """
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, pattern, payload],
        capture_output=True,
        text=True,
        timeout=KILL_SECONDS,
    )
    assert proc.returncode == 0, f"probe child failed: {proc.stderr}"
    return float(proc.stdout.strip())


# --------------------------------------------------------------------------
# Structural guard: an absence here must fail, never silently empty the suite
# --------------------------------------------------------------------------


def test_both_flag_scanner_patterns_are_found_in_source() -> None:
    """If a rename hides the patterns, every test below would vacuously pass."""
    assert SESSION_LOCK.is_file(), f"missing hook source: {SESSION_LOCK}"
    assert set(PATTERNS) == {"dash_c", "git_dir"}, (
        "expected exactly the -C and --git-dir flag scanners in "
        f"{SESSION_LOCK.name}; found {sorted(PATTERNS)}"
    )


# --------------------------------------------------------------------------
# ReDoS: the regression this file exists for
# --------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["dash_c", "git_dir"])
def test_flag_scanner_resists_catastrophic_backtracking(key: str) -> None:
    """A long run of dashes that never reaches the tail must not blow up.

    RED on the pre-fix source: the child is killed at KILL_SECONDS and this
    fails with subprocess.TimeoutExpired.
    """
    pattern = PATTERNS[key]
    try:
        elapsed = _time_search(pattern, PATHOLOGICAL)
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"{key} pattern exceeded {KILL_SECONDS}s on {len(PATHOLOGICAL)} chars "
            "of dash-run input (catastrophic backtracking — py/redos). "
            f"pattern: {pattern!r}"
        )
    assert elapsed < BUDGET_SECONDS, (
        f"{key} pattern took {elapsed:.3f}s (budget {BUDGET_SECONDS}s) on "
        f"{len(PATHOLOGICAL)} chars of dash-run input"
    )


@pytest.mark.parametrize("key", ["dash_c", "git_dir"])
def test_flag_scanner_cost_does_not_grow_with_dash_run_length(key: str) -> None:
    """Doubling the pathological input must not explode the cost.

    Guards the CLASS, not just the one length above: any future edit that
    reintroduces an ambiguous parse would show up here as superlinear growth.
    """
    pattern = PATTERNS[key]
    long_payload = "git " + "--- " * 56
    try:
        elapsed = _time_search(pattern, long_payload)
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"{key} pattern exceeded {KILL_SECONDS}s at double length — cost "
            "grows with dash-run length (ambiguous parse reintroduced)"
        )
    assert elapsed < BUDGET_SECONDS


# --------------------------------------------------------------------------
# Behaviour preservation: the gate's real job is extracting the repo path
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git -C /some/path status", "/some/path"),
        ("git --no-pager -C /some/path log", "/some/path"),
        ("git --no-pager --no-replace-objects -C /p log", "/p"),
        ("git --literal-pathspecs -C /p status", "/p"),
        ("git -C /p -c user.name=x commit", "/p"),
        # Unresolved shell variable: the caller checks for "$" and fails open.
        ('git -C "$d" status', '"$d"'),
        # No -C at all.
        ("git commit -m 'hi'", None),
        ("git --git-dir=/p/.git status", None),
    ],
)
def test_dash_c_scanner_still_extracts_the_path(
    command: str, expected: str | None
) -> None:
    import re

    match = re.search(PATTERNS["dash_c"], command)
    assert (match.group(1) if match else None) == expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git --git-dir=/p/.git status", "/p/.git"),
        ("git --git-dir /p/.git status", "/p/.git"),
        ("git --git-dir=/p/.git --work-tree=/w status", "/p/.git"),
        # --work-tree is deliberately NOT matched: it does not move the
        # git-dir, so matching it would relax the gate. See the comment above
        # the mg = re.search(...) line in session-lock.py.
        ("git --work-tree=/p status", None),
        ("git --work-tree /p status", None),
        ("git -C /some/path status", None),
    ],
)
def test_git_dir_scanner_still_extracts_the_git_dir(
    command: str, expected: str | None
) -> None:
    import re

    match = re.search(PATTERNS["git_dir"], command)
    assert (match.group(1) if match else None) == expected


def test_separate_value_flag_still_defeats_the_scanner() -> None:
    """`git -c <name>=<value> -C <path>` does NOT match — and did not before.

    `-c` takes its value as a SEPARATE token, and the starred group requires
    every token to start with a dash, so `core.x=y` stops the walk. This is a
    PRE-EXISTING limitation of both the vulnerable and the fixed pattern, not
    a regression introduced by the ReDoS fix; it is asserted here so the fix
    is provably behaviour-preserving on this input rather than silently
    assumed to extract a path it never extracted.

    Consequence is fail-CLOSED: no -C is seen, so the command is attributed to
    the effective cwd rather than let through as another repo's business.
    """
    import re

    assert re.search(PATTERNS["dash_c"], "git -c core.x=y -C /p status") is None


def test_end_of_options_separator_is_not_treated_as_a_flag() -> None:
    """`git -- -C /other/repo commit` no longer matches. Deliberate.

    This is the ONE input whose behaviour the ReDoS fix changes. It is not a
    real git invocation: git rejects a bare `--` as a global option
    ("unknown option: --", verified against the installed git), so nothing
    that works on a command line stops working here.

    The direction is safe. In the unbalanced-quotes branch an extracted -C
    path is used to let a command THROUGH ("not this lock's business"), so
    dropping this match makes the gate strictly more conservative — it now
    falls back to cwd attribution instead of opening an escape hatch keyed on
    a token git itself refuses.
    """
    import re

    assert re.search(PATTERNS["dash_c"], "git -- -C /other/repo commit") is None
