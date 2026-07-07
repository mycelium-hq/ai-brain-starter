#!/usr/bin/env python3
"""journal-preflight.py — ONE command that pulls EVERY configured /journal context
source and prints a consolidated, RELATIONAL-FIRST digest, so daily-journal can never
ship a contextless (or life-blind) entry again.

Why (2026-07-07 incident, twice): Step 0 was a checklist the model could skip -> a blank
opener; then a THIN pull buried the fact that the user's sister was flying in. Two failure
modes: (1) skipped the pull, (2) pulled but buried the human stuff under dev chatter.
This fixes both — one mandatory command, and family/partner threads surfaced FIRST.

Sources:
  SCRIPT (pulled here, MCP-independent):
    - messages   : WhatsApp (direct + groups) + iMessage, whole gap, RELATIONAL-FIRST
    - rescuetime : per day across the gap
    - seeds      : close-cascade journal seeds (Session Captures.md, [emotional] tagged)
    - activity   : today's vault git commits
    - email      : the triage digest (Email Needs You.md) + honest age flag
    - slack      : on-disk Slack export (recent)
  MCP (preflight prints the exact call; the skill makes it — pure Python can't):
    - calendar   : cal_list_events for the window
    - email_live : gmail_search since last journal (the digest is often stale)
    - slack_live : slack search/read recent (on-disk export is sparse)
    - health     : latest Health Pattern Report + yesterday's Body track

Writes a marker at `<vault>/⚙️ Meta/.journal-context/<date>.json`; the save-time guard
(warn-journal-saved-without-context.py) refuses a journal whose marker is missing.

Fails honest per source (a source that errors says so, never fabricated). Exit 0 always.

Usage:
  python3 "<vault>/⚙️ Meta/scripts/journal-preflight.py"
  python3 "<vault>/⚙️ Meta/scripts/journal-preflight.py" --since 2026-06-29 --until 2026-07-07
  python3 "<vault>/⚙️ Meta/scripts/journal-preflight.py" --json
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
MAX_GAP_DAYS = 14

CONFIG = os.path.join(META, "journal-config.md")
CAPTURES = os.path.join(META, "Session Captures.md")
EMAIL_DIGEST = os.path.join(META, "Email Needs You.md")
MARKER_DIR = os.path.join(META, ".journal-context")

# Relational names surfaced FIRST in the message digest so family/partner threads are
# never buried under work chatter (the 2026-07-07 relational-thread miss). Defaults
# cover generic family/partner terms; add specific names via `relational_priority:` in
# journal-config.md. Matched case-insensitively against the contact/thread name.
RELATIONAL_DEFAULTS = [
    "mom", "mamá", "mama", "dad", "papá", "papa", "sister", "hermana",
    "brother", "hermano", "wife", "husband", "partner", "novio", "novia",
    "esposo", "esposa", "familia", "family",
]

# Config-toggle key -> fetcher token ("__x__" = inline handler; None = MCP-only).
SOURCE_FETCHERS = {
    "whatsapp_24h": "journal-messages-fetch.py",
    "imessage_24h": "journal-messages-fetch.py",
    "rescuetime": "rescuetime-fetch.py",
    "session_captures": "__captures__",
    "todays_activity": "__git__",
    "email": "__email__",
    "slack": "__slack__",
    "calendar": None,          # MCP: cal_list_events
    "body_health": None,       # MCP: health-mcp / Health Pattern Report
}


def _first_dir(*cands):
    for c in cands:
        p = os.path.join(VAULT, c)
        if os.path.isdir(p):
            return p
    return os.path.join(VAULT, cands[-1])


JOURNALS = _first_dir("📓 Journals", "Journals")
AICHATS = _first_dir("🤖 AI Chats", "AI Chats")


def target_today():
    now = datetime.datetime.now()
    b = now.replace(hour=DAY_BOUNDARY_HOUR, minute=DAY_BOUNDARY_MIN, second=0, microsecond=0)
    d = now.date()
    if now < b:
        d -= datetime.timedelta(days=1)
    return d


def read_config():
    """Return (toggles dict, relational_names list). Fail-open: unknown/missing => all
    sources ON (a silently-off source is the bug we're killing)."""
    toggles = {k: True for k in SOURCE_FETCHERS}
    relational = list(RELATIONAL_DEFAULTS)
    try:
        txt = open(CONFIG, encoding="utf-8").read()
    except OSError:
        return toggles, relational
    m = re.search(r"data_sources:\s*\n(.*?)(?:\n[A-Za-z_]+:|\n---)", txt, re.S)
    for line in (m.group(1).splitlines() if m else []):
        mm = re.match(r"\s+([A-Za-z0-9_]+):\s*(on|off)\b", line)
        if mm and mm.group(1) in toggles:
            toggles[mm.group(1)] = (mm.group(2) == "on")
    rm = re.search(r"relational_priority:\s*\[([^\]]*)\]", txt)
    if rm:
        relational += [x.strip().strip("'\"").lower() for x in rm.group(1).split(",") if x.strip()]
    return toggles, sorted(set(relational))


def last_entry_date(until_d):
    best = None
    files = sorted(glob.glob(os.path.join(JOURNALS, "*", "*.md")),
                   key=lambda p: os.path.getmtime(p), reverse=True)
    for p in files[:80]:
        try:
            head = open(p, encoding="utf-8", errors="replace").read(600)
        except OSError:
            continue
        m = re.search(r"creationDate:\s*(\d{4}-\d{2}-\d{2})", head)
        if m and m.group(1) < until_d.isoformat() and (best is None or m.group(1) > best):
            best = m.group(1)
    return best


def _run(cmd, timeout=150):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "").strip()
        if r.returncode != 0 and r.stderr:
            out += f"\n[stderr rc={r.returncode}] {r.stderr.strip()[:400]}"
        return out, (r.returncode == 0)
    except Exception as e:  # noqa: BLE001
        return f"[preflight] could not run: {type(e).__name__}: {e}", False


