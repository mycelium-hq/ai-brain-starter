"""shell_parse — quote-aware primitives for hooks that must reason about a
Bash command STRING before the shell runs it.

A PreToolUse(Bash) guard is handed one string and has to answer questions a
naive `re.split` cannot: which commands are actually in here, where would each
one run, and which of them carries the advertised bypass. Every hook that
hand-rolled that walk grew its own set of fail-opens, because all four of the
hard parts are invisible until they bite:

  - QUOTES. `echo "hi; cd /tmp" && git push` has ONE `cd`-looking token and it
    is inside a string. A splitter that ignores quotes forges a segment
    boundary there and reads a `cd` the shell never runs.
  - SEPARATORS. `cd X && cmd` runs cmd in X; `cd X || cmd` runs it in the OLD
    cwd, because the right side of `||` runs only when the left FAILED. A
    splitter that discards the operator cannot tell those apart, and every
    consumer read `cd /tmp || git push` as a push from /tmp.
  - HEREDOC BODIES. A heredoc body is data, never commands, but it is full of
    real operator characters. Truncating at the first `<<` instead (the older
    approach) threw away every command AFTER the heredoc, which is where the
    interesting one usually is.
  - `$VAR`. `W=/path; cd "$W" && git push` is the shape people actually write.
    Without expansion the target is the literal string `$W`, which resolves to
    no repo at all -- and a guard that reads "no repo" as "not my repo" fails
    open on precisely the command it exists to catch.

Shared primitive, per-caller policy: this module answers "what does the shell
see", never "should it be allowed". Callers keep their own scoping and
fail-open/fail-closed decisions, which differ by guard.
"""

from __future__ import annotations

import os
import re
import shlex

__all__ = [
    "ASSIGN_RE",
    "cwd_candidates",
    "ENV_ASSIGN_RE",
    "WRAPPER_PREFIXES",
    "expand_vars",
    "leading_env_assigns",
    "segment_bypass_flags",
    "split_segments_with_seps",
    "strip_heredoc_bodies",
    "strip_noncode",
    "tokens",
]

# Words that may sit in FRONT of a command without changing which program runs.
# `env` may additionally carry `VAR=VAL` arguments.
WRAPPER_PREFIXES = {"env", "command", "exec", "builtin", "nohup", "sudo", "time"}

ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")

_VAR_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")

# Strip body + closing delimiter; everything before `<<` (the actual command)
# is outside the match and survives.
_HEREDOC = re.compile(
    r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1[^\n]*\n"  # <<EOF + rest of line
    r".*?"                                                # body (non-greedy)
    r"\n[ \t]*\2[ \t]*(?=\n|$)",                          # closing delimiter line
    re.DOTALL,
)
# A herestring (`<<<`) is NOT a heredoc: no body, no closing delimiter. The
# distinction matters below, where a LEFTOVER `<<` means "unterminated heredoc,
# be conservative" -- treating `<<<` as unterminated would needlessly discard
# every command after a herestring.
_HEREDOC_OPEN = re.compile(r"(?<!<)<<(?!<)")


def expand_vars(value, variables):
    """Expand `$VAR` / `${VAR}` from assignments seen EARLIER in the same command.

    Only literal, already-seen assignments are expanded. An unknown name or a
    command substitution (`$(...)`, backticks) is left INTACT on purpose, so the
    caller can still SEE a `$` and know the target is unresolved rather than
    silently receiving a wrong path. That distinction is the whole value: a
    guard can then treat "unresolved" as ambiguous instead of as "not mine".
    """
    if not value or "$" not in value:
        return value
    out = value
    for _ in range(5):  # bounded: resolves VAR=$OTHER chains, never loops forever
        nxt = _VAR_REF.sub(
            lambda m: variables.get(m.group(1) or m.group(2), m.group(0)), out)
        if nxt == out:
            break
        out = nxt
    return out


_SHLEX_MAX_CHARS = 16384

