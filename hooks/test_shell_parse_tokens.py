#!/usr/bin/env python3
"""Regression + cost tests for `_lib/shell_parse.py`'s `tokens()` / `_scan_tokens()`.

THE DEFECT. `tokens(seg)` used to be a one-line `shlex.split(seg)`. CPython's
`shlex.read_token` builds each token with `self.token += nextchar` on an
INSTANCE ATTRIBUTE: every `+=` loads that attribute onto the interpreter
stack first, so its refcount is never 1 at the point of the append, which
disqualifies CPython's in-place string-resize fast path and forces a full
copy of the token-so-far on every character. Cost grows with the SQUARE of
one token's length, not the length of the command. Measured CPU time of a
single `tokens("echo " + "a"*N)` call against the pre-fix module: N=50k
0.03s, 100k 0.14s, 200k 0.41s, 400k 1.43s. Several PreToolUse Bash hooks call
`tokens()` on every Bash command (directly, and transitively through
`leading_env_assigns`, `segment_bypass_flags`, `cwd_candidates` in this same
module), so one huge inline argument stalls every Bash call in the session.

THE FIX under test. `_scan_tokens(seg)` is a linear-time reimplementation of
the exact state machine `shlex.split` runs (POSIX, `whitespace_split=True`,
no comments, no `punctuation_chars`), built with a list buffer instead of
string-attribute concatenation. `tokens()` still calls the real
`shlex.split` for any segment up to `_SHLEX_MAX_CHARS` (16384 chars) -- so
every ordinary command is byte-identical to before -- and only reaches
`_scan_tokens` above that threshold. Both paths keep the pre-existing
`except ValueError: return seg.split()` fallback.

WHY THE MODULE IMPORT IS AT THE TOP BUT THE NEW NAMES ARE NOT. This file is
imported once, then every test reaches into `sp.tokens` / `sp._scan_tokens` /
`sp._SHLEX_MAX_CHARS` from inside its own body, rather than via a top-level
`from _lib.shell_parse import _scan_tokens, _SHLEX_MAX_CHARS`. `tokens()`
existed before this fix; `_scan_tokens` and `_SHLEX_MAX_CHARS` did not. A
top-level import of the new names would raise ImportError and crash the
WHOLE file when run against the pre-fix module, hiding every test behind one
opaque traceback. Reaching for `sp.<name>` from inside each test instead
means the one test that needs only `tokens()` and nothing else -- the cost
test -- can actually RUN TO COMPLETION against the pre-fix module and show
its TRUE behavior: it fails on the CPU-budget and call-count assertions
(23s CPU and one real `shlex.split` call, measured), not on an import error.
Every other test here also reaches `sp._scan_tokens` or `sp._SHLEX_MAX_CHARS`
somewhere in its own body (directly, or in a fixture-sanity assert), so each
of THOSE fails with a clear per-test `AttributeError` naming the missing
attribute, instead of one opaque import-time crash for the whole file.

Run: /usr/bin/python3 hooks/test_shell_parse_tokens.py   (Python 3.9, no pytest)
Stdlib only.
"""
from __future__ import annotations

import contextlib
import random
import shlex
import sys
import time
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS))

import _lib.shell_parse as sp  # noqa: E402


@contextlib.contextmanager
def _counting_shlex_split():
    """Patch `shlex.split` with a call-counting wrapper for the `with` block;
    yields the (mutable, append-only) list of calls made through it. Affects
    `shell_parse.py`'s `shlex.split(...)` too, since `import shlex` there
    binds the SAME module object -- there is only one `shlex` in `sys.modules`."""
    original_split = shlex.split
    calls = []

    def counting_split(*args, **kwargs):
        calls.append((args, kwargs))
        return original_split(*args, **kwargs)

    shlex.split = counting_split
    try:
        yield calls
    finally:
        shlex.split = original_split


# --------------------------------------------------------------------------
# a. EQUIVALENCE (fuzz): _scan_tokens(s) must match shlex.split(s) for every
#    s, or both must raise ValueError. Fixed seed -> reproducible.
# --------------------------------------------------------------------------

