#!/usr/bin/env python3
"""PreToolUse hook: block Bash commands that print environment VALUES.

Pattern this prevents: `env`, `printenv`, bare `export`/`set`, `declare -p`,
a `ps` invocation with an environment flag, `/proc/<pid>/environ`, or an
`echo $SECRET_VAR` put a live credential's VALUE into the session
transcript (~/.claude/projects/.../*.jsonl), where it persists and leaks
permanently -- a value in a transcript cannot be un-persisted. Unlike a
stdout scan (detect-secrets-in-bash-output.py, PostToolUse -- by the time it
runs, the value already landed), this runs PreToolUse and refuses the
command before it ever executes. Ticket MYC-4988.

Presence and length checks are NOT dumps and stay allowed: `[ -n
"${NAME:-}" ]`, `echo ${#NAME}`, `compgen -e` (names only), and `env | cut
-d= -f1` / `sed 's/=.*//'` / `awk -F= '{print $1}'` (the three extractors
that provably strip every value before anything downstream ever sees it).

Also folds in the REMOTE secret-dump vocabulary (heroku config, aws ssm
get-parameter, gcloud secrets versions access, vercel env pull, doppler
secrets download, fly secrets list, fly/flyctl ssh -C '...printenv/env...')
ported VERBATIM from the hookify rule `block-secret-dump-command-class`
(~/.claude/hookify.block-secret-dump-command-class.local.md) so one guard
owns the whole class instead of splitting it across a personal hookify rule
and a substrate hook.

Parses with hooks/_lib/shell_parse.py (quote-aware segments, heredoc-body
and comment-tail stripping) rather than a regex over the raw string -- the
lesson of MYC-4626: a naive regex reads a dangerous command out of a quoted
string, a comment, or a heredoc body and calls it code, or misses one
hidden behind a heredoc.

Bypass: ENV_DUMP_BYPASS=1 (inline `VAR=1 <cmd>` prefix or session env).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "_lib"))
try:
    from cmd_env import inline_bypass
except Exception:
    def inline_bypass(command, var, value="1"):  # type: ignore
        return False

try:
    from shell_parse import (
        ENV_ASSIGN_RE,
        WRAPPER_PREFIXES,
        split_segments_with_seps,
        strip_heredoc_bodies,
        strip_noncode,
        tokens,
    )
    _LIB_OK = True
except Exception:
    _LIB_OK = False

# Transparent wrappers to skip past when looking for the real command word.
# `env` is EXCLUDED on purpose: it is also one of the commands this hook
# inspects directly (a bare `env` dumps values; `env CMD` does not), so it
# must stay visible as the resolved word instead of being skipped over.
_SKIP_WRAPPERS = (WRAPPER_PREFIXES - {"env"}) if _LIB_OK else set()

# Shell keywords that precede a real command word without being one
# themselves: `if env; then` / `while env; do` run env as their condition,
# `do env; done` and `{ env; }` run it as their body, `! env` negates its
# exit status -- none of these change WHAT runs, only when/whether.
_SKIP_KEYWORDS = {"then", "do", "else", "elif", "if", "while", "until", "{", "!", "("}

# Substrings that mark a NAME as secret wherever they appear, even glued to
# other text with no "_" boundary (PGPASSWORD, DATABASE_URL is a separate
# suffix rule below since neither half is one of these words on its own).
_SECRET_NAME_SUBSTRINGS = ("PASSWORD", "PASSWD", "SECRET", "TOKEN", "APIKEY", "CREDENTIAL")

# Name components (NAME split on "_") that mark it secret only as a WHOLE
# component -- "KEY"/"PAT"/"DSN" as substrings alone would false-positive on
# ordinary words (PATCH, KEYCHAIN). Exempt when the LAST component reads as
# a path to the secret rather than the secret itself (SSH_KEY_PATH).
_SECRET_NAME_COMPONENTS = {"KEY", "PAT", "DSN"}
_PATH_LIKE_LAST_COMPONENT = {"PATH", "FILE", "DIR"}

# `${!NAME}` / `${!NAME*}` / `${!NAME@}` -- bash indirect expansion: NAME
# holds the NAME of another variable. `${!NAME}` expands to THAT variable's
# VALUE (the target is not statically knowable, so this counts unconditionally
# regardless of how NAME itself looks); `*`/`@` list matching variable NAMES
# only, never a value, and stay allowed.
_INDIRECT_VAR_RE = re.compile(r"\$\{!([A-Za-z_][A-Za-z0-9_]*)(\*|@)?\}")

# `${NAME<suffix>}`, NOT the length form `${#NAME}` (negative lookahead on
# `#`) and NOT indirect (negative lookahead on `!`, handled above). `suffix`
# is captured so the caller can exempt `:+x` / `+x` (substitutes a LITERAL
# alternate, never reveals NAME's real value) while still denying `:-` / `-`
# (expands to the real value whenever NAME is actually set) and substring
# extraction (`:0:8`).
_BRACE_VAR_RE = re.compile(r"\$\{(?!#)(?!!)([A-Za-z_][A-Za-z0-9_]*)([^}]*)\}")

# Bare `$NAME` (no braces, so no parameter-expansion suffix is possible).
_BARE_VAR_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")

# echo/printf piped into one of these still puts the value in the visible
# transcript (or reformats/greps it there); piped into anything else (a
# non-printer like `docker login --password-stdin`) is allowed.
_ECHO_PRINTERS = {
    "cat", "grep", "head", "tail", "sed", "awk", "cut", "tr", "sort",
    "uniq", "tee", "less", "xxd", "od", "base64", "jq",
}

# `env`'s own no-argument options. `-u NAME` is handled separately below (it
# consumes the following token too).
_ENV_OPT_NO_ARG = {"-i", "-0"}

# A redirect operator, with everything shlex glues to it in ONE token: shlex
# has no notion of `<`/`>` as shell metacharacters, so `env>out.txt`,
# `2>/dev/null` and `>>x` all survive tokenization as a single token apiece
# (verified against shlex.split directly). `prefix` is what came before the
# operator in the SAME token; `tail` is what came after (a filename, a dup-fd
# `&1`, or nothing when the target is a separate following token).
_REDIR_TOKEN_RE = re.compile(r"^(?P<prefix>[^><]*)(?P<op>&?(?:>>|<<|>|<))(?P<tail>.*)$")


def _is_redirect_fd_prefix(prefix: str) -> bool:
    """True when `prefix` is an fd number or empty -- part of the operator
    itself (`2>`), never a real command/argument word."""
    return prefix == "" or prefix.isdigit()


def _strip_redirect_tokens(toks: list) -> list:
    """Drop every redirect clause from an already-tokenized argument list:
    a bare operator plus its separate target token (`>` `/tmp/x`), and an
    attached form glued by shlex into one token (`2>/dev/null`, `>>x`). A
    non-fd word glued to the operator in an ARGUMENT position is kept (rare,
    but `_split_glued_redirect` below is the one that matters for the verb
    itself)."""
    out, i, n = [], 0, len(toks)
    while i < n:
        t = toks[i]
        if "<" not in t and ">" not in t:
            out.append(t)
            i += 1
            continue
        m = _REDIR_TOKEN_RE.match(t)
        prefix, tail = m.group("prefix"), m.group("tail")
        if prefix and not _is_redirect_fd_prefix(prefix):
            out.append(prefix)
        skip_next = not tail and i + 1 < n
        i += 2 if skip_next else 1
    return out


def _split_glued_redirect(word: str, rest: list) -> tuple:
    """As `_strip_redirect_tokens`, but for the CANDIDATE COMMAND WORD itself
    (`env>out.txt`, `export>file`): returns the real word (or "" when the
    token is entirely a redirect, e.g. a bare `>out.txt` in word position)
    plus `rest` with a separate target token consumed when the operator had
    nothing attached in the same token."""
    if "<" not in word and ">" not in word:
        return word, rest
    m = _REDIR_TOKEN_RE.match(word)
    prefix, tail = m.group("prefix"), m.group("tail")
    if not tail and rest:
        rest = rest[1:]
    return ("" if _is_redirect_fd_prefix(prefix) else prefix), rest

# /proc/<pid>/environ, /proc/self/environ, /proc/$$/environ, /proc/*/environ
# -- anywhere in UNQUOTED text (the caller masks quotes first, so a mention
# inside a commit message or grep pattern never matches).
_PROC_ENVIRON_RE = re.compile(r"/proc/[^/\s]+/environ")

# Remote secret-dump vocabulary, ported VERBATIM from the `pattern:` field of
# ~/.claude/hookify.block-secret-dump-command-class.local.md
# (rule: block-secret-dump-command-class) so one guard owns the whole class.
# Do NOT reword -- keep this byte-identical to the source hookify rule.
_REMOTE_DUMP_RE = re.compile(
    r"""(heroku\s+(config(\s|$)|config:get|releases:info|secrets|run\s+.*env(\s|$|\|)))|aws\s+ssm\s+get-parameter|gcloud\s+secrets\s+versions\s+access|vercel\s+env\s+pull|doppler\s+secrets\s+download|fly\s+secrets\s+list|(fly|flyctl)\s+ssh\s+.*-C\s+["'][^"']*(\bprintenv\b|\benv(\s|$|\|))"""
)

