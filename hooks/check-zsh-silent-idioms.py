#!/usr/bin/env python3
"""
PreToolUse Bash hook: bash idioms that silently do the wrong thing under zsh.

One guard, one bug class. On a zsh shell a bash idiom runs, exits 0, prints no
error, and returns output that looks like a legitimate answer: empty, or
false-red. Two detectors, deliberately independent, so one raising can never
disarm the other. One bypass covers the whole guard.

1. git-ref. Unbraced `$VAR:path` in a git object read.
   zsh applies HISTORY MODIFIERS after `$VAR:`, so `git show "$SHA:src/app.py"`
   expands to something else entirely and prints NOTHING. The command exits 0
   with empty output, which is byte-identical to "this path does not exist at
   this ref": a silent false clean on an absence claim, and absence is the
   most dangerous result a search can return. Witnessed twice: a session
   reported a LIVE fix as undeployed, and a later session probed four branches
   for a security regression and got `<NONE FOUND>` on all four while the
   symbol was plainly present. Only a positive control caught the second one.
   The fix is two characters and is correct in BOTH shells:
       git show "$SHA:path"     ->  git show "${SHA}:path"
   Fires in any shell, because the braced form is correct everywhere.

2. word-split. An unquoted `$VAR` as a `for X in` list item or a `set --`
   operand. zsh does not word-split an unquoted parameter expansion
   (SH_WORD_SPLIT is off); bash does. `set -- $r` leaves `$1` holding the whole
   string, and `for c in $CHECKS` runs ONCE with a newline-separated list as a
   single argument. Witnessed repeatedly across sessions as empty or false-red
   output with no error.
   Fires only when $SHELL is zsh: the fixes it offers include `${=VAR}`, a bad
   substitution in bash, where the idiom is already correct.
   Matches a WHOLE word that is exactly `$name` or `${name}`. Allowed, because
   zsh splits it, bash reads it, or there is nothing to split: `${=name}`,
   `"$@"` and `$@`, a quoted `"$name"`, command substitution `$(...)` and
   backticks, a literal list, an array assigned in the same command
   (`v=(a b)`, `typeset -a v`, `read -A v`), zsh's own array parameters
   (`$path`), `setopt shwordsplit` in the same command, anything inside a
   `bash -c '...'` or `sh -c '...'` string, and a heredoc body.
   Not covered: `arr=($v)`, `cmd $v`, `select`, positional parameters such as
   `$1`, and the contents of a `zsh -c '...'` string.

Bypass: ZSH_SILENT_IDIOMS_BYPASS=1, from the env OR as an inline prefix. Both are
honored, because a guard whose advertised inline bypass cannot fire is a guard
that lies. One bypass covers both detectors.

Self-test: `check-zsh-silent-idioms.py --selftest` proves it BOTH ways.
"""
import contextlib
import io
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    # Heredoc-aware shared primitive (MYC-4115). A local re-implementation is
    # the GUARD-DISARMED-BY-ITS-OWN-OUTPUT class (MYC-4724): a naive whole-string
    # regex counts a bypass token that merely APPEARS in a heredoc body or in
    # trailing text, so quoting this guard's own block message next to a git
    # command would disarm it.
    from _lib.cmd_env import inline_bypass
except Exception:                                    # pragma: no cover - fail open
    def inline_bypass(command, var, value="1"):
        return False

GUARD = "check-zsh-silent-idioms"
BYPASS = "ZSH_SILENT_IDIOMS_BYPASS"


# ---------------------------------------------------------------------------
# Detector 1: unbraced `$VAR:path` in a git object read (fires in any shell).
# ---------------------------------------------------------------------------

# A git read that resolves a <rev>:<path> object spec.
GIT_OBJECT_READ = re.compile(
    r"\bgit\b[^\n|;&]{0,200}?\b(show|cat-file|grep|diff|log|archive)\b"
)
# `$VAR:` with NO braces, followed by something path-shaped.
UNBRACED_REF = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*):(?=[A-Za-z0-9_./~-])")