_EQUIV_SEED = 20260926
_EQUIV_TRIALS = 20000
_EQUIV_ALPHABET = (
    " \t\n\r"        # space, tab, newline, CR (all four are real shlex whitespace)
    "'\"\\;|$"       # quotes, escape, and shell-meaningful punctuation
    "ab-="           # ordinary word characters
    "#"              # comment-shaped, but NOT a comment char here (commenters='')
    "\x00"           # NUL -- an ordinary character to shlex, not whitespace
    "\x0b\x0c"       # vertical tab, form feed: str.isspace() but NOT shlex whitespace
    "\xa0"           # NBSP: str.isspace() but NOT shlex whitespace
    "　"         # ideographic space (U+3000): str.isspace() but NOT shlex whitespace
    "é"         # 'e' with acute accent -- ordinary non-ASCII character
    "\U0001f600"     # (grinning face) -- ordinary character outside the BMP
)
_EQUIV_MAX_LEN = 60

# Coverage floors for the fuzz loop below. A run that only ever hits the
# ValueError branch on both sides proves nothing about correct TOKENIZATION --
# measured at 63% of the previous 20,000-trial run before these floors and
# the wider alphabet existed. "Both sides produced a token list" and "that
# list has 2+ tokens" are asserted as hard minimums so the equivalence claim
# is backed by real token-level comparisons, not mostly-matching exceptions.
_EQUIV_MIN_BOTH_TOKENIZED = 5000
_EQUIV_MIN_BOTH_MULTI_TOKEN = 2000


def _compare_scan_vs_shlex(seg):
    """(ok, detail) -- ok iff _scan_tokens(seg) == shlex.split(seg), or both
    raise ValueError (the exact message need not match, only the raise/no-raise
    split and the token list itself)."""
    try:
        want = shlex.split(seg)
        want_err = None
    except ValueError as exc:
        want = None
        want_err = str(exc) or exc.__class__.__name__
    try:
        got = sp._scan_tokens(seg)
        got_err = None
    except ValueError as exc:
        got = None
        got_err = str(exc) or exc.__class__.__name__

    if want_err is None and got_err is None:
        ok = want == got
    elif want_err is not None and got_err is not None:
        ok = True
    else:
        ok = False
    return ok, {"seg": seg, "want": want, "want_err": want_err,
                "got": got, "got_err": got_err}


def _preview_tokens(toks, max_tokens=4, max_chars=60):
    """Bounded, readable preview of a token list for failure messages -- shows
    actual CONTENT, not only a count, without dumping a potentially
    16,000+-char single token into the output."""
    shown = []
    for t in toks[:max_tokens]:
        r = repr(t)
        if len(r) > max_chars:
            r = r[:max_chars] + "...<+{} more char(s)>".format(len(t) - max_chars + 2)
        shown.append(r)
    if len(toks) > max_tokens:
        shown.append("...<+{} more token(s)>".format(len(toks) - max_tokens))
    return "[" + ", ".join(shown) + "]"


def _diff_token_lists(got, want):
    """First point where two token lists diverge -- an index and both values,
    or a length mismatch and the first extra token -- for a failure message
    that shows WHAT differs instead of only how many tokens each side has."""
    for i, (g, w) in enumerate(zip(got, want)):
        if g != w:
            return "first difference at index {}: got {} want {}".format(
                i, _preview_tokens([g]), _preview_tokens([w]))
    if len(got) != len(want):
        longer, which = (got, "got") if len(got) > len(want) else (want, "want")
        shorter_len = min(len(got), len(want))
        return "lengths differ (got {} want {}); `{}` has an extra token at index {}: {}".format(
            len(got), len(want), which, shorter_len, _preview_tokens([longer[shorter_len]]))
    return "(no difference found -- lists compare equal)"


