#!/usr/bin/env python3
"""
detect-closing-signal.py — UserPromptSubmit hook.

Detects when the user is signaling session close ("bye", "thanks that's all",
"good night", "/wrap-up", emoji-only farewells, multilingual variants), then
runs all FAST deterministic prep work BEFORE the model sees the prompt and
injects a structured system block telling the model exactly what to capture.

Layered defense (this is Layer 1 of 3):
  - Layer 1: this hook (UserPromptSubmit) — pre-execution + signal detection
  - Layer 2: model writes captures using injected paths/inputs
  - Layer 3: session-end-hook.sh (Stop) — aggregators, git, retention, fallback

Why this hook exists: the prior architecture relied entirely on the model
"noticing" closing signals and choosing to read the cascade rule file.
Three brittle steps that failed silently. This hook makes detection
deterministic and pre-resolves all paths so the model only does the
irreducibly creative work (conversation scan + verbatim capture).

Behavior contract:
  - Reads user prompt from stdin (Claude Code hook contract)
  - Detects close signal via language-pack regex + optional Haiku fallback
  - Runs FAST prep (timestamp, paths, marker file, decisions-with-empty-outcome
    list, recently-touched-files list, session-file shell pre-build)
  - Returns additionalContext that injects all of the above plus the cascade
    instructions inline (no separate rule-file read needed)
  - Skips entirely if session is trivial (<5 user messages, no captures detected)
  - Fails open: any error returns empty context, never blocks the user

Performance budget: < 500ms total. Heavy work (aggregators, git, retention)
runs in the Stop hook AFTER the model finishes.

Usage in hooks.json:
  "UserPromptSubmit": [{"hooks": [{"type": "command",
    "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/detect-closing-signal.py"
  }]}]

Or via absolute path during install:
  python3 ~/.claude/skills/ai-brain-starter/hooks/detect-closing-signal.py

Environment variables (all optional):
  VAULT_ROOT — vault path. Defaults to cwd. Worktree paths are collapsed to
               the main vault root so session artifacts never strand on a
               worktree (see resolve_main_vault).
  CLOSING_SIGNAL_LANGS — comma-separated language packs to load (default: en,es,pt)
  CLOSING_SIGNAL_DETECTION — "regex" (default) or "hybrid" (regex + Haiku fallback)
  CLOSING_SIGNAL_DEBUG — set to 1 for stderr trace
  ANTHROPIC_API_KEY — required only if CLOSING_SIGNAL_DETECTION=hybrid

Output marker file:
  ~/.claude/.closing-signal-{session_id}.json
  Contains: timestamp, matched signal, language, confidence, pre-resolved paths
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime


def log_debug(msg: str) -> None:
    if os.environ.get("CLOSING_SIGNAL_DEBUG") == "1":
        print(f"[detect-closing-signal] {msg}", file=sys.stderr)


def read_hook_input() -> dict:
    """Read JSON from stdin (Claude Code hook contract)."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        return json.loads(raw)
    except (json.JSONDecodeError, OSError) as e:
        log_debug(f"failed to read hook input: {e}")
        return {}


def emit_passthrough() -> None:
    """Return nothing-special — let the model process normally."""
    print(json.dumps({"continue": True, "suppressOutput": True}))


def emit_context(context: str) -> None:
    """Return injected context to the model."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }))


def find_repo_root() -> Path:
    """Locate this script's repo root (where templates/ lives)."""
    here = Path(__file__).resolve().parent
    # hooks/ is 1 level deep
    candidate = here.parent
    if (candidate / "templates" / "closing-signals").is_dir():
        return candidate
    # Fall back: walk up looking for templates/closing-signals
    for ancestor in here.parents:
        if (ancestor / "templates" / "closing-signals").is_dir():
            return ancestor
    return candidate