# Commands the remote vocabulary above is scoped to. Checked per-SEGMENT
# against the segment's own resolved command, not the whole command string --
# otherwise a commit message or PR body that merely MENTIONS "heroku config"
# or "vercel env pull" matches too.
_REMOTE_DUMP_COMMANDS = {"heroku", "aws", "gcloud", "vercel", "doppler", "fly", "flyctl"}


def _mask_quoted(text: str) -> str:
    """Blank out BOTH single- and double-quoted spans, leaving only text a
    shell would treat as unquoted/literal. Used so a whole-string pattern
    check (/proc/.../environ) matches a real path, never a mention of one
    inside a commit message, grep pattern, or PR body."""
    out, quote, i, n = [], None, 0, len(text)
    while i < n:
        c = text[i]
        if quote:
            if c == "\\" and quote == '"' and i + 1 < n:
                i += 2
                out.append("  ")
                continue
            if c == quote:
                quote = None
            out.append(" ")
            i += 1
            continue
        if c in ("'", '"'):
            quote = c
            out.append(" ")
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _bare_inline_bypass(command: str, var: str, value: str = "1") -> bool:
    """Like cmd_env.inline_bypass, but does not require the assignment to be
    followed by anything else.

    shell_parse.leading_env_assigns treats `env` (and every other transparent
    wrapper) as needing a real command AFTER it to "count" -- correct for its
    own callers, but this hook's whole subject is exactly the shape where
    `env` has nothing after it. `ENV_DUMP_BYPASS=1 env` is bare on purpose
    (that is the command being bypassed), so `leading_env_assigns` silently
    drops the assignment and the advertised inline bypass could never fire.
    This checks only ITS OWN var, at the front of each segment, with no such
    restriction.
    """
    if not _LIB_OK or not command:
        return False
    cleaned = strip_noncode(strip_heredoc_bodies(command))
    for _sep, seg in split_segments_with_seps(cleaned):
        for tok in tokens(seg.strip()):
            if not ENV_ASSIGN_RE.match(tok):
                break
            k, _, v = tok.partition("=")
            if k == var and v == value:
                return True
    return False