_WHITESPACE = " \t\r\n"          # shlex default `whitespace`
_QUOTES = "'\""                  # shlex default `quotes`; only '"' is `escapedquotes`


def _scan_tokens(seg):
    """Linear-time reproduction of `shlex.split(seg)` for the FIXED config
    `shlex.split` actually uses: POSIX mode, `whitespace_split=True`, no
    comments, no `punctuation_chars`. `tokens()` below only reaches this for
    a segment longer than `_SHLEX_MAX_CHARS`; every ordinary command still
    goes through the real `shlex.split`.

    WHY THIS EXISTS. CPython's `shlex.read_token` (see its source for the
    reference state machine this ports) builds each token with
    `self.token += nextchar` where `self.token` is an INSTANCE ATTRIBUTE.
    Every `+=` first LOADs that attribute onto the interpreter stack, so its
    refcount is never 1 at the point of the append -- which disqualifies
    CPython's in-place string-resize fast path and forces a full copy of the
    token-so-far on every single character. Cost grows with the SQUARE of one
    token's length, not the length of the command. Measured CPU time of one
    `tokens("echo " + "a"*N)` call: N=50k 0.03s, 100k 0.14s, 200k 0.41s, 400k
    1.43s -- and this runs inside several PreToolUse Bash hooks, on EVERY Bash
    command, so one huge inline argument (a long diff, a base64 blob, a big
    heredoc-free literal) stalls every Bash call in the session.

    The fix is the same algorithm with the token built in a LIST and joined
    once (`"".join(parts)`) instead of appended to a string attribute one
    character at a time -- linear in the segment length, not the token
    length. This function must keep matching `shlex.split` byte-for-byte
    (including which inputs raise `ValueError`, and with the exact same
    message text is NOT required, only the exact same token stream or the
    exact same raise/no-raise split) -- see hooks/test_shell_parse_tokens.py
    for the equivalence fuzz that pins this down. If shlex's own read_token
    ever changes, port the change here too.

    Escaping rules mirrored from read_token, for this config only:
      - Outside quotes, `\\` makes the NEXT character literal (including a
        quote char, `;`, `|`, `$`, whitespace, or another `\\`) and is itself
        dropped.
      - Inside `"..."` (the only `escapedquotes` entry), `\\` escapes only
        `"` and `\\` itself; before any other character the backslash is KEPT
        literally alongside that character.
      - Inside `'...'`, `\\` has no special meaning at all -- it is just
        another literal character.
      - A quote closes on the next matching quote char; adjacent quoted and
        unquoted pieces concatenate into ONE token (`a"b c"d` -> `ab cd`).
      - `''` (or `""`) with nothing else on the segment yields one EMPTY
        token, because `quoted` -- not the token buffer -- decides whether an
        empty result still counts as a token.
      - A `\\` with nothing after it (segment ends right there), or a quote
        that never closes, is what `shlex.split` raises `ValueError` on;
        `_scan_tokens` raises the same so `tokens()`'s existing fallback to
        `seg.split()` still fires either way.
    """
    out = []
    parts = []
    quoted = False
    state = "ws"          # "ws" (between tokens) | "word" | "'" | '"' | "esc"
    escapedstate = "word"  # state to RETURN to once the escaped char is consumed
    n = len(seg)
    i = 0
    while i <= n:                      # one extra pass with c=None models EOF
        c = seg[i] if i < n else None
        i += 1

        if state == "ws":
            if c is None:
                break
            elif c in _WHITESPACE:
                pass                    # skip run of whitespace between tokens
            elif c == "\\":
                escapedstate = "word"
                state = "esc"
            elif c in _QUOTES:
                state = c
            else:
                parts.append(c)
                state = "word"

        elif state in _QUOTES:
            quoted = True
            if c is None:
                raise ValueError("No closing quotation")
            if c == state:
                state = "word"          # closing quote consumed, not appended
            elif c == "\\" and state == '"':
                escapedstate = state
                state = "esc"
            else:
                parts.append(c)         # includes a literal `\` inside '...'

        elif state == "esc":
            if c is None:
                raise ValueError("No escaped character")
            # Inside quotes, only the quote char or `\` itself may be
            # escaped; anything else keeps the backslash AND the character.
            if escapedstate in _QUOTES and c != "\\" and c != escapedstate:
                parts.append("\\")
            parts.append(c)
            state = escapedstate

        else:  # state == "word"
            if c is None:
                break
            elif c in _WHITESPACE:
                state = "ws"
                if parts or quoted:
                    out.append("".join(parts))
                    parts = []
                    quoted = False
                continue                # don't fall through to the shared flush below
            elif c in _QUOTES:
                state = c               # quote glues onto the same token
            elif c == "\\":
                escapedstate = "word"
                state = "esc"
            else:
                parts.append(c)

    if parts or quoted:
        out.append("".join(parts))
    return out


