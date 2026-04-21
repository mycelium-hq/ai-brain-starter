#!/usr/bin/env python3
"""
Granola local cache → Obsidian vault transcript export.

Reads Granola's local cache directly — no API key, no network call.
Exports full timestamped transcripts as markdown to your vault's meeting
notes folder. Works on any Mac with Granola installed.

Auto-run setup (fires when Granola updates its cache after each meeting):
  launchctl load ~/Library/LaunchAgents/com.granola-export.plist

Usage:
  python3 granola_sync.py              # export all cached transcripts
  python3 granola_sync.py --dry-run   # show what would be exported
  python3 granola_sync.py --vault-root /path/to/vault
  python3 granola_sync.py --meeting-dir "Meeting Notes"
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

CACHE_PATH = Path.home() / "Library/Application Support/Granola/cache-v6.json"


def detect_vault_root() -> Path:
    env_root = os.environ.get("VAULT_ROOT")
    if env_root:
        return Path(env_root)
    script_dir = Path(__file__).resolve().parent
    for candidate in [script_dir.parent, script_dir.parent.parent]:
        if (candidate / "⚙️ Meta").is_dir() or (candidate / ".obsidian").is_dir():
            return candidate
    return Path.cwd()


def detect_meeting_dir(vault_root: Path, override: str = None) -> Path:
    if override:
        return vault_root / override
    for pattern in ["**/📝 Meeting Notes", "**/Meeting Notes"]:
        matches = list(vault_root.glob(pattern))
        if matches:
            return matches[0]
    return vault_root / "Meeting Notes"


def load_state(state_file: Path) -> dict:
    if state_file.exists():
        with open(state_file) as f:
            return json.load(f)
    return {"exported": []}


def save_state(state_file: Path, state: dict):
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def safe_filename(title: str, date: str) -> str:
    clean = re.sub(r'[/\\:*?"<>|]', "-", title).strip()[:60]
    return f"{date} - {clean} - Transcript.md"


def format_transcript(utterances: list, meeting_start: datetime) -> str:
    """Group consecutive utterances by source into labeled paragraphs."""
    paragraphs = []
    current_source = None
    current_texts = []
    current_start = None

    def flush():
        if not current_texts:
            return
        text = " ".join(current_texts)
        if current_source == "microphone":
            label = "**You**"
        elif current_source and current_source != "system":
            label = f"**{current_source.replace('_', ' ').title()}**"
        else:
            return  # skip system messages
        elapsed = max(0, (current_start - meeting_start).total_seconds())
        mins, secs = divmod(int(elapsed), 60)
        paragraphs.append(f"`{mins:02d}:{secs:02d}` {label}: {text}")

    for u in utterances:
        source = u.get("source", "unknown")
        if source == "system":
            continue
        text = u.get("text", "").strip()
        if not text:
            continue
        ts_str = u.get("start_timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            ts = meeting_start

        if source != current_source:
            flush()
            current_source = source
            current_texts = [text]
            current_start = ts
        else:
            current_texts.append(text)

    flush()
    return "\n\n".join(paragraphs)


def export_one(doc_id: str, doc: dict, utterances: list,
               meeting_dir: Path, dry_run: bool = False):
    title = doc.get("title", "Untitled Meeting")
    created = doc.get("created_at", "")
    date = created[:10] if created else datetime.now().strftime("%Y-%m-%d")

    try:
        meeting_start = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        meeting_start = datetime.now(timezone.utc)

    non_system = [u for u in utterances if u.get("source") != "system"]
    utterance_count = len(non_system)

    filename = safe_filename(title, date)
    filepath = meeting_dir / filename

    if filepath.exists():
        return None, f"SKIP (exists): {filename}"

    transcript_text = format_transcript(utterances, meeting_start)
    notes_md = (doc.get("notes_markdown") or "").strip()

    content = f"""---
creationDate: {date}
type: meeting
source: granola-local
granola_id: {doc_id}
utterances: {utterance_count}
---

# {title}

*Exported from Granola local cache — {date}*

"""
    if notes_md:
        content += f"## Granola Notes\n\n{notes_md}\n\n"

    if transcript_text:
        content += f"## Full Transcript\n\n{transcript_text}\n"
    else:
        content += "*No transcript available for this meeting.*\n"

    if dry_run:
        return filename, f"DRY RUN: {filename} ({utterance_count} utterances)"

    meeting_dir.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding="utf-8")
    return filename, f"SAVED: {filename} ({utterance_count} utterances)"


def main():
    parser = argparse.ArgumentParser(
        description="Export Granola meeting transcripts to Obsidian vault"
    )
    parser.add_argument("--vault-root", type=Path)
    parser.add_argument("--meeting-dir", help="Meeting notes folder (relative to vault root)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not CACHE_PATH.exists():
        print(f"Granola cache not found: {CACHE_PATH}")
        print("Make sure Granola is installed and has been run at least once.")
        sys.exit(1)

    with open(CACHE_PATH, encoding="utf-8") as f:
        state_data = json.load(f)["cache"]["state"]

    transcripts = state_data.get("transcripts", {})
    documents = state_data.get("documents", {})

    if not transcripts:
        print("No transcripts in Granola cache.")
        return

    vault_root = (args.vault_root or detect_vault_root()).resolve()
    meeting_dir = detect_meeting_dir(vault_root, args.meeting_dir)
    state_file = vault_root / "⚙️ Meta" / "scripts" / ".granola_export_state.json"
    if not (vault_root / "⚙️ Meta").exists():
        state_file = vault_root / ".granola_export_state.json"

    state = load_state(state_file)
    exported_ids = set(state.get("exported", []))

    newly_exported = []
    for doc_id, utterances in transcripts.items():
        if doc_id in exported_ids:
            continue

        doc = documents.get(doc_id)
        if not doc:
            print(f"SKIP (no document): {doc_id[:8]}...")
            continue

        filename, msg = export_one(doc_id, doc, utterances, meeting_dir, args.dry_run)
        print(msg)

        if filename and not args.dry_run:
            newly_exported.append(doc_id)

    if newly_exported:
        state["exported"].extend(newly_exported)
        save_state(state_file, state)

    print(f"Done. {len(newly_exported)} exported.")


if __name__ == "__main__":
    main()