def test_equivalence_fuzz_matches_shlex_split():
    rng = random.Random(_EQUIV_SEED)
    mismatches = 0
    first = None
    both_tokenized = 0     # neither side raised -- a REAL token-list comparison happened
    both_multi_token = 0   # both_tokenized AND the (agreeing) list has 2+ tokens
    for _ in range(_EQUIV_TRIALS):
        length = rng.randint(0, _EQUIV_MAX_LEN)
        seg = "".join(rng.choice(_EQUIV_ALPHABET) for _ in range(length))
        ok, detail = _compare_scan_vs_shlex(seg)
        if not ok:
            mismatches += 1
            if first is None:
                first = detail
        # Counted independently of `ok`: "both sides returned tokens" means
        # neither raised, regardless of whether their lists agreed -- that
        # agreement is what `mismatches` already tracks above.
        if detail["want_err"] is None and detail["got_err"] is None:
            both_tokenized += 1
            if len(detail["want"]) >= 2:
                both_multi_token += 1
    print("    [equivalence] {} trials, {} mismatch(es), {} both-tokenized, "
          "{} both-tokenized-with-2+-tokens".format(
              _EQUIV_TRIALS, mismatches, both_tokenized, both_multi_token))

    problems = []
    if mismatches:
        d = first
        problems.append(
            "{} of {} fuzzed segment(s) mismatched shlex.split. FIRST MISMATCH "
            "seg={!r}\n        shlex.split   -> tokens={!r} err={!r}\n"
            "        _scan_tokens  -> tokens={!r} err={!r}".format(
                mismatches, _EQUIV_TRIALS, d["seg"], d["want"], d["want_err"],
                d["got"], d["got_err"]))
    if both_tokenized < _EQUIV_MIN_BOTH_TOKENIZED:
        problems.append(
            "only {} of {} trials had BOTH sides actually tokenize (neither raised); "
            "want at least {} -- a run dominated by the ValueError branch on both "
            "sides proves nothing about correct tokenization".format(
                both_tokenized, _EQUIV_TRIALS, _EQUIV_MIN_BOTH_TOKENIZED))
    if both_multi_token < _EQUIV_MIN_BOTH_MULTI_TOKEN:
        problems.append(
            "only {} of {} trials produced 2+ agreeing tokens on both sides; want "
            "at least {}".format(both_multi_token, _EQUIV_TRIALS, _EQUIV_MIN_BOTH_MULTI_TOKEN))
    if problems:
        raise AssertionError("; ".join(problems))


# --------------------------------------------------------------------------
# b. EQUIVALENCE (hand-picked edges): the exact shapes named in the brief --
#    quote/unquoted concatenation, escapes in/out of each quote style, an
#    empty quoted token, both unclosed-quote forms, a trailing backslash, a
#    real newline inside quotes, and backslash-newline outside quotes.
# --------------------------------------------------------------------------

_EDGE_CASES = [
    ("a\"b c\"d",  "quoted + unquoted pieces concatenate into ONE token"),
    ("'' x",       "an empty single-quoted token, then a real token"),
    ("a\\ b",      "backslash escapes a space outside quotes"),
    ("\"a\\\"b\"", "backslash escapes a doublequote INSIDE doublequotes"),
    ("\"a\\\\b\"", "backslash escapes a backslash INSIDE doublequotes"),
    ("\"a\\$b\"",  "backslash before a non-special char inside doublequotes keeps BOTH"),
    ("'a\\b'",     "backslash has NO special meaning inside singlequotes"),
    ("a\\\\",      "a valid escaped backslash outside quotes (even count)"),
    ("foo\\",      "a trailing UNESCAPED backslash (odd count) -- ValueError"),
    ("\"abc",      "an unclosed doublequote -- ValueError"),
    ("'abc",       "an unclosed singlequote -- ValueError"),
    ("\"a\nb\"",   "a real newline embedded inside quotes"),
    ("x\\\ny",     "backslash immediately followed by a real newline, outside quotes"),
    ("a\rb",       "a bare CR outside quotes IS whitespace to real shlex -- splits into 2"),
    ("#x y",       "a leading '#' is NOT a comment here (commenters=''); stays 2 tokens"),
    ("a\x0bb",     "a bare vertical tab is NOT shlex whitespace, despite str.isspace()"),
    ("a\x00b",     "a bare NUL is an ordinary character, not whitespace"),
    ("a\xa0b",     "a bare NBSP is NOT shlex whitespace, despite str.isspace()"),
]