def _skip_leading(toks: list) -> int:
    """Index of the first token past leading `VAR=val` assigns and
    transparent wrappers (env excluded -- see _SKIP_WRAPPERS)."""
    i, n = 0, len(toks)
    while i < n:
        if (ENV_ASSIGN_RE.match(toks[i]) or toks[i] in _SKIP_WRAPPERS
                or toks[i] in _SKIP_KEYWORDS):
            i += 1
            continue
        break
    return i


def _env_is_bare_dump(rest: list) -> bool:
    """True iff `rest` (env's own argv, with redirects already stripped by
    the caller) leaves no command to run: env's inline `VAR=val` assigns and
    `-i` / `-0` / `-u NAME` consumed, and nothing left over."""
    i, n = 0, len(rest)
    while i < n:
        t = rest[i]
        if ENV_ASSIGN_RE.match(t) or t in _ENV_OPT_NO_ARG:
            i += 1
            continue
        if t == "-u" and i + 1 < n:
            i += 2
            continue
        break
    return i >= n


def _is_names_only_extractor(toks: list) -> bool:
    """True for the three pipeline stages that provably strip every value
    before anything downstream can see it: `cut -d= -f1`, `sed 's/=.*//'`,
    `awk -F= '{print $1}'` (spacing/quoting variants). A builder-style sed
    that keeps a value snippet (`s/^([^=]+)=(.{0,10}).*/...`) is NOT this --
    it must match the exact blessed script, not merely start with `s/`."""
    if not toks:
        return False
    cmd, rest = toks[0], toks[1:]
    joined = " ".join(rest)
    if cmd == "cut":
        return bool(re.search(r"-d\s*=", joined)) and bool(re.search(r"-f\s*1\b", joined))
    if cmd == "sed":
        return "s/=.*//" in rest
    if cmd == "awk":
        return bool(re.search(r"-F\s*=", joined)) and "{print $1}" in rest
    return False


