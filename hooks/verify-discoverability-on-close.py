#!/usr/bin/env python3
"""Stop hook: blocks session close if any artifact THIS SESSION authored
lacks a same-session discoverability companion.

Per the same-session discoverability-enforcement rule (codified 2026-05-13
after the gbrain-build wiring gap).

Bug class blocked: ARTIFACT-WITHOUT-DISCOVERABILITY.

Mechanism:
1. Detect closing-claim in the model's last assistant message (the shared
   MENTION-vs-USE-aware detector in _lib/closing_claim.py — the same one the
   session-close-cascade hook uses, so both Stop hooks fire on one surface).
2. If closing claim detected, run discoverability-verifier.py --json on
   the last 24h of commits + recently-modified Agent Memory audit memos.
3. Partition the verifier's gap list into:
     - SESSION-AUTHORED: the gap's artifact file was written/edited by THIS
       session's transcript (Write/Edit/MultiEdit file_path, or a Bash command
       naming the file). These are OUR gaps — HARD-BLOCK the close.
     - SIBLING / PRE-EXISTING: the artifact was not touched by this session.
       In a many-concurrent-session workflow these belong to a sibling session
       (or predate this session). Emit a SOFT informational note only — never
       block. The closing session cannot fix another session's audit memo
       without fabricating cherry-pick analysis for repos it never audited
       (a zero-hallucination violation), so blocking on them only teaches the
       bypass env var, which then masks THIS session's real gaps
       (the over-strict-verification-teaches-bypass failure mode).

Scoping signal: the session transcript (`transcript_path` on stdin) is a JSONL
of this session's tool calls. The set of file paths this session wrote is the
authority for "ours". An artifact flagged by the verifier that does NOT appear
as a write target in this transcript = not-ours = soft note only.

MYC-766 (2026-06-10): before this change the hook hard-blocked on ANY gap the
verifier returned, including sibling sessions' incomplete audit memos surfaced
by the verifier's mtime-based Agent-Memory scan. That false-blocked unrelated
sessions' closes.

VAULT_ROOT: resolved from the VAULT_ROOT env var (default ~/vault), so the hook
is portable across installs — the deploying vault supplies its own root (e.g.
via the Claude settings `env` block). MYC-1270 (cross-repo de-dup: one canonical
copy, the consumer vendors it byte-identical).

Fail-open: a crash in this non-blocking nudge must never crash-block a close.
Any exception → exit 0.

Bypass: DISCOVERABILITY_VERIFIER_BYPASS=1.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# MYC-791: close-claim detection lives in the shared, de-drifted detector
# (_lib/closing_claim.py), MENTION-vs-USE aware — a sign-off QUOTED as an
# example or DISCUSSED as meta is not a close claim.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from _lib.closing_claim import is_closing_claim  # noqa: E402
except Exception:  # fail-open: if the lib cannot load, never block a close
    def is_closing_claim(_text: str) -> bool:  # type: ignore
        return False

# Shared vault-root resolver - single source of truth (_lib/vault_root.py).
# Repo-aware, mirroring detect-closing-signal.py and
# verify-session-close-cascade.py: a session working inside its own
# vault-shaped repo resolves gaps against that repo, not an unrelated
# global VAULT_ROOT default (which would otherwise scan a DIFFERENT vault's
# git history / Agent Memory for "did this session wire discoverability" —
# a scope leak as well as a correctness bug).
try:
    from _lib.vault_root import resolve_vault_root  # noqa: E402
except Exception:  # fail-open: if the lib cannot load, fall back to env/home
    def resolve_vault_root(cwd: Path, env_vault_root: str | None) -> Path:  # type: ignore
        return Path(env_vault_root) if env_vault_root else (cwd or Path.home() / "vault")

# MYC-5434: the verifier is a vault script this hook does not ship. It runs under
# the python3 a plain shell would pick, never under a session's PATH shim (which
# refuses `python3 <script>`, so the hook saw no gaps) and never under this hook's
# own interpreter (which can be too old for it). See _lib/script_python.py.
try:
    from _lib.script_python import script_python  # noqa: E402
except Exception:  # fail-open: the pre-MYC-5434 PATH lookup, so a missing lib changes nothing
    def script_python() -> str:  # type: ignore
        return "python3"

DEV_ROOT = Path.home() / "dev"

# Import-time placeholders so the module stays importable without a hook
# payload. main() calls _resolve_vault_context(cwd) right after confirming
# there's a closing claim worth acting on, rebinding these to the SAME
# repo-aware vault detect-closing-signal.py resolved for this session.
#
# MYC-3529: these used to be seeded from a naive
# `os.environ.get("VAULT_ROOT", str(Path.home() / "vault"))`. The seed was
# always overwritten before use, but it is the exact #375/#404 shape and it
# made the module's import-time answer wrong for every vault not literally
# named "vault" — including for anything that imports this module without
# calling main(). They are now seeded through the SAME sanctioned resolver
# the rebind uses, so the import-time answer and the per-invocation answer
# can never disagree by construction.
#
# Test seam, preserved: DISCOVERABILITY_VERIFIER_PATH overrides the verifier
# the hook shells out to, so tests can inject a deterministic stub verifier and
# stay independent of the live (concurrent-session) Agent Memory state. Unset
# in production → the canonical vault verifier is used (no behavior change).
VAULT_ROOT: Path
MEMORY_ROOT: Path
VERIFIER: Path


def _resolve_vault_context(cwd: str) -> None:
    """Recompute VAULT_ROOT/MEMORY_ROOT/VERIFIER for THIS invocation's cwd,
    repo-aware. DISCOVERABILITY_VERIFIER_PATH still wins outright when set
    (test seam, unchanged). Every helper below reads these as module
    globals, so rebinding here (called once, early in main()) is enough to
    put the whole hook in lockstep with the cwd it was invoked with.
    """
    global VAULT_ROOT, MEMORY_ROOT, VERIFIER
    VAULT_ROOT = resolve_vault_root(Path(cwd) if cwd else Path.cwd(), os.environ.get("VAULT_ROOT"))
    MEMORY_ROOT = VAULT_ROOT / "⚙️ Meta" / "Agent Memory"
    VERIFIER = Path(
        os.environ.get(
            "DISCOVERABILITY_VERIFIER_PATH",
            str(VAULT_ROOT / "⚙️ Meta" / "scripts" / "discoverability-verifier.py"),
        )
    )


# Seed the module globals declared above. Going through _resolve_vault_context
# rather than repeating the expression is the point: one resolution path, so an
# import-time read can never drift from the per-invocation rebind.
_resolve_vault_context("")

# Tool calls that author/modify a file by an explicit file_path argument.
# These are the primary "this session wrote X" signal.
FILE_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

# A Bash command joins the "ours" fallback blob only for what it actually WRITES.
# A pure read that merely NAMES an artifact — `git log -- discovery_foo_audited.md`,
# `rg foo MEMORY.md`, `cat sibling.md` — must NOT mark that artifact as ours;
# doing so re-introduces the exact false-block MYC-766 fixes.
#
# The command is read structurally, because one regex over the whole text was
# wrong both ways (MYC-5434 review, measured):
#   - a bare `<<` hint counted EVERY heredoc, so a `python3 - <<PY` that only read
#     a sibling's memo hard-blocked the close on that sibling's gap (measured live:
#     a memo 16h older than the session, never edited by it);
#   - dropping `<<` lost real heredoc writes (`cat >memo.md <<EOF`,
#     `cat <<EOF >"$V/memo.md"`, json.dump / write_bytes / writelines / shutil.copy
#     in a heredoc'd script, `git apply <<EOF`), and a `>` in a script body
#     (`if len(l) > 80:`) or a `sys.stdout.write(` still read as a write.
# So the command is split into its own lines and the heredoc bodies they open, each
# body kept with the line that opens it. What counts as a write:
#   - a redirect or tee TARGET on the command's own lines. A target that cannot be
#     pinned down (a $variable, a backtick) counts the whole command, which is
#     usually where the variable is set (`F=...; cat > "$F" <<EOF`, a for-list);
#   - a line of the command, or a heredoc'd script, that calls a file-writing API.
#     Writing to stdout or stderr is printing, not authoring. A writing script also
#     brings its opener line, which can carry the target (`python3 - "$p" <<PY`);
#   - a heredoc fed to a shell (`bash <<EOF`), read again as shell commands;
#   - a heredoc fed to `git apply` / `patch`, as the files it changes (not a dry run).
# Only that text is matched against an artifact's name. Still not seen: cp, mv,
# sed -i and other commands that write without a redirect (FILE_WRITE_TOOLS covers
# the sessions that author files the usual way), and a multi-line `python3 -c`
# whose path and write call sit on different lines. A script that reads one file
# and writes another counts as naming both. Bug class:
# READ-CLASSIFIED-AS-AUTHORSHIP (family: MYC-766 false-block).

# A heredoc opener and its delimiter word, quoted or not. A here-string (<<<) is not one.
_HEREDOC_START = re.compile(r"(?<!<)<<(?!<)-?\s*([\"']?)([A-Za-z_][\w.-]*)\1")
# A redirect that writes: >, >>, N>, &>, with or without a space before the target.
# Not an fd duplication (>&2, 2>&1).
_REDIRECT = re.compile(r"(?:^|[^<>&\d])(?:\d*|&)>>?(?!&)\s*(\"[^\"\n]*\"|'[^'\n]*'|[^\s;|&<>()]+)")
_TEE = re.compile(r"\btee\b((?:[ \t]+(?:\"[^\"\n]*\"|'[^'\n]*'|[^\s;|&<>()]+))+)")
_UNPINNED = re.compile(r"[$`]")
# Script text that writes a file. Writing to stdout or stderr is printing, not authoring.
_CODE_WRITE = re.compile(
    r"write_text\s*\(|write_bytes\s*\(|\.writelines\s*\("
    r"|(?<!stdout)(?<!stderr)(?<!stdout\.buffer)(?<!stderr\.buffer)\.write\s*\("
    r"|\.(?:safe_)?dump\s*\(|shutil\.(?:copy\w*|move)\s*\(|os\.(?:replace|rename)\s*\("
    r"|\bprint\s*\(.*\bfile\s*=(?!\s*sys\.(?:stdout|stderr)\b)"
    r"|\bopen\s*\(.*,\s*(?:mode\s*=\s*)?[\"'][wax]"
)
# A heredoc fed to a shell is shell commands.
_SHELL_FEEDER = re.compile(r"\b(?:bash|sh|zsh|dash|ksh)\b[^;&|\n]*<<")
# A heredoc fed to one of these names the files it changes, unless it is a dry run.
_PATCH_FEEDER = re.compile(
    r"\bgit\s+apply\b(?![^\n]*\s--(?:check|stat|numstat|summary)\b)"
    r"|\bpatch\b(?![^\n]*\s--dry-run\b)"
)


def _split_heredocs(cmd: str) -> tuple[str, list[tuple[str, str]]]:
    """(the command's own lines, [(opener line, heredoc body), ...]), as bash reads them."""
    lines = cmd.split("\n")
    shell: list[str] = []
    bodies: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        shell.append(line)
        i += 1
        for m in _HEREDOC_START.finditer(line):
            delim = m.group(2)
            body: list[str] = []
            while i < len(lines) and lines[i].strip() != delim:
                body.append(lines[i])
                i += 1
            i += 1  # the delimiter line
            bodies.append((line, "\n".join(body)))
    return "\n".join(shell), bodies


def _bash_writes(cmd: str, depth: int = 0) -> str:
    """The text of what this Bash command WRITES, to match artifact names against.
    Empty when the command only reads. See the comment above _HEREDOC_START."""
    shell, bodies = _split_heredocs(cmd)
    parts: list[str] = []
    unpinned = False
    for m in _REDIRECT.finditer(shell):
        target = m.group(1).strip("\"'")
        if target and target != "/dev/null":
            parts.append(target)
            unpinned = unpinned or bool(_UNPINNED.search(target))
    for m in _TEE.finditer(shell):
        parts.append(m.group(1))
        unpinned = unpinned or bool(_UNPINNED.search(m.group(1)))
    if unpinned:
        parts.append(shell)
    parts += [line for line in shell.split("\n") if _CODE_WRITE.search(line)]
    for opener, body in bodies:
        if depth < 3 and _SHELL_FEEDER.search(opener):
            parts.append(_bash_writes(body, depth + 1))
        elif _PATCH_FEEDER.search(opener):
            parts.append(body)
        elif _CODE_WRITE.search(body):
            parts += [opener, body]
    return "\n".join(p for p in parts if p)


def _norm(p: str | Path) -> str:
    """Canonical comparison key for a filesystem path: realpath + normcase.

    realpath resolves symlinks (the Agent Memory dir is reached via a symlinked
    `~/.claude/projects/.../memory` on some surfaces) so a transcript that wrote
    via one alias still matches a gap resolved via another. normcase handles
    the case-insensitive macOS filesystem.
    """
    try:
        return os.path.normcase(os.path.realpath(os.fspath(p)))
    except Exception:
        return os.path.normcase(str(p))


def _get_last_assistant_text(transcript_path: str) -> str:
    if not transcript_path or not os.path.exists(transcript_path):
        return ""
    try:
        # The transcript is UTF-8 JSONL; the locale encoding (cp1252 on a stock
        # Windows box) would mis-read every non-ASCII character without raising.
        with open(transcript_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return ""
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if entry.get("type") != "assistant":
            continue
        msg = entry.get("message", {})
        content = msg.get("content", [])
        text_parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                text_parts.append(c.get("text", ""))
        if text_parts:
            return "\n".join(text_parts)
    return ""


def _session_written_paths(transcript_path: str) -> tuple[set[str], str]:
    """Scan this session's transcript for files it authored/modified.

    Returns (normalized_path_set, bash_command_blob_lowercased).

    The path set is the primary "ours" signal: every `file_path` argument to a
    Write/Edit/MultiEdit/NotebookEdit tool_use, normalized via _norm. The Bash
    command blob is a secondary fallback so a memo authored by a heredoc / `tee`
    (rare, but possible) still counts as ours when matched by bare filename —
    failing toward hard-blocking OUR OWN work, the safe direction.

    Fails soft: an unreadable / malformed transcript yields an EMPTY set, which
    means "block nothing as ours" — the conservative direction for a
    non-blocking nudge (we'd rather under-block on a parse failure than
    false-block a sibling). The caller treats an empty set + present gaps as
    "all gaps are sibling/pre-existing → soft note only".
    """
    written: set[str] = set()
    bash_blob_parts: list[str] = []
    if not transcript_path or not os.path.exists(transcript_path):
        return (written, "")
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return (written, "")
    for line in lines:
        try:
            rec = json.loads(line)
        except Exception:
            continue
        content = rec.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict) or c.get("type") != "tool_use":
                continue
            name = c.get("name", "")
            inp = c.get("input", {})
            if not isinstance(inp, dict):
                continue
            if name in FILE_WRITE_TOOLS:
                fp = inp.get("file_path") or inp.get("notebook_path")
                if isinstance(fp, str) and fp.strip():
                    written.add(_norm(fp))
            elif name == "Bash":
                cmd = inp.get("command", "")
                # Only what the command WRITES joins the fallback blob — a read
                # that names an artifact must not claim it as ours (MYC-766
                # false-block). See _bash_writes.
                if isinstance(cmd, str) and cmd:
                    writes = _bash_writes(cmd)
                    if writes:
                        bash_blob_parts.append(writes)
    return (written, "\n".join(bash_blob_parts).lower())


def _gap_abspath(gap: dict) -> str | None:
    """Resolve a verifier gap dict to the absolute on-disk path of its artifact.

    The verifier emits artifact = {repo, path, kind, commit, name}.
      - repo == "memory"      → MEMORY_ROOT / path   (path is the bare filename)
      - repo == "vault"       → VAULT_ROOT / path
      - repo == "dev/<name>"  → DEV_ROOT / <name> / path
    Returns None if the shape is unrecognized.
    """
    art = gap.get("artifact", {})
    if not isinstance(art, dict):
        return None
    repo = art.get("repo", "")
    rel = art.get("path", "")
    if not isinstance(repo, str) or not isinstance(rel, str) or not rel:
        return None
    if repo == "memory":
        return str(MEMORY_ROOT / rel)
    if repo == "vault":
        return str(VAULT_ROOT / rel)
    if repo.startswith("dev/"):
        return str(DEV_ROOT / repo[len("dev/"):] / rel)
    return None


def _run_verifier() -> list[dict]:
    """Return the verifier's raw gap list (each a dict), or [] on any failure.

    Failure to run the verifier never blocks the close — the hook is a nudge.
    """
    if not VERIFIER.exists():
        return []
    try:
        result = subprocess.run(
            [script_python(), str(VERIFIER), "--hours", "24", "--json"],
            # Explicit UTF-8: the gap paths are vault paths ("⚙️ Meta/..."), and a
            # locale decode that raised here would read as "no gaps".
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except Exception:
        return []
    try:
        payload = json.loads(result.stdout)
    except Exception:
        return []
    gaps = payload.get("gaps", [])
    return gaps if isinstance(gaps, list) else []


def _partition_gaps(
    gaps: list[dict], written: set[str], bash_blob: str
) -> tuple[list[dict], list[dict]]:
    """Split gaps into (ours, theirs).

    A gap is OURS when its artifact path was written by this session — either
    the normalized abspath is in `written`, OR the artifact's bare filename
    appears in this session's Bash command blob (heredoc/tee fallback).
    Everything else is a sibling's or pre-existing artifact → theirs.
    """
    ours: list[dict] = []
    theirs: list[dict] = []
    for gap in gaps:
        if not isinstance(gap, dict):
            continue
        abspath = _gap_abspath(gap)
        is_ours = False
        if abspath is not None and _norm(abspath) in written:
            is_ours = True
        else:
            # Heredoc / tee fallback: did a Bash command name this file?
            base = ""
            art = gap.get("artifact", {})
            if isinstance(art, dict):
                rel = art.get("path", "")
                if isinstance(rel, str) and rel:
                    base = os.path.basename(rel).lower()
            if base and bash_blob and base in bash_blob:
                is_ours = True
        (ours if is_ours else theirs).append(gap)
    return (ours, theirs)


def _format_gap_lines(gaps: list[dict], limit: int = 8) -> str:
    lines: list[str] = []
    for gap in gaps[:limit]:
        art = gap.get("artifact", {})
        repo = art.get("repo", "?") if isinstance(art, dict) else "?"
        path = art.get("path", "?") if isinstance(art, dict) else "?"
        kind = art.get("kind", "?") if isinstance(art, dict) else "?"
        lines.append(f"      - {repo} :: {path}")
        lines.append(f"          kind: {kind}")
        lines.append(f"          fix: {gap.get('suggestion', '(none)')}")
    if len(gaps) > limit:
        lines.append(f"      ... and {len(gaps) - limit} more")
    return "\n".join(lines)


def main() -> int:
    if os.environ.get("DISCOVERABILITY_VERIFIER_BYPASS") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    transcript_path = payload.get("transcript_path", "")
    last_text = _get_last_assistant_text(transcript_path)
    if not is_closing_claim(last_text):
        return 0

    # Repo-aware vault resolution, now that we know this is worth the work:
    # put this hook in lockstep with whichever vault
    # detect-closing-signal.py resolved for THIS cwd (see _lib/vault_root.py).
    _resolve_vault_context(payload.get("cwd", ""))

    gaps = _run_verifier()
    if not gaps:
        return 0

    written, bash_blob = _session_written_paths(transcript_path)
    ours, theirs = _partition_gaps(gaps, written, bash_blob)

    # Soft note for sibling / pre-existing gaps — informational, never blocks.
    if theirs:
        soft = (
            "[verify-discoverability-on-close] note (non-blocking): "
            f"{len(theirs)} discoverability gap(s) exist on artifact(s) this "
            "session did NOT author (sibling session or pre-existing). Not "
            "blocking this close — the owning session must wire them.\n"
            + _format_gap_lines(theirs)
        )
        print(soft, file=sys.stderr)

    # Hard-block ONLY on gaps THIS session authored.
    if not ours:
        return 0

    msg = (
        f"BLOCKED by verify-discoverability-on-close hook.\n\n"
        f"Per the same-session discoverability-enforcement rule\n"
        f"(codified 2026-05-13): every artifact ships discoverability wiring\n"
        f"in the same session as the artifact itself.\n\n"
        f"Bug class: ARTIFACT-WITHOUT-DISCOVERABILITY.\n\n"
        f"  • {len(ours)} artifact(s) THIS SESSION authored lack "
        f"discoverability wiring:\n"
        f"{_format_gap_lines(ours)}\n\n"
        f"Two ways to clear this block:\n"
        f"  (a) Wire the discoverability for each artifact NOW (preferred).\n"
        f"      For SKILL.md: ln -sfn <skill-dir> ~/.claude/skills/<name>\n"
        f"      For rules:    write .claude/hookify.<rule-name>.local.md\n"
        f"      For scripts:  add to sunday-review SKILL.md OR a hook OR cron\n"
        f"      For audit memos: extend the memo per the suggestion above\n"
        f"      For workflows: add 'on:' trigger block\n\n"
        f"  (b) File a handoff at <meta>/Handoffs/<date>-<slug>.md mentioning\n"
        f"      the artifact name + the word 'discoverability' + a re-evaluate\n"
        f"      date. The verifier treats explicit handoff acknowledgment as\n"
        f"      a valid dismissal.\n\n"
        f"Bypass for one close (use sparingly): DISCOVERABILITY_VERIFIER_BYPASS=1\n"
    )
    print(msg, file=sys.stderr)
    return 2


if __name__ == "__main__":
    # Windows cp1252-console safety (ai-brain-starter#313; hooks/ sweep #314).
    # A hook that print()s non-ASCII raises UnicodeEncodeError on a cp1252
    # console: the gate then fails silently OPEN, or denies the tool call with
    # no legible cause. Idempotent; a no-op on an already-UTF-8 console.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass
    try:
        sys.exit(main())
    except Exception:
        # Fail-open: a non-blocking nudge must never crash-block a close.
        sys.exit(0)