def tokens(seg):
    """shlex tokens for one segment, falling back to a whitespace split when the
    segment is not lexable on its own (an unbalanced quote from slicing).

    Delegates to the real `shlex.split` for anything up to `_SHLEX_MAX_CHARS`,
    so every normal command tokenizes byte-identically to before this
    threshold existed. Only a segment LONGER than that -- which means one
    huge token, since ordinary command lines are nowhere near 16KB -- takes
    the linear-time `_scan_tokens` path. See `_scan_tokens` for why: without
    it, one long inline argument makes shlex's own per-character string-attr
    concatenation cost grow with the SQUARE of that argument's length, and
    this runs inside PreToolUse Bash hooks on every Bash command.
    """
    try:
        if len(seg) <= _SHLEX_MAX_CHARS:
            return shlex.split(seg)
        return _scan_tokens(seg)
    except ValueError:
        return seg.split()


def strip_heredoc_bodies(command):
    """Remove heredoc BODIES (data, never commands) while KEEPING the commands
    that follow the closing delimiter.

    Replaces the older "truncate at the first `<<`" approach. Truncating threw
    away everything after the heredoc, so the dominant shape

        cat > notes.md <<'BODY'
        ...body...
        BODY
        cd some/repo
        git push

    hid BOTH the `cd` and the push from every parser that truncated. Writing
    body text to a FILE first is the recommended shape, so this is the common
    case, not an exotic one.

    Unterminated heredoc (an opener with no closing delimiter line) -> fall back
    to truncating at that opener, so an unmatched body can never be misread as
    commands. Strictly safer than either extreme.
    """
    if not command:
        return command
    stripped = _HEREDOC.sub("", command)
    m = _HEREDOC_OPEN.search(stripped)
    if m:                       # unterminated heredoc -> conservative truncation
        stripped = stripped[:m.start()]
    return stripped


def strip_noncode(command):
    """Reduce a command to the text a shell would actually parse as code: drop
    `#`-to-end-of-line comments outside quotes.

    A comment tail is TEXT THE SHELL NEVER RUNS, but the operators inside it are
    still real characters, so a splitter walks straight through them: in
    `git push # note ; cd /elsewhere` the `;` creates a segment boundary and
    ` cd /elsewhere` reads as a genuine `cd`. Stripping cuts BOTH ways -- it
    stops a phantom `cd` from moving a guard off its target (a fail-open), and
    stops one from dragging an unrelated target ON to it (a false block).

    Line continuations are NOT handled here: split_segments_with_seps deletes
    `\\`+newline for every consumer, so doing it again would be a second place
    to keep correct.

    Quote-aware, because the symmetric bug is over-stripping: `-m "issue #42"`
    and `-m "fix: a # b"` must survive untouched.
    """
    out, quote, i, n = [], None, 0, len(command)
    while i < n:
        c = command[i]
        if quote:
            out.append(c)
            if c == "\\" and quote == '"' and i + 1 < n:
                out.append(command[i + 1]); i += 2; continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ("'", '"'):
            quote = c; out.append(c); i += 1; continue
        if c == "\\" and i + 1 < n:
            out.append(c); out.append(command[i + 1]); i += 2; continue
        if c == "#" and (not out or out[-1].isspace()):
            while i < n and command[i] != "\n":     # to end of LINE, not of string
                i += 1
            continue
        out.append(c); i += 1
    return "".join(out)


