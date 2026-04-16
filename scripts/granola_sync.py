#!/usr/bin/env python3
"""
Granola -> Obsidian Vault Sync
Pulls new meeting notes from Granola API and saves as Obsidian markdown.
Runs via cron every 30 minutes.

Requires GRANOLA_API_KEY environment variable to be set.

Usage:
  GRANOLA_API_KEY=grn_... python3 granola_sync.py
  GRANOLA_API_KEY=grn_... python3 granola_sync.py --vault-root /path/to/vault
  GRANOLA_API_KEY=grn_... python3 granola_sync.py --meeting-dir "Meeting Notes"
"""

import argparse
import os
import json
import re
import sys
import requests
from datetime import datetime, timezone
from pathlib import Path


def detect_vault_root() -> Path:
    """Detect vault root from $VAULT_ROOT env var or script location."""
    env_root = os.environ.get("VAULT_ROOT")
    if env_root:
        return Path(env_root)
    script_dir = Path(__file__).resolve().parent
    candidate = script_dir.parent.parent
    if (candidate / "⚙️ Meta").is_dir():
        return candidate
    return Path.cwd()


# --- CONFIG ---
BASE_URL = "https://public-api.granola.ai/v1"


def log(msg, log_file):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(log_file, "a") as f:
        f.write(line + "\n")


def get_last_sync(state_file):
    """Read last sync timestamp."""
    if os.path.exists(state_file):
        with open(state_file) as f:
            return f.read().strip()
    return None


def set_last_sync(state_file, ts):
    """Save last sync timestamp."""
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, "w") as f:
        f.write(ts)


def safe_filename(title, date):
    """Create safe Obsidian filename from title and date."""
    clean = re.sub(r'[/\\:*?"<>|]', '-', title)
    clean = clean.strip()[:60]
    return f"{clean} - {date}.md"


def note_exists(meeting_dir, filename):
    """Check if note already exists in vault."""
    return os.path.exists(os.path.join(meeting_dir, filename))


def format_transcript(transcript_items):
    """Format transcript array into readable text."""
    if not transcript_items:
        return ""

    lines = []
    current_speaker = None
    current_text = []

    for item in transcript_items:
        speaker = item.get("speaker", {}).get("name", item.get("speaker", {}).get("source", "Unknown"))
        text = item.get("text", "").strip()

        if not text:
            continue

        if speaker != current_speaker:
            if current_text:
                lines.append(f"**{current_speaker}:** {' '.join(current_text)}")
            current_speaker = speaker
            current_text = [text]
        else:
            current_text.append(text)

    # Flush last speaker
    if current_text:
        lines.append(f"**{current_speaker}:** {' '.join(current_text)}")

    return "\n\n".join(lines)


def format_note(note_data):
    """Convert Granola API response to Obsidian markdown."""
    title = note_data.get("title", "Untitled Meeting")
    created = note_data.get("created_at", "")
    date = created[:10] if created else datetime.now().strftime("%Y-%m-%d")

    # Calendar event details
    cal = note_data.get("calendar_event") or {}
    start_time = cal.get("scheduled_start_time", "")
    end_time = cal.get("scheduled_end_time", "")

    # Attendees
    attendees = note_data.get("attendees", [])
    attendee_names = [a.get("name", a.get("email", "Unknown")) for a in attendees]
    attendee_list = "\n".join(f"- {name}" for name in attendee_names) if attendee_names else "- (none recorded)"

    # Panels / notes content
    panels = note_data.get("panels", [])
    notes_content = ""
    if panels:
        for panel in panels:
            panel_title = panel.get("title", "")
            panel_html = panel.get("html", "")
            clean = re.sub(r'<[^>]+>', '', panel_html)
            clean = clean.strip()
            if clean:
                if panel_title:
                    notes_content += f"\n### {panel_title}\n{clean}\n"
                else:
                    notes_content += f"\n{clean}\n"

    # Transcript
    transcript = note_data.get("transcript", [])
    transcript_text = format_transcript(transcript) if transcript else ""

    # Build markdown
    md = f"""---
creationDate: {date}
type: meeting
source: granola
granola_id: {note_data.get('id', '')}
attendees: [{', '.join(attendee_names)}]
---

*Auto-imported from [[Granola]] - {date}*

## Attendees
{attendee_list}
"""

    if start_time:
        start_fmt = start_time[:16].replace("T", " ")
        end_fmt = end_time[:16].replace("T", " ") if end_time else ""
        md += f"\n**Time:** {start_fmt} -> {end_fmt}\n"

    if notes_content:
        md += f"\n## Notes\n{notes_content}\n"

    if transcript_text:
        md += f"\n## Transcript\n\n{transcript_text}\n"

    md += f"\n---\n*See also: [[Meeting Notes Index]]*\n"

    return md