def _fetcher(name):
    p = os.path.join(SCRIPT_DIR, name)
    return p if os.path.exists(p) else None


def surface_relational_first(messages_md, names):
    """Reorder the messages digest so threads whose contact matches a relational name
    come FIRST under a ⭐ banner. Split on '### <Contact>' blocks; keep the preamble."""
    parts = re.split(r"(?m)^(?=### )", messages_md)
    if len(parts) <= 1:
        return messages_md, []
    preamble, blocks = parts[0], parts[1:]
    rel, other = [], []
    for b in blocks:
        head = b.splitlines()[0] if b.strip() else ""
        contact = re.sub(r"^###\s*", "", head).split("  _(")[0].strip().lower()
        (rel if any(n in contact for n in names) else other).append(b)
    surfaced = [re.sub(r"^###\s*", "### ⭐ ", b, count=1) for b in rel]
    rel_names = [re.sub(r"^###\s*", "", b.splitlines()[0]).split("  _(")[0].strip() for b in rel]
    body = preamble
    if surfaced:
        body += "\n\n— ⭐ RELATIONAL / FAMILY / PARTNER (surfaced first) —\n\n" + "".join(surfaced)
        body += "\n— everything else —\n\n" + "".join(other)
    else:
        body += "".join(other)
    return body, rel_names