def detect_unbraced_git_ref(command: str, zsh: bool) -> list:
    """Detector 1. One deny block when a git object read carries `$VAR:path`.

    `zsh` is unused on purpose: the braced fix is correct in every shell, so
    this detector never needs to know which one is running.
    """
    if not GIT_OBJECT_READ.search(command):
        return []
    names = [m.group(1) for m in UNBRACED_REF.finditer(command)]
    if not names:
        return []
    first = names[0]
    return [
        f"BLOCKED by {GUARD}: `${first}:` is unbraced in a git object read.\n\n"
        f"Under zsh, `$VAR:` triggers a HISTORY MODIFIER. The command prints NOTHING "
        f"and exits 0 — indistinguishable from 'that path does not exist at that ref'. "
        f"Every absence you conclude from it is a false clean.\n\n"
        f"Brace it (correct in bash AND zsh):\n"
        f'    git show "${{{first}}}:path/to/file"\n\n'
        f"If you are asserting an ABSENCE from this command, also run a positive "
        f"control: the same command against a ref where the symbol is known present."
    ]


# ---------------------------------------------------------------------------
# Detector 2: unsplit `$VAR` in `set --` / `for X in` (zsh only).
# ---------------------------------------------------------------------------

_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_IDENT_RE = re.compile(_IDENT + r"\Z")
# A WHOLE word that is exactly one plain parameter expansion: `$v` or `${v}`.
# Not matched: `${=v}`, `${v:-x}`, `${v[@]}`, `$@`, `$1`, `"$v"`, `$v/x`.
_BARE_PARAM = re.compile(rf"\$(?:({_IDENT})|\{{({_IDENT})\}})\Z")
_LOOP_OR_SET = re.compile(r"\b(?:for|set)\b")
# zsh's OWN array parameters, which `print ${(Pt)name}` reports as `array...`
# under zsh. `for p in $path` is correct zsh, not the trap.
_ZSH_ARRAYS = frozenset({
    "path", "fpath", "cdpath", "manpath", "mailpath", "psvar", "argv",
    "pipestatus", "signals", "watch", "funcstack", "dirstack", "fignore",
    "module_path", "historywords", "zsh_eval_context",
})
# Words that may sit in front of a command word: `then for ...`, `do set -- ...`.
_CMD_PREFIX = frozenset({"{", "then", "do", "else", "!", "time"})
_ARRAY_FLAG = re.compile(r"-[A-Za-z]*[aA][A-Za-z]*\Z")
# `v=(a b)` / `v+=(c)` / `declare -a v=(...)`, searched on quote-masked code.
_ARRAY_ASSIGN = re.compile(rf"(?<![A-Za-z0-9_$])({_IDENT})\+?=\(")
# `setopt shwordsplit` / `set -o SH_WORD_SPLIT` turn bash-style splitting ON.
# The lookbehind rejects `noshwordsplit` / `no_sh_word_split`, which turn it off.
_SHWORDSPLIT = re.compile(
    r"\b(?:setopt|set\s+-o)\b[^;&|\n]*?(?<![A-Za-z_])sh_?word_?split",
    re.IGNORECASE,
)


def _mask_quotes(code: str) -> str:
    """`code` with the INSIDE of every quoted string blanked (same length).

    A pattern search over shell CODE must be neither satisfied nor disarmed by
    text that merely sits in a string: `echo "v=(a b)"` assigns no array.
    """
    out = []
    quote = None
    i, n = 0, len(code)
    while i < n:
        c = code[i]
        if quote:
            if c == "\\" and quote == '"' and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if c == quote:
                quote = None
                out.append(c)
            else:
                out.append(" ")
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            out.append(c)
            out.append(code[i + 1])
            i += 2
            continue
        if c in "'\"":
            quote = c
        out.append(c)
        i += 1
    return "".join(out)


