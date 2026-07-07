#!/usr/bin/env python3
"""journal-preflight.py — ONE command that pulls EVERY configured /journal context
source and prints a consolidated digest, so daily-journal can never ship a contextless
entry again.

Why this exists (2026-07-07 incident): Step 0 of the skill was a CHECKLIST the model
could silently skip -> a blank journal with no calendar / messages / RescueTime / activity
context, and nothing caught it. This turns discipline into infrastructure. The skill's
FIRST action is now `python3 journal-preflight.py`; a save-time guard
(warn-journal-saved-without-context.py) refuses any journal that lacks the marker this
writes.

Covers the SCRIPT-based sources directly (messages, RescueTime, Session Captures,
today's activity). The two MCP-only sources (Calendar via google-workspace, Health via
health-mcp) cannot be called from pure Python — it prints the EXACT pull the skill must
make and records them PENDING in the marker so the guard can verify they landed.

Fails honest per source: a source that errors prints a clear note and is recorded as
FAILED, never fabricated. Exit 0 always (context-gatherer, not a gate).

Usage:
  python3 "<vault>/⚙️ Meta/scripts/journal-preflight.py"                 # auto-span since last entry
  python3 "<vault>/⚙️ Meta/scripts/journal-preflight.py" --since 2026-06-29 --until 2026-07-07
  python3 "<vault>/⚙️ Meta/scripts/journal-preflight.py" --json          # print marker JSON, no digest
"""
import os
import re
import sys
import glob
import json
import datetime
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
META = os.path.dirname(SCRIPT_DIR)          # the "⚙️ Meta" (or "Meta") dir
VAULT = os.path.dirname(META)

DAY_BOUNDARY_HOUR = 3                        # 3:45am boundary: pre-3:45 belongs to prior day
DAY_BOUNDARY_MIN = 45
MAX_GAP_DAYS = 14                            # cap RescueTime day-loop / span

CONFIG = os.path.join(META, "journal-config.md")
CAPTURES = os.path.join(META, "Session Captures.md")
MARKER_DIR = os.path.join(META, ".journal-context")

# Config-toggle key -> which fetcher(s) satisfy it. MCP-only keys have fetcher None.
SOURCE_FETCHERS = {
    "whatsapp_24h": "journal-messages-fetch.py",
    "imessage_24h": "journal-messages-fetch.py",
    "rescuetime": "rescuetime-fetch.py",
    "session_captures": "__captures__",
    "todays_activity": "__git__",
    "calendar": None,          # MCP: google-workspace cal_list_events
    "body_health": None,       # MCP: health-mcp / regenerate-health-pattern-report.py
}


def _journal_dir():
    for cand in ("📓 Journals", "Journals"):
        p = os.path.join(VAULT, cand)
        if os.path.isdir(p):
            return p
    return os.path.join(VAULT, "Journals")


JOURNALS = _journal_dir()


def target_today():
    now = datetime.datetime.now()
    boundary = now.replace(hour=DAY_BOUNDARY_HOUR, minute=DAY_BOUNDARY_MIN,
                           second=0, microsecond=0)
    d = now.date()
    if now < boundary:
        d -= datetime.timedelta(days=1)
    return d


def read_config_toggles():
    """data_sources toggles. Default: all ON if the file/parse is missing (fail-open to
    MORE context, never less — a silently-off source is the exact bug we're killing)."""
    toggles = {k: True for k in SOURCE_FETCHERS}
    try:
        txt = open(CONFIG, encoding="utf-8").read()
    except OSError:
        return toggles
    m = re.search(r"data_sources:\s*\n(.*?)(?:\n[A-Za-z_]+:|\n---)", txt, re.S)
    block = m.group(1) if m else ""
    for line in block.splitlines():
        mm = re.match(r"\s+([A-Za-z0-9_]+):\s*(on|off)\b", line)
        if mm and mm.group(1) in toggles:
            toggles[mm.group(1)] = (mm.group(2) == "on")
    return toggles


def last_entry_date(until_d):
    """Newest journal creationDate strictly before `until`. Bounded scan (recent mtime)."""
    best = None
    files = glob.glob(os.path.join(JOURNALS, "*", "*.md"))
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for p in files[:80]:
        try:
            head = open(p, encoding="utf-8", errors="replace").read(600)
        except OSError:
            continue
        m = re.search(r"creationDate:\s*(\d{4}-\d{2}-\d{2})", head)
        if not m:
            continue
        d = m.group(1)
        if d < until_d.isoformat() and (best is None or d > best):
            best = d
    return best


def _run(cmd, timeout=150):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = r.stdout or ""
        if r.returncode != 0 and r.stderr:
            out += f"\n[stderr rc={r.returncode}] {r.stderr.strip()[:400]}"
        return out.strip(), (r.returncode == 0)
    except Exception as e:  # noqa: BLE001 — fail honest
        return f"[preflight] could not run: {type(e).__name__}: {e}", False


def _fetcher_path(name):
    p = os.path.join(SCRIPT_DIR, name)
    return p if os.path.exists(p) else None