def split_segments_with_seps(command):
    """Split a command on shell operators that are OUTSIDE quotes, reporting the
    operator BETWEEN each adjacent pair.

    Returns `[(sep_before, text), ...]`; `sep_before` is `""` for the first
    segment and otherwise the exact operator that separated it from the
    previous one: `&&`, `||`, `|`, `;`, `&`, a newline, `(` or `)`.

    WHY the separator is load-bearing: a `cd` does NOT unconditionally take
    effect for whatever follows it, and a splitter that throws the operator away
    cannot tell the cases apart:

        cd X && cmd    -> cmd runs in X           (cd succeeded)
        cd X || cmd    -> cmd runs in the OLD cwd (right side runs only on FAILURE)
        cd X |  cmd    -> cmd runs in the OLD cwd (subshell)
        cd X &  cmd    -> cmd runs in the OLD cwd (the cd was backgrounded)
        ( cd X ) cmd   -> cmd runs in the OLD cwd (subshell scope)
        cd X ;  cmd    -> AMBIGUOUS: X if the cd succeeded, the OLD cwd if not

    LINE CONTINUATIONS are DELETED here, outside single quotes, because a shell
    deletes `\\`+newline before any other parsing: `git \\<newline>push` IS
    `git push`. Keeping the backslash left a non-whitespace byte between a verb
    and its argument, so a consumer's `verb\\s+arg` pattern silently stopped
    matching a command that had merely been wrapped at 80 columns. Consequence
    to know: the segments no longer reconstruct the input BYTE-for-byte -- they
    reconstruct what a shell would run.
    """
    segs, cur, sep = [], [], ""
    i, n, quote = 0, len(command), None
    while i < n:
        c = command[i]
        if quote:                      # inside a quote: copy verbatim to the close
            if c == "\\" and quote == '"' and i + 1 < n and command[i + 1] == "\n":
                i += 2; continue           # line continuation: deleted, even in " "
            cur.append(c)
            if c == "\\" and quote == '"' and i + 1 < n and command[i + 1] in '"\\$`':
                cur.append(command[i + 1]); i += 2; continue   # \" \\ \$ \` in " "
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ("'", '"'):
            quote = c; cur.append(c); i += 1; continue
        if c == "\\" and i + 1 < n:     # escaped operator outside quotes -> literal
            if command[i + 1] == "\n":
                i += 2; continue           # LINE CONTINUATION -> delete both
            cur.append(c); cur.append(command[i + 1]); i += 2; continue
        two = command[i:i + 2]
        if two in ("&&", "||"):
            segs.append((sep, "".join(cur))); cur = []; sep = two; i += 2; continue
        if c in ("|", ";", "\n", "&", "(", ")"):
            segs.append((sep, "".join(cur))); cur = []; sep = c; i += 1; continue
        cur.append(c); i += 1
    segs.append((sep, "".join(cur)))
    return segs


