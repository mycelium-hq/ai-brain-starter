#!/usr/bin/env python3
"""
Granola Public API -- shared core (the single source of truth for the contract).

ONE module, imported by BOTH copies so they cannot drift:
  - scripts/granola_sync.py            (this substrate's zero-config exporter)
  - a private vault's granola_export.py (adds a Gmail follow-up drafter on top)

The API contract (auth, HTTP, paging, transcript formatting, the vault filename
contract, the incremental window, state) lives HERE. Before this module the two
copies were ~250-line near-duplicates that had already diverged within three
weeks (speaker labels, frontmatter, User-Agent). The original incident: the
personal copy was migrated to the Public API weeks before this substrate copy,
which silently exported nothing in the meantime.
Bug class: DISCIPLINE-FIX-NOT-PORTED-TO-SUBSTRATE.

WHY THE API (history): Granola migrated local storage to an encrypted SQLite DB
around 2026-05-12. The previous reader parsed
cache-v6.json["cache"]["state"]["transcripts"], which became an empty {} after
the migration -> it printed "No transcripts in cache." and exited 0 for weeks
(a silent failure: exit 0, zero output, nothing wrong-looking). The Public API
is vendor-supported and survives local-storage migrations.
Bug class: VENDOR-LOCAL-CACHE-SCHEMA-MIGRATION-SILENT-FAILURE.

AUTH: a Granola API key, resolved in order:
  1. GRANOLA_API_KEY environment variable
  2. a key_file the caller passes (a bare key, or a `GRANOLA_API_KEY=...` line)
  3. ~/.config/granola/api-key (same format)
Generate the key in Granola: Settings > Connectors > API keys (requires a plan
with API access). The key is read at runtime and is never written to the repo.

This module has no CLI of its own -- it is imported, not run. The substrate
exporter is scripts/granola_sync.py.
"""
from __future__ import annotations  # PEP 604 `X | None` annotations safe on py3.8+

import gzip
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_BASE = "https://public-api.granola.ai/v1"
DEFAULT_KEY_FILE = Path.home() / ".config" / "granola" / "api-key"
DEFAULT_USER_AGENT = "ai-brain-starter-granola-export/2.0"

# First-run window if no prior state (avoid pulling full history on day one).
DEFAULT_WINDOW_DAYS = 21

# Trailing re-scan applied on top of last_sync. A note's transcript/summary can
# finalize minutes-to-days after its created_at, and the API only returns a note
# once it is finalized. A window keyed strictly on last_sync would therefore
# SILENTLY skip any note that finalized after the window advanced past its
# created_at. Re-scanning a trailing window catches them; the exported-id dedup
# keeps it idempotent. Bug class: INCREMENTAL-WINDOW-MISSES-LATE-FINALIZED-NOTES.
SAFETY_LOOKBACK_DAYS = 4


# --------------------------------------------------------------------------- #
# auth + http
# --------------------------------------------------------------------------- #
def _read_key_file(path: Path) -> str:
    """First non-comment line of a key file: a bare key, or `GRANOLA_API_KEY=...`."""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("GRANOLA_API_KEY="):
                return line.split("=", 1)[1].strip()
            return line  # bare key on its own line
    except OSError:
        return ""
    return ""


def load_api_key(key_file: Path | None = None) -> str:
    """Resolve a key: env GRANOLA_API_KEY -> caller key_file -> DEFAULT_KEY_FILE.

    Fails LOUD (non-zero exit + named cause) when no key is found. This is the
    anti-silent-failure guarantee: the whole reason for the API rewrite was that
    the old cache reader exited 0 with empty output.
    """
    key = os.environ.get("GRANOLA_API_KEY", "").strip()
    if not key:
        for candidate in [key_file, DEFAULT_KEY_FILE]:
            if candidate and Path(candidate).is_file():
                key = _read_key_file(Path(candidate))
                if key:
                    break
    if not key:
        sys.exit(
            "FATAL: no Granola API key found.\n"
            "  Provide one of:\n"
            "    - env GRANOLA_API_KEY=grn_...\n"
            f"    - a key file (default {DEFAULT_KEY_FILE}); callers may pass another path\n"
            "  Generate it in Granola: Settings > Connectors > API keys."
        )
    return key