def load_language_packs(langs: list[str]) -> dict:
    """Load JSON language packs and merge into a single rule set.

    strict_guards (codified 2026-05-25): override ALL tiers including
    explicit + high_confidence. Used for unambiguous non-close contexts
    (meta-discussion of close cascade, debugging, technical references)
    where false positives are very costly. The original false_positive_guards
    only suppress weak tiers (ambiguous / emoji_only).
    """
    repo = find_repo_root()
    pack_dir = repo / "templates" / "closing-signals"
    merged = {
        "explicit": [],
        "high_confidence": [],
        "ambiguous": [],
        "emoji_only": [],
        "false_positive_guards": [],
        "strict_guards": [],
    }
    for lang in langs:
        path = pack_dir / f"{lang.strip()}.json"
        if not path.is_file():
            log_debug(f"language pack not found: {path}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log_debug(f"failed to load {path}: {e}")
            continue
        for key in merged:
            merged[key].extend(data.get(key, []))
    return merged


def load_user_custom_signals(vault_root: Path) -> list[str]:
    """Read user's CLAUDE.md for closingSignals.custom: [...]."""
    claude_md = vault_root / "CLAUDE.md"
    if not claude_md.is_file():
        return []
    try:
        text = claude_md.read_text(encoding="utf-8")
    except OSError:
        return []
    # Look for either YAML frontmatter array or inline list
    match = re.search(
        r"closingSignals\.custom\s*[:=]\s*\[([^\]]*)\]",
        text,
        re.IGNORECASE,
    )
    if not match:
        return []
    raw = match.group(1)
    items = []
    for piece in re.findall(r"[\"']([^\"']+)[\"']", raw):
        items.append(re.escape(piece.strip()))
    return items


def is_false_positive(prompt: str, guards: list) -> bool:
    """Check if any false-positive guard matches; if so, skip detection."""
    for guard in guards:
        if isinstance(guard, dict):
            pattern = guard.get("pattern", "")
        else:
            pattern = str(guard)
        if not pattern:
            continue
        try:
            if re.search(pattern, prompt, re.IGNORECASE | re.MULTILINE):
                return True
        except re.error as e:
            log_debug(f"bad guard regex '{pattern}': {e}")
            continue
    return False


def classify_signal(prompt: str, packs: dict, custom: list[str]) -> tuple[str | None, str | None]:
    """Return (confidence, matched_pattern) or (None, None) if no match.

    Confidence levels: explicit > high > ambiguous > emoji.
    """
    if not prompt or not prompt.strip():
        return (None, None)

    text = prompt.strip()

    # Strong-tier matches (custom, explicit, high_confidence) OVERRIDE
    # false-positive guards. The guard is meant to catch "okay let's continue"
    # mid-conversation transitions — NOT to suppress "okay let's close this
    # session" which contains a clear close verb. Fix shipped 2026-05-12 after
    # an "Okay, let's close this session" prompt was silently suppressed by the
    # `^ok(ay)?[,.\s]+(let'?s|now)...` guard despite high_confidence pattern
    # `\b(let'?s\s+)?close\s+(this|the)\s+session\b` also matching.

    # STRICT guards (codified 2026-05-25): override EVERYTHING, including
    # explicit/high_confidence/custom. Use only for unambiguous non-close
    # contexts where false positives are very costly. Checked FIRST so
    # meta-discussion of close cascade never fires a stub. The original
    # FP guards remain for weak-tier-only suppression — strict guards do
    # NOT override the user's custom patterns, those still win.
    if is_false_positive(text, packs.get("strict_guards", [])):
        log_debug("strict guard matched, suppressing ALL tiers")
        return (None, None)

    # User custom patterns are highest authority — always win, FP guard skipped
    for pattern in custom:
        try:
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                return ("explicit", pattern)
        except re.error:
            continue

    # Strong tiers (explicit, high_confidence) override FP guards
    for level in ("explicit", "high_confidence"):
        for pattern in packs.get(level, []):
            try:
                if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                    log_debug(f"matched [{level}] (FP guard bypassed): {pattern}")
                    return (level, pattern)
            except re.error as e:
                log_debug(f"bad pattern '{pattern}': {e}")
                continue

    # For weaker tiers (emoji_only, ambiguous), apply FP guards
    if is_false_positive(text, packs.get("false_positive_guards", [])):
        log_debug("false-positive guard matched (no strong-tier match), skipping")
        return (None, None)

    for level in ("emoji_only", "ambiguous"):
        for pattern in packs.get(level, []):
            try:
                if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                    log_debug(f"matched [{level}]: {pattern}")
                    return (level, pattern)
            except re.error as e:
                log_debug(f"bad pattern '{pattern}': {e}")
                continue

    return (None, None)


def ambiguous_haiku_check(prompt: str) -> bool:
    """Optional: ask Haiku 'is this a session-close intent?' for ambiguous cases.

    Only fires if CLOSING_SIGNAL_DETECTION=hybrid AND ANTHROPIC_API_KEY set.
    Returns True if Haiku says yes.
    """
    if os.environ.get("CLOSING_SIGNAL_DETECTION") != "hybrid":
        return False
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # type: ignore
    except ImportError:
        log_debug("anthropic SDK not installed; hybrid detection unavailable")
        return False
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            system=(
                "You classify whether a user message is a session-close intent. "
                "Reply with exactly 'yes' or 'no'. A session-close intent is a "
                "natural sign-off: saying goodbye, signaling done for now, "
                "ending the conversation. Mid-conversation transitions like "
                "'ok now do X' or 'great, what's next' are NOT session-close."
            ),
            messages=[{"role": "user", "content": prompt[:500]}],
        )
        answer = (resp.content[0].text or "").strip().lower() if resp.content else ""
        return answer.startswith("yes")
    except Exception as e:
        log_debug(f"hybrid haiku check failed: {e}")
        return False


