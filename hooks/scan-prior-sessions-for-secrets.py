#!/usr/bin/env python3
"""SessionStart hook: scan every project's session JSONL for unredacted secrets.

Defense layer 4 of the secret-detection stack. PreToolUse hookify blocks
forward, PostToolUse redacts on detect, SessionEnd scrubs on close, and
THIS hook catches anything historical that slipped through — from sessions
that ended before the scrub hook existed, or before a given pattern was
added to the registry.

Behavior:
  - Detect: scans every `~/.claude/projects/**/*.jsonl` against the
    registry (`_lib/secret_patterns.scan`). Rate-limited to one run per 6h
    via `.last-secret-scan` marker.
  - Auto-scrub (opt-in via `VAULT_ROOT` env var): if a JSONL's parent
    worktree is NOT currently in `git worktree list`, backups + redacts
    the file in-place. Logs each scrub to
    `~/.claude/secret-detection-log.jsonl` (structured records, NEVER
    secret values).
  - Mid-session safety: a JSONL whose worktree IS active is SKIPPED with
    "will retry next SessionStart after close" — scrubbing a mid-session
    JSONL corrupts Claude Code's resume state.
  - Warn: surfaces residual findings (post-scrub) + threat-model reminder
    so the next response checks the leak vector before recommending
    rotation.

Environment:
  - `VAULT_ROOT` — absolute path to the user's vault git repo. **Required
    for auto-scrub.** Without it the hook cannot verify which worktrees
    are active and falls back to warn-only mode (safe default — never
    risks corrupting a mid-session JSONL).
  - `SCAN_PRIOR_AUTO_SCRUB_BYPASS=1` — forensic mode: skip auto-scrub
    even when VAULT_ROOT is set. Useful for inspecting findings before
    scrubbing.

Pairs with the other secret-defense layers; see `_lib/secret_patterns.py`
docstring for the full architecture.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOK_DIR))

from _lib.secret_patterns import redact, scan  # noqa: E402

MARKER = HOOK_DIR / ".last-secret-scan"
COOLDOWN_SECONDS = 6 * 60 * 60  # 6h

# Auto-scrub additions
AUTO_SCRUB_LOG = Path.home() / ".claude" / "secret-detection-log.jsonl"
VAULT_ROOT_ENV = "VAULT_ROOT"
BYPASS_ENV = "SCAN_PRIOR_AUTO_SCRUB_BYPASS"
BACKUP_SUFFIX_TEMPLATE = ".bak.{date}-secret-scrub"


def _within_cooldown() -> bool:
    if not MARKER.exists():
        return False
    try:
        last = float(MARKER.read_text().strip())
    except (ValueError, OSError):
        return False
    return (time.time() - last) < COOLDOWN_SECONDS


def _stamp() -> None:
    try:
        MARKER.write_text(f"{time.time():.0f}\n")
    except OSError:
        pass


def _vault_root() -> Path | None:
    """Resolve VAULT_ROOT or return None (disables auto-scrub safely)."""
    val = os.environ.get(VAULT_ROOT_ENV, "").strip()
    if not val:
        return None
    p = Path(val).expanduser()
    return p if p.exists() else None


def _active_worktree_slugs(vault_root: Path) -> set[str]:
    """Return slugs of currently active vault worktrees.

    Slugs look like `silly-edison-565ec5` from branches named
    `claude/silly-edison-565ec5`. Used to skip scrubbing JSONLs whose
    parent worktree is mid-session — mid-session scrub corrupts Claude
    Code's resume state.

    Empty set on any error (fail-closed: if we can't tell which worktrees
    are active, we DON'T auto-scrub anything — the warn path still fires).
    """
    try:
        proc = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(vault_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if proc.returncode != 0:
        return set()
    slugs: set[str] = set()
    for line in proc.stdout.splitlines():
        if line.startswith("branch refs/heads/claude/"):
            slugs.add(line.split("refs/heads/claude/", 1)[1].strip())
    return slugs


def _jsonl_is_in_active_worktree(jsonl: Path, active_slugs: set[str]) -> bool:
    """A JSONL belongs to an active worktree if its project-dir basename
    contains any active slug. Project dirs encode the worktree path with `/`
    replaced by `-`. Subagent files live one level deeper in `subagents/`;
    walk up to the project root before matching.
    """
    project_dir = jsonl.parent
    if project_dir.name == "subagents":
        project_dir = project_dir.parent.parent
    name = project_dir.name
    return any(slug in name for slug in active_slugs)


def _log_scrub(record: dict) -> None:
    """Append a structured record to ~/.claude/secret-detection-log.jsonl.

    Records what was scrubbed, when, and why. NEVER includes secret values.
    Schema: timestamp_iso, action, jsonl_path, backup_path, redacted_patterns,
    redaction_count, reason.
    """
    try:
        AUTO_SCRUB_LOG.parent.mkdir(parents=True, exist_ok=True)
        with AUTO_SCRUB_LOG.open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # Logging is best-effort; never blocks the hook.


def _auto_scrub(jsonl: Path) -> tuple[bool, str]:
    """Backup + scrub a single JSONL. Returns (success, message).

    Backup naming: <file>.bak.YYYYMMDD-secret-scrub. Skips if the backup
    already exists (idempotent across cooldown re-fires within one day).
    """
    today = _dt.date.today().strftime("%Y%m%d")
    backup = jsonl.with_name(jsonl.name + BACKUP_SUFFIX_TEMPLATE.format(date=today))
    if backup.exists():
        return False, f"backup {backup.name} already exists — skipping"
    try:
        shutil.copy2(jsonl, backup)
    except OSError as exc:
        return False, f"backup failed: {exc}"
    try:
        text = jsonl.read_text(errors="replace")
        redacted, hit_names = redact(text)
        if not hit_names:
            backup.unlink(missing_ok=True)  # No-op scrub; drop the backup.
            return False, "no patterns matched on re-scan (registry may have tightened)"
        jsonl.write_text(redacted)
    except OSError as exc:
        return False, f"scrub failed: {exc}"
    _log_scrub(
        {
            "timestamp_iso": _dt.datetime.now().isoformat(),
            "action": "auto_scrub_closed_session_jsonl",
            "jsonl_path": str(jsonl),
            "backup_path": str(backup),
            "redacted_patterns": hit_names,
            "redaction_count": len(hit_names),
            "reason": "SessionStart auto-scrub (closed worktree)",
        }
    )
    return True, f"scrubbed {len(hit_names)} pattern(s): {', '.join(hit_names)}"


def main() -> int:
    if _within_cooldown():
        print(json.dumps({"continue": True, "suppressOutput": True}))
        return 0

    projects = Path.home() / ".claude" / "projects"
    if not projects.exists():
        _stamp()
        print(json.dumps({"continue": True, "suppressOutput": True}))
        return 0

    findings: list[tuple[Path, list[tuple[str, int]]]] = []
    for jsonl in projects.rglob("*.jsonl"):
        try:
            text = jsonl.read_text(errors="replace")
        except OSError:
            continue
        hits = scan(text)
        if hits:
            findings.append((jsonl, hits))

    _stamp()

    if not findings:
        print(json.dumps({"continue": True, "suppressOutput": True}))
        return 0

    # Cap to most-recent 5 to keep the warning short.
    findings.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)
    findings = findings[:5]

    # Auto-scrub: requires VAULT_ROOT set + not bypassed. Without VAULT_ROOT
    # we cannot detect active worktrees, so we fall back to warn-only (safe).
    bypass_auto_scrub = os.environ.get(BYPASS_ENV, "").strip() not in ("", "0", "false")
    vault_root = _vault_root()
    auto_scrub_enabled = (vault_root is not None) and (not bypass_auto_scrub)
    active_slugs = _active_worktree_slugs(vault_root) if auto_scrub_enabled else set()

    auto_scrubbed: list[tuple[Path, str]] = []
    skipped_active: list[Path] = []
    for path, _hits in list(findings):
        if not auto_scrub_enabled:
            continue
        if _jsonl_is_in_active_worktree(path, active_slugs):
            skipped_active.append(path)
            continue
        ok, msg = _auto_scrub(path)
        if ok:
            auto_scrubbed.append((path, msg))

    # Re-scan remaining findings post-scrub so the warning surface reflects
    # actual residual exposure, not pre-scrub state.
    residual_findings: list[tuple[Path, list[tuple[str, int]]]] = []
    for path, _hits in findings:
        try:
            new_hits = scan(path.read_text(errors="replace"))
        except OSError:
            continue
        if new_hits:
            residual_findings.append((path, new_hits))

    lines = [
        "🔒 [secret-scan] Found unredacted secrets in prior session JSONLs:",
    ]
    if auto_scrubbed:
        lines.append(f"Auto-scrubbed {len(auto_scrubbed)} closed-worktree JSONL(s):")
        for path, msg in auto_scrubbed:
            lines.append(f"  ✓ {path.name}: {msg}")
    if skipped_active:
        lines.append(f"Skipped {len(skipped_active)} active-worktree JSONL(s) (mid-session safety):")
        for path in skipped_active:
            lines.append(f"  ⏸  {path.name}: will retry next SessionStart after close")
    if residual_findings:
        lines.append("Residual findings (re-scan post-scrub):")
        for path, hits in residual_findings:
            summary = ", ".join(f"{n}×{c}" for n, c in hits)
            lines.append(f"  ⚠ {path.name}: {summary}")
    if not (auto_scrubbed or skipped_active or residual_findings):
        # Defensive fallback (shouldn't reach given the earlier early-return).
        for path, hits in findings:
            summary = ", ".join(f"{n}×{c}" for n, c in hits)
            lines.append(f"  {path.name}: {summary}")
    if not auto_scrub_enabled:
        if vault_root is None:
            lines.append(
                f"Auto-scrub DISABLED ({VAULT_ROOT_ENV} env var not set or path missing). "
                f"Export VAULT_ROOT=/path/to/your/vault to enable closed-session auto-scrub."
            )
        elif bypass_auto_scrub:
            lines.append(f"Auto-scrub BYPASSED via {BYPASS_ENV}=1.")
    lines.append(f"Auto-scrub log: {AUTO_SCRUB_LOG}")
    lines.append(
        "Threat-model check before recommending rotation: when a leak is "
        "confined to local disk + the model API context only, rotation is "
        "rarely the right call; rotate when the vector extends to public "
        "internet / third-party services / untrusted machines / broadcast "
        "channels. See hookify rule "
        "`warn-rotation-push-on-local-only-leak.local.md`."
    )
    lines.append(
        f"Manual scrub: python3 -c \"import sys; sys.path.insert(0, '{HOOK_DIR}'); "
        f"from _lib.secret_patterns import redact; from pathlib import Path; "
        f"p = Path('<path>'); p.write_text(redact(p.read_text())[0])\""
    )

    warning = "\n".join(lines)
    print(warning, file=sys.stderr)
    print(
        json.dumps(
            {
                "continue": True,
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": warning,
                },
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