def _raw_words(seg: str) -> list:
    """Split one command segment into words, KEEPING the quote characters.

    The shared `tokens()` strips quotes, and quoting is exactly the fact this
    detector needs: `"$v"` is fine, a bare `$v` is the trap. Whitespace does not
    split a word inside quotes, a `${...}`, or backticks.
    """
    words, cur = [], []
    quote = None
    brace = 0
    tick = False
    i, n = 0, len(seg)
    while i < n:
        c = seg[i]
        if quote:
            cur.append(c)
            if c == "\\" and quote == '"' and i + 1 < n:
                cur.append(seg[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            cur.append(c)
            cur.append(seg[i + 1])
            i += 2
            continue
        if c in "'\"":
            quote = c
        elif c == "`":
            tick = not tick
        elif c == "$" and seg.startswith("${", i):
            brace += 1
            cur.append("${")
            i += 2
            continue
        elif c == "}" and brace:
            brace -= 1
        elif c.isspace() and not tick and not brace:
            if cur:
                words.append("".join(cur))
                cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    if cur:
        words.append("".join(cur))
    return words


def _strip_prefix(words: list) -> list:
    i = 0
    while i < len(words) and words[i] in _CMD_PREFIX:
        i += 1
    return words[i:]


def _statements(segs: list) -> list:
    """Whole statements, rebuilt from the shared splitter's `(sep, text)` segments.

    The splitter cuts at every `(` and `)`, so `for x in $(cat f) $v` arrives as
    three pieces and the bare `$v` lands in a segment that no longer begins with
    `for`. Re-join the text around each `$( ... )` (the substitution itself
    becomes a placeholder word) and emit the substitution's own statements
    separately, so a loop INSIDE `$( ... )` is still scanned.
    """
    out, cur, stack = [], [], []
    for sep, text in segs:
        if sep == "(":
            if cur and cur[-1].endswith("$"):        # `$(`: command substitution
                cur[-1] = cur[-1][:-1] + "S"
                stack.append(("sub", cur))
            else:                                    # subshell, `f()`, `v=(`
                out.append("".join(cur))
                stack.append(("plain", None))
            cur = [text]
        elif sep == ")":
            out.append("".join(cur))
            kind, outer = stack.pop() if stack else ("plain", None)
            cur = outer + [text] if kind == "sub" else [text]
        else:                                        # ; & | && || newline
            out.append("".join(cur))
            cur = [text]
    out.append("".join(cur))
    while stack:                                     # unclosed `$(`: keep the outer text
        kind, outer = stack.pop()
        if kind == "sub":
            out.append("".join(outer))
    return out


def _operands(w: list):
    """`(shape, operand_words)` when `w` is `for NAME... in OPERANDS` or
    `set ... -- OPERANDS`, else None."""
    if not w:
        return None
    if w[0] == "for" and "in" in w[1:]:
        k = w.index("in", 1)
        if k >= 2 and all(_IDENT_RE.match(x) for x in w[1:k]):
            return "for", w[k + 1:]
    elif w[0] == "set" and "--" in w[1:]:
        return "set", w[w.index("--", 1) + 1:]
    return None


def _declared_arrays(w: list) -> set:
    """Names a command makes into ARRAYS without writing `NAME=(`:
    `typeset -a v`, `local -a v`, `read -A v`, `set -A v ...`."""
    if not w:
        return set()
    flags = [x for x in w[1:] if x.startswith("-")]
    if w[0] in ("declare", "typeset", "local", "readonly") and any(
            _ARRAY_FLAG.match(f) for f in flags):
        names = {x.split("=", 1)[0] for x in w[1:] if not x.startswith("-")}
        return {n for n in names if _IDENT_RE.match(n)}
    if w[0] == "read" and any(_ARRAY_FLAG.match(f) for f in flags):
        return {x for x in w[1:] if _IDENT_RE.match(x)}
    if w[0] == "set" and "-A" in w[1:]:
        k = w.index("-A", 1)
        if k + 1 < len(w) and _IDENT_RE.match(w[k + 1]):
            return {w[k + 1]}
    return set()


def _word_split_block(shape: str, name: str) -> str:
    use = f"set -- ${name}" if shape == "set" else f"for X in ${name}"
    fixed = f"set -- ${{={name}}}" if shape == "set" else f"for X in ${{={name}}}"
    fixes = (
        (fixed, "zsh syntax: splits like bash"),
        (f'read -r a b c <<< "${name}"', "a fixed number of fields, both shells"),
        ("bash -c '...'", f"run the loop under bash (export {name} first)"),
    )
    return (
        f"BLOCKED by {GUARD}: `{use}` is not word-split under zsh: zsh keeps an "
        f"unquoted `${name}` as ONE word where bash splits it, so the loop runs "
        f"once on the whole string (or `set --` puts it all in `$1`) and nothing "
        f"errors.\n\n"
        f"Fix it, any one of:\n"
        + "\n".join(f"    {cmd:<34}{why}" for cmd, why in fixes)
    )


def detect_unsplit_param(command: str, zsh: bool) -> list:
    """Detector 2. One deny block for an unsplit `$VAR` in `set --` / `for X in`."""
    if not zsh or "$" not in command or not _LOOP_OR_SET.search(command):
        return []
    # Imported here, not at module top: a missing shared parser must silence THIS
    # detector only. A top-level failure would take detector 1 down with it.
    from _lib.shell_parse import (
        split_segments_with_seps, strip_heredoc_bodies, strip_noncode)

    # A heredoc body is data and a comment tail is text the shell never runs.
    code = strip_noncode(strip_heredoc_bodies(command))
    masked = _mask_quotes(code)
    if "shwordsplit" in masked.lower().replace("_", "") and _SHWORDSPLIT.search(masked):
        return []
    arrays = set(_ZSH_ARRAYS)
    arrays.update(m.group(1) for m in _ARRAY_ASSIGN.finditer(masked))
    found = []
    # `bash -c '...'` and `sh -c '...'` stay ONE quoted segment led by `bash`/`sh`,
    # so they never reach `_operands`: bash reads those strings, not zsh.
    for seg in _statements(split_segments_with_seps(code)):
        w = _strip_prefix(_raw_words(seg))
        arrays.update(_declared_arrays(w))
        got = _operands(w)
        if not got:
            continue
        shape, operands = got
        for word in operands:
            m = _BARE_PARAM.match(word)
            if m:
                found.append((shape, m.group(1) or m.group(2)))
    for shape, name in found:
        if name not in arrays:
            return [_word_split_block(shape, name)]
    return []


# ---------------------------------------------------------------------------
# Guard: run every detector independently, build one deny.
# ---------------------------------------------------------------------------

DETECTORS = (
    ("git-ref", detect_unbraced_git_ref),
    ("word-split", detect_unsplit_param),
)

_BYPASS_NOTE = (
    "A documented inline bypass exists for the case where the flagged shape is "
    "genuinely safe; see the hook docstring. It is deliberately not printed "
    "here, so quoting this message next to a command cannot disarm the guard "
    "(MYC-4724)."
)


def _shell_is_zsh() -> bool:
    """Is the Bash tool's shell zsh? Detector 2 means nothing anywhere else."""
    return os.path.basename(os.environ.get("SHELL", "")) == "zsh"


def run_detectors(command: str, zsh: bool) -> list:
    """Every detector's deny blocks. A detector that raises is skipped, loudly
    (stderr, ASCII only), and NEVER takes the others down with it."""
    blocks = []
    for name, fn in DETECTORS:
        try:
            blocks.extend(fn(command, zsh))
        except Exception as exc:
            print(
                f"{GUARD}: detector {name!r} failed ({type(exc).__name__}); "
                f"it is skipped, the other detectors still run",
                file=sys.stderr,
            )
    return blocks


def _isolation_ok() -> bool:
    """A detector that raises must not disarm the other one, in either order."""
    global DETECTORS
    real = DETECTORS

    def boom(command, zsh):
        raise RuntimeError("injected failure")

    try:
        with contextlib.redirect_stderr(io.StringIO()):
            DETECTORS = (("boom", boom),) + real
            word_split = run_detectors("for c in $CHECKS; do :; done", True)
            DETECTORS = real + (("boom", boom),)
            git_ref = run_detectors('git show "$SHA:x.py"', True)
    finally:
        DETECTORS = real
    return bool(word_split) and bool(git_ref)


def _selftest() -> int:
    git, split = 0, 1   # indexes into DETECTORS
    cases = [
        # (detector, command, should_fire)
        # --- detector 1: git-ref ---
        (git, 'git show "$SHA:src/app.py"', True),
        (git, "git show $SHA:src/app.py", True),
        (git, 'git grep -n foo "$REF:path/x.py"', True),
        (git, 'git show "${SHA}:src/app.py"', False),          # braced = correct
        (git, "git show origin/main:src/app.py", False),        # no variable
        (git, 'echo "$MSG: done"', False),                      # not a git read
        (git, 'git log --format="%H"', False),                  # no ref spec
        (git, 'ZSH_SILENT_IDIOMS_BYPASS=1 git show "$SHA:x.py"', False),  # real inline bypass
        # the token merely APPEARING in a heredoc body must NOT disarm it
        (git, 'cat <<EOF\nZSH_SILENT_IDIOMS_BYPASS=1\nEOF\ngit show "$SHA:x.py"', True),
        # --- detector 2: word-split, must FIRE ---
        (split, 'for r in "repo 1420 1421"; do set -- $r; echo "$1"; done', True),
        (split, 'for c in $CHECKS; do node "$c"; done', True),
        (split, "set -- $r", True),
        (split, 'for x in a $v b; do echo "$x"; done', True),   # among other words
        (split, 'for x in ${v}; do echo "$x"; done', True),     # braced plain
        (split, 'for x in "$a" $b; do :; done', True),          # only the bare one
        (split, 'v=$(cat list.txt); for x in $v; do :; done', True),  # scalar
        (split, 'if [ -n "$q" ]; then for x in $v; do :; done; fi', True),
        (split, 'echo ok && { for x in $v; do :; done; }', True),
        (split, 'out=$(for x in $v; do echo "$x"; done)', True),  # inside $( )
        (split, 'echo "v=(a b)"; for x in $v; do :; done', True),  # array text in a string
        (split, 'unsetopt shwordsplit; for x in $v; do :; done', True),
        (split, 'setopt noshwordsplit; for x in $v; do :; done', True),
        (split, 'cat <<EOF\nsetopt shwordsplit\nEOF\nfor x in $v; do :; done', True),
        (split, 'cat <<EOF\nZSH_SILENT_IDIOMS_BYPASS=1\nEOF\nfor x in $v; do :; done', True),
        (split, 'for x in $(cat f) $v; do :; done', True),      # bare one AFTER a $(...)
        (split, 'set -- $(cmd) $v', True),
        (split, 'for x in $(cat f | sort; echo z) $v; do :; done', True),
        (split, 'for x in $(for y in $v; do echo "$y"; done); do :; done', True),  # loop inside
        (split, 'echo $((1+2)); for x in $v; do :; done', True),
        # --- detector 2: word-split, must stay SILENT ---
        (split, "for x in ${=v}; do :; done", False),           # zsh splitting flag
        (split, "set -- ${=v}", False),
        (split, 'for x in "$@"; do :; done', False),
        (split, "for x in $@; do :; done", False),              # zsh splits $@
        (split, 'set -- "$@"', False),
        (split, "set -- $@", False),
        (split, "for x in $(ls); do :; done", False),           # zsh splits $(...)
        (split, "for x in `ls`; do :; done", False),
        (split, "v=(a b); for x in $v; do :; done", False),     # array, same command
        (split, "typeset -a v; for x in $v; do :; done", False),
        (split, 'read -A v <<< "a b"; for x in $v; do :; done', False),
        (split, "for x in a b c; do :; done", False),           # literal words
        (split, "for x in *.txt; do :; done", False),
        (split, "for x in {1..3}; do :; done", False),
        (split, 'bash -c \'for x in $v; do echo "$x"; done\'', False),
        (split, 'sh -c "set -- \\$v; echo \\$1"', False),
        (split, 'bash <<\'EOF\'\nfor x in $v; do echo "$x"; done\nEOF', False),
        (split, 'for x in "$v"; do :; done', False),            # quoted
        (split, "for x in '$v'; do :; done", False),
        (split, 'for p in $path; do echo "$p"; done', False),   # zsh's own array
        (split, "setopt shwordsplit; for x in $v; do :; done", False),
        (split, "echo for x in $v", False),                     # not a loop
        (split, 'git commit -m "set -- $v"', False),
        (split, "for x in $v/*.txt; do :; done", False),        # not a bare word
        (split, "for x in ${v:-a b}; do :; done", False),
        (split, "for x in ${v[@]}; do :; done", False),
        (split, "# for x in $v; do :; done", False),            # comment
        (split, "echo ok  # for x in $v", False),
        (split, "export ZSH_SILENT_IDIOMS_BYPASS=1; for x in $v; do :; done", False),
        (split, 'for x in $(cat f) "$v"; do :; done', False),
        (split, 'for x in $(cat f) ${=v}; do :; done', False),
        (split, 'n=$(( 2 * 3 )); for x in a b; do :; done', False),
    ]
    bad = 0
    for idx, cmd, want in cases:
        got = bool(DETECTORS[idx][1](cmd, True)) and not inline_bypass(cmd, BYPASS)
        if got != want:
            bad += 1
        print(f"  [{'ok ' if got == want else 'FAIL'}] fire={got!s:5} want={want!s:5}"
              f"  {DETECTORS[idx][0]:10} {cmd!r}")
    total = len(cases)
    if not _isolation_ok():
        bad += 1
        print("  [FAIL] a raising detector disarmed the other one")
    else:
        print("  [ok ] a raising detector does not disarm the other one (both orders)")
    total += 1
    print(f"\n{'PASS' if not bad else 'FAIL'}: {total - bad}/{total} cases")
    return 1 if bad else 0


def main() -> None:
    if "--selftest" in sys.argv:
        sys.exit(_selftest())

    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if not isinstance(data, dict) or data.get("tool_name", "") != "Bash":
        sys.exit(0)

    tool_input = data.get("tool_input")
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not isinstance(command, str) or not command:
        sys.exit(0)

    if os.environ.get(BYPASS) == "1":
        sys.exit(0)
    try:
        bypassed = inline_bypass(command, BYPASS)
    except Exception:
        bypassed = False     # a failing bypass read must never disarm a detector
    if bypassed:
        sys.exit(0)

    blocks = run_detectors(command, _shell_is_zsh())
    if not blocks:
        sys.exit(0)

    reason = "\n\n".join(blocks) + "\n\n" + _BYPASS_NOTE
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
    # Windows cp1252-console safety (ai-brain-starter#313; hooks/ sweep #314).
    # A hook that print()s non-ASCII raises UnicodeEncodeError on a cp1252
    # console: the gate then fails silently OPEN, or denies the tool call with
    # no legible cause. This one's deny reason carries em dashes, so it is in
    # exactly that class. Idempotent; a no-op on an already-UTF-8 console.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass
    main()
