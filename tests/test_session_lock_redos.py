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

NOTE ON THE PATHOLOGICAL INPUT. A run of BARE `--` tokens does NOT reproduce
this — `--?` takes `-`, `[\\w-]+` takes `-`, and there is no second parse, so
`'git ' + '-- ' * 40` completes in 0.0000s even against the VULNERABLE
pattern. A test built on that input would have passed before the fix. Three
or more dashes per token is what splits two ways; that is what is used here.

These tests read the pattern text straight out of the committed source rather
than re-declaring it, so they bind to what actually ships. Re-declared copies
would pass while the real hook stayed vulnerable.

RUNNER CONTRACT. scripts/ci.sh runs every PY_DIRECT suite as a PLAIN SCRIPT
(`"$PY" "$t"`), under a Python 3.9 that has no pytest installed. So this file
must not import pytest and must execute its own checks from __main__ — a
pytest-only file registered in PY_DIRECT satisfies the dormancy invariant's
letter while running zero assertions, which is a silent false green. It stays
pytest-COLLECTABLE (plain `test_*` functions, plain asserts) so `pytest
tests/` locally exercises exactly the same checks.

No network, no imports from the hook module (it is a PreToolUse hook and its
filename is not a valid module name); the source is parsed as text with `ast`.
The timing probe runs in a subprocess so a pathological pattern is KILLED by
the timeout instead of hanging the suite.

Run either way:
    python3 tests/test_session_lock_redos.py
    python3 -m pytest tests/test_session_lock_redos.py -v
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

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


def _extract_flag_scanner_patterns():
    """Pull the two git-global-flag regex literals out of the committed source.

    Matches on the shape of the pattern (a starred git-global-flag group plus
    the tail it is scanning for), not on a line number, so the test survives
    the file moving around.
    """
    tree = ast.parse(SESSION_LOCK.read_text(encoding="utf-8"))
    found = {}
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


def _time_search(pattern, payload):
    """Run one re.search in a child process; return the seconds it took.

    Raises subprocess.TimeoutExpired (child killed) if it overruns.
    """
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, pattern, payload],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=KILL_SECONDS,
    )
    assert proc.returncode == 0, "probe child failed: {}".format(proc.stderr)
    return float(proc.stdout.strip())


# --------------------------------------------------------------------------
# Structural guard: an absence here must fail, never silently empty the suite
# --------------------------------------------------------------------------


def test_both_flag_scanner_patterns_are_found_in_source():
    """If a rename hides the patterns, every test below would vacuously pass."""
    assert SESSION_LOCK.is_file(), "missing hook source: {}".format(SESSION_LOCK)
    assert set(PATTERNS) == {"dash_c", "git_dir"}, (
        "expected exactly the -C and --git-dir flag scanners in {}; found {}".format(
            SESSION_LOCK.name, sorted(PATTERNS)
        )
    )


# --------------------------------------------------------------------------
# ReDoS: the regression this file exists for
# --------------------------------------------------------------------------


def test_flag_scanner_resists_catastrophic_backtracking():
    """A long run of dashes that never reaches the tail must not blow up.

    RED on the pre-fix source: the child is killed at KILL_SECONDS and this
    fails with subprocess.TimeoutExpired.
    """
    for key in ("dash_c", "git_dir"):
        pattern = PATTERNS[key]
        try:
            elapsed = _time_search(pattern, PATHOLOGICAL)
        except subprocess.TimeoutExpired:
            raise AssertionError(
                "{} pattern exceeded {}s on {} chars of dash-run input "
                "(catastrophic backtracking — py/redos). pattern: {!r}".format(
                    key, KILL_SECONDS, len(PATHOLOGICAL), pattern
                )
            )
        assert elapsed < BUDGET_SECONDS, (
            "{} pattern took {:.3f}s (budget {}s) on {} chars of dash-run "
            "input".format(key, elapsed, BUDGET_SECONDS, len(PATHOLOGICAL))
        )