def test_equivalence_hand_picked_edge_cases():
    failures = []
    for seg, label in _EDGE_CASES:
        ok, detail = _compare_scan_vs_shlex(seg)
        print("    [edge] {:4} {!r:14} {}".format("ok" if ok else "FAIL", seg, label))
        if not ok:
            failures.append((label, detail))
    if failures:
        label, d = failures[0]
        raise AssertionError(
            "{} of {} hand-picked edge case(s) mismatched shlex.split. FIRST "
            "MISMATCH ({}) seg={!r}\n        shlex.split   -> tokens={!r} err={!r}\n"
            "        _scan_tokens  -> tokens={!r} err={!r}".format(
                len(failures), len(_EDGE_CASES), label, d["seg"], d["want"],
                d["want_err"], d["got"], d["got_err"]))


# --------------------------------------------------------------------------
# c. COST (structural): a 1,000,005-char segment (one 1,000,000-char token)
#    must NEVER reach the real shlex.split, must still tokenize correctly,
#    and must cost well under the quadratic blowup the pre-fix code paid.
# --------------------------------------------------------------------------

_COST_SEGMENT = "echo " + "a" * 1_000_000
_COST_CPU_BUDGET_SECONDS = 2.0


def test_cost_huge_segment_skips_shlex_and_stays_under_budget():
    with _counting_shlex_split() as calls:
        t0 = time.process_time()
        result = sp.tokens(_COST_SEGMENT)
        elapsed = time.process_time() - t0

    print("    [cost] {:.4f}s CPU for a {}-char segment, shlex.split call count={}".format(
        elapsed, len(_COST_SEGMENT), len(calls)))

    problems = []
    if len(calls) != 0:
        problems.append(
            "shlex.split was called {} time(s), expected 0 -- tokens() must route a "
            "{}-char segment through _scan_tokens, never the real shlex.split"
            .format(len(calls), len(_COST_SEGMENT)))
    expected = ["echo", "a" * 1_000_000]
    if result != expected:
        problems.append(
            "wrong tokens: got {} token(s) with lengths {}, want {} token(s) with "
            "lengths {}".format(len(result), [len(t) for t in result],
                                 len(expected), [len(t) for t in expected]))
    if elapsed >= _COST_CPU_BUDGET_SECONDS:
        problems.append("{:.4f}s CPU >= the {:.1f}s budget (this is the quadratic "
                         "blowup the fix exists to remove)".format(
                             elapsed, _COST_CPU_BUDGET_SECONDS))
    if problems:
        raise AssertionError("; ".join(problems))


# --------------------------------------------------------------------------
# d. THRESHOLD: an ordinary short command (1,000 chars, well under
#    _SHLEX_MAX_CHARS) must still go through the REAL shlex.split exactly
#    once, with byte-identical output to calling shlex.split directly.
# --------------------------------------------------------------------------

def test_threshold_short_command_still_uses_real_shlex():
    cmd = "echo " + "a" * 1000
    assert len(cmd) <= sp._SHLEX_MAX_CHARS, "fixture must stay under the threshold"
    expected = shlex.split(cmd)

    with _counting_shlex_split() as calls:
        result = sp.tokens(cmd)

    print("    [threshold] {}-char command, shlex.split call count={}".format(len(cmd), len(calls)))
    problems = []
    if len(calls) != 1:
        problems.append("shlex.split was called {} time(s), expected exactly 1".format(len(calls)))
    if result != expected:
        problems.append("output changed vs. calling shlex.split directly: got {!r}, want {!r}"
                         .format(result, expected))
    if problems:
        raise AssertionError("; ".join(problems))


# --------------------------------------------------------------------------
# e. THRESHOLD BOUNDARY: pin the `<=` in `len(seg) <= _SHLEX_MAX_CHARS`
#    directly. A segment of EXACTLY _SHLEX_MAX_CHARS chars must still go
#    through the real shlex.split (this is the "at or under" half of `<=`);
#    one char longer must NOT (a `<=` -> `<` mutant would call shlex.split
#    one char too early -- i.e. it would ALSO call it at exactly the
#    threshold, so the first half alone cannot tell them apart -- while a
#    `<` -> `<=` mutant, or any off-by-one the other direction, is caught by
#    the second half calling shlex.split when it must not).
# --------------------------------------------------------------------------