def _names_secret_var(name: str) -> bool:
    """Only an ALL-UPPERCASE name counts (`$key` is exempt, `$KEY` is not).
    Secret if it contains a password/secret/token/apikey/credential SUBSTRING
    anywhere, ends in `DATABASE_URL`, or has a whole `_`-component equal to
    KEY/PAT/DSN -- unless its LAST component reads as a path to the secret
    (`_PATH`/`_FILE`/`_DIR`), not the secret's own value."""
    if not name or not name.isupper():
        return False
    if name.endswith("DATABASE_URL"):
        return True
    if any(s in name for s in _SECRET_NAME_SUBSTRINGS):
        return True
    parts = name.split("_")
    if parts[-1] in _PATH_LIKE_LAST_COMPONENT:
        return False
    return any(p in _SECRET_NAME_COMPONENTS for p in parts)


def _mask_single_quoted(text: str) -> str:
    """Blank out single-quoted SPANS: bash never expands anything inside
    '...', so a `$NAME` written there is literal text, not a real reference.
    Quote-aware: a "'" that lives inside a double-quoted span ("it's $X")
    has no special meaning and must not be misread as opening one."""
    out, quote, i, n = [], None, 0, len(text)
    while i < n:
        c = text[i]
        if quote == "'":
            out.append(" " if c != "'" else "'")
            if c == "'":
                quote = None
            i += 1
            continue
        if quote == '"':
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1]); i += 2; continue
            if c == '"':
                quote = None
            i += 1
            continue
        if c == "'":
            quote = "'"; out.append(" "); i += 1; continue
        if c == '"':
            quote = '"'; out.append(c); i += 1; continue
        if c == "\\" and i + 1 < n:
            out.append(c); out.append(text[i + 1]); i += 2; continue
        out.append(c); i += 1
    return "".join(out)


def _piped_into_printer(segs, idx) -> bool:
    """True iff the segment right after `segs[idx]` is piped-to AND resolves
    to one of `_ECHO_PRINTERS`. No next segment, a non-`|` separator, or a
    pipe into anything else (assumed a non-printer, e.g. `docker login
    --password-stdin`) -- all False, matching the "goes to the transcript"
    default of `_echo_reveals_secret` when there is nowhere else for it to go."""
    if segs is None or idx is None:
        return True  # no pipe context available: conservative default
    nxt = segs[idx + 1] if idx + 1 < len(segs) else None
    if not nxt or nxt[0] != "|":
        return True
    toks = tokens(nxt[1].strip())
    return bool(toks) and os.path.basename(toks[0]) in _ECHO_PRINTERS


def _echo_reveals_secret(seg_text: str, segs=None, idx=None) -> bool:
    scan = _mask_single_quoted(seg_text)

    for m in _INDIRECT_VAR_RE.finditer(scan):
        if not m.group(2):                 # ${!v} unconditional; ${!v*}/${!v@} list names only
            return _piped_into_printer(segs, idx)

    for m in _BRACE_VAR_RE.finditer(scan):
        suffix = m.group(2)
        if suffix.startswith(":+") or suffix.startswith("+"):
            continue                       # presence-substitution: never reveals the value
        if _names_secret_var(m.group(1)):
            return _piped_into_printer(segs, idx)

    for m in _BARE_VAR_RE.finditer(scan):
        if _names_secret_var(m.group(1)):
            return _piped_into_printer(segs, idx)

    return False


