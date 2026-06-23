#!/usr/bin/env bash
# Network-free regression test for scripts/granola_sync.py.
#
# granola_sync.py is the Granola Public-API exporter (MYC-1510). Its critical
# guarantees do not need the network to verify:
#   1. FAIL-LOUD on no key. The whole reason for the API rewrite was that the
#      old cache reader exited 0 with empty output (a silent connector). With no
#      key, the script MUST exit non-zero AND say so -- never the silent exit 0.
#   2. Key-file parsing: a bare key on its own line, OR a `GRANOLA_API_KEY=...`
#      line. Env var beats file.
#   3. Filename contract: safe_filename() output MUST match the regex
#      check-connector-liveness.py uses to count Granola data-days
#      (`^\d{4}-\d{2}-\d{2} - .* - Transcript\.md$`). If these drift, the
#      liveness watchdog silently stops seeing Granola.
#   4. format_transcript keeps BOTH speaker channels (mic == You, other ==
#      Speaker). Dropping the non-mic channel guts lectures/webinars/1:1s where
#      the user listens more than talks (codified lesson, originally 7 dropped
#      transcripts).
#
# Self-contained. Exit 0 = pass. Exit 1 = fail with details.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

SCRIPT="scripts/granola_sync.py"
FAILED=0
fail() { echo "FAIL: $1" >&2; FAILED=$((FAILED + 1)); }

[ -f "$SCRIPT" ] || { echo "FAIL: $SCRIPT not found" >&2; exit 1; }

# --- (1) FAIL-LOUD on no key (the anti-silent-failure guarantee) -------------
TMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME"' EXIT
set +e
OUT="$(env -u GRANOLA_API_KEY HOME="$TMP_HOME" python3 "$SCRIPT" --health 2>&1)"
CODE=$?
set -e
if [ "$CODE" -eq 0 ]; then
  fail "(1) --health with no key exited 0 (silent). Must fail loud."
else
  echo "PASS(1a): no key -> non-zero exit ($CODE)"
fi
case "$OUT" in
  *"no Granola API key"*) echo "PASS(1b): no key -> says 'no Granola API key'" ;;
  *) fail "(1b) no-key output did not name the missing key. out=[$OUT]" ;;
esac

# --- (2)-(5) pure-function contracts (no network) ----------------------------
python3 - "$REPO_ROOT" <<'PY'
import sys, pathlib, tempfile, re
repo = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(repo / "scripts"))
import granola_sync as g
from datetime import datetime, timezone

fails = []
def check(cond, msg):
    print(("PASS: " if cond else "FAIL: ") + msg)
    if not cond:
        fails.append(msg)

# (2) key-file parsing: bare key
with tempfile.TemporaryDirectory() as d:
    kf = pathlib.Path(d) / "api-key"
    kf.write_text("grn_barekey_123\n")
    check(g.load_api_key(kf) == "grn_barekey_123", "(2a) bare-key file parses")
    # (2b) KEY=value line
    kf.write_text("# comment\nGRANOLA_API_KEY=grn_eqform_456\n")
    check(g.load_api_key(kf) == "grn_eqform_456", "(2b) GRANOLA_API_KEY= line parses")
    # (2c) env beats file
    import os
    os.environ["GRANOLA_API_KEY"] = "grn_envwins_789"
    check(g.load_api_key(kf) == "grn_envwins_789", "(2c) env var beats key file")
    del os.environ["GRANOLA_API_KEY"]

# (3) filename contract MUST match the liveness watchdog's regex
LIVENESS_RE = re.compile(r"^\d{4}-\d{2}-\d{2} - .* - Transcript\.md$")
fn = g.safe_filename("A/B", "2026-06-22")
check(fn == "2026-06-22 - A-B - Transcript.md", f"(3a) safe_filename exact: {fn!r}")
check(bool(LIVENESS_RE.match(fn)), "(3b) safe_filename matches liveness regex")
# illegal chars are sanitized, never leak into the filename
fn2 = g.safe_filename('Q3: plan/ops*', "2026-01-02")
check(bool(LIVENESS_RE.match(fn2)) and "/" not in fn2 and ":" not in fn2,
      f"(3c) illegal chars sanitized: {fn2!r}")

# (4) format_transcript keeps BOTH channels
start = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)
transcript = [
    {"text": "hi there", "speaker": {"source": "microphone"}, "start_time": "2026-06-22T12:00:01Z"},
    {"text": "hello back", "speaker": {"source": "speaker"}, "start_time": "2026-06-22T12:00:05Z"},
]
out = g.format_transcript(transcript, start)
check("**You**" in out, "(4a) mic channel labeled You")
check("**Speaker**" in out and "hello back" in out, "(4b) other channel kept as Speaker")

sys.exit(1 if fails else 0)
PY
PY_CODE=$?
[ "$PY_CODE" -eq 0 ] || fail "(2-4) pure-function contract check failed (see above)"

if [ "$FAILED" -ne 0 ]; then
  echo "test_granola_sync_offline: $FAILED failure(s)" >&2
  exit 1
fi
echo "test_granola_sync_offline: all checks passed"
