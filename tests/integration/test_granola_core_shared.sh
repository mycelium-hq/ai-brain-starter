#!/usr/bin/env bash
# Network-free regression test for scripts/granola_core.py -- the SHARED Granola
# API core, and the structural guarantee that scripts/granola_sync.py does not
# re-vendor it.
#
# WHY THIS EXISTS (MYC-1529): the Granola API contract used to live as two
# near-duplicate copies (this substrate's granola_sync.py + a private vault's
# granola_export.py). The personal copy was migrated to the Public API three
# weeks before the substrate copy, which silently exported nothing in between.
# Bug class: DISCIPLINE-FIX-NOT-PORTED-TO-SUBSTRATE. The durable fix is ONE
# module both copies import, so the contract cannot drift.
#
# This test pins two things the network cannot change:
#   1. NO RE-VENDOR (the structural guarantee + its own negative control). The
#      contract functions exposed by granola_sync MUST be the very same objects
#      defined in granola_core (identity, `is`). If a future edit copy-pastes one
#      back into granola_sync, identity breaks and this test fails loudly -- that
#      is the whole anti-drift mechanism, and it is silent only while the two are
#      genuinely one.
#   2. The core's pure-function contracts: the external-attendee frontmatter
#      variation point (write_transcript_md extra_frontmatter) and the
#      incremental window math (incremental_created_after).
#
# Self-contained. Exit 0 = pass. Exit 1 = fail with details.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

[ -f scripts/granola_core.py ] || { echo "FAIL: scripts/granola_core.py not found" >&2; exit 1; }
[ -f scripts/granola_sync.py ] || { echo "FAIL: scripts/granola_sync.py not found" >&2; exit 1; }

python3 - "$REPO_ROOT" <<'PY'
import sys, pathlib, tempfile, re
repo = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(repo / "scripts"))
import granola_core as core
import granola_sync as g
from datetime import datetime, timezone

fails = []
def check(cond, msg):
    print(("PASS: " if cond else "FAIL: ") + msg)
    if not cond:
        fails.append(msg)

# (1) NO RE-VENDOR: granola_sync re-exports the SAME objects from granola_core.
# This identity check IS the anti-drift guarantee and its own negative control:
# the day someone forks a function back into granola_sync, `is` becomes False.
for name in ("api_get", "list_notes", "format_transcript", "safe_filename",
             "load_api_key", "write_transcript_md", "load_state", "save_state",
             "incremental_created_after"):
    same = getattr(g, name, None) is getattr(core, name, object())
    check(same, f"(1) granola_sync.{name} is the shared granola_core.{name} (no re-vendor)")

# (2) write_transcript_md: substrate mode omits external_attendees; the personal
# exporter injects it via extra_frontmatter WITHOUT forking the function.
note = {
    "id": "n_123",
    "title": "Q3 / Plan: ops",   # also exercises filename sanitization
    "created_at": "2026-06-22T15:00:00Z",
    "web_url": "https://granola.ai/n_123",
    "summary_markdown": "We agreed on the plan.",
    "transcript": [
        {"text": "kickoff", "speaker": {"source": "microphone"}, "start_time": "2026-06-22T15:00:01Z"},
        {"text": "sounds good", "speaker": {"source": "speaker"}, "start_time": "2026-06-22T15:00:04Z"},
    ],
}
with tempfile.TemporaryDirectory() as d:
    mdir = pathlib.Path(d)
    fp, _msg = core.write_transcript_md(note, mdir, dry_run=False)
    body = fp.read_text(encoding="utf-8")
    check("source: granola-api" in body, "(2a) substrate frontmatter has source: granola-api")
    check("external_attendees" not in body, "(2b) substrate frontmatter omits external_attendees")
    check("**You**" in body and "**Speaker**" in body, "(2c) both transcript channels kept")
    # filename obeys the liveness watchdog regex (illegal chars sanitized)
    LIVENESS_RE = re.compile(r"^\d{4}-\d{2}-\d{2} - .* - Transcript\.md$")
    check(bool(LIVENESS_RE.match(fp.name)) and "/" not in fp.name and ":" not in fp.name,
          f"(2d) filename sanitized + matches liveness regex: {fp.name!r}")

with tempfile.TemporaryDirectory() as d:
    mdir = pathlib.Path(d)
    note2 = dict(note, id="n_456", title="Vendor sync")
    fp2, _ = core.write_transcript_md(
        note2, mdir, dry_run=False,
        extra_frontmatter={"external_attendees": "Dana <dana@example.com>"},
    )
    body2 = fp2.read_text(encoding="utf-8")
    check("external_attendees: Dana <dana@example.com>" in body2,
          "(2e) extra_frontmatter injects external_attendees (personal-exporter mode)")

# (3) incremental_created_after: --since override, an OLD last_sync (older than
# the safety lookback) is honored verbatim, and a fresh state yields a window.
check(core.incremental_created_after({}, since="2026-05-01") == "2026-05-01T00:00:00Z",
      "(3a) --since date is normalized to ISO midnight Z")
old = core.incremental_created_after({"last_sync": "2026-01-01T00:00:00Z"})
check(old == "2026-01-01T00:00:00Z", f"(3b) old last_sync honored (min with lookback): {old!r}")
firstrun = core.incremental_created_after({})
check(firstrun.endswith("Z") and firstrun < datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
      f"(3c) first-run window is a past ISO-Z instant: {firstrun!r}")

sys.exit(1 if fails else 0)
PY

echo "test_granola_core_shared: all checks passed"