def leading_env_assigns(command):
    """Dict of `VAR=value` assignments that PREFIX a real command in `command`.

    `FOO=1 BAR=2 git push`           -> {'FOO': '1', 'BAR': '2'}
    `export FOO=1; git push`         -> {'FOO': '1'}   (exported: reaches later)
    `git push ; FOO=1`               -> {}             (bare: prefixes nothing)
    `git status && BSB=1 git switch` -> {'BSB': '1'}   (union across segments)
    `echo 'FOO=1 git push'`          -> {}             (quoted, not a real assign)

    An inline `VAR=1 <cmd>` prefix lives ONLY in the command STRING and never
    reaches the hook process's `os.environ`. A gate that advertises an inline
    bypass must therefore read the token from HERE, not from os.environ alone,
    or the bypass printed in its own block message can never fire -- which
    trains people to channel-switch around the gate instead.

    Skips transparent wrappers the way a shell does. Empty dict when none or
    unparseable. Heredoc (`<<` anywhere): only line 1 up to the first `<<` is
    parsed, so a heredoc BODY line that merely looks like `X=1 cmd` can never
    be counted.
    """
    if not command or "=" not in command:
        return {}
    if "<<" in command:
        command = command.split("\n", 1)[0].split("<<", 1)[0]
    assigns = {}
    for _sep, seg in split_segments_with_seps(command):
        seg = seg.strip()
        if not seg:
            continue
        toks = tokens(seg)
        if not toks:
            continue
        exported = toks[0] == "export"
        i = 1 if exported else 0
        here = {}
        while i < len(toks) and (ENV_ASSIGN_RE.match(toks[i])
                                 or toks[i] in WRAPPER_PREFIXES):
            if ENV_ASSIGN_RE.match(toks[i]):
                k, _, v = toks[i].partition("=")
                here[k] = v
            i += 1
        # These must PREFIX A REAL COMMAND. A bare trailing `VAR=1` sets only a
        # SHELL variable -- unexported, so it never reaches any child process's
        # environment and cannot be a bypass for one. Counting it meant
        # `<gated cmd> ; GATE_BYPASS=1` silently disarmed a gate for a command
        # that had ALREADY RUN. `export VAR=1` DOES reach later commands.
        if here and (exported or i < len(toks)):
            assigns.update(here)
    return assigns


def segment_bypass_flags(segments, var, value="1"):
    """Per-segment bypass truth for an ALREADY-SPLIT command: `[bool, ...]`,
    aligned to `segments`.

    `leading_env_assigns` unions across the whole line, which cannot answer the
    question a gate actually has -- "is the bypass on the command I am about to
    block?" -- so a real assignment ANYWHERE disarmed every rule, including one
    on an unrelated command (`git push && BYPASS=1 echo hi`).

    The caller passes its OWN segments because each gate sanitizes differently
    (heredoc bodies, comment tails). A bare `VAR=1` segment does not carry to
    later commands; an `export` does, and is honoured from that point on.
    """
    flags, exported = [], False
    for seg in segments:
        here = exported or leading_env_assigns(seg).get(var) == value
        toks = tokens(seg.strip())
        if toks and toks[0] == "export" and f"{var}={value}" in toks:
            exported = True
            here = True
        flags.append(here)
    return flags


_GLOB_CHARS = set("*?[")


def _cd_operand(rest):
    """The single directory operand of a `cd`, or None when unresolvable.

    None means "this cd may have gone somewhere I cannot name", which callers
    must treat as AMBIGUOUS (keep the previous cwd in play), never as "no cd
    happened". `cd -` (OLDPWD, which this process cannot know) and a
    multi-operand `cd` land here on purpose -- resolving `cd -` to HOME by
    discarding the "-" as a flag is a fail-open dressed as a confident answer.
    """
    if "-" in rest[1:]:
        return None
    operands = [t for t in rest[1:] if not t.startswith("-")]
    if not operands:
        return os.path.expanduser("~")          # bare `cd` -> HOME
    if len(operands) > 1:
        return None
    return operands[0]


