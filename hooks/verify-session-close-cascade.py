#!/usr/bin/env python3
"""
Stop hook: blocks responses that CLAIM to close the session without actually
running the FULL cascade (session file + session-close-runner.sh report).

Failure modes this prevents:
  - 2026-05-10 busy-pasteur: model wrote summary saying "closing the session"
    but never ran Phase 0-3 of ⚙️ Meta/rules/session-close.md.
  - 2026-05-11 gallant-kalam: model wrote session file + committed it, then
    posted a "## Session ... — final summary" message claiming closure
    without running session-close-runner.sh (aggregators, Phase 0c-e,
    worktree-settle). the user flagged: "this keeps happening, make the fix
    permanent."

Three-gate check when a closing claim is detected:
  1. Session file exists at ⚙️ Meta/Sessions/YYYY-MM-DD*<worktree>*.md
  2. session-close-runner.sh ran in the last 30 min — verified via
     /tmp/abs-session-close-runner.report ending in `RUNNER COMPLETE @ <ts>`.
  3. No uncommitted session-close artifacts (today's Sessions/Decisions/
     Captures files must be staged + committed via vault-safe-commit.sh).

All three must be true. Two-gate version was the 2026-05-12 funny-golick
gap: session file existed, runner ran, but 5 files (session + 3 decisions
+ Captures + to-do append) sat uncommitted until the worktree archive
prompt caught them. Permanent-fix-pattern: don't rely on user-visible UI
warnings; block at the model layer.

Spanish closing patterns added 2026-05-13 — the same session's goodbye
("Que descanses, Ade") slipped past the English-only regex, so the
two-gate check never even fired.

Bypass: VERIFY_CASCADE_BYPASS=1.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

VAULT_ROOT = Path(os.environ.get("VAULT_ROOT", str(Path.home() / "vault")))
SESSIONS_DIR = VAULT_ROOT / "⚙️ Meta" / "Sessions"
RUNNER_REPORT = Path("/tmp/abs-session-close-runner.report")
RUNNER_FRESH_SECONDS = 1800  # 30 minutes

# High-confidence closing-claim patterns. Conservative — only matches when the
# model is CLAIMING closure, not discussing the rule meta.
#
# Patterns extended 2026-05-11 after the gallant-kalam miss: the previous
# regex set required literal "closing the session" / "closing this session",
# but the model can claim closure via summary-style markdown headers
# ("## Session ... — final summary") or one-word "Closing." replies. Both
# slip past the old patterns. New patterns cover those forms.
CLOSING_PATTERNS = [
    # 2026-05-12 fix: dropped `\.?$` anchors. Previous version required the
    # closing phrase to END a line; "Closing the session. Writing the artifact..."
    # slipped through because "session." was mid-line. Now matches anywhere.
    r"\bclosing the session\b",
    r"\bclosing this session\b",
    r"\bsession is closed\b",
    r"\bsession[- ]end cascade hook should pick up\b",
    r"\bsession[- ]end cascade will handle\b",
    r"\bsafe to archive\b.*\bworktree\b",
    r"\bcascade complete\b",
    # 2026-05-11 additions — summary-style closure claims
    r"^closing\.?\s*$",                     # bare "Closing." reply
    r"^##\s+Session\s+.+—\s*final summary",  # ## Session ... — final summary
    r"\bfinal summary\b.*\bsession\b",
    r"\bsession (?:summary|wrap[- ]?up|recap)\b",
    r"\bdogfood install (?:complete|done)\b.*\bsession\b",
    # 2026-05-12 additions — late-night close phrasings the model uses
    r"\bgood night\b",
    r"\bwriting the session artifact\b",
    r"\brunning the (?:close )?cascade\b",
    # 2026-05-13 additions — Spanish closing phrasings (caught after the
    # funny-golick-fe8400 miss where "Que descanses, Ade" slipped past the
    # English-only patterns and 5 files almost got discarded at archive)
    r"\bque descanses\b",
    r"\bbuenas noches\b",
    r"\bhasta mañana\b",
    r"\bdulces sueños\b",
    r"\bnos vemos mañana\b",
    r"\bcerrando la sesión\b",
    r"\bcierro la sesión\b",
    r"\bsesión cerrada\b",
    r"\bchao\b.*\b(ade|adelaida)\b",
]

# Negation contexts — phrases that mean the model is DISCUSSING closure, not
# claiming it. If any of these appear, skip the check.
NEGATION_PATTERNS = [
    r"how do we make sure",
    r"did you run",
    r"didn't run",
    r"did not run",
    r"keeps not happening",
    r"\bI should have\b",
    r"how to ",
    r"why didn't",
    r"the fix is",
]


def get_last_assistant_text(transcript_path: str) -> str:
    """Read the last assistant message text from the transcript JSONL."""
    if not transcript_path or not os.path.exists(transcript_path):
        return ""
    try:
        with open(transcript_path) as f:
            lines = f.readlines()
    except Exception:
        return ""
    # Walk backwards to find the most recent assistant message
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


def extract_worktree_slug(cwd: str) -> str:
    """Extract the worktree slug from a cwd like .../worktrees/<slug>/..."""
    m = re.search(r"/worktrees/([^/]+)", cwd or "")
    return m.group(1) if m else ""


def is_closing_claim(text: str) -> bool:
    """True iff the text claims session closure (and isn't a discussion of it)."""
    if not text:
        return False
    # Skip if any negation context appears — model is discussing, not claiming
    for pat in NEGATION_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return False
    # Look for a closing claim
    for pat in CLOSING_PATTERNS:
        if re.search(pat, text, re.IGNORECASE | re.MULTILINE):
            return True
    return False


def session_file_exists_for_today(worktree_slug: str) -> bool:
    """True iff a session file exists for today (or yesterday, to handle the
    midnight-roll case) matching the worktree slug.

    Yesterday-fallback added 2026-05-13 after funny-golick-fe8400: session
    was authored at 23:59 on 2026-05-12, cascade ran past midnight, hook
    checked for 2026-05-13-dated file only and false-flagged the existing
    file as missing. Sessions span calendar boundaries; the check should too.
    """
    if not SESSIONS_DIR.exists():
        return False
    from datetime import timedelta
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    for date_prefix in (today, yesterday):
        for path in SESSIONS_DIR.glob(f"{date_prefix}*.md"):
            if worktree_slug and worktree_slug in path.name:
                return True
    return False


def _decision_belongs_to_worktree(path_str: str, worktree_slug: str) -> bool:
    """Check decision-file frontmatter for `worktree: <slug>` match.

    Decision filenames are date-only (no worktree slug), so frontmatter is
    the only attribution signal. If frontmatter is missing or unreadable,
    we ERR ON THE SIDE OF NOT BLOCKING — false-positives here block the
    legitimate goodbye of an unrelated session, which is worse than
    missing a real uncommitted artifact.
    """
    try:
        full_path = VAULT_ROOT / path_str
        if not full_path.exists():
            return False
        head = full_path.read_text(encoding="utf-8", errors="replace")[:2000]
    except Exception:
        return False
    m = re.search(r"^worktree:\s*(\S+)\s*$", head, re.MULTILINE)
    if not m:
        return False
    return m.group(1).strip() == worktree_slug


def uncommitted_session_artifacts(worktree_slug: str) -> list[str]:
    """Return paths of uncommitted session-close artifacts owned by THIS
    worktree's session.

    Scoping rules (added 2026-05-13 after the funny-golick gate caught
    parallel-session work):
      - Sessions/: match filename contains today's OR yesterday's date AND
        the worktree slug.
      - Decisions/: filename has no worktree, so read frontmatter
        `worktree: <slug>` and match.
      - Session Captures.md: shared across sessions; flag only if THIS
        worktree also has an uncommitted session file (likely-same-batch
        proxy). This avoids blocking goodbye on another session's append.

    Empty list = clean for this worktree. Non-empty = block.

    Original failure: funny-golick-fe8400 wrote 5 files at session close
    and almost lost them at archive. Permanent-fix-pattern: block at the
    model layer, not the UI layer.
    """
    import subprocess
    from datetime import timedelta
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        result = subprocess.run(
            ["git", "-C", str(VAULT_ROOT), "status", "--short",
             "--", "⚙️ Meta/Sessions/", "⚙️ Meta/Decisions/", "⚙️ Meta/Session Captures.md"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []

    sessions_unc: list[str] = []
    decisions_unc: list[str] = []
    captures_unc: list[str] = []
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line or len(line) < 4:
            continue
        path = line[3:].strip().strip('"')
        if "Session Captures.md" in path:
            captures_unc.append(path)
            continue
        if "/Sessions/" in path or path.startswith("⚙️ Meta/Sessions/"):
            if (today in path or yesterday in path) and worktree_slug and worktree_slug in path:
                sessions_unc.append(path)
            continue
        if "/Decisions/" in path or path.startswith("⚙️ Meta/Decisions/"):
            if today in path or yesterday in path:
                if _decision_belongs_to_worktree(path, worktree_slug):
                    decisions_unc.append(path)
            continue

    # Captures only flags when this worktree also has an uncommitted session
    # file (same-batch proxy); otherwise it's another session's append.
    flagged_captures = captures_unc if sessions_unc else []
    return sessions_unc + decisions_unc + flagged_captures


def runner_ran_recently() -> bool:
    """True iff session-close-runner.sh wrote a fresh RUNNER COMPLETE marker.

    The runner writes to /tmp/abs-session-close-runner.report on every run
    and ends with `RUNNER COMPLETE @ <ISO8601-UTC>`. The marker is fresh
    iff timestamp is within RUNNER_FRESH_SECONDS of now (UTC).

    Missing report file, missing marker, or stale marker → False.
    """
    if not RUNNER_REPORT.exists():
        return False
    try:
        text = RUNNER_REPORT.read_text(errors="replace")
    except Exception:
        return False
    m = re.search(r"RUNNER COMPLETE @ (\S+)", text)
    if not m:
        return False
    ts_raw = m.group(1).strip()
    # Accept either trailing Z (zulu) or +00:00 offset
    if ts_raw.endswith("Z"):
        ts_raw = ts_raw[:-1] + "+00:00"
    try:
        ts = datetime.fromisoformat(ts_raw)
    except Exception:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - ts).total_seconds() <= RUNNER_FRESH_SECONDS


def main() -> int:
    if os.environ.get("VERIFY_CASCADE_BYPASS") == "1":
        return 0

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0  # malformed payload — don't block

    cwd = payload.get("cwd", "")
    transcript_path = payload.get("transcript_path", "")

    worktree_slug = extract_worktree_slug(cwd)
    if not worktree_slug:
        return 0  # not in a worktree — skip

    last_text = get_last_assistant_text(transcript_path)
    if not is_closing_claim(last_text):
        return 0  # no closing claim — skip

    # Two-gate check: BOTH must be true. Single-gate (file-only) was the
    # 2026-05-11 gallant-kalam miss — session file existed but runner never
    # ran, so aggregators / Phase 0c-e / worktree settle all silently skipped.
    today = datetime.now().strftime("%Y-%m-%d")
    file_ok = session_file_exists_for_today(worktree_slug)
    runner_ok = runner_ran_recently()
    uncommitted = uncommitted_session_artifacts(worktree_slug)
    commit_ok = not uncommitted

    if file_ok and runner_ok and commit_ok:
        return 0  # all three gates clear — cascade ran fully

    # Block with diagnostic naming WHICH gate failed
    failures = []
    if not file_ok:
        failures.append(
            f"  • Session file missing at ⚙️ Meta/Sessions/{today}T*-{worktree_slug}.md\n"
            f"    Author it manually (Phase 2 of session-close.md) before retry."
        )
    if not runner_ok:
        runner_state = "missing" if not RUNNER_REPORT.exists() else "stale (>30min old)"
        failures.append(
            f"  • session-close-runner.sh report is {runner_state}\n"
            f"    Path: {RUNNER_REPORT}\n"
            f"    Run: bash \"⚙️ Meta/scripts/session-close-runner.sh\"\n"
            f"    The runner handles Phase 0c-0e + Phase 2 aggregators +\n"
            f"    Phase 2c worktree settle deterministically."
        )
    if not commit_ok:
        sample = "\n".join(f"      {p}" for p in uncommitted[:8])
        more = f"\n      ... and {len(uncommitted) - 8} more" if len(uncommitted) > 8 else ""
        failures.append(
            f"  • Session-close artifacts uncommitted ({len(uncommitted)} files):\n"
            f"{sample}{more}\n"
            f"    Run vault-safe-commit.sh BEFORE the goodbye:\n"
            f"      bash \"⚙️ Meta/scripts/vault-safe-commit.sh\" \\\n"
            f"        \"session-close: <worktree> — <one-line summary>\" \\\n"
            f"        \"<path1>\" \"<path2>\" ..."
        )

    msg = (
        f"BLOCKED by verify-session-close-cascade hook.\n\n"
        f"Your last response claims to close the session, but the cascade\n"
        f"did not fully run. Two-gate check (BOTH required):\n\n"
        + "\n".join(failures) + "\n\n"
        f"Manual phases (not in runner — still your job): Phase 0b\n"
        f"(incomplete-work gate), Phase 1 (conversation scan + Pending\n"
        f"Signals), Phase 2 (session file authorship), Phase 2b\n"
        f"(vault-safe-commit), Phase 3 (functional audit on public ships).\n\n"
        f"Bypass (use sparingly): VERIFY_CASCADE_BYPASS=1\n"
    )
    print(msg, file=sys.stderr)
    return 2  # block


if __name__ == "__main__":
    sys.exit(main())