def test_threshold_boundary_exact_16384_vs_16385():
    at_threshold = "a" * sp._SHLEX_MAX_CHARS
    over_threshold = "a" * (sp._SHLEX_MAX_CHARS + 1)
    assert len(at_threshold) == sp._SHLEX_MAX_CHARS
    assert len(over_threshold) == sp._SHLEX_MAX_CHARS + 1

    problems = []

    with _counting_shlex_split() as calls_at:
        result_at = sp.tokens(at_threshold)
    print("    [boundary] exactly {}-char segment, shlex.split call count={}".format(
        len(at_threshold), len(calls_at)))
    if len(calls_at) != 1:
        problems.append(
            "at exactly _SHLEX_MAX_CHARS ({} chars) shlex.split was called {} time(s), "
            "expected exactly 1 (a `<=` -> `<` mutant would call it 0 here)".format(
                sp._SHLEX_MAX_CHARS, len(calls_at)))
    if result_at != [at_threshold]:
        problems.append("at-threshold segment tokenized wrong: got {} token(s), want 1"
                         .format(len(result_at)))

    with _counting_shlex_split() as calls_over:
        result_over = sp.tokens(over_threshold)
    print("    [boundary] {}-char segment (threshold+1), shlex.split call count={}".format(
        len(over_threshold), len(calls_over)))
    if len(calls_over) != 0:
        problems.append(
            "at _SHLEX_MAX_CHARS+1 ({} chars) shlex.split was called {} time(s), expected "
            "exactly 0 (a mutant widening the threshold, e.g. `<` -> `<=` alone with no "
            "matching change, would call it here)".format(len(over_threshold), len(calls_over)))
    if result_over != [over_threshold]:
        problems.append("over-threshold segment tokenized wrong: got {} token(s), want 1"
                         .format(len(result_over)))

    if problems:
        raise AssertionError("; ".join(problems))


# --------------------------------------------------------------------------
# f. FALLBACK: an unclosed quote on a segment LONGER than _SHLEX_MAX_CHARS
#    must still fall back to plain seg.split(), same as it always did for
#    the ValueError case below the threshold.
# --------------------------------------------------------------------------

def test_fallback_unclosed_quote_over_threshold_uses_plain_split():
    bad_seg = "\"" + "a" * (sp._SHLEX_MAX_CHARS + 5000)   # unclosed doublequote, over threshold
    result = sp.tokens(bad_seg)
    expected = bad_seg.split()
    print("    [fallback] {}-char segment with an unclosed quote -> {} plain-split token(s)"
          .format(len(bad_seg), len(result)))
    if result != expected:
        raise AssertionError(
            "tokens() on an unclosed quote over the threshold did not match plain "
            "seg.split(): {}\n        got  ({} token(s)) = {}\n"
            "        want ({} token(s)) = {}".format(
                _diff_token_lists(result, expected), len(result), _preview_tokens(result),
                len(expected), _preview_tokens(expected)))


# --------------------------------------------------------------------------
# Plain-script runner: scripts/ci.sh invokes this file directly, with no
# pytest available (PY_DIRECT). EXPECTED_TEST_COUNT is a HARD FLOOR: if a
# test silently stops being discovered (renamed away from `test_`, deleted,
# a typo), the run must fail LOUD instead of quietly reporting fewer tests
# as if that were fine -- exactly the SILENT-NO-OP-ON-UNEVALUABLE-SPEC shape
# this suite exists to avoid becoming an instance of.
# --------------------------------------------------------------------------

EXPECTED_TEST_COUNT = 6

if __name__ == "__main__":
    checks = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    if len(checks) < EXPECTED_TEST_COUNT:
        print("FAIL: only {} test_* function(s) discovered, expected at least {} "
              "(a test was silently dropped -- fix the DEFINITION, never lower "
              "this floor to match).".format(len(checks), EXPECTED_TEST_COUNT))
        sys.exit(1)

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