def cwd_candidates(segs, base):
    """Every cwd a command could run in, plus the literal `VAR=` assignments.

    Returns ``(set_of_cwds, variables)``. A guard blocks when ANY member is a
    directory it protects.

    FAIL-CLOSED BY CONSTRUCTION, and that is the whole point. A single
    "effective cwd" forces a guess at each ambiguity, and every wrong guess in
    the walks this replaces pointed the same way -- off the protected tree, i.e.
    open. Measured shapes that a single-guess walk let through:

        W=<protected>; cd "$W" && git push   -- `$W` never expanded
        echo "hi; cd /tmp" && git push       -- `cd` cut out of a QUOTED string
        cd /tmp || git push                  -- `||` treated as unconditional

    Ambiguity UNIONS instead of overwriting, so the protected path stays in the
    set and the block stands. The cost is a possible over-block on a genuinely
    ambiguous command, which is loud and bypassable; the old cost was a silent
    allow on the exact command the guard exists to stop.

    This also subsumes the "ignore a `cd` whose target does not exist" clause
    some callers carried: unioning cannot move the set OFF the protected tree,
    so a bogus `cd` can no longer disarm a guard that fails open on an
    unresolvable repo.

    `segs` is the output of split_segments_with_seps on ALREADY-SANITIZED text
    (heredoc bodies and comment tails stripped) -- both carry operators that
    would otherwise forge segment boundaries.
    """
    base = os.path.expanduser(base) if base else ""
    cur = {base} if base else set()
    variables = {}

    depth = 0
    for idx, (sep, seg) in enumerate(segs):
        # `(` and `)` arrive as separators, so paren depth is a running count --
        # and it covers BOTH `( cd X ; ... )` and `$( cd X && ... )`, because a
        # command substitution opens the same paren. A cd below the top level
        # changes only the SUBSHELL's cwd and is invisible to the parent.
        # Tracking only the separator IMMEDIATELY after the cd was not enough:
        # in `(cd /tmp; true) && git push` the cd is followed by `;`, so it
        # looked top-level and escaped its own subshell.
        # A brace group is deliberately NOT counted: `{ cd X; }` runs in the
        # CURRENT shell and its cd really does move the caller.
        if sep == "(":
            depth += 1
        elif sep == ")":
            depth = max(0, depth - 1)
        if depth > 0:
            continue
        toks = tokens(seg.strip())
        if not toks:
            continue
        k = 1 if toks[0] == "export" else 0
        while k < len(toks) and ASSIGN_RE.match(toks[k]):
            name, _, val = toks[k].partition("=")
            variables[name] = expand_vars(val, variables)
            k += 1
        while k < len(toks) and toks[k] in WRAPPER_PREFIXES:
            k += 1
        rest = toks[k:]
        if not rest or rest[0] != "cd":
            continue

        raw = _cd_operand(rest)
        target = expand_vars(raw, variables) if raw else None
        # An unexpanded `$`, a command substitution or a glob is a target that
        # cannot be named -- treat as unresolved rather than resolving it wrongly.
        if target and ("$" in target or set(target) & _GLOB_CHARS):
            target = None

        if target is None:
            moved = set()                      # unknown destination
        else:
            t = os.path.expanduser(target)
            moved = ({t} if os.path.isabs(t)
                     else {os.path.normpath(os.path.join(b, t)) for b in (cur or {""})})

        # The operator JOINING this cd to what follows decides whether the cd is
        # in effect for it. See split_segments_with_seps for the full table.
        nxt = segs[idx + 1][0] if idx + 1 < len(segs) else ""
        if not moved:
            continue                           # destination unknown -> keep old cwd
        if nxt == "&&":
            # The right-hand side runs IF AND ONLY IF the cd succeeded, so where
            # it runs is not in doubt. No existence check: an earlier segment may
            # legitimately create the directory (`git worktree add W && cd W`).
            cur = moved
        elif nxt in (";", "\n", ""):
            # `cd X ; cmd` runs cmd in X when the cd succeeds and in the OLD cwd
            # when it fails. That is DECIDABLE, not a coin flip: a cd fails when
            # the target is not a directory. Deciding it matters -- unioning
            # unconditionally would keep the protected path in the set for the
            # everyday `cd /repo` + newline + command shape and false-block every
            # one of them, which is precisely what teaches the bypass.
            if all(os.path.isdir(m) for m in moved):
                cur = moved
            else:
                cur = cur | {m for m in moved if os.path.isdir(m)}
        # "||", "|", "&", "(", ")" -> the next command runs in the OLD cwd.
    return cur, variables