def sync(vault_root, meeting_dir, state_file, log_file, api_key):
    """Main sync: fetch new notes from Granola, save to vault."""
    headers = {"Authorization": f"Bearer {api_key}"}
    log("Starting Granola sync...", log_file)

    last_sync = get_last_sync(state_file)

    # Fetch notes list
    params = {"limit": 20}
    resp = requests.get(f"{BASE_URL}/notes", headers=headers, params=params)

    if resp.status_code != 200:
        log(f"ERROR: API returned {resp.status_code}: {resp.text[:200]}", log_file)
        return

    data = resp.json()
    notes = data.get("notes", [])

    if not notes:
        log("No notes found.", log_file)
        return

    new_count = 0
    skip_count = 0
    latest_ts = last_sync or ""

    for note_summary in notes:
        note_id = note_summary["id"]
        created = note_summary.get("created_at", "")
        title = note_summary.get("title", "Untitled")
        date = created[:10] if created else datetime.now().strftime("%Y-%m-%d")

        if last_sync and created <= last_sync:
            skip_count += 1
            continue

        filename = safe_filename(title, date)
        if note_exists(meeting_dir, filename):
            log(f"SKIP (exists): {filename}", log_file)
            skip_count += 1
            continue

        detail_resp = requests.get(
            f"{BASE_URL}/notes/{note_id}?include=transcript",
            headers=headers
        )

        if detail_resp.status_code != 200:
            log(f"ERROR fetching {note_id}: {detail_resp.status_code}", log_file)
            continue

        note_data = detail_resp.json()

        md_content = format_note(note_data)
        filepath = os.path.join(meeting_dir, filename)

        os.makedirs(meeting_dir, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md_content)

        log(f"SAVED: {filename}", log_file)
        new_count += 1

        if created > latest_ts:
            latest_ts = created

    if latest_ts:
        set_last_sync(state_file, latest_ts)

    log(f"Done. {new_count} new, {skip_count} skipped.", log_file)


def main():
    parser = argparse.ArgumentParser(description="Sync Granola meeting notes to Obsidian vault")
    parser.add_argument("--vault-root", type=Path, default=None,
                        help="Path to vault root (default: auto-detected)")
    parser.add_argument("--meeting-dir", default=None,
                        help="Meeting notes folder relative to vault root (default: auto-detected)")
    args = parser.parse_args()

    api_key = os.environ.get("GRANOLA_API_KEY")
    if not api_key:
        print("ERROR: GRANOLA_API_KEY environment variable not set.", file=sys.stderr)
        print("  Set it with: export GRANOLA_API_KEY=grn_...", file=sys.stderr)
        sys.exit(1)

    vault_root = (args.vault_root or detect_vault_root()).resolve()

    # Auto-detect meeting notes directory
    if args.meeting_dir:
        meeting_dir = str(vault_root / args.meeting_dir)
    else:
        # Look for common meeting note folder patterns
        for candidate in vault_root.rglob("Meeting Notes"):
            if candidate.is_dir():
                meeting_dir = str(candidate)
                break
        else:
            meeting_dir = str(vault_root / "Meeting Notes")

    # Auto-detect Meta folder for state/log files
    meta_dir = None
    for candidate in vault_root.iterdir():
        if candidate.is_dir() and candidate.name.endswith("Meta"):
            meta_dir = candidate
            break
    if meta_dir is None:
        meta_dir = vault_root / "Meta"

    state_file = str(meta_dir / "scripts" / ".granola_last_sync")
    log_file = str(meta_dir / "scripts" / ".granola_sync.log")

    sync(vault_root, meeting_dir, state_file, log_file, api_key)


if __name__ == "__main__":
    main()