def api_get(path: str, key: str, retries: int = 4, user_agent: str = DEFAULT_USER_AGENT) -> dict:
    """GET with bearer auth, gzip, and 429 backoff. Fails loud on 401/403/persistent error."""
    url = API_BASE + path
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "User-Agent": user_agent,
    }
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=45) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            body = e.read()
            try:
                if body[:2] == b"\x1f\x8b":
                    body = gzip.GzipFile(fileobj=io.BytesIO(body)).read()
            except Exception:
                pass
            msg = body[:300].decode(errors="replace")
            if e.code in (401, 403):
                sys.exit(
                    f"FATAL: Granola API {e.code} -- key invalid/expired or the plan lacks API access.\n"
                    f"  {msg}\n  Regenerate the key in Granola: Settings > Connectors > API keys."
                )
            if e.code == 429:
                wait = 2 ** attempt
                sys.stderr.write(f"  rate-limited (429); backing off {wait}s\n")
                time.sleep(wait)
                last_err = e
                continue
            last_err = e
            time.sleep(1 + attempt)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            time.sleep(1 + attempt)
    sys.exit(f"FATAL: Granola API request failed after {retries} attempts: {path}\n  {last_err}")


def list_notes(key: str, created_after: str | None, user_agent: str = DEFAULT_USER_AGENT) -> list[dict]:
    """Page through /notes (newest first), following the cursor."""
    notes: list[dict] = []
    cursor, pages = None, 0
    while True:
        q = []
        if created_after:
            q.append("created_after=" + urllib.parse.quote(created_after))
        if cursor:
            q.append("cursor=" + urllib.parse.quote(cursor))
        data = api_get("/notes" + ("?" + "&".join(q) if q else ""), key, user_agent=user_agent)
        notes.extend(data.get("notes", []))
        pages += 1
        cursor = data.get("cursor")
        if not data.get("hasMore") or not cursor or pages >= 50:
            break
        time.sleep(0.25)  # stay well under the rate limit
    return notes


# --------------------------------------------------------------------------- #
# vault + filesystem
# --------------------------------------------------------------------------- #
def detect_vault_root() -> Path:
    env_root = os.environ.get("VAULT_ROOT")
    if env_root:
        return Path(env_root)
    script_dir = Path(__file__).resolve().parent
    for candidate in [script_dir.parent, script_dir.parent.parent]:
        if (candidate / "⚙️ Meta").is_dir() or (candidate / ".obsidian").is_dir():
            return candidate
    return Path.cwd()


def detect_meeting_dir(vault_root: Path, override: str | None = None) -> Path:
    if override:
        return vault_root / override
    for pattern in ["**/📝 Meeting Notes", "**/Meeting Notes"]:
        matches = list(vault_root.glob(pattern))
        if matches:
            return matches[0]
    return vault_root / "Meeting Notes"


def safe_filename(title: str, date: str) -> str:
    clean = re.sub(r'[/\\:*?"<>|]', "-", title or "Untitled").strip()[:60]
    return f"{date} - {clean} - Transcript.md"


# --------------------------------------------------------------------------- #
# formatting
# --------------------------------------------------------------------------- #
def _speaker_label(source: str) -> str:
    if source in ("microphone", "mic", "me"):
        return "**You**"
    # Keep the other channel as content -- never filter it. For lectures /
    # webinars / one-on-ones where you listen more than talk, this IS the meeting.
    return "**Speaker**"


def _parse_dt(s: str) -> datetime:
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc)