def derive_worktree(cwd: Path) -> str:
    """Derive worktree slug from path or .git file."""
    cwd_str = str(cwd)
    m = re.search(r"/\.claude/worktrees/([^/]+)", cwd_str)
    if m:
        return m.group(1)
    git_file = cwd / ".git"
    if git_file.is_file():
        try:
            text = git_file.read_text(encoding="utf-8")
            m2 = re.search(r"worktrees/([^/\s]+)", text)
            if m2:
                return m2.group(1).strip()
        except OSError:
            pass
    return "main"


def resolve_main_vault(path: Path) -> Path:
    """Collapse a worktree path to the MAIN vault root.

    If `path` is inside `<vault>/.claude/worktrees/<slug>/...`, return
    `<vault>` — the main vault root. Otherwise return `path` unchanged.

    Session artifacts (the session file, Decisions/, Captures, Time
    Tracking) MUST land in the main vault. A worktree's own checkout sits
    on a throwaway `claude/<slug>` branch; anything written there is
    discarded when the worktree is archived. The close cascade can fire
    from inside a worktree, so the cwd-derived vault root must be
    collapsed back to main before any artifact path is resolved.

    Mirrors resolve_main_vault() in scripts/session-end-hook.sh — the same
    fix applied to the Stop hook for issue #65 / PR #66. This hook (the
    UserPromptSubmit Layer 1 of the cascade) was never brought to parity.
    """
    marker = "/.claude/worktrees/"
    text = str(path)
    if marker in text:
        return Path(text.split(marker, 1)[0])
    return path


def find_meta_dir(vault_root: Path) -> Path:
    """Auto-detect Meta folder. Returns the canonical dir for THIS vault.

    Resolution order:
      1. Common explicit prefixes first (emoji + plain). Cheap stat checks
         beat directory iteration on large vaults and avoid relying on
         iterdir order.
      2. Iteration fallback for any other suffix-"Meta" dir name.
      3. Final fallback: plain `Meta` under vault_root. Caller MUST verify
         the returned path exists before emitting it (see verify_meta_dir).

    The emoji-first probe fixes a class of bugs where iterdir() either
    returned partial results, hit a NFD/NFC normalization mismatch on
    macOS APFS, or failed silently. When `⚙️ Meta` exists on disk, this
    function now returns it deterministically without iterating.
    """
    # 1. Explicit prefix probes (deterministic, cheap, robust).
    for candidate_name in ("⚙️ Meta", "Meta"):
        candidate = vault_root / candidate_name
        if candidate.is_dir():
            return candidate

    # 2. Iterate as fallback for unconventional suffixes.
    try:
        for child in sorted(vault_root.iterdir()):
            if child.is_dir() and child.name.endswith("Meta"):
                return child
    except OSError:
        pass

    # 3. Last resort. Caller verifies existence.
    return vault_root / "Meta"


