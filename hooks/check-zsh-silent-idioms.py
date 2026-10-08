#!/usr/bin/env python3
"""
PreToolUse Bash hook: bash idioms that silently do the wrong thing under zsh.

Two independent detectors (one raising never disarms the other), one bypass.

1. git-ref, in any shell. An unbraced `$VAR:` plus a letter in a git object read
   (show, cat-file, grep, diff, log, archive, rev-parse, ls-tree). zsh can read
   it as a history modifier, so the result is unpredictable: `"$SHA:src/app.py"` is
   a bad substitution, `"$SHA:hooks/x"` reads `.ooks/x`. A silent miss looks
   exactly like "that path does not exist at that ref". The braced
   `"${SHA}:path"` is always right. Only code is scanned (heredoc bodies,
   comments and single-quoted text are skipped), and the `$VAR:` must sit in
   the same statement as the git verb.

2. word-split, only when the Bash tool's shell is zsh (`_shell_is_zsh`). A whole
   word that is exactly `$name` or `${name}` as a `for X in` item or a `set --`
   operand. zsh does not word-split an unquoted parameter, so `set -- $r` leaves
   `$1` holding the whole string and `for c in $CHECKS` runs once. Allowed:
   `${=name}`, `"$@"` and `$@`, quoted words, `$(...)` and backticks, literal
   lists, an array assigned in the same command (`v=(a b)`, `typeset -a v`,
   `read -A v`), zsh's own array parameters (`$path`), `setopt shwordsplit`, a
   `bash -c` / `sh -c` string, and a heredoc body.

Not covered: `arr=($v)`, `cmd $v`, `select`, `set $LINE` without `--`, positional
parameters such as `$1`, a bare `$v` after a `$(...)` in the same list, loops
inside backticks, a `zsh -c '...'` string, `emulate sh` (not read as turning
splitting on), text after a stray `<<` (the shared `strip_heredoc_bodies` cuts
there), and a failing detector (skipped with a stderr note only).

Bypass: ZSH_SILENT_IDIOMS_BYPASS=1, from the env or as an inline prefix; both are
honored, because a guard whose advertised inline bypass cannot fire lies.
"""
import json
import os
import re
import shutil
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
# Shared: blank the inside of quoted strings.
# ---------------------------------------------------------------------------


def _mask_quotes(code: str, kinds: str = "'\"") -> str:
    """`code` with the INSIDE of each quoted string blanked (same length), for the
    quote characters in `kinds`. The other kind is still tracked, never blanked.

    A pattern search over shell CODE must be neither satisfied nor disarmed by
    text that merely sits in a string: `echo "v=(a b)"` assigns no array, and
    nothing inside single quotes is expanded.
    """
    out = []
    quote = None
    i, n = 0, len(code)
    while i < n:
        c = code[i]
        if quote:
            blank = quote in kinds
            if c == "\\" and quote == '"' and i + 1 < n:
                out.append("  " if blank else code[i:i + 2])
                i += 2
                continue
            if c == quote:
                quote = None
                out.append(c)
            else:
                out.append(" " if blank else c)
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


# ---------------------------------------------------------------------------
# Detector 1: unbraced `$VAR:path` in a git object read (fires in any shell).
# ---------------------------------------------------------------------------

# A git read that resolves a <rev>:<path> object spec.
GIT_OBJECT_READ = re.compile(
    r"\bgit\b[^\n|;&]{0,200}?"
    r"\b(show|cat-file|grep|diff|log|archive|rev-parse|ls-tree)\b"
)
# `$VAR:` with NO braces, then a LETTER. zsh modifiers are letters, so `$PATH:/opt`,
# `$HOST:8080` and `$SHA:.gitignore` are plain text in every shell and never match.
UNBRACED_REF = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*):(?=[A-Za-z])")


def _git_statements(command: str) -> list:
    """The command's statements as shell CODE: heredoc bodies and comments gone,
    single-quoted text blanked (nothing in it is expanded), cut at every shell
    operator. A missing or failing shared parser falls back to the raw command,
    so this detector is never disarmed by a broken `_lib`."""
    try:
        from _lib.shell_parse import (
            split_segments_with_seps, strip_heredoc_bodies, strip_noncode)
        code = _mask_quotes(strip_noncode(strip_heredoc_bodies(command)), "'")
        return [seg for _sep, seg in split_segments_with_seps(code)]
    except Exception:
        return [command]


def detect_unbraced_git_ref(command: str, zsh: bool) -> list:
    """Detector 1. One deny block when a git object read carries `$VAR:path` in
    the SAME statement.

    `zsh` is unused on purpose: the braced fix is correct in every shell, so
    this detector never needs to know which one is running.
    """
    if "$" not in command or ":" not in command or "git" not in command:
        return []        # cheap exit: this runs on every Bash call
    first = None
    for stmt in _git_statements(command):
        m = UNBRACED_REF.search(stmt) if GIT_OBJECT_READ.search(stmt) else None
        if m:
            first = m.group(1)
            break
    if first is None:
        return []
    return [
        f"BLOCKED by {GUARD}: `${first}:` is unbraced in a git object read.\n\n"
        f"Under zsh, `$VAR:` followed by a letter can be read as a HISTORY MODIFIER, so the "
        f"unbraced form is unpredictable: it can fail outright or read an empty or "
        f"wrong path, and the braced form is always right. A silent miss looks "
        f"exactly like 'that path does not exist at that ref'.\n\n"
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
    for _sep, seg in split_segments_with_seps(code):
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
    """Is the Bash tool's shell zsh? Detector 2 means nothing anywhere else.

    Mirrors the order Claude Code uses to pick that shell: CLAUDE_CODE_SHELL when
    it names bash or zsh, else bash if SHELL names bash, else zsh when it is
    installed, else bash. $SHELL alone is not enough: an override or a fish login
    shell changes the answer.
    """
    forced = os.path.basename(os.environ.get("CLAUDE_CODE_SHELL", ""))
    if forced in ("bash", "zsh"):
        return forced == "zsh"
    if os.path.basename(os.environ.get("SHELL", "")) == "bash":
        return False
    return shutil.which("zsh") is not None


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


def main() -> None:
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
    # no legible cause. The deny text is ASCII today; this keeps it safe if an
    # edit ever adds a non-ASCII character. Idempotent; a no-op on UTF-8.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass
    main()