def main():
    args = sys.argv[1:]
    json_only = "--json" in args
    since = until = None
    for i, a in enumerate(args):
        if a == "--since" and i + 1 < len(args):
            since = args[i + 1]
        if a == "--until" and i + 1 < len(args):
            until = args[i + 1]

    until_d = datetime.date.fromisoformat(until) if until else target_today()
    if not since:
        since = last_entry_date(until_d) or (until_d - datetime.timedelta(days=3)).isoformat()
    since_d = datetime.date.fromisoformat(since)
    # clamp absurd spans
    if (until_d - since_d).days > MAX_GAP_DAYS:
        since_d = until_d - datetime.timedelta(days=MAX_GAP_DAYS)
        since = since_d.isoformat()

    toggles = read_config_toggles()
    pulled, failed, pending_mcp, skipped_off = [], [], [], []
    sections = []  # (title, body)

    # ---- Messages (WhatsApp + iMessage), spanning the whole gap ----
    if toggles.get("whatsapp_24h") or toggles.get("imessage_24h"):
        fp = _fetcher_path("journal-messages-fetch.py")
        if fp:
            body, ok = _run(["python3", fp, "--since", since, "--until", until_d.isoformat()])
            sections.append(("MESSAGES (WhatsApp + iMessage) since last entry", body))
            (pulled if ok and body else failed).append("messages")
        else:
            sections.append(("MESSAGES", "[preflight] journal-messages-fetch.py not installed in this vault — skipping (fresh install?)."))
            failed.append("messages")
    else:
        skipped_off.append("messages")

    # ---- RescueTime, per-day across the gap (fixed: honors each date) ----
    if toggles.get("rescuetime"):
        fp = _fetcher_path("rescuetime-fetch.py")
        if fp:
            lines, any_ok = [], False
            n = min((until_d - since_d).days + 1, MAX_GAP_DAYS)
            for k in range(n):
                d = (until_d - datetime.timedelta(days=k)).isoformat()
                body, ok = _run(["python3", fp, d], timeout=40)
                if body:
                    lines.append(body)
                    any_ok = any_ok or ok
            sections.append(("RESCUETIME (per day, newest first)", "\n\n".join(lines) or "[preflight] no RescueTime output."))
            (pulled if any_ok else failed).append("rescuetime")
        else:
            sections.append(("RESCUETIME", "[preflight] rescuetime-fetch.py not installed — skipping."))
            failed.append("rescuetime")
    else:
        skipped_off.append("rescuetime")

    # ---- Session Captures (verbatim seeds from the day's other sessions) ----
    if toggles.get("session_captures"):
        try:
            txt = open(CAPTURES, encoding="utf-8", errors="replace").read()
            head = "\n".join(txt.splitlines()[:120])
            sections.append(("SESSION CAPTURES (staging seeds)", head or "[empty]"))
            pulled.append("session_captures")
        except OSError:
            sections.append(("SESSION CAPTURES", "[preflight] Session Captures.md not found — skipping."))
            failed.append("session_captures")
    else:
        skipped_off.append("session_captures")

    # ---- Today's activity (git commits touching the vault today) ----
    if toggles.get("todays_activity"):
        body, ok = _run(["git", "-C", VAULT, "log",
                         f"--since={until_d.isoformat()} 00:00",
                         f"--until={until_d.isoformat()} 23:59",
                         "--oneline", "--no-decorate"], timeout=60)
        sections.append(("TODAY'S VAULT COMMITS", body or "[no commits today]"))
        pulled.append("todays_activity")
    else:
        skipped_off.append("todays_activity")

    # ---- MCP-only sources: cannot call from pure Python. Emit the exact pull + mark pending.
    if toggles.get("calendar"):
        pending_mcp.append("calendar")
    if toggles.get("body_health"):
        pending_mcp.append("body_health")

    # ---- Write the marker (the save-time guard reads this) ----
    os.makedirs(MARKER_DIR, exist_ok=True)
    marker = {
        "date": until_d.isoformat(),
        "since": since,
        "until": until_d.isoformat(),
        "ran_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "config_enabled": sorted([k for k, v in toggles.items() if v]),
        "sources_pulled": sorted(set(pulled)),
        "sources_failed": sorted(set(failed)),
        "sources_pending_mcp": sorted(set(pending_mcp)),
        "sources_skipped_off": sorted(set(skipped_off)),
    }
    marker_path = os.path.join(MARKER_DIR, f"{until_d.isoformat()}.json")
    with open(marker_path, "w", encoding="utf-8") as f:
        json.dump(marker, f, indent=2, ensure_ascii=False)

    if json_only:
        print(json.dumps(marker, indent=2, ensure_ascii=False))
        return 0

    # ---- Human/model-readable consolidated digest ----
    print(f"# /journal preflight — context {since} → {until_d.isoformat()}")
    print(f"_pulled: {', '.join(marker['sources_pulled']) or 'none'}"
          f" | failed: {', '.join(marker['sources_failed']) or 'none'}"
          f" | MCP-pending: {', '.join(marker['sources_pending_mcp']) or 'none'}_\n")
    for title, body in sections:
        print(f"\n{'='*72}\n## {title}\n{'='*72}")
        print(body if body else "[empty]")

    if pending_mcp:
        print(f"\n{'='*72}\n## ▶ MCP PULLS THE SKILL MUST STILL MAKE (preflight can't call MCP)\n{'='*72}")
        if "calendar" in pending_mcp:
            print(f"- CALENDAR: cal_list_events(time_min='{since}T00:00:00-05:00', "
                  f"time_max='{until_d.isoformat()}T23:59:59-05:00', verbose=true) "
                  "— fold meetings/attendees into ## Today, then note calendar in context_sources.")
        if "body_health" in pending_mcp:
            print("- HEALTH: read the latest Health Pattern Report + yesterday's ## Body track, "
                  "or run regenerate-health-pattern-report.py if the iPhone synced. Fold the roll-up in.")
        print("\nAfter these land, the journal frontmatter MUST carry a `context_sources:` block "
              "listing every pulled + MCP source, or warn-journal-saved-without-context.py fires.")

    print(f"\n_marker: {marker_path}_")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