def verify_meta_dir(meta_dir: Path) -> tuple[bool, str]:
    """Confirm the resolved Meta dir exists and contains the expected layout.

    Returns (ok, reason). The cascade caller should refuse to emit pre-resolved
    paths when ok is False — better to skip the cascade than to send the model
    to a phantom directory where its writes will be silently lost.
    """
    if not meta_dir.exists():
        return False, f"resolved meta_dir does not exist: {meta_dir}"
    if not meta_dir.is_dir():
        return False, f"resolved meta_dir is not a directory: {meta_dir}"
    sessions = meta_dir / "Sessions"
    if not sessions.exists():
        # Auto-create the standard subdirs the cascade will write into.
        try:
            sessions.mkdir(parents=True, exist_ok=True)
            (meta_dir / "Decisions").mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return False, f"could not create Sessions/ subdir: {e}"
    return True, ""


def count_user_messages(transcript_path: str | None) -> int:
    """Count user messages in the transcript to enforce skip-if-trivial rule."""
    if not transcript_path:
        return 99  # unknown — assume substantive
    p = Path(transcript_path)
    if not p.is_file():
        return 99
    count = 0
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") == "user" or (
                    isinstance(rec.get("message"), dict)
                    and rec["message"].get("role") == "user"
                ):
                    count += 1
    except OSError:
        return 99
    return count