def _age_note(path):
    try:
        mt = datetime.datetime.fromtimestamp(os.path.getmtime(path))
        hrs = (datetime.datetime.now() - mt).total_seconds() / 3600
        if hrs > 24:
            return f"  ⚠ STALE: last refreshed {round(hrs)}h ago ({mt:%Y-%m-%d %H:%M}). Make the fresh MCP pull below."
        return f"  (refreshed {round(hrs)}h ago)"
    except OSError:
        return ""


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
    if (until_d - since_d).days > MAX_GAP_DAYS:
        since_d = until_d - datetime.timedelta(days=MAX_GAP_DAYS)
        since = since_d.isoformat()

    toggles, relational = read_config()
    pulled, failed, pending_mcp, skipped_off, rel_surfaced = [], [], [], [], []
    sections = []

    # ---- Messages (WhatsApp direct+groups + iMessage), relational-first ----
    if toggles.get("whatsapp_24h") or toggles.get("imessage_24h"):
        fp = _fetcher("journal-messages-fetch.py")
        if fp:
            body, ok = _run(["python3", fp, "--since", since, "--until", until_d.isoformat()])
            body, rel_surfaced = surface_relational_first(body, relational)
            sections.append(("MESSAGES — WhatsApp (direct + groups) + iMessage, relational-first", body))
            (pulled if ok and body else failed).append("messages")
        else:
            sections.append(("MESSAGES", "[preflight] journal-messages-fetch.py not installed — skipping."))
            failed.append("messages")
    else:
        skipped_off.append("messages")

    # ---- RescueTime, per-day ----
    if toggles.get("rescuetime"):
        fp = _fetcher("rescuetime-fetch.py")
        if fp:
            lines, any_ok = [], False
            for k in range(min((until_d - since_d).days + 1, MAX_GAP_DAYS)):
                d = (until_d - datetime.timedelta(days=k)).isoformat()
                b, ok = _run(["python3", fp, d], timeout=40)
                if b:
                    lines.append(b)
                    any_ok = any_ok or ok
            sections.append(("RESCUETIME (per day, newest first)", "\n\n".join(lines) or "[none]"))
            (pulled if any_ok else failed).append("rescuetime")
        else:
            sections.append(("RESCUETIME", "[preflight] rescuetime-fetch.py not installed — skipping."))
            failed.append("rescuetime")
    else:
        skipped_off.append("rescuetime")

    # ---- Close-cascade journal seeds (Session Captures.md, [emotional]-tagged) ----
    if toggles.get("session_captures"):
        try:
            txt = open(CAPTURES, encoding="utf-8", errors="replace").read()
            head = "\n".join(txt.splitlines()[:140])
            sections.append(("CLOSE-CASCADE JOURNAL SEEDS (Session Captures.md — [emotional] = personal)", head or "[empty]"))
            pulled.append("session_captures")
        except OSError:
            sections.append(("CLOSE-CASCADE JOURNAL SEEDS", "[preflight] Session Captures.md not found — skipping."))
            failed.append("session_captures")
    else:
        skipped_off.append("session_captures")

    # ---- Today's activity ----
    if toggles.get("todays_activity"):
        body, _ = _run(["git", "-C", VAULT, "log",
                        f"--since={until_d.isoformat()} 00:00",
                        f"--until={until_d.isoformat()} 23:59", "--oneline", "--no-decorate"], timeout=60)
        sections.append(("TODAY'S VAULT COMMITS", body or "[no commits today]"))
        pulled.append("todays_activity")
    else:
        skipped_off.append("todays_activity")

    # ---- Email triage digest (script; often stale -> also queue a fresh MCP pull) ----
    if toggles.get("email"):
        if os.path.exists(EMAIL_DIGEST):
            try:
                txt = open(EMAIL_DIGEST, encoding="utf-8", errors="replace").read()
                head = "\n".join(txt.splitlines()[:90])
                sections.append((f"EMAIL — triage digest{_age_note(EMAIL_DIGEST)}", head))
                pulled.append("email")
            except OSError:
                failed.append("email")
        else:
            sections.append(("EMAIL", "[preflight] Email Needs You.md not found — use the gmail MCP pull below."))
        pending_mcp.append("email_live")
    else:
        skipped_off.append("email")

    # ---- Slack on-disk export (sparse; fresh pull via MCP below) ----
    if toggles.get("slack"):
        # Slack export nests by workspace (Slack/mycelium/*.md, Slack/onde/*.md) — recurse.
        sfiles = sorted(glob.glob(os.path.join(AICHATS, "Slack", "**", "*.md"), recursive=True),
                        key=lambda p: os.path.getmtime(p), reverse=True)[:6]
        if sfiles:
            chunks = []
            for p in sfiles:
                try:
                    tail = "\n".join(open(p, encoding="utf-8", errors="replace").read().splitlines()[-25:])
                    chunks.append(f"#### {os.path.basename(p)[:-3]}\n{tail}")
                except OSError:
                    continue
            sections.append(("SLACK — on-disk export (recent tails; sparse — pull fresh via MCP below)", "\n\n".join(chunks) or "[empty]"))
            pulled.append("slack")
        else:
            sections.append(("SLACK", "[preflight] no on-disk Slack export — use the slack MCP pull below."))
        pending_mcp.append("slack_live")
    else:
        skipped_off.append("slack")

    # ---- MCP-only sources ----
    if toggles.get("calendar"):
        pending_mcp.append("calendar")
    if toggles.get("body_health"):
        pending_mcp.append("body_health")

    # ---- Marker ----
    os.makedirs(MARKER_DIR, exist_ok=True)
    marker = {
        "date": until_d.isoformat(), "since": since, "until": until_d.isoformat(),
        "ran_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "config_enabled": sorted([k for k, v in toggles.items() if v]),
        "sources_pulled": sorted(set(pulled)),
        "sources_failed": sorted(set(failed)),
        "sources_pending_mcp": sorted(set(pending_mcp)),
        "sources_skipped_off": sorted(set(skipped_off)),
        "relational_surfaced": rel_surfaced,
    }
    marker_path = os.path.join(MARKER_DIR, f"{until_d.isoformat()}.json")
    with open(marker_path, "w", encoding="utf-8") as f:
        json.dump(marker, f, indent=2, ensure_ascii=False)

    if json_only:
        print(json.dumps(marker, indent=2, ensure_ascii=False))
        return 0

    print(f"# /journal preflight — context {since} → {until_d.isoformat()}")
    print(f"_pulled: {', '.join(marker['sources_pulled']) or 'none'}"
          f" | failed: {', '.join(marker['sources_failed']) or 'none'}"
          f" | MCP-pending: {', '.join(marker['sources_pending_mcp']) or 'none'}_")
    if rel_surfaced:
        print(f"_⭐ relational threads surfaced: {', '.join(rel_surfaced)}_")
    for title, body in sections:
        print(f"\n{'='*72}\n## {title}\n{'='*72}")
        print(body if body else "[empty]")

    if pending_mcp:
        print(f"\n{'='*72}\n## ▶ MCP PULLS THE SKILL MUST STILL MAKE (preflight can't call MCP)\n{'='*72}")
        cal = f"time_min='{since}T00:00:00-05:00', time_max='{until_d.isoformat()}T23:59:59-05:00'"
        if "calendar" in pending_mcp:
            print(f"- CALENDAR: cal_list_events({cal}, verbose=true) — meetings + attendees into ## Today.")
        if "email_live" in pending_mcp:
            print(f"- EMAIL (fresh, relational): gmail_search each account, e.g. "
                  f"`after:{since.replace('-','/')}` — surface FAMILY / friends / commitments, not just the stale triage above.")
        if "slack_live" in pending_mcp:
            print("- SLACK (fresh): slack search_messages / read recent DMs + #daily-updates since the last entry.")
        if "body_health" in pending_mcp:
            print("- HEALTH: latest 🏠 Home/Health Pattern Report + yesterday's ## Body track (or regenerate-health-pattern-report.py).")
        print("\nAfter these land, the entry frontmatter MUST carry `context_sources:` naming every "
              "source folded in, or warn-journal-saved-without-context.py fires.")

    print(f"\n_marker: {marker_path}_")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