def test_flag_scanner_cost_does_not_grow_with_dash_run_length():
    """Doubling the pathological input must not explode the cost.

    Guards the CLASS, not just the one length above: any future edit that
    reintroduces an ambiguous parse would show up here as superlinear growth.
    """
    long_payload = "git " + "--- " * 56
    for key in ("dash_c", "git_dir"):
        pattern = PATTERNS[key]
        try:
            elapsed = _time_search(pattern, long_payload)
        except subprocess.TimeoutExpired:
            raise AssertionError(
                "{} pattern exceeded {}s at double length — cost grows with "
                "dash-run length (ambiguous parse reintroduced)".format(
                    key, KILL_SECONDS
                )
            )
        assert elapsed < BUDGET_SECONDS


# --------------------------------------------------------------------------
# Behaviour preservation: the gate's real job is extracting the repo path
#
# These 12 cases pass IDENTICALLY against the pre-fix and post-fix source.
# That is the point: this file has a documented false-block history
# (MYC-717 / 578 / 680 / 622), so the fix must not quietly narrow the gate.
# --------------------------------------------------------------------------

DASH_C_CASES = [
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
]

GIT_DIR_CASES = [
    ("git --git-dir=/p/.git status", "/p/.git"),
    ("git --git-dir /p/.git status", "/p/.git"),
    ("git --git-dir=/p/.git --work-tree=/w status", "/p/.git"),
    # --work-tree is deliberately NOT matched: it does not move the git-dir,
    # so matching it would relax the gate. See the comment above the
    # mg = re.search(...) line in session-lock.py.
    ("git --work-tree=/p status", None),
    ("git --work-tree /p status", None),
    ("git -C /some/path status", None),
]


def test_dash_c_scanner_still_extracts_the_path():
    for command, expected in DASH_C_CASES:
        match = re.search(PATTERNS["dash_c"], command)
        got = match.group(1) if match else None
        assert got == expected, "{!r}: expected {!r}, got {!r}".format(
            command, expected, got
        )


def test_git_dir_scanner_still_extracts_the_git_dir():
    for command, expected in GIT_DIR_CASES:
        match = re.search(PATTERNS["git_dir"], command)
        got = match.group(1) if match else None
        assert got == expected, "{!r}: expected {!r}, got {!r}".format(
            command, expected, got
        )


def test_separate_value_flag_still_defeats_the_scanner():
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
    assert re.search(PATTERNS["dash_c"], "git -c core.x=y -C /p status") is None


def test_end_of_options_separator_is_not_treated_as_a_flag():
    """`git -- -C /other/repo commit` no longer matches. Deliberate.

    This is the ONE input whose behaviour the ReDoS fix changes. Verified
    against the installed git (2.50.1): a bare `--` is rejected as a global
    option ("unknown option: --"), so nothing that works on a command line
    stops working here. Differentially tested across 97,656 inputs per
    scanner; this family is the only divergence.

    The direction is safe. In the unbalanced-quotes branch an extracted -C
    path is used to let a command THROUGH ("not this lock's business"), so
    dropping this match makes the gate strictly more conservative — it now
    falls back to cwd attribution instead of opening an escape hatch keyed on
    a token git itself refuses.
    """
    assert re.search(PATTERNS["dash_c"], "git -- -C /other/repo commit") is None


# --------------------------------------------------------------------------
# Plain-script runner: scripts/ci.sh invokes this file directly, with no
# pytest available. Without this block the file would exit 0 having asserted
# nothing.
# --------------------------------------------------------------------------

if __name__ == "__main__":
    checks = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    assert checks, "no test_* functions found — the runner would be vacuous"
    failures = 0
    for name, fn in checks:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - report, do not mask
            failures += 1
            print("FAIL  {}: {}".format(name, exc))
        else:
            print("PASS  {}".format(name))
    print("\n{} passed, {} failed".format(len(checks) - failures, failures))
    sys.exit(1 if failures else 0)