def list_decisions_with_empty_outcome(meta_dir: Path) -> list[str]:
    """Return relative paths of Decisions/ files where Outcome: is blank."""
    decisions_dir = meta_dir / "Decisions"
    if not decisions_dir.is_dir():
        return []
    out = []
    for path in sorted(decisions_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        # Match `Outcome:` followed only by whitespace or a placeholder marker
        if re.search(r"^\s*outcome:\s*(\(pending\)|tbd|—|-|)\s*$",
                     text, re.IGNORECASE | re.MULTILINE):
            out.append(path.name)
    return out[:20]  # cap to keep injected context small


def pre_build_session_shell(
    sessions_dir: Path,
    timestamp_file: str,
    worktree: str,
    timestamp_human: str,
) -> Path:
    """Pre-create session file with frontmatter + section headers.

    Model only fills in the body. Returns the absolute path.
    """
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = sessions_dir / f"{timestamp_file}-{worktree}.md"
    if path.exists() and path.stat().st_size > 0:
        # Don't clobber a partial session file from earlier in the same minute
        return path
    shell = f"""---
creationDate: {timestamp_human}
type: session
worktree: {worktree}
session_date: {timestamp_human[:10]}
session_label: "update pending"
---

# Session — {timestamp_human}

## What happened

<!-- Brief summary of the session: what was worked on, what was produced. -->

## Decisions

<!-- New decisions logged this session. Per-decision files in ⚙️ Meta/Decisions/. -->

## Captures

<!-- Journal seeds (verbatim), writing notes, actionable content. -->

## To-dos filed

<!-- Personal vs team, with destination file. -->

## Delegations

<!-- Items handed to others, with drafted message. -->

## Pending / incomplete

<!-- Background tasks, killed runs, items deferred to next session. -->
"""
    try:
        path.write_text(shell, encoding="utf-8")
    except OSError as e:
        log_debug(f"failed to write session shell: {e}")
    return path


def write_marker(
    session_id: str,
    payload: dict,
) -> Path:
    """Write closing-signal marker file for the Stop hook to find."""
    home = Path.home()
    marker_dir = home / ".claude"
    marker_dir.mkdir(parents=True, exist_ok=True)
    marker = marker_dir / f".closing-signal-{session_id}.json"
    try:
        marker.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        log_debug(f"failed to write marker: {e}")
    return marker


def build_injected_context(
    confidence: str,
    matched: str,
    timestamp_human: str,
    timestamp_file: str,
    worktree: str,
    vault_root: Path,
    meta_dir: Path,
    session_file: Path,
    decisions_dir: Path,
    captures_file: Path,
    pending_outcomes: list[str],
    is_trivial: bool,
    is_ambiguous: bool,
) -> str:
    """Compose the system block injected into the model's context.

    Kept under ~600 tokens. All paths pre-resolved. Cascade phases summarized
    inline so the model doesn't need to read a separate rule file.
    """
    if is_trivial:
        return (
            f"SESSION CLOSE detected (signal: {matched!r}, confidence: {confidence}). "
            f"This session is trivial (<5 user messages). Per the skip rule, "
            f"skip the cascade and just say a clean goodbye. The Stop hook will "
            f"still log a timestamp."
        )

    if is_ambiguous:
        # User said "ok" or similar — confirm before running the heavy cascade
        return (
            f"POSSIBLE SESSION CLOSE detected (signal: {matched!r}, confidence: ambiguous). "
            f"This could be a close, or it could be a mid-conversation transition. "
            f"Before running the cascade, confirm in ONE short sentence: "
            f"\"Wrapping up, or keeping going?\" — and then act on the answer. "
            f"If they confirm close, follow the FULL cascade instructions below. "
            f"If they keep going, just continue normally.\n\n"
            + _full_cascade_block(
                timestamp_human, timestamp_file, worktree, vault_root,
                meta_dir, session_file, decisions_dir, captures_file,
                pending_outcomes,
            )
        )

    return (
        f"SESSION CLOSE detected (signal: {matched!r}, confidence: {confidence}, "
        f"language pack matched). Run the FULL cascade.\n\n"
        + _full_cascade_block(
            timestamp_human, timestamp_file, worktree, vault_root,
            meta_dir, session_file, decisions_dir, captures_file,
            pending_outcomes,
        )
    )


def _full_cascade_block(
    timestamp_human: str,
    timestamp_file: str,
    worktree: str,
    vault_root: Path,
    meta_dir: Path,
    session_file: Path,
    decisions_dir: Path,
    captures_file: Path,
    pending_outcomes: list[str],
) -> str:
    """The reusable cascade-instruction block."""
    pending = ", ".join(pending_outcomes) if pending_outcomes else "(none)"
    # Pre-resolve the Time Tracking surface (codified 2026-05-14). The Phase 1
    # bullet used to say "if vault uses it" and require the model to infer
    # presence; that produced a false-negative when the model checked the
    # wrong directory. Resolving here mirrors the pattern for session_file +
    # captures_file: the model trusts the injected path, no inference.
    time_tracking_file = meta_dir / "Time Tracking.md"
    if time_tracking_file.is_file():
        tt_line = (
            f"  Time tracking:    {time_tracking_file}  "
            f"(append today's entry under a ## YYYY-MM-DD heading; create the heading if missing)"
        )
    else:
        tt_line = "  Time tracking:    (not in this vault, skip the time-tracking step)"
    return f"""SESSION CLOSE — pre-resolved context (use these exact values):

  Timestamp:        {timestamp_human}
  Worktree:         {worktree}
  Vault root:       {vault_root}
  Session file:     {session_file}  (already pre-built with frontmatter + headers; fill in the body)
  Decisions dir:    {decisions_dir}  (write per-decision files here, slug-named)
  Captures file:    {captures_file}
{tt_line}
  Decisions with empty Outcome (review for backfill): {pending}

PHASE 0a — RUN THE CANONICAL RUNNER FIRST (codified 2026-05-27 after the
session-close-runner stale-report block incident). Single most-important
step in the cascade. This bash invocation IS Phases 0c + 0d + 0e + Phase 2
aggregators executed deterministically, AND it refreshes the report file
the verify-session-close-cascade Stop hook checks. Skipping it = guaranteed
Stop-hook block + forced cascade re-run + redundant manual phase-walking.

  bash "{meta_dir}/scripts/session-close-runner.sh"

The runner handles: handoff-folder scan, orphan-task-list check, launchd
health, aggregate-sessions / aggregate-decisions / Session Start Brief /
passive-capture / drift-detection / Rule Conflicts. Output ends with the
list of Phases that are STILL your manual job (0b + 1 + 2 + 2b + 3).

After it finishes, walk the remaining Phases (0b → 1 → 2 → 2b → 3) below.
The detailed phase descriptions that follow are reference for those manual
steps — do NOT re-walk Phases 0c/0d/0e by hand; the runner already did
those deterministically.

Banned framings (treating the runner as optional): "I walked Phases 0c-0e
manually," "the runner is one of several ways," "I skipped the runner since
I checked individually." The runner IS the canonical entry point; manual
phase-walking races with the verifier hooks and burns a close-attempt.

PHASE 0b — Incomplete-work gate (DO THIS AFTER 0a, before any writes):
Surface any background tasks still running, pipeline phases killed mid-run,
errors not retried. Ask the user "finish now, or defer?" Wait for their call.
If nothing incomplete: say "No incomplete work" and proceed.

PHASE 0c / 0d / 0e — Already run by Phase 0a's runner.
(Listed below only as reference for what the runner did. Do NOT re-execute
these manually; trust the runner output.)
  Phase 0c — Consumable-artifact cleanup: scans Handoffs/ + consumes_when frontmatter.
  Phase 0d — Orphan task-list guard: runs check-orphan-task-lists.py.
  Phase 0e — Launchd health check: runs check-launchd-health.sh.

PHASE 1 — Single-pass conversation scan (compose all in memory before writing):
  • Belief shifts: did the user end the session believing something different?
  • Journal seeds: VERBATIM quotes where they revealed a belief, observation,
    or change of mind. Tag emotional ones [emotional]. Never reword.
  • Writing note candidates (if user has a Substack/blog setup): apply kill
    conditions before drafting (no "I did today", no LinkedIn-thought-leader
    tone, no diary, must read as universal observation). Bilingual pair if
    configured.
  • Actionable content: strategy, product insights, partnership leads. File
    to canonical location per the vault map; default to Captures.
  • To-dos: separate personal vs team. Apply self-contained capture rule —
    each task must include a context prefix in brackets, a wikilink, a URL,
    or a file path so it stands alone when surfaced out of session context.
  • To-do reconciliation: check off completed items in Get to-do, team to-do,
    Current Priorities. Match by substance, not exact wording.
  • Decision logging: any new decisions get a per-decision file in Decisions/
    with What/Why/Floor/Stakes/Speed/Outcome.
  • Decision outcome backfill: review the empty-outcome list above; fill in
    Outcomes where this session resolved them.
  • Delegations: items for others get @Name + drafted Slack/WhatsApp/email
    message ready to send.
  • Time tracking entry: append to the Time tracking file resolved above
    (path is authoritative, do NOT search for it or claim it doesn't exist).
    One line, format "HH:MMam - HH:MMam | Category | Brief", inferred from
    conversation. If the resolved path says "(not in this vault, skip)",
    skip this step. Otherwise: append under today's date heading; create
    the heading if missing.

PHASE 2 — Batch writes (one tool-call block, append never overwrite):
  • Fill in the pre-built session file (paths above).
  • Create per-decision files in Decisions/ as needed.
  • Append journal seeds to Captures.
  • Personal vs team firewall: never let personal content leak to a team vault.

PHASE 2b — vault-safe-commit IS YOUR MANUAL JOB (codified 2026-05-25
after the cascade double-fire incident). You MUST run vault-safe-commit.sh
with explicit paths for every session-close artifact you wrote (session
file + decisions + captures + time-tracking + any rule/inventory edits)
BEFORE drafting the goodbye. The verify-session-close-cascade Stop hook
checks for uncommitted session-close artifacts and BLOCKS the close if
any are present — earlier docs said the post-Stop hook would auto-commit
this, which was wrong: the verify hook fires BEFORE the post-Stop hook,
so trusting auto-commit causes a hard block + forced re-run.

The post-Stop hook handles ONLY: aggregators (aggregate-sessions.py /
aggregate-decisions.py), retention cleanup (stubs >7d), worktree-archive
preparation. It does NOT auto-commit; that is Phase 2b above and it is
your job before goodbye.

Phases 0c/0d/0e and the Phase 3 audit are MODEL-SIDE. The post-Stop hook
does NOT run them.

PHASE 3 — Functional audit (conditional, MODEL-SIDE):
If this session shipped code or docs to a PUBLIC REPO that users download
(ai-brain-starter, humanizer, mycelium-site, any *-mcp, etc.), run the
6-step audit before close:
  1. Syntax: `python3 -m py_compile` every new/modified .py;
     `bash -n` every new/modified .sh;
     `python3 -c "import json; json.load(open(...))"` every new/modified .json.
  2. Path resolution: grep every `~/.claude/skills/...` path in docs/templates
     against the actual filesystem. Every path must resolve.
  3. Orphan scan: grep every new file under hooks/, scripts/, templates/
     against the docs that should reference it. Unreferenced = invisible.
  4. Smoke test: invoke each new script with `--help` or minimal args.
  5. Misleading copy: search shipped docs for "this hook blocks X" /
     "three gates enforce Y" that imply auto-installation. If the artifact
     isn't auto-installed, rewrite to "opt-in, install via:".
  6. Relative link check: resolve every `](...)` relative link in modified
     README/docs against the filesystem.
Report: "Audit: N python OK, M bash OK, K JSON OK, P paths resolved,
Q orphans found + fixed, R smoke tests passed."
If session shipped to a public repo and you SKIP this audit, you've left
the close cascade incomplete. CI covers the bulk-mechanical checks
(syntax, em-dash, cross-reference) but does NOT cover smoke tests,
misleading copy, or unreferenced files. The audit catches what CI can't.

PHASE 4 — Final summary (one line, after audit if Phase 3 fired):
"Filed X seeds, Y to-dos (yours: A, delegations: B), Z decisions, checked
off M items. Anything I missed?"

Then say goodbye in the user's primary language, warm, no machinery
narration."""


def main() -> int:
    start = time.time()
    try:
        hook_input = read_hook_input()
        prompt = (hook_input.get("prompt") or "").strip()
        session_id = hook_input.get("session_id") or "unknown"
        transcript_path = hook_input.get("transcript_path")
        cwd = Path(hook_input.get("cwd") or os.getcwd())

        if not prompt:
            emit_passthrough()
            return 0

        # Skip detection on Stop-hook-feedback prompts. Claude Code injects
        # blocking-hook stderr output as the next "user message" so the model
        # can self-correct. These are NOT user-initiated close signals; letting
        # them through creates a retry-loop where every Stop-hook block spawns
        # a new pre-built session file at a new timestamp.
        #
        # Codified 2026-05-24 after verify-session-close-cascade kept blocking
        # the session close (legitimately — uncommitted session artifacts), and
        # its feedback message contained "claims to close the session" which
        # re-fired this hook's `\bclose\s+(this|the)\s+session\b` regex,
        # spawning stubs at T10-55, T11-00 on each retry. Same bug class as
        # CASCADE-PHASE-SILENT-SKIP: hook-feedback re-injection is not a
        # user-prompt event and must be filtered before any signal detection.
        #
        # Expanded 2026-05-24 (T14 round): the original `startswith` check
        # missed re-injections that arrived with prepended system-reminder
        # context, and `BLOCKED by` was bounded to the first 300 chars which
        # also missed wrapped messages. Now we scan the first ~2KB for any
        # of the distinctive markers, including verifier-hook names that
        # uniquely identify Claude Code feedback re-injection. Same session
        # spawned 6 spurious stubs (T14-16, T14-20, T14-23, T14-25, T14-27,
        # T14-30) before the broader filter shipped.
        prefix = prompt[:2000]
        feedback_markers = (
            "Stop hook feedback:",
            "Hook feedback:",
            "BLOCKED by ",
            "verify-session-close-cascade",
            "verify-discoverability-on-close",
            "verify-cascade",
        )
        if any(m in prefix for m in feedback_markers):
            log_debug("Stop-hook-feedback prompt, skipping close detection")
            emit_passthrough()
            return 0

        # Resolve the vault root. When the close cascade fires from inside a
        # worktree, cwd IS the worktree; resolve_main_vault collapses it back
        # so every session artifact lands in the main vault, never a throwaway
        # claude/<slug> branch that gets discarded when the worktree archives.
        vault_root = resolve_main_vault(
            Path(os.environ.get("VAULT_ROOT") or cwd)
        )

        langs = [
            x.strip() for x in
            os.environ.get("CLOSING_SIGNAL_LANGS", "en,es,pt").split(",")
            if x.strip()
        ]
        packs = load_language_packs(langs)
        custom = load_user_custom_signals(vault_root)

        confidence, matched = classify_signal(prompt, packs, custom)

        # Hybrid: ambiguous matches OR no match get a Haiku second look
        if confidence in (None, "ambiguous"):
            if ambiguous_haiku_check(prompt):
                confidence = confidence or "high_confidence"
                matched = matched or prompt[:60]

        if confidence is None:
            log_debug(f"no signal match in: {prompt[:80]!r}")
            emit_passthrough()
            return 0

        # Resolve all paths up front. Verify the resolution lands on a real
        # directory before emitting the cascade — a phantom meta_dir sends
        # the model writes that the aggregator will never pick up.
        meta_dir = find_meta_dir(vault_root)
        ok, reason = verify_meta_dir(meta_dir)
        if not ok:
            log_debug(f"meta_dir verification failed, skipping cascade: {reason}")
            emit_passthrough()
            return 0
        sessions_dir = meta_dir / "Sessions"
        decisions_dir = meta_dir / "Decisions"
        captures_file = meta_dir / "Session Captures.md"

        worktree = derive_worktree(cwd)
        now = datetime.now()
        timestamp_human = now.strftime("%Y-%m-%d %H:%M")
        timestamp_file = now.strftime("%Y-%m-%dT%H-%M")

        user_msg_count = count_user_messages(transcript_path)
        is_trivial = user_msg_count < 5

        is_ambiguous = (confidence == "ambiguous")

        # Pre-build session file shell unless trivial
        session_file = sessions_dir / f"{timestamp_file}-{worktree}.md"
        if not is_trivial:
            session_file = pre_build_session_shell(
                sessions_dir, timestamp_file, worktree, timestamp_human,
            )

        # Pre-fetch decisions with empty outcomes
        pending_outcomes = []
        if not is_trivial:
            pending_outcomes = list_decisions_with_empty_outcome(meta_dir)

        # Write marker for Stop hook
        write_marker(session_id, {
            "timestamp": timestamp_human,
            "timestamp_file": timestamp_file,
            "matched_signal": matched,
            "confidence": confidence,
            "language_packs": langs,
            "worktree": worktree,
            "vault_root": str(vault_root),
            "meta_dir": str(meta_dir),
            "session_file": str(session_file),
            "user_msg_count": user_msg_count,
            "is_trivial": is_trivial,
            "is_ambiguous": is_ambiguous,
            "elapsed_ms": int((time.time() - start) * 1000),
        })

        context = build_injected_context(
            confidence=confidence,
            matched=matched or "",
            timestamp_human=timestamp_human,
            timestamp_file=timestamp_file,
            worktree=worktree,
            vault_root=vault_root,
            meta_dir=meta_dir,
            session_file=session_file,
            decisions_dir=decisions_dir,
            captures_file=captures_file,
            pending_outcomes=pending_outcomes,
            is_trivial=is_trivial,
            is_ambiguous=is_ambiguous,
        )
        emit_context(context)
        log_debug(f"injected context for {confidence} signal in {int((time.time() - start) * 1000)}ms")
        return 0
    except Exception as e:  # never block the user on hook errors
        log_debug(f"unexpected error: {e!r}")
        emit_passthrough()
        return 0


if __name__ == "__main__":
    sys.exit(main())