def format_transcript(transcript: list[dict], meeting_start: datetime) -> str:
    """Group consecutive same-source utterances; prefix each block with relative mm:ss."""
    blocks: list[str] = []
    cur_src, cur_texts, cur_start = None, [], None

    def flush():
        if not cur_texts:
            return
        elapsed = max(0, int((cur_start - meeting_start).total_seconds()))
        mm, ss = divmod(elapsed, 60)
        blocks.append(f"`{mm:02d}:{ss:02d}` {_speaker_label(cur_src)}: {' '.join(cur_texts)}")

    for u in transcript:
        text = (u.get("text") or "").strip()
        if not text:
            continue
        src = (u.get("speaker") or {}).get("source", "unknown")
        ts = _parse_dt(u.get("start_time") or "")
        if src != cur_src:
            flush()
            cur_src, cur_texts, cur_start = src, [text], ts
        else:
            cur_texts.append(text)
    flush()
    return "\n\n".join(blocks)


# --------------------------------------------------------------------------- #
# incremental window
# --------------------------------------------------------------------------- #
def incremental_created_after(
    state: dict,
    since: str | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    lookback_days: int = SAFETY_LOOKBACK_DAYS,
) -> str:
    """The created_after window: explicit --since, else last_sync minus a safety
    lookback, else a first-run window. Identical math in every caller, so it lives
    here once."""
    if since:
        return since if "T" in since else f"{since}T00:00:00Z"
    last = state.get("last_sync")
    if last:
        lookback = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        return min(_parse_dt(last), lookback).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (datetime.now(timezone.utc) - timedelta(days=window_days)).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# state (lives in the vault, beside the user's data -- not in the repo)
# --------------------------------------------------------------------------- #
def state_path_for(vault_root: Path) -> Path:
    if (vault_root / "⚙️ Meta").exists():
        return vault_root / "⚙️ Meta" / "scripts" / ".granola_export_state.json"
    return vault_root / ".granola_export_state.json"


def load_state(state_file: Path) -> dict:
    if Path(state_file).exists():
        try:
            s = json.loads(Path(state_file).read_text())
        except (OSError, json.JSONDecodeError):
            s = {}
    else:
        s = {}
    s.setdefault("exported", [])     # note ids whose transcript .md was written
    s.setdefault("last_sync", None)  # ISO of the last successful run
    return s


def save_state(state_file: Path, state: dict) -> None:
    Path(state_file).parent.mkdir(parents=True, exist_ok=True)
    Path(state_file).write_text(json.dumps(state, indent=2))


# --------------------------------------------------------------------------- #
# export one note
# --------------------------------------------------------------------------- #
def write_transcript_md(
    note: dict,
    meeting_dir: Path,
    dry_run: bool,
    extra_frontmatter: dict | None = None,
) -> tuple[Path | None, str]:
    """Write one note's transcript .md. `extra_frontmatter` lets a caller add
    keys (e.g. the personal exporter's `external_attendees`) without forking this
    function -- the only sanctioned point of variation."""
    title = note.get("title") or "Untitled Meeting"
    created = note.get("created_at") or ""
    date = created[:10] if created else datetime.now().strftime("%Y-%m-%d")
    meeting_start = _parse_dt(created)
    transcript = note.get("transcript") or []
    n_utt = sum(1 for u in transcript if (u.get("text") or "").strip())
    summary_md = (note.get("summary_markdown") or "").strip()
    web_url = note.get("web_url") or ""

    filepath = meeting_dir / safe_filename(title, date)
    if filepath.exists():
        return None, f"SKIP (file exists): {filepath.name}"

    fm = [
        "---",
        f"creationDate: {date}",
        "type: meeting",
        "source: granola-api",
        f"granola_id: {note.get('id', '')}",
        f"granola_url: {web_url}",
        f"utterances: {n_utt}",
    ]
    for k, v in (extra_frontmatter or {}).items():
        fm.append(f"{k}: {v}")
    fm.append("---")

    body = format_transcript(transcript, meeting_start)
    content = "\n".join(fm) + "\n\n"
    content += f"# {title}\n\n"
    content += f"*Pulled from the Granola API on {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
    if summary_md:
        content += f"## Summary\n\n{summary_md}\n\n"
    content += f"## Full Transcript\n\n{body or '_(empty transcript)_'}\n"

    if dry_run:
        return filepath, f"DRY-RUN would write {filepath.name} ({n_utt} utterances)"
    meeting_dir.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding="utf-8")
    return filepath, f"SAVED {filepath.name} ({n_utt} utterances)"