def _declare_denied(rest: list) -> bool:
    """`declare`/`typeset` with no operands, or any flag containing `p`."""
    flags = [t for t in rest if t.startswith("-") and t != "--"]
    operands = [t for t in rest if not t.startswith("-")]
    return (not operands) or any("p" in f for f in flags)


def _ps_denied(rest: list) -> bool:
    """A single-dash SHORT flag group containing uppercase E (macOS `ps
    -E`), or a BSD-style dashless FIRST argument containing lowercase e
    (`ps eww`, `ps auxe`). A double-dash long flag never counts, even when
    it happens to contain a capital E (`ps aux --sort=-%MEM`). `ps -e` and
    `ps -p 123 -o pid=` are explicitly fine."""
    if not rest:
        return False
    if any(t.startswith("-") and not t.startswith("--") and "E" in t for t in rest):
        return True
    first = rest[0]
    return not first.startswith("-") and "e" in first


def _deny_reason(command: str):
    """Short reason string if `command` should be denied, else None."""
    if not command or not command.strip():
        return None
    cleaned = strip_noncode(strip_heredoc_bodies(command)) if _LIB_OK else command

    if _PROC_ENVIRON_RE.search(_mask_quoted(cleaned)):
        return "reads /proc/<pid>/environ (the whole process environment)"
    if not _LIB_OK:
        return None  # degraded: only the two whole-string checks above ran

    segs = split_segments_with_seps(cleaned)
    for idx, (_sep, text) in enumerate(segs):
        toks = tokens(text.strip())
        if not toks:
            continue
        i = _skip_leading(toks)
        if i >= len(toks):
            continue
        word, rest = toks[i], toks[i + 1:]
        word, rest = _split_glued_redirect(word, rest)
        rest = _strip_redirect_tokens(rest)
        base = os.path.basename(word)

        if base in _REMOTE_DUMP_COMMANDS and _REMOTE_DUMP_RE.search(text):
            return "prints a remote secret/config-var store in plaintext"
        if base == "env":
            if not _env_is_bare_dump(rest):
                continue
            nxt = segs[idx + 1] if idx + 1 < len(segs) else None
            if nxt and nxt[0] == "|" and _is_names_only_extractor(tokens(nxt[1].strip())):
                continue  # provably strips every value before anyone sees it
            return "bare `env` prints every variable's value"
        if base == "printenv":
            return "`printenv` prints one or every variable's value"
        if base == "export":
            if not rest or rest == ["-p"]:
                return "bare `export`/`export -p` prints every exported variable's value"
            continue
        if base == "set":
            if not rest:
                return "bare `set` prints every shell variable and function body"
            continue
        if base in ("declare", "typeset"):
            if _declare_denied(rest):
                return f"`{base}` with no operands or a -p flag prints variable values"
            continue
        if base == "ps":
            if _ps_denied(rest):
                return "`ps` with an environment flag exposes process environ blocks"
            continue
        if base in ("echo", "printf"):
            if _echo_reveals_secret(text, segs, idx):
                return f"`{base}` expands a secret-shaped variable"
            continue
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # fail open: malformed stdin is not this hook's call to make

    tool = payload.get("tool_name") or payload.get("tool", "")
    if tool != "Bash":
        return 0

    cmd = (payload.get("tool_input") or {}).get("command", "")
    if not cmd:
        return 0

    if (os.environ.get("ENV_DUMP_BYPASS") == "1"
            or inline_bypass(cmd, "ENV_DUMP_BYPASS")
            or _bare_inline_bypass(cmd, "ENV_DUMP_BYPASS")):
        return 0

    try:
        reason = _deny_reason(cmd)
    except Exception:
        return 0  # fail open: a parsing bug must never crash-block a command

    if not reason:
        return 0

    print(
        "[block-env-dump] BLOCKED: " + reason + "\n"
        "Environment values here land in the session transcript permanently\n"
        "(a leaked secret cannot be un-persisted). Safe forms instead:\n"
        '  `[ -n "${NAME:-}" ] && echo set`,  `env | cut -d= -f1`,  `echo ${#NAME}`\n'
        "Bypass: ENV_DUMP_BYPASS=1",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
